"""Type the party credited by a source before treating it as an outside human creator."""
from collections import Counter
import json
import re
from typing import Literal

from openai import APIError
from pydantic import BaseModel, ValidationError

from .recheck_creator_role import MODEL, PROVIDER, ModelClaim, human_credit_rule_id, qwen_client
from .storage import digest, encode, read_json, write_json


RULES = """For each item, start by typing the exact alleged_outside_party. Give its ordinary literal identity:
a human, a human team, an AI/agent/model, a software tool/engine/framework, a fictional character, a work/title,
an effect/description, or unknown. Do not infer that it is human because a verb like 'made', 'built', 'generated'
or 'coded' has it as subject: AI models and tools are often explicitly credited as the builder. Next use the
entire original post and actual picture to resolve the person behind the work. Another model mentioned, the same
creator's avatar/character, or an engine/company tagged as a TOOL is not a different human creator.
If an actually external human/team made this specific project, quote both a phrase identifying them (an unnamed
'my friend', 'another developer', etc. also works) and the exact full clause assigning this work to them.
These must concern the same subject and work. If no such outside human is evidenced, this DOES NOT prove the
poster made it. Only recognize the poster when affirmative exact source words identify THEIR concrete prompt,
experiment, iteration, creation or demonstrated OWN work. An early model title can be linked to an explicit
later creation statement in the same post. 'I found/played/like/reviewed' is not making it. If authorship remains
unclear, label unresolved. Decline promo, redistribution, roundups, tools without a specific first-party spatial
work, 2D-only and generative footage without code/engine evidence. Video game characters never count as external
human creators. Classify actual spatial 3D or explicitly coded/engine shader output, including static work.
For own works give short verbatim quotes for authorship, project and each AI model actually used; preserve exact
characters and never reuse a neighboring item's text/image. If an alleged outside model name is wrong, say so
even if your final authorship is unresolved. Return JSON following the supplied schema."""


class EntityVerdict(BaseModel):
    index: int
    alleged_kind: Literal["human", "team", "ai_model", "software", "fiction", "work", "effect", "unknown"]
    creator: Literal["poster", "outside_human_or_team", "unresolved"]
    human_identity_quote: str
    human_credit_clause: str
    personal_creation_quote: str
    project_quote: str
    spatial_or_coded_scene: bool
    supported_original_work: bool
    exclusion: Literal["none", "reporting", "advertising", "wrong_scope", "unclear"]
    models: list[ModelClaim]
    findings: str


class EntityVerdicts(BaseModel):
    items: list[EntityVerdict]


def signature():
    return digest(encode([MODEL, PROVIDER, RULES, EntityVerdicts.model_json_schema()]))


# Require the *whole* phrase to consist of model/engine labels. An outside human who uses a model
# (for example "a developer using Gemini") must never be removed by a substring test.
TOOL_PHRASE = re.compile(r"(?:(?:claude|code|fable|opus|sonnet|haiku|gpt|chatgpt|codex|astra|sol|gemini|neon|"
    r"argon|carbon|hydrogen|krypton|deepseek|qwen|grok|meshy|tripo|blender|unity|unreal|engine|three[.]?js|"
    r"godot|webgl|webgpu|pro|max|preview|flash|model|and|with|和|与|と|模型|[0-9]+|[^\w])\s*)+", re.I)


REPORT_OR_NAME = re.compile(r"^\s*[,：:，]?\s*(?:(?:says?|said|reports?|claims?|announced|praised|named|called)\b"
    r"|(?:表示|声称|稱讚|称赞|报道称|命名|起名|给.{0,4}起名|給.{0,4}起名))", re.I)
SELF_BUILD = re.compile(r"\b(?:they|we|I)\s+(?:(?:have|had|actually|personally)\s+)?(?:built|coded|made|"
    r"prompted|created|rendered|programmed)\b|(?:自己|亲自|親自|自分で).{0,8}(?:做|制作|開発|开发|作っ)", re.I)


def direct_credit_clause(who, clause):
    if not who or not clause:
        return False
    start = clause.casefold().find(who.casefold())
    if start < 0 or TOOL_PHRASE.fullmatch(who.strip()):
        return False
    after = clause[start + len(who):]
    # A company saying that its model built an example, or a person naming a game, establishes a speaker.
    # A quote such as "the studio says they built the game" actually assigns a creation action to it.
    return not REPORT_OR_NAME.search(after) or bool(SELF_BUILD.search(after))


def ground_entity(packet, previous, item, *, observed):
    from .recheck_attribution import Verdict, grounded, verbatim
    texts = [packet["post"], *packet["thread"], packet["own_quote"]]
    who = verbatim(item.human_identity_quote, texts)
    clause = verbatim(item.human_credit_clause, texts)
    personal = verbatim(item.personal_creation_quote, texts)
    project = verbatim(item.project_quote, texts)
    external = direct_credit_clause(who, clause)
    if who == previous["claimed_party"] and item.alleged_kind not in {"human", "team"}:
        external = False
    mistaken_identity = (item.alleged_kind in {"ai_model", "software", "fiction", "work", "effect"}
                         or bool(TOOL_PHRASE.fullmatch(previous["claimed_party"].strip())))
    own = (mistaken_identity and not external and item.creator == "poster" and item.supported_original_work and item.spatial_or_coded_scene
           and item.exclusion == "none" and bool(personal and project and item.findings.strip())
           and (observed or previous.get("source_basis") == "explicit_original_implementation"))
    result = grounded(packet, Verdict(index=item.index, decision="allow" if own else "hold", quote=personal,
                      models=[m.model_dump() for m in item.models]))
    kind = "external_person_or_team" if external and item.creator == "outside_human_or_team" else "unresolved"
    if result["decision"] == "allow":
        kind = "posting_person_or_team"
    return {**result, "subject_quote": project, "human_credit": kind, "outside_party_span": who if external else "",
            "credited_work_span": clause if external else "", "posting_creator_span": personal,
            "who_made_what": item.findings, "alleged_kind": item.alleged_kind}


