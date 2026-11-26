"""Replay pending X duplicate hints against the local raw corpus. Defaults to a dry run."""
import argparse
from collections import defaultdict
from contextlib import nullcontext
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from rapidfuzz import fuzz
import yaml

from .dedup import attributed_elsewhere, deduplicate, post_text, record_work_keys
from .links import identity_url, post_id, repo_root, urls_in
from .models import AIWorldCase, RawTweetRecord, ReviewStatus
from .public_x_media import cached_native_entities, origins as public_origins
from .recheck_attribution import apply_attribution, load_policy
from .qualify_candidates import PROMO
from .storage import read_json, run_lock, write_json, write_text
from .x_media import POSITIONAL_KEY, attachment_keys, load_media_evidence, record_keys


def source_id(url):
    try:
        return post_id(url)
    except ValueError:
        return None


CREDIT = re.compile(
    r"(?:\b(?:made|built|created|coded|developed)\s+by|\b(?:creator|developer|dev|credit(?:s)?(?: to)?)\s*[:：]|"
    r"\bcredit to|(?:原作者|作者|開発者|制作者)\s*[:：])\s*@([a-z0-9_]{1,15})(?![a-z0-9_])", re.I)
OWN_BUILD = re.compile(
    r"\b(?:i|we)(?:['’]ve)?\s+(?:(?:just|recently|finally|also)\s+)?(?:built|made|coded|created|developed)\b"
    r"|\b(?:i|we) (?:asked|prompted|used) [^.!?\n]{1,65} to (?:build|make|code|create|generate)\b"
    r"|(?:我|我们)(?:用[^。！？\n]{0,36})?(?:做了|制作|开发了|生成了)|(?:作りました|作ってみた|制作しました)", re.I)
DERIVATIVE = re.compile(r"\b(?:re-?(?:make|made|built|build|create|created|implement(?:ed)?)|remix(?:ed)?|fork(?:ed)?|"
                        r"inspired by|my (?:own )?version|our (?:own )?version|adaptation|port(?:ed)? from)\b"
                        r"|复刻|仿作|二创|致敬|改编|リメイク|再現", re.I)
MIXED = re.compile(r"\b(?:roundup|collection of|thread of|vs\.?|(?:two|three|multiple|several|best|top|[2-9]) "
                   r"(?:different )?(?:worlds|games|projects|demos|builds))\b|合集|盘点|作品集|まとめ", re.I)
REPORTING = re.compile(r"\b(?:repost(?:ing)?|sharing|check (?:this|it) out|look (?:at (?:this|what)|what)|"
                       r"(?:incredible|amazing|impressive|great) (?:work|demo|build)|"
                       r"(?:this|that) (?:is|looks) (?:really )?(?:amazing|incredible|impressive))\b"
                       r"|转发|转推|转自|分享|すごい|紹介", re.I)


MENTION = re.compile(r"(?<![\w@])@([a-z0-9_]{1,15})\b", re.I)
PARTIAL_CREDIT = re.compile(r"\b(?:music|audio|sound|asset|assets|footage|image|photo|video|inspiration|idea)"
                            r"\s+(?:credit|credits|by)\b|音乐|素材来源|楽曲", re.I)
SECONDARY_OWN = re.compile(r"\b(?:i|we)(?:[’']ve)?\s+(?:(?:just|also)\s+)?(?:added|changed|adapted|modified|extended|improved|tweaked|ported|translated)\b"
                           r"|\b(?:my|our)\s+(?:(?:new|first|own)\s+)?(?:game|world|scene|demo|build|take|experiment)\b"
                           r"|(?:我|我们)(?:做的|自己的)|自作", re.I)
QUOTED = re.compile(r'^\s*>.*$|“[^”]*”|「[^」]*」|"[^"]*"', re.M)


def direct_status_targets(post):
    result = {}
    for url, _ in urls_in(post.text):
        expanded = post.expanded_urls.get(url, url)
        target = source_id(expanded)
        if target and target != post.tweet_id:
            result[target] = expanded
    return result


def definite_asset(keys):
    numbers = {k for k in keys if re.fullmatch(r"[0-9]{12,20}", k)}
    links = {k for k in keys if k.startswith("https://pbs.twimg.com/")}
    # One attachment can have a numeric ID and one CDN preview. A gallery cannot establish which work is credited.
    return keys if keys == (numbers | links) and len(numbers) <= 1 and len(links) <= 1 else set()


