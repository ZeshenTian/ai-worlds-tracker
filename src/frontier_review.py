"""First-party presentation can be grounded in a particular upload without an 'I built' claim."""

from collections import Counter
import re
import yaml

from .links import post_id
from .model_era import CUE
from .models import AIWorldCase, ReviewStatus
from .qualify_candidates import PROMO
from .storage import (
    digest,
    encode,
    read_json,
    read_rows,
    run_lock,
    write_json,
    write_rows,
)

OFFICIAL = {
    "google",
    "googleai",
    "googledeepmind",
    "openai",
    "openaidevs",
    "claudeai",
    "anthropicai",
}
PRESENTATION = re.compile(
    r"\b(?:made|built|generated|simulated|created|coded|rendered|asked|prompted|my|our|i love this|this is insane|the goat|my prompt|one[- ]shot|one prompt|single prompt|vibe[- ]coded|here['’]s)\b|制作|做了|生成|作って|作りました",
    re.I,
)
SPATIAL = re.compile(
    r"\b(?:fps|first[- ]person shooter|3d|voxel|diorama|ray[- ]?trac\w*|path[- ]?trac\w*|three[ .]?js|webgpu|webgl|shader|procedural (?:geometry|terrain)|blender|unreal engine|flight sim\w*)\b|三维|3Dシーン",
    re.I,
)
ARTIFACT = re.compile(
    r"\b(?:scene|world|game|fps|shooter|flight|simulation|simulator|terrain|city|island|village|diorama|building|geometry|modeling|shader|animation|physics|particles|creature|car|engine demo|walkthrough|prototype|landscape|render|sculpture|room|castle|forest|aquarium)\b|场景|世界|游戏|シーン|ゲーム",
    re.I,
)
THIRD = re.compile(
    r"\b(?:by|credit(?:s)? to|dev[:：]|from)\s+@(\w+)|\b(?:check out|look at) what\s+@?[\w-]+\s+(?:built|made|created)|(?:^|\n)\s*RT\s+@",
    re.I,
)
TOOL_HANDLES = OFFICIAL | {
    "threejs",
    "webgpu",
    "playcanvas",
    "blender",
    "unity",
    "unrealengine",
    "googlegemini",
    "chatgptapp",
    "claudecode",
}
LIST = re.compile(
    r"\b(?:pricing (?:guide|plans?)|black friday|affiliate code|sponsored|tool roundup|(?:top|best) \d+ (?:tools|repos)|workflow breakdown|model leaderboard)\b|【PR】",
    re.I,
)
DISCLOSURE = re.compile(
    r"(?:\b(?:claude[\s(-]+)?(?:fable|opus|sonnet|haiku)[\s(-]*(?:model\s*\()?[\d]+(?:\.\d+)*|\b(?:chat)?gpt[- ]*(?:astra[- ]*)?\d+(?:\.\d+)*(?:[- ]*(?:astra|atra|sol))?|\b(?:astra|sol)\s*[\d.]+|\b[\d.]+\s+astra|\bgemini\s*\d+(?:\.\d+)*(?:\s+(?:neon|carbon|argon|hydrogen))?|\b(?:neon|hydrogen|carbon|argon)\s+4|\bclaude code\b|\b(?:claude|gemini|codex|chatgpt|gpt)\b)",
    re.I | re.ASCII,
)
GUIDANCE = """Treat a particular model output accompanied by the presenter's own native media and admiration as first-party presentation whenever there is no outside human credit. An engine or AI handle is not another maker. Official AI lab accounts presenting concrete spatial demos qualify. A launch, pricing announcement, external quote, explicit human credit or aggregator does not qualify."""


