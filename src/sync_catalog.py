"""Discover once per query, then process works missing from the durable ledger."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import UTC, datetime
import re
import os
from pathlib import Path

from dotenv import load_dotenv
import httpx
import yaml

from .apify_x import restore_quote_signals
from .catalog_posts import resolve_seeds
from .qualify_candidates import previously_declined_with_media, qualify, self_quoted_source
from .recheck_attribution import load_policy, prepare as prepare_attribution
from .model_era import CUE, TOKEN_FLAGS, explicit_frontier, has_frontier_signal
from .x_covers import build as build_covers
from .primary_covers import build as build_project_covers
from .cli import FIXTURES, PROJECT, Mode, Pipeline
from .dedup import deduplicate
from .reconcile_sources import apply_additions, candidate_groups, source_additions
from .x_media import load_media_evidence
from .enrich_firecrawl import EnrichmentCache, Firecrawl, FixtureScraper
from .extract_structured import AnnotatedExtractor, AutoExtractor, ChatExtractor, OpenAIExtractor, extract_cases, merge_prepared_cases, prepare_case
from .ingest_x import MockXAdapter, OfficialXApiAdapter, ThirdPartyXAdapter, cache_posts, ingest
from .links import post_id
from .models import RawTweetRecord, ReviewStatus
from .publish_catalog import publish
from .storage import read_json, run_lock, write_json
from .verify_demos import verify


ENGINE = re.compile(r"three[ .]?js|webgl|webgpu|glsl|babylon|godot|blender|unreal|unity|shader|(?:single|one)[- ]html", re.I)
BUILD = re.compile(r"\b(?:i|we) (?:made|built|coded|created|asked|prompted)|\b(?:built|made|coded|generated) (?:with|using|in)|作って|制作|做了|开发", re.I)
FAMILIES = (("GPT", re.compile(r"\b(?:gpt|chatgpt|astra|codex)\b", TOKEN_FLAGS)),
            ("Gemini", re.compile(r"\b(?:gemini|neon|hydrogen|argon|carbon)\b", TOKEN_FLAGS)),
            ("Claude", re.compile(r"\b(?:claude|opus|fable)\b", TOKEN_FLAGS)))


def rank_groups(groups, attempts, *, frontier_only=False, signals=None):
    """Prioritize firsthand construction evidence and give each model family a turn."""
    buckets = defaultdict(lambda: defaultdict(list))
    for group in groups:
        post = group.original.post
        text = "\n".join([post.text, *(reply.text for reply in group.original.thread)])
        receipt = (signals or {}).get(post.tweet_id, {})
        own_quote = self_quoted_source(post, receipt)
        if own_quote:
            text += "\n" + own_quote["text"]
        signal = has_frontier_signal(text, post.published_at)
        if frontier_only and not signal:
            continue
        family = next((name for name, pattern in FAMILIES if pattern.search(text)), "Other")
        stage = (not signal, bool(attempts.get(post.tweet_id)))
        quality = (not bool(ENGINE.search(text)),
                   not bool(group.demo_urls or group.repo_urls or BUILD.search(text)),
                   not bool(CUE.search(text)), not explicit_frontier(text), -int(post.tweet_id))
        has_media = bool(receipt.get("media_url") or group.demo_urls or group.repo_urls)
        popular = (not has_media, not bool(CUE.search(text)), -int(receipt.get("likes") or 0), quality)
        buckets[stage][family].append((quality, popular, group))
    ranked = []
    for stage in sorted(buckets):
        families = buckets[stage]
        queues = []
        for name in sorted(families):
            entries = families[name]
            by_evidence = iter(sorted(entries, key=lambda entry: entry[0]))
            by_engagement = iter(sorted(entries, key=lambda entry: entry[1]))
            seen, queue = set(), []
            # Alternate independent queues so high-interest demos and small
            # accounts with concrete technical evidence both receive slots.
            for i in range(len(entries)):
                stream = by_evidence if i % 3 == 2 else by_engagement
                candidate = next(item[2] for item in stream if item[2].original.post.tweet_id not in seen)
                seen.add(candidate.original.post.tweet_id)
                queue.append(candidate)
            queues.append(queue)
        for i in range(max(map(len, queues))):
            ranked.extend(queue[i] for queue in queues if i < len(queue))
    return ranked


def sync(pipeline, platform: Path):
    config = yaml.safe_load(pipeline.seeds.read_text())
    mock = pipeline.source == "mock"
    if mock:
        adapter = MockXAdapter(FIXTURES / "tweets.json")
    elif pipeline.source == "x_api_v2":
        adapter = OfficialXApiAdapter(pipeline.required_env("X_BEARER_TOKEN"), pipeline.client,
                                      archive=os.getenv("X_THREAD_ARCHIVE", "").lower() == "true")
    elif pipeline.source == "third_party":
        adapter = ThirdPartyXAdapter(pipeline.required_env("X_THIRD_PARTY_BASE_URL"),
                                     pipeline.required_env("X_THIRD_PARTY_API_KEY"), pipeline.client)
    elif pipeline.source == "apify":
        adapter = None  # The discovery command checkpoints remote runs before processing.
    else:
        raise ValueError("Choose an X discovery adapter")
    root = pipeline.root
    rows = pipeline.cases(missing_ok=True)
    existing_ids = {case.world_id for case in rows}
    known_sources = {url for c in rows for url in [c.original_post_url, *c.related_post_urls]}
    client = None if mock else pipeline.client
    raw = root / "raw/x"
    new_seeds = [post_id(url) for url in config.get("seed_urls", []) if url not in known_sources]
    if adapter is not None:
        cache_posts(adapter, new_seeds, raw, client, refresh=False)
        ingest(adapter, config, root, Mode.INCREMENTAL, 30, client)
    else:
        known_ids = {url.rsplit("/",1)[-1] for url in known_sources}
        resolve_seeds(root, client, known_ids, int(os.getenv("ATLAS_CATALOG_LIMIT", "16")))
    if pipeline.source == "apify":
        restore_quote_signals(root)
    records = [RawTweetRecord.model_validate_json(path.read_bytes()) for path in raw.glob("*.json")]
    signals = {p.stem: read_json(p) for p in (raw / "signals").glob("*.json")}
    excluded = config.get("excluded_aggregator_accounts", ())
    additions = source_additions(rows, records, excluded)
    apply_additions(root, additions)
    for case in rows:
        case.related_post_urls.extend(additions.get(case.world_id, ()))
    media = load_media_evidence(root, signals)
    deduped = deduplicate(records, excluded_authors=excluded, media_evidence=media)
    groups = candidate_groups(deduped, rows, records, excluded_authors=excluded, media_evidence=media)
    attempts_path = root / "state/extraction_attempts.json"
    attempts = read_json(attempts_path) if attempts_path.exists() else {}
    frontier_only = os.getenv("ATLAS_FRONTIER_ONLY", "").lower() == "true"
    remaining = rank_groups(groups, attempts, frontier_only=frontier_only, signals=signals)
    minimum = int(os.getenv("ATLAS_MIN_LIKES", "0"))
    if minimum and not mock:
        watched = {a.casefold() for a in config.get("watch_accounts",())}
        remaining = [g for g in remaining if g.original.post.author_handle.casefold() in watched
                     or int(signals.get(g.original.post.tweet_id,{}).get("likes") or 0)>=minimum]
        repair = root/"state/apify_x/phase2_recovery.json"
        if repair.exists():
            recovered = set(read_json(repair)["new_post_ids"])
            remaining.sort(key=lambda g: g.original.post.tweet_id not in recovered)
    if not mock and os.getenv("ATLAS_RECHECK_MEDIA_DECLINES", "").lower() == "true":
        # Reassess old text-only decisions when we can also supply the attachment
        # or project metadata. Use organic ranking and the normal publication rules.
        remaining = [group for group in remaining if previously_declined_with_media(group, root, signals)]
    batches = 1 if mock else max(1, int(os.getenv("ATLAS_BACKLOG_BATCHES", "1")))
    for batch in range(batches):
        groups = remaining
        if not mock:
            groups = qualify(groups, root, config=config, model=os.getenv("GATE_MODEL","auto"),
                             limit=int(os.getenv("ATLAS_GATE_LIMIT", "300")))
            groups = rank_groups(groups, attempts, frontier_only=frontier_only, signals=signals)
            if minimum and not mock and repair.exists():
                groups.sort(key=lambda g:g.original.post.tweet_id not in recovered)
            groups = groups[:int(os.getenv("ATLAS_EXTRACT_LIMIT", "60"))]
        if groups:
            if mock:
                scraper = FixtureScraper(FIXTURES / "pages.json")
            else:
                scraper = Firecrawl(os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_TOKEN", ""),
                                    pipeline.client, os.getenv("GITHUB_TOKEN"))
            model = os.getenv("EXTRACTION_MODEL", "auto")

            def extractor():
                if mock:
                    return AnnotatedExtractor(FIXTURES / "extractions.json")
                if model == "auto" or model.startswith("auto:"):
                    return AutoExtractor(root)
                if model.startswith(("gemini-","MiniMax-")):
                    key = "MINIMAX_API_KEY" if model.startswith("MiniMax-") else "GEMINI_API_KEY"
                    return ChatExtractor(pipeline.required_env(key),model,root)
                return OpenAIExtractor(pipeline.required_env("OPENAI_API_KEY"), model, root)

            cache = EnrichmentCache(root)
            namespace = (
                "mock"
                if mock
                else "auto:dashscope-opencode"
                if model == "auto" or model.startswith("auto:")
                else f"gemini:{model}"
                if model.startswith("gemini-")
                else f"minimax:{model}"
                if model.startswith("MiniMax-")
                else f"openai:{model}"
            )
            if not mock:
                # Enrich shared URLs once. Prepare independent proposals concurrently,
                # then merge them in priority order with a single ledger writer.
                try:
                    cache.enrich(groups, scraper, jobs=4)
                except ValueError:
                    print("Some external pages failed; using the available evidence")
                runner = extractor()

                def prepare(group):
                    try:
                        return prepare_case(group, cache.evidence(group, available_only=True),
                                            root, namespace, lambda: runner)
                    except (ValueError, KeyError) as error:
                        print(f"Deferred {group.original.original_url}: {str(error).splitlines()[0]}", flush=True)
                        return None

                with ThreadPoolExecutor(max_workers=max(1, int(os.getenv("ATLAS_EXTRACT_WORKERS", "4")))) as pool:
                    prepared = [case for case in pool.map(prepare, groups) if case is not None]
                if prepared:
                    rows = merge_prepared_cases(prepared, rows, root)
            else:
                cache.enrich(groups, scraper)
                rows = extract_cases(groups, root, namespace, extractor, rows)
            for group in groups:
                attempts[group.original.post.tweet_id] = datetime.now(UTC).isoformat()
            write_json(attempts_path, attempts)
        if not groups:
            break
        completed = {g.original.post.tweet_id for g in groups}
        remaining = [g for g in remaining if g.original.post.tweet_id not in completed]
        print(f"Completed candidate batch {batch + 1}/{batches}: {len(groups)} extraction attempts", flush=True)
    candidates = [c.model_dump(mode="json") for c in rows if c.review_status != ReviewStatus.REJECTED]
    if os.getenv("ATLAS_BACKLOG_ONLY", "").lower() == "true":
        candidates = [row for row in candidates if row["world_id"] not in existing_ids]
    health_file = root / "state/demo_health.json"
    health = read_json(health_file) if health_file.exists() else {}
    candidates.sort(key=lambda c: health.get(c["world_id"], {}).get("checked_at",""))
    bounded = [r for r in candidates if r["live_demo_url"]][:int(os.getenv("ATLAS_VERIFY_LIMIT","12"))]
    if frontier_only and not mock:
        from .verify_demos import frontier_demo_queue
        bounded = frontier_demo_queue(candidates, health, signals)[:int(os.getenv("ATLAS_VERIFY_LIMIT","12"))]
    bounded.extend(r for r in candidates if not r["live_demo_url"])
    asyncio.run(verify(bounded, health_file, platform / "public/thumbnails",
                       channel=os.getenv("ATLAS_BROWSER_CHANNEL") or None, jobs=int(os.getenv("ATLAS_VERIFY_JOBS","3")),
                       max_age_hours=0 if frontier_only and not mock else 24))
    if not mock:
        build_covers(candidates, root, platform / "public/thumbnails")
        build_project_covers(candidates, root, platform / "public/thumbnails")
    auto = os.getenv("AUTO_APPROVE_TRUSTED", "").lower() == "true"
    policy = load_policy(root)
    if not mock and auto and policy:
        if frontier_only and minimum:
            from .frontier_review import evaluate_rows
            evaluate_rows(root, rows, policy, config)
        else:
            prepare_attribution(root, policy, rows)
    publish(root, platform, auto=auto)


if __name__ == "__main__":
    load_dotenv(PROJECT / ".env", override=False)
    if os.getenv("X_ADAPTER") in {"mock", "manual"}:
        raise SystemExit("Use src.cli with an isolated fixture root for mock or manual collection")
    root = PROJECT / "data"
    with httpx.Client(timeout=45) as http, run_lock(root):
        pipeline = Pipeline(os.environ.get("X_ADAPTER", "x_api_v2"), root, None, root / "exports/report.md", http)
        sync(pipeline, PROJECT / "platform")