def media_origin_receipts(root, by_id):
    """Cross-check the later attachment entity against the creator's own saved attachment."""
    owners, own_media, reported = defaultdict(set), defaultdict(set), defaultdict(list)
    for path in (root / "raw/apify").glob("*.json"):
        items = read_json(path)
        while items:
            item = items.pop()
            if not isinstance(item, dict) or item.get("isRetweet") or item.get("is_retweet"):
                continue
            quote = item.get("quotedTweet") or item.get("quote") or item.get("quoted_tweet")
            if isinstance(quote, dict):
                items.append(quote)
            identifier = str(item.get("id", ""))
            record = by_id.get(identifier)
            account = item.get("author") or {}
            handle = item.get("username") or account.get("userName") or account.get("username") or ""
            if not record or handle.casefold() != record.post.author_handle.casefold():
                continue
            owner_id = str(item.get("user_id") or account.get("id") or "")
            if owner_id.isdecimal():
                owners[identifier].add(owner_id)
            for container in (item, item.get("extendedEntities"), item.get("extended_entities"), item.get("entities")):
                if not isinstance(container, dict):
                    continue
                for media in container.get("media") or ():
                    if not isinstance(media, dict):
                        continue
                    keys = definite_asset(attachment_keys([media]))
                    if not keys:
                        continue
                    permalink = media.get("expanded_url") or ""
                    link_id = source_id(permalink) if re.search(r"/(?:video|photo)/[0-9]+/?$", permalink) else None
                    origin_id = str(media.get("source_status_id_str") or media.get("source_status_id") or "")
                    if link_id == identifier and (not origin_id or origin_id == identifier):
                        if urlsplit(permalink).path.split("/")[1].casefold() == handle.casefold():
                            own_media[identifier].update(keys)
                    if origin_id and origin_id != identifier:
                        target = origin_id
                        proof = "native_attachment_source_status"
                    elif link_id and link_id != identifier and not origin_id:
                        target = link_id
                        proof = "native_attachment_creator_permalink"
                    else:
                        continue
                    # A provider can return a permalink to the containing post even when source_status_id is explicit.
                    if link_id not in {None, target, identifier}:
                        reported[identifier].append((None, None, None, None, None, None))
                        continue
                    owner = str(media.get("source_user_id_str") or media.get("source_user_id") or "")
                    details = (media.get("additional_media_info") or {}).get("source_user") or {}
                    user = ((details.get("user_results") or {}).get("result") or {}) if isinstance(details, dict) else {}
                    handle_hint = (user.get("core") or {}).get("screen_name") or (user.get("legacy") or {}).get("screen_name")
                    nested_id = str(user.get("rest_id") or "")
                    if owner and nested_id and owner != nested_id:
                        reported[identifier].append((None, None, None, None, None, None))
                        continue
                    origin_link = permalink if link_id == target else None
                    reported[identifier].append((target, proof, keys, owner or nested_id, handle_hint, origin_link))

    verified = {}
    for reporter, receipts in reported.items():
        targets = {r[0] for r in receipts}
        if len(targets) != 1:
            continue
        target = targets.pop()
        source = by_id.get(target)
        if not source or not own_media[target]:
            continue
        handle = source.post.author_handle.casefold()
        for _, proof, keys, owner, handle_hint, permalink in receipts:
            if ((owner and owners[target] != {owner}) or (handle_hint and handle_hint.casefold() != handle)
                    or (permalink and urlsplit(permalink).path.split("/")[1].casefold() != handle)):
                break
            if not keys & own_media[target]:
                break
            if not permalink and not owner:
                break
        else:
            reason = next((r[1] for r in receipts if r[1] == "native_attachment_source_status"), receipts[0][1])
            verified[(target, reporter)] = (reason, next((r[5] for r in receipts if r[5]), target))
    return verified