def assess(case, packet, signal, prior, excluded):
    from .recheck_creator_role import independent_scope_exclusion
    from .recheck_attribution import verbatim

    author = case.author_handle.casefold()
    text = packet["post"]
    statements = [
        s.strip()
        for t in [text, *packet["thread"], packet["own_quote"]]
        for s in re.split(r"\n+|(?<=[.!?。！？])\s+", t)
        if s.strip()
    ]

    def result(decision, reason, **more):
        return dict(
            decision=decision,
            reason=reason,
            source=case.original_post_url,
            packet_key=digest(encode(packet)),
            **more,
        )

    if author in excluded or PROMO.search(text) or LIST.search(text):
        return result("reject", "excluded_account_or_promotion")
    if any(
        not m[1] or m[1].lower() not in TOOL_HANDLES | {author}
        for m in THIRD.finditer(text)
    ):
        return result("hold", "third_party_credit")
    role = prior.get("creator_resolution", {})
    if (
        role.get("human_credit") == "other_human_or_team"
        or role.get("outside_party_span")
        and role.get("credited_work_span")
    ):
        return result("hold", "credited_outside_maker")
    if (
        signal.get("quoted_author")
        and str(signal["quoted_author"]).casefold().lstrip("@") != author
        and not packet.get("own_quote")
    ):
        return result("hold", "outside_quotation")
    if not (packet["has_attached_media"] or case.live_demo_url):
        return result("hold", "no_attached_work")
    if independent_scope_exclusion(prior):
        return result("hold", "independent_flat_ui_evidence")
    if re.search(
        r"\b(?:sora|veo|kling|runway|seedance)\b", text, re.I
    ) and not CUE.search(text):
        return result("hold", "diffusion_without_engine")
    visual = any(
        v.get("frame_type") == "spatial_render"
        for v in [prior.get("visual", {}), prior.get("video_visual", {})]
    )
    spatial = [s for s in statements if SPATIAL.search(s)]
    artifact = [s for s in statements if ARTIFACT.search(s)]
    own = [s for s in statements if PRESENTATION.search(s)]
    # An unrelated model mention in a camera-ready clip or announcement cannot
    # establish who used the model. Preserve positive model-disclosure quotes.
    if not (
        (spatial or visual)
        and (artifact or visual and spatial)
        and (
            author in OFFICIAL
            or own
            or spatial
            and role.get("scope") in {"interactive_spatial", "coded_scene"}
        )
    ):
        return result("hold", "work_or_presentation_unclear")
    if (
        not own
        and author in OFFICIAL
        and not any(
            ARTIFACT.search(s) and (SPATIAL.search(s) or DISCLOSURE.search(s))
            for s in statements
        )
    ):
        return result("hold", "official_announcement_without_demonstration")
    found = {}
    for s in statements:
        if len(s) > 1200 or re.search(
            r"\b(?:compatible with|supports? (?:multiple|both)|never used|did not use|instead of|unlike|coming soon|will support)\b",
            s,
            re.I,
        ):
            continue
        for match in DISCLOSURE.finditer(s):
            label = match[0]
            # An @handle alone does not disclose a model used to construct the work.
            if match.start() and s[match.start() - 1] == "@":
                continue
            if (
                len(statements) == 1
                or PRESENTATION.search(s)
                or SPATIAL.search(s)
                or any(
                    verbatim(q, [s]) and label.lower() in q.lower()
                    for q in case.evidence_quotes
                )
                or s.strip(" :-") == label
            ):
                found.setdefault(label.casefold(), {"term": label, "quote": s})
    if not found:
        return result("hold", "missing_model_disclosure")
    return result(
        "allow",
        "official_first_party" if author in OFFICIAL else "native_creator_presentation",
        quote=(artifact or spatial)[0],
        models=list(found.values()),
    )


def native_review_receipt(case, packet, screening, review, cover):
    """Accept an independent frame review only for the same source, text and media."""
    from .recheck_creator_role import Resolution, ground_resolution, RULES
    if (screening["reason"] not in {"work_or_presentation_unclear", "missing_model_disclosure",
                                   "native_creator_presentation", "official_first_party"}
            or not packet.get("has_attached_media") or not review or not cover
            or review.get("provider_model") != "MiniMax-M3"
            or review.get("rules") != digest(RULES)
            or review.get("source") != case.original_post_url or cover.get("source_url") != case.original_post_url
            or not cover.get("source_sha256") or review.get("source_sha256") != cover["source_sha256"]
            or review.get("packet_key") != digest(encode(packet))):
        return screening
    item = Resolution.model_validate(review["resolution"])
    result = ground_resolution(packet, item, has_images=True, previous_quotes=[])
    if result["decision"] != "allow" or result["source_basis"] != "actual_frame_and_original":
        return screening
    return {**screening, **result, "reason": "verified_native_frame",
            "frame_sha256": review["source_sha256"]}