def prepare_entities(root, policy, rows, *, cache_only=False, workers=8):
    from .recheck_attribution import complete_batches, evidence, in_scope, original_frame, record_usage, save_visual, small_frame
    from .recheck_creator_role import independent_scope_exclusion
    from .recheck_video_attribution import verify_files
    from .models import ReviewStatus
    from hashlib import sha256
    cp = root / "state/x_covers.json"
    covers = read_json(cp) if cp.exists() else {}
    mp = root / "raw/x/video_evidence/manifest.json"
    videos = {r["world_id"]: r for r in read_json(mp)["records"]} if mp.exists() else {}
    jobs, saved, counts = [], {}, Counter()
    for case in rows:
        if not in_scope(case, policy) or case.review_status == ReviewStatus.REJECTED:
            continue
        entry = policy["decisions"].get(case.world_id, {})
        primary = entry.get("creator_resolution", {})
        if primary.get("reference_rules") != human_credit_rule_id():
            continue
        if primary.get("entity_rules") == signature():
            if (primary.get("human_credit") == "external_person_or_team"
                    and not direct_credit_clause(primary.get("outside_party_span"), primary.get("credited_work_span"))):
                saved[case.world_id] = {**primary, "human_credit": "unresolved", "outside_party_span": "",
                                       "credited_work_span": "", "decision": "hold", "models": [],
                                       "entity_note": "The cited clause identifies a speaker or names the work without crediting creation."}
            counts["durable"] += 1
            continue
        if primary.get("human_credit") != "external_person_or_team":
            continue
        alleged = primary.get("outside_party_span")
        if not alleged:
            continue
        jobkey = digest(encode([primary["key"], primary["reference_rules"], alleged, signature()]))
        cache = root / "processed/extraction/creator_entities" / f"{jobkey}.json"
        if cache.exists():
            saved[case.world_id] = read_json(cache)
            counts["cached"] += 1
            continue
        packet = evidence(root, case)
        if not packet:
            counts["missing_source"] += 1
            continue
        paths = []
        if primary.get("verified_media", {}).get("video_url"):
            paths = [p for p, _, _ in (verify_files(root, case, videos.get(case.world_id, {})) or [])]
        elif frame := original_frame(covers, case, root):
            paths = [frame[0]]
        if [sha256(p.read_bytes()).hexdigest() for p in paths] != primary["frame_sha256"]:
            counts["missing_media"] += 1
            continue
        jobs.append((case, {**primary, "claimed_party": alleged}, packet, paths, cache, independent_scope_exclusion(entry)))
    save_visual(root, saved, policy, field="creator_resolution")
    if not jobs or cache_only:
        return {**counts, "missing_receipt": len(jobs)}
    client = qwen_client()
    if client is None:
        return {**counts, "provider_unconfigured": len(jobs)}
    def check(batch):
        content = []
        for i, (_, prev, packet, paths, *_) in enumerate(batch):
            content.append({"type": "text", "text": encode({"index": i, **packet, "alleged_outside_party": prev["claimed_party"],
                            "claimed_work_excerpt": prev.get("credited_work_span"), "verified_frames": len(paths)})})
            for p in paths:
                content.append({"type": "image_url", "image_url": {"url": small_frame(p)}})
        try:
            response = client.chat.completions.create(model=MODEL, temperature=0, max_tokens=5000,
                messages=[{"role": "system", "content": RULES + "\nJSON schema: " + encode(EntityVerdicts.model_json_schema())},
                          {"role": "user", "content": content}], response_format={"type": "json_object"}, extra_body={"enable_thinking": False})
            record_usage(root, MODEL, "creator_entity_review", response)
            result = EntityVerdicts.model_validate_json(response.choices[0].message.content)
        except (APIError, ValidationError, OSError, ValueError, IndexError) as error:
            print(f"Source identity deferred ({type(error).__name__})", flush=True)
            return Counter(deferred=len(batch)), {}
        seen = Counter(item.index for item in result.items)
        results, output = Counter(), {}
        for item in result.items:
            if not 0 <= item.index < len(batch) or seen[item.index] != 1:
                continue
            case, previous, packet, paths, cache, excluded = batch[item.index]
            proof = ground_entity(packet, previous, item, observed=bool(paths))
            if excluded:
                proof.update(decision="hold", models=[])
            merged = {**previous, **proof, "entity_rules": signature(), "entity_model": MODEL}
            write_json(cache, merged)
            output[case.world_id] = merged
            results[proof["decision"]] += 1
        results["deferred"] = len(batch) - sum(results.values())
        return results, output
    print(f"Checking whether {len(jobs)} alleged outside sources are human creators", flush=True)
    return complete_batches(jobs, 1 if len(jobs) <= 10 else 3, workers, check, counts,
                            lambda changes: save_visual(root, changes, policy, field="creator_resolution"))