def attributed_repost(original, later, original_keys, later_keys, signal, excluded, native_origin=None, *, independent_allow=False):
    """Return an auditable, directional reason that a later source only reports the original."""
    author, repost = original.post, later.post
    handle = author.author_handle.casefold()
    if (handle in excluded or handle == repost.author_handle.casefold() or int(author.tweet_id) >= int(repost.tweet_id)
            or not author.published_at or not repost.published_at):
        return
    if (author.published_at.tzinfo is None or repost.published_at.tzinfo is None or author.published_at >= repost.published_at):
        return
    shared = definite_asset(original_keys) & definite_asset(later_keys)
    ids_a = {k for k in original_keys if k.isdecimal()}
    ids_b = {k for k in later_keys if k.isdecimal()}
    urls_a, urls_b = original_keys - ids_a, later_keys - ids_b
    if (not shared or (ids_a and ids_b and ids_a != ids_b) or (urls_a and urls_b and urls_a != urls_b)
            or any(POSITIONAL_KEY.fullmatch(k) and int(re.search(r"\d+$", k)[0]) > 0
                   for k in author.media_keys + repost.media_keys)):
        return
    own_text = QUOTED.sub("", author.text)
    claim = OWN_BUILD.search(own_text)
    hypothetical = claim and re.search(r"\b(?:if|as if|wish|pretend|not (?:saying|claiming))\s+(?:that\s+)?$",
                                       own_text[:claim.start()], re.I)
    validated_native = native_origin and native_origin[0] == "public_x_native_source_status" and independent_allow
    if ((not claim and not validated_native) or hypothetical or OWN_BUILD.search(repost.text)
            or SECONDARY_OWN.search(repost.text) or PARTIAL_CREDIT.search(repost.text)):
        return
    if any(m.casefold() not in {handle, repost.author_handle.casefold()} for m in MENTION.findall(repost.text)):
        return
    if re.match(r"^\s*(?:RT\s+@|repost(?:ing)?\b|转推|转发)", author.text, re.I):
        return
    if (attributed_elsewhere(original) or any(match[1].casefold() != handle for match in CREDIT.finditer(author.text))
            or any(test.search(text) for test in (PROMO, DERIVATIVE, MIXED) for text in (author.text, repost.text))):
        return
    demos, projects = record_work_keys(original)
    other_demos, other_projects = record_work_keys(later)
    if len(demos | other_demos) > 1 or len(projects | other_projects) > 1:
        return
    # A second source promoting its own separate destination may be a different build.
    if other_demos - demos or other_projects - projects:
        return
    if direct_status_targets(author):
        return
    targets = direct_status_targets(repost)
    others = (set(targets) | set(repost.referenced_post_ids)) - {author.tweet_id}
    if others:
        return
    credits = list(CREDIT.finditer(repost.text))
    if any(match[1].casefold() != handle for match in credits):
        return
    quote_id = str(signal.get("quoted_id") or "")
    quote_author = (signal.get("quoted_author") or "").casefold()
    if quote_id and (quote_id != author.tweet_id or (quote_author and quote_author != handle)):
        return
    linked = targets.get(author.tweet_id)
    if linked and urlsplit(linked).path.strip("/").split("/")[0].casefold() not in {handle, "i"}:
        return
    reference = None
    if credits:
        reason, reference = "explicit_creator_credit", credits[0][0]
    elif native_origin:
        reason, reference = native_origin
    elif quote_id == author.tweet_id and quote_id in repost.referenced_post_ids and REPORTING.search(repost.text):
        reason, reference = "creator_quote_report", quote_id
    elif linked and REPORTING.search(repost.text):
        reason, reference = "creator_post_report", linked
    else:
        return
    return {"original":original.original_url, "report":later.original_url, "proof":reason,
            "reference":reference, "shared_media":sorted(shared)}