def evaluate_rows(root, rows, policy, config):
    from .recheck_attribution import evidence, in_scope

    previous = policy.get("presentations", {})
    visual_path = root / "state/frontier_native_reviews.json"
    cover_path = root / "state/x_covers.json"
    native = read_json(visual_path) if visual_path.is_file() else {}
    covers = read_json(cover_path) if native and cover_path.is_file() else {}
    excluded = {h.casefold() for h in config.get("excluded_aggregator_accounts", [])}
    watched = {h.casefold() for h in config.get("watch_accounts", [])}
    policy["native_sources"] = covers
    jobs = []
    for case in rows:
        if not in_scope(case, policy) or case.review_status != ReviewStatus.PENDING:
            continue
        path = root / "raw/x/signals" / (post_id(case.original_post_url) + ".json")
        sig = read_json(path) if path.exists() else {}
        jobs.append((case, sig))
    jobs.sort(
        key=lambda j: (
            j[0].author_handle.casefold() not in watched
            and int(j[1].get("likes") or 0) < 15,
            -int(j[1].get("likes") or 0),
            j[0].world_id,
        )
    )
    counts = Counter()
    for case, sig in jobs:
        packet = evidence(root, case)
        if not packet:
            counts["no_raw_source"] += 1
            continue
        receipt = assess(
            case, packet, sig, policy["decisions"].get(case.world_id, {}), excluded
        )
        if case.world_id in native:
            from .recheck_creator_role import prior_counterquotes
            if not prior_counterquotes(policy["decisions"].get(case.world_id, {})):
                receipt = native_review_receipt(case, packet, receipt, native[case.world_id], covers.get(case.world_id))
        previous[case.world_id] = receipt
        counts[receipt["decision"]] += 1
    write_json(root / "state/frontier_presentations.json", previous)
    policy["presentations"] = previous
    return dict(counts)


def unblock(root, seed_path):
    from .reconcile_sources import canonical_originals
    from .recheck_attribution import apply_attribution, load_policy
    from .publish_catalog import trusted
    from .enrich_firecrawl import EnrichmentCache

    config = yaml.safe_load(seed_path.read_text())
    ledger = root / "processed/cases.jsonl"
    with run_lock(root):
        cases = read_rows(ledger, AIWorldCase)
        eligible = {
            c.world_id
            for c in cases
            if c.model_era == "frontier" and c.review_status == ReviewStatus.PENDING
        }
        policy = load_policy(root)
        if policy is None:
            raise ValueError("Missing attribution policy for backlog review")
        pairs = canonical_originals(
            root, cases, config.get("excluded_aggregator_accounts", ())
        )
        rows = [c for c in cases if c.world_id in eligible]
        counts = evaluate_rows(root, rows, policy, config)
        cache = EnrichmentCache(root)
        for case in rows:
            case.normalize_taxonomy()
            verdict = apply_attribution(case, root, policy)
            case.normalize_taxonomy()
            path = (
                root
                / "raw/x/signals"
                / (case.original_post_url.rsplit("/", 1)[-1] + ".json")
            )
            signal = read_json(path) if path.exists() else {}
            if verdict in {"allow", "unscoped"} and trusted(
                case,
                config,
                cache,
                int(signal.get("likes") or 0),
                video=bool(signal.get("has_video")),
                native_presentation=verdict == "allow" and policy["presentations"].get(
                    case.world_id, {}).get("reason") == "verified_native_frame",
            ):
                case.review_status = ReviewStatus.APPROVED
        write_rows(ledger, cases)
        write_json(
            root / "state/phase2_backlog_review.json",
            dict(
                pending_before=len(rows),
                results=counts,
                cohort={c.world_id: c.review_status.value for c in rows},
                duplicate_changes=pairs,
            ),
        )
        print(
            f"Reviewed {len(rows)} pending frontier cases: {counts}; final cohort statuses {Counter(c.review_status.value for c in rows)}",
            flush=True,
        )
