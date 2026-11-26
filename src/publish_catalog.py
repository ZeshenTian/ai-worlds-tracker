"""Publish reviewed records and keep the complete moderation ledger separate."""
import argparse
from collections import Counter
from datetime import UTC, datetime
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
import yaml

from .enrich_firecrawl import EnrichmentCache
from .export_and_analyze import REVIEW_FIELDS, write_csv
from .extract_structured import apply_verified_research, mentions_model, source_model_quote
from .links import identity_url, post_id, repo_root
from .qualify_candidates import PROMO
from .recheck_attribution import apply_attribution, load_policy, record_manual_reviews
from .reconcile_sources import canonical_originals
from .models import AIWorldCase, DemoHealth, ReviewStatus
from .storage import read_json, read_rows, run_lock, write_json, write_rows


PROJECT = Path(__file__).resolve().parents[1]


CODE_TECH = re.compile(
    r"\b(?:three[ .]?js|webgpu|webgl|glsl|wgsl|babylon[ .]?js|playcanvas|javascript|typescript|"
    r"html5?|unity|unreal(?: engine)?|godot|shader[s]?|python)\b", re.I | re.ASCII)


def documented_code(case):
    def technologies(text):
        return {re.sub(r"[ .]", "", term.casefold()) for term in CODE_TECH.findall(text)}
    return bool(technologies(" ".join(case.tech_stack)) & technologies(" ".join(case.evidence_quotes)))


def trusted(case, config, cache, likes=0, *, video=False, native_presentation=False):
    if (case.author_handle or "").casefold() in {a.casefold() for a in config.get("excluded_aggregator_accounts", [])}:
        return False
    host = urlsplit(case.original_post_url).hostname
    catalog = case.source_kind == "primary_page" and host in config.get("trusted_catalog_hosts", [])
    author = case.source_kind == "x_post" and (case.author_handle or "").lower() in {
        account.lower() for account in config.get("watch_accounts", [])
    }
    if case.review_status == ReviewStatus.REJECTED or not case.models_used or not case.evidence_quotes or case.possible_duplicate_urls:
        return False
    if native_presentation and case.model_era == "frontier" and (author or likes >= 15):
        return True
    if case.demo_health_status == DemoHealth.VERIFIED:
        return True
    repo = repo_root(case.repo_url) if case.repo_url else None
    path = cache.catalog_path(repo) if repo else None
    if path and path.exists() and read_json(path).get("exists") is True:
        return True
    demo_host = urlsplit(case.live_demo_url or "").hostname or ""
    hosted = any(demo_host == h or demo_host.endswith("." + h) for h in config.get("trusted_demo_hosts", []))
    if case.model_era == "frontier" and case.tech_stack:
        if (author or case.live_demo_url) and likes >= 1:
            return True
        if likes >= 15 and (video or case.work_type == "coded_3d_scene" or documented_code(case)):
            return True
    return (author or catalog or hosted) and likes >= 40


def family(model):
    name = model.strip()
    for prefix, label in (
        (r"^(?:(?:openai(?:['’]s)?\s+)?(?:gpt|chatgpt|codex|astra|sol)(?=\b|\d)|\d+(?:\.\d+)?\s+astra\b)", "GPT"),
        (r"^(?:(?:anthropic(?:['’]s)?|routed)\s+)?(?:claude|opus|fable|haiku|sonnet)(?=\b|\d)", "Claude"),
        (r"^(?:google(?:['’]s)?\s+)?(?:gemini|neon|argon|hydrogen|carbon|antigravity)(?=\b|\d)", "Gemini"),
        (r"^(?:world ?labs? )?marble\b", "Marble"),
        (r"^kimi\b", "Kimi"),
    ):
        if re.search(prefix, name, re.I | re.ASCII):
            return label
    for name in ("DeepSeek","Qwen","Grok","MiniMax","Step","GLM","Gemma","Llama","Mistral","Mixtral"):
        if re.match(re.escape(name)+r"(?=\b|\d)", model.strip(), re.I):
            return name
    return model


def cover_matches(case, source_url, kind):
    if not source_url:
        return False
    if kind == "project_media":
        return identity_url(source_url) == identity_url(case.original_post_url)
    try:
        identifier = post_id(source_url)
    except ValueError:
        return False
    for url in [case.original_post_url, *case.related_post_urls]:
        try:
            if post_id(url) == identifier:
                return True
        except ValueError:
            continue
    return False