def repair(root: Path, seed_path: Path, *, apply=False, audit_path=None):
    with run_lock(root) if apply else nullcontext():
        records = [RawTweetRecord.model_validate_json(p.read_bytes()) for p in (root / "raw/x").glob("*.json")]
        signals = {p.stem: read_json(p) for p in (root / "raw/x/signals").glob("*.json")}
        evidence = load_media_evidence(root, signals)
        config = (yaml.safe_load(seed_path.read_text()) or {}) if seed_path.is_file() else {}
        excluded = {h.casefold() for h in config.get("excluded_aggregator_accounts", ())}
        groups = deduplicate(records, excluded_authors=excluded,
                             media_evidence=evidence)
        by_id = {r.post.tweet_id: r for r in records}
        media_origins = media_origin_receipts(root, by_id)
        live_proofs = public_origins(cached_native_entities(root, by_id))
        policy = load_policy(root) if live_proofs else None
        prior_targets = {later:earlier for earlier,later in media_origins}
        for pair, native in live_proofs.items():
            earlier,later = pair
            if prior_targets.get(later, earlier) != earlier:
                media_origins.pop((prior_targets[later], later), None)
            elif {native["media_id"],native["media_url"]} <= record_keys(by_id[earlier], evidence) & record_keys(by_id[later], evidence):
                media_origins[pair] = ("public_x_native_source_status", native["attachment_url"])
        groups_by_id = {post_id(url): g for g in groups for url in [g.original.original_url, *g.related_post_urls]}
        identities = {i: record_keys(r, evidence) for i, r in by_id.items()}
        positions = {i: {k for k in r.post.media_keys if POSITIONAL_KEY.fullmatch(k)} for i, r in by_id.items()}
        texts = {i: post_text(r) for i, r in by_id.items()}

        path = root / "processed/cases.jsonl"
        with path.open(encoding="utf-8", newline="") as ledger:
            lines = ledger.readlines()
        rows = {i: json.loads(line) for i, line in enumerate(lines) if line.strip()}
        catalog_links = {}
        approved_sources = set()
        attribution_rows = {}
        attribution_allow = {}
        resolved = {}
        for row in rows.values():
            identifier = source_id(row["original_post_url"])
            if identifier:
                attribution_rows[identifier] = row
                if row.get("review_status") == ReviewStatus.APPROVED:
                    approved_sources.add(identifier)
                catalog_links[identifier] = {repo_root(u) or identity_url(u) for u in
                                             (row.get("live_demo_url"), row.get("repo_url")) if u}

        def existing_allow(identifier):
            if identifier not in attribution_allow:
                row = attribution_rows.get(identifier)
                attribution_allow[identifier] = bool(policy and row
                    and apply_attribution(AIWorldCase.model_validate(row), root, policy) == "allow")
            return attribution_allow[identifier]

        def placeholder_only(identifier, other):
            # Unavailable posts and older flags without a known positional collision remain for review.
            if other not in by_id or not positions[identifier].intersection(positions[other]):
                return False
            if (groups_by_id[identifier] is groups_by_id[other] or identities[identifier] & identities[other]
                    or catalog_links.get(identifier, set()) & catalog_links.get(other, set())):
                return False
            a, b = texts[identifier], texts[other]
            return (min(len(a), len(b)) < 32 or fuzz.ratio(a, b) < 89.999999
                    or max(SequenceMatcher(None, a, b).ratio(), SequenceMatcher(None, b, a).ratio()) < 0.9)

        counts = {"pending_x": 0, "missing_source": 0, "changed": 0, "removed": 0, "added": 0}
        for n, row in rows.items():
            if (row.get("review_status", ReviewStatus.PENDING) != ReviewStatus.PENDING
                    or row.get("source_kind", "x_post") != "x_post"):
                continue
            counts["pending_x"] += 1
            identifier = source_id(row["original_post_url"])
            group = groups_by_id.get(identifier)
            if group is None:
                counts["missing_source"] += 1
                continue
            original = row.get("possible_duplicate_urls", [])
            new = group.possible_duplicate_urls
            proven = set()
            if (row.get("author_handle") or "").casefold() == by_id[identifier].post.author_handle.casefold():
                for url in set(original + new):
                    other = source_id(url)
                    if other not in by_id or other in approved_sources:
                        continue
                    pair = (identifier, other)
                    origin = media_origins.get(pair)
                    public = origin and origin[0] == "public_x_native_source_status"
                    if public and existing_allow(other):
                        # A borrowed frame alone cannot establish a competing creator. Require an
                        # actual authorship claim in the reporting account's own post or thread.
                        later_texts = [by_id[other].post.text, *(reply.text for reply in by_id[other].thread)]
                        if any(OWN_BUILD.search(QUOTED.sub("", text)) or SECONDARY_OWN.search(QUOTED.sub("", text))
                               for text in later_texts):
                            continue
                    independent = public and existing_allow(identifier)
                    receipt = attributed_repost(by_id[identifier], by_id[other], identities[identifier], identities[other],
                                                signals.get(other, {}), excluded, origin, independent_allow=independent)
                    if receipt and origin and origin[0] == "public_x_native_source_status":
                        receipt["public_x_media"] = live_proofs[pair]
                    if receipt:
                        proven.add(other)
                        resolved[(identifier, other)] = receipt
            new = [url for url in new if source_id(url) not in proven]
            new_ids = {source_id(url) for url in new}
            kept = [url for url in original if source_id(url) not in proven
                    and (source_id(url) in new_ids or not placeholder_only(identifier, source_id(url)))]
            kept_ids = {source_id(url) for url in kept}
            added = [url for url in new if source_id(url) not in kept_ids]
            if kept != original or added:
                counts["changed"] += 1
                counts["removed"] += len(original) - len(kept)
                counts["added"] += len(added)
                row["possible_duplicate_urls"] = kept + added
                lines[n] = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        if rows and all("model_era" in row and "title" in row for row in rows.values()):
            from .reconcile_sources import canonical_originals
            cases = {n:AIWorldCase.model_validate(row) for n,row in rows.items()}
            directional = canonical_originals(root,cases.values(),excluded)
            for n,case in cases.items():
                if case.world_id in directional:
                    lines[n] = case.model_dump_json()+"\n"
            counts["directional_changes"] = len(directional)
        if apply and (counts["changed"] or counts.get("directional_changes")):
            write_text(path, "".join(lines))
        if resolved:
            counts["credited_repost_pairs"] = len(resolved)
        if audit_path is not None:
            write_json(audit_path, [resolved[key] for key in sorted(resolved)])
        return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--seeds", type=Path, default=Path("config/seeds.yaml"))
    parser.add_argument("--apply", action="store_true", help="Atomically update only duplicate hints for pending X cases.")
    parser.add_argument("--audit-output", type=Path, help="Save the evidence for resolved, directionally credited reposts.")
    args = parser.parse_args()
    print(json.dumps({"apply": args.apply, **repair(args.data_dir, args.seeds, apply=args.apply, audit_path=args.audit_output)}))