def earlier_x_duplicate(case):
    if case.source_kind != "x_post":
        return False
    original = int(post_id(case.original_post_url))
    for url in case.possible_duplicate_urls:
        try:
            if int(post_id(url)) < original:
                return True
        except ValueError:
            continue
    return False


def merge_duplicate_demos(cases, legacy):
    # A later post can reveal a demo URL which was unknown when the first post was grouped.
    kept = {}
    order = sorted(cases.values(), key=lambda c: (
        earlier_x_duplicate(c),
        int(post_id(c.original_post_url)) if c.source_kind=="x_post" else float("inf"),
        c.world_id not in legacy, c.first_seen_at or "", c.world_id))
    for case in order:
        if not case.live_demo_url or case.review_status == ReviewStatus.REJECTED:
            continue
        if case.review_status != ReviewStatus.APPROVED and case.world_id not in legacy:
            continue
        url = identity_url(case.live_demo_url)
        first = kept.setdefault(url, case)
        if first is case:
            continue
        for source in [case.original_post_url, *case.evidence_source_urls]:
            if source not in first.evidence_source_urls:
                first.evidence_source_urls.append(source)
        if case.source_kind == "x_post" and case.original_post_url != first.original_post_url:
            first.related_post_urls = list(dict.fromkeys([*first.related_post_urls, case.original_post_url]))
        case.review_status = ReviewStatus.REJECTED
        case.possible_duplicate_urls = list(dict.fromkeys([*case.possible_duplicate_urls, first.original_post_url]))


def import_catalog_batch(cases, path):
    """Import a reviewed source batch without changing existing moderation decisions."""
    known_sources, known_works = set(), set()
    imported = []

    def source_key(case):
        return post_id(case.original_post_url) if case.source_kind == "x_post" else identity_url(case.original_post_url)

    def remember(case):
        known_sources.add(source_key(case))
        known_works.update(identity_url(u) for u in (case.live_demo_url, case.repo_url) if u)

    for case in cases.values():
        remember(case)
    for item in read_json(path):
        case = AIWorldCase.model_validate(item)
        previous = cases.get(case.world_id)
        if previous and (source_key(case) != source_key(previous) or previous.review_status == ReviewStatus.REJECTED):
            continue
        if not previous and (source_key(case) in known_sources or
                any(identity_url(u) in known_works for u in (case.live_demo_url, case.repo_url) if u)):
            continue
        direct = case.original_post_url in case.evidence_source_urls
        if case.source_kind == "primary_page" and repo_root(case.original_post_url):
            repo_path = urlsplit(repo_root(case.original_post_url)).path.lower() + "/"
            direct = direct or any(urlsplit(u).hostname == "raw.githubusercontent.com"
                                   and urlsplit(u).path.lower().startswith(repo_path)
                                   for u in case.evidence_source_urls)
        if (not case.summary_en or not case.evidence_quotes or not case.models_used
                or not direct
                or case.possible_duplicate_urls or case.review_status == ReviewStatus.REJECTED):
            raise ValueError(f"Incomplete editorial evidence for {case.world_id}")
        if previous:
            case.first_seen_at = previous.first_seen_at
        case.review_status = ReviewStatus.APPROVED
        cases[case.world_id] = case
        remember(case)
        imported.append(case)
    return imported


def recover_model_disclosures(cases, root):
    """Recheck pending extraction proposals against their own source, across the backlog."""
    missing = {case.world_id: case for case in cases if case.review_status == ReviewStatus.PENDING
               and case.source_kind == "x_post" and not case.models_used}
    if not missing:
        return
    for path in (root / "processed/extraction").glob("*.json"):
        proposal = read_json(path)
        case = missing.get(proposal.get("world_id"))
        if not case or proposal.get("review_status") == "rejected" or proposal.get("original_post_url") != case.original_post_url:
            continue
        raw = root / "raw/x" / (post_id(case.original_post_url) + ".json")
        if not raw.exists():
            continue
        record = read_json(raw)
        author = record["post"]
        if author["author_handle"].casefold() != (case.author_handle or "").casefold():
            continue
        texts = [author["text"], *(r["text"] for r in record["thread"]
                 if r["author_handle"].casefold() == author["author_handle"].casefold())]
        for name in proposal.get("models_used", []):
            if name in case.models_used:
                continue
            quote = next((q for q in case.evidence_quotes if mentions_model(name, q)
                          and any(q in text for text in texts)), None) or source_model_quote(name, texts)
            if quote:
                case.models_used.append(name)
                if quote not in case.evidence_quotes:
                    case.evidence_quotes.append(quote)


def publish(root, platform, *, curate=False, auto=False, timestamp=None, editorial=None):
    processed = root / "processed" / "cases.jsonl"
    base = read_json(PROJECT / "research/seed_snapshot/worlds.json")
    legacy = {row["world_id"] for row in base}
    ledger = read_rows(processed, AIWorldCase) if processed.exists() else []
    cases = {case.world_id: case for case in ledger}
    for item in base:
        cases.setdefault(item["world_id"], AIWorldCase.model_validate(item))
    now = timestamp or datetime.now(UTC).isoformat(timespec="seconds")
    if curate:
        for name in ("gemini", "gpt"):
            for item in read_json(PROJECT / f"research/expansion/{name}.json"):
                record = AIWorldCase.model_validate(item)
                old = cases.get(record.world_id)
                if old and old.review_status == ReviewStatus.REJECTED:
                    continue
                if not record.evidence_quotes or not record.models_used:
                    raise ValueError(f"Missing curated source evidence: {record.title}")
                record.review_status = ReviewStatus.APPROVED
                record.first_seen_at = old.first_seen_at if old else None
                cases[record.world_id] = record
        evidence = read_json(PROJECT / "research/expansion/repo_evidence.json")
        for world_id, item in evidence["cases"].items():
            cases[world_id] = apply_verified_research(cases[world_id], item)
    if editorial:
        record_manual_reviews(root, import_catalog_batch(cases, editorial))
    health_file = root / "state/demo_health.json"
    health = read_json(health_file) if health_file.exists() else {}
    cover_path = root / "state/x_covers.json"
    covers = read_json(cover_path) if cover_path.exists() else {}
    project_path = root / "state/primary_covers.json"
    project_covers = read_json(project_path) if project_path.exists() else {}
    cache = EnrichmentCache(root)
    config = yaml.safe_load((PROJECT / "config/seeds.yaml").read_text())
    canonical_originals(root, cases.values(), config.get("excluded_aggregator_accounts", ()))
    policy = load_policy(root)
    if auto:
        recover_model_disclosures(cases.values(), root)
    for case in cases.values():
        case.first_seen_at = case.first_seen_at or ("2026-11-24T06:31:01+00:00" if case.world_id in legacy else now)
        check = health.get(case.world_id, {})
        if check and check.get("live_demo_url") == case.live_demo_url:
            case.demo_health_status = DemoHealth(check["demo_health_status"])
            case.thumbnail_url = check.get("thumbnail_url")
        if not case.live_demo_url:
            case.demo_health_status = DemoHealth.NO_DEMO
        if case.thumbnail_url == f"/thumbnails/{case.world_id}.webp" and (platform / "public" / case.thumbnail_url.lstrip("/")).is_file():
            case.cover_source = "demo"
            case.cover_source_url = case.live_demo_url
        else:
            case.thumbnail_url = case.cover_source = case.cover_source_url = None
            for store, kind in ((covers,"x_media"), (project_covers,"project_media")):
                cover = store.get(case.world_id, {})
                media = cover.get("thumbnail_url")
                if media and cover_matches(case, cover.get("source_url"), kind) and (platform / "public" / media.lstrip("/")).is_file():
                    case.thumbnail_url = media
                    case.cover_source = "project_poster" if kind == "project_media" and cover.get("cover_source") == "project_poster" else kind
                    case.cover_source_url = cover["source_url"]
                    break
        info = root / "raw/x/signals" / (case.original_post_url.rsplit("/", 1)[-1] + ".json")
        signal = read_json(info) if info.exists() else {}
        likes = int(signal.get("likes") or 0)
        case.normalize_taxonomy()
        if case.source_kind == "x_post":
            raw = root / "raw/x" / info.name
            text = read_json(raw)["post"]["text"] if raw.exists() else " ".join(case.evidence_quotes)
            if (case.author_handle or "").casefold() in {a.casefold() for a in config.get("excluded_aggregator_accounts", [])} or PROMO.search(text + " " + (signal.get("quoted_text") or "")):
                case.review_status = ReviewStatus.REJECTED
        attribution = apply_attribution(case, root, policy)
        case.normalize_taxonomy()
        case = AIWorldCase.model_validate(case.model_dump())
        presentation = (policy or {}).get("presentations", {}).get(case.world_id, {})
        confirmed_native = attribution == "allow" and presentation.get("reason") == "verified_native_frame"
        if confirmed_native:
            from .recheck_attribution import evidence, presentation_matches
            confirmed_native = presentation_matches(case, evidence(root, case), policy, presentation)
        video = bool(signal.get("has_video") or re.search(
            r"(?:ext_tw_video_thumb|amplify_video_thumb|tweet_video_thumb)", signal.get("media_url") or ""))
        if (auto and attribution in {"unscoped", "allow"} and case.review_status == ReviewStatus.PENDING
                and trusted(case, config, cache, likes, video=video, native_presentation=confirmed_native)):
            case.review_status = ReviewStatus.APPROVED
        cases[case.world_id] = case
    merge_duplicate_demos(cases, legacy)
    ordered = sorted(cases.values(), key=lambda c: c.world_id)
    public = [c for c in ordered if c.review_status == ReviewStatus.APPROVED or
              (c.world_id in legacy and c.review_status == ReviewStatus.PENDING and not earlier_x_duplicate(c))]
    data = [c.model_dump(mode="json") for c in public]
    queue = [c.model_dump(mode="json") for c in ordered if c.review_status == ReviewStatus.PENDING]
    watched = {a.lower() for a in config.get("watch_accounts", [])}
    author_counts = Counter(c.author_handle.lower() for c in public if c.author_handle)
    write_json(root / "state/watch_suggestions.json", {
        author:n for author,n in sorted(author_counts.items()) if n >= 2 and author not in watched and author not in {a.casefold() for a in config.get("excluded_aggregator_accounts", [])}
    })
    write_rows(processed, ordered)
    exports = root / "exports"
    write_csv(exports / "review_queue.csv", queue, REVIEW_FIELDS)
    write_json(exports / "ai_worlds.json", data)
    write_csv(exports / "ai_worlds.csv", data, list(AIWorldCase.model_fields))
    meta = {
        "last_updated_at": now, "total": len(public),
        "frontier_total": sum(c.model_era == "frontier" for c in public),
        "legacy_total": sum(c.model_era == "legacy" for c in public),
        "frontier_model_family_counts": dict(Counter(m for c in public if c.model_era == "frontier" for m in set(map(family,c.models_used)))),
        "model_counts": dict(Counter(m for c in public for m in set(c.models_used))),
        "model_family_counts": dict(Counter(m for c in public for m in set(map(family,c.models_used)))),
        "playable_count": sum(c.demo_health_status == DemoHealth.VERIFIED for c in public),
        "open_source_count": sum(c.is_open_source is True for c in public),
    }
    write_json(exports / "meta.json", meta)
    write_json(platform / "data/worlds.json", data)
    write_json(platform / "data/meta.json", meta)
    print(f"{len(public)} public cases, {len(queue)} pending; {meta['playable_count']} verified playable")


if __name__ == "__main__":
    load_dotenv(PROJECT / ".env", override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("--curate", action="store_true", help="Import source-reviewed expansion files")
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "data")
    parser.add_argument("--platform", type=Path, default=PROJECT / "platform")
    parser.add_argument("--editorial", type=Path, help="Import a checked, bilingual X-source batch")
    parser.add_argument("--review", metavar="WORLD_ID")
    parser.add_argument("--status", choices=["approved", "rejected", "pending"])
    args = parser.parse_args()
    if bool(args.review) != bool(args.status):
        parser.error("--review and --status must be supplied together")
    with run_lock(args.data_dir):
        if args.review:
            path = args.data_dir / "processed/cases.jsonl"
            rows = read_rows(path, AIWorldCase)
            match = next((row for row in rows if row.world_id == args.review), None)
            if not match:
                parser.error("unknown world ID")
            match.review_status = ReviewStatus(args.status)
            record_manual_reviews(args.data_dir, [match])
            write_rows(path, rows)
        publish(args.data_dir, args.platform, curate=args.curate, editorial=args.editorial,
                auto=os.getenv("AUTO_APPROVE_TRUSTED", "").lower() == "true")
