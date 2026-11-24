"""Discover once per query, then process works missing from the durable ledger."""
import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path

from dotenv import load_dotenv
import httpx
import yaml

from .catalog_posts import resolve_seeds
from .qualify_candidates import qualify
from .x_covers import build as build_covers
from .primary_covers import build as build_project_covers
from .cli import FIXTURES, PROJECT, Mode, Pipeline
from .dedup import deduplicate
from .enrich_firecrawl import EnrichmentCache, Firecrawl, FixtureScraper
from .extract_structured import AnnotatedExtractor, OpenAIExtractor, extract_cases
from .ingest_x import MockXAdapter, OfficialXApiAdapter, ThirdPartyXAdapter, cache_posts, ingest
from .links import identity_url, post_id
from .models import RawTweetRecord, ReviewStatus
from .publish_catalog import publish
from .storage import read_json, run_lock, write_json
from .verify_demos import verify


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
    records = [RawTweetRecord.model_validate_json(path.read_bytes()) for path in raw.glob("*.json")]
    known_works = {identity_url(url) for c in rows for url in [c.repo_url, c.live_demo_url] if url}
    groups = [g for g in deduplicate(records) if g.original.original_url not in known_sources and
              not any(identity_url(url) in known_works for url in g.repo_urls + g.demo_urls)]
    attempts_path = root / "state/extraction_attempts.json"
    attempts = read_json(attempts_path) if attempts_path.exists() else {}
    groups.sort(key=lambda g: (attempts.get(g.original.post.tweet_id, ""), -int(g.original.post.tweet_id)))
    if not mock:
        groups = qualify(groups, root, model=os.getenv("GATE_MODEL","gpt-4.1-mini"),
                         limit=int(os.getenv("ATLAS_GATE_LIMIT", "80")))
        groups.sort(key=lambda g: (attempts.get(g.original.post.tweet_id, ""), -int(g.original.post.tweet_id)))
        groups = groups[:int(os.getenv("ATLAS_EXTRACT_LIMIT", "12"))]
    if groups:
        if mock:
            scraper = FixtureScraper(FIXTURES / "pages.json")
        else:
            scraper = Firecrawl(os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_TOKEN", ""),
                                pipeline.client, os.getenv("GITHUB_TOKEN"))
        model = os.getenv("EXTRACTION_MODEL", "gpt-5-mini")

        def extractor():
            return (AnnotatedExtractor(FIXTURES / "extractions.json") if mock else
                    OpenAIExtractor(pipeline.required_env("OPENAI_API_KEY"), model, root))

        for group in groups:
            cache = EnrichmentCache(root)
            try:
                cache.enrich([group], scraper)
            except ValueError:
                if mock:
                    raise
                print(f"Using the available sources for {group.original.original_url}; some external pages failed")
            try:
                pages = cache.evidence(group, available_only=not mock)
                rows = extract_cases([group], root, "mock" if mock else f"openai:{model}", extractor, rows, pages)
            except ValueError as error:
                if mock:
                    raise
                print(f"Deferred {group.original.original_url}: {str(error).splitlines()[0]}")
            attempts[group.original.post.tweet_id] = datetime.now(UTC).isoformat()
        write_json(attempts_path, attempts)
    candidates = [c.model_dump(mode="json") for c in rows if c.review_status != ReviewStatus.REJECTED]
    health_file = root / "state/demo_health.json"
    health = read_json(health_file) if health_file.exists() else {}
    candidates.sort(key=lambda c: health.get(c["world_id"], {}).get("checked_at",""))
    bounded = [r for r in candidates if r["live_demo_url"]][:int(os.getenv("ATLAS_VERIFY_LIMIT","12"))]
    bounded.extend(r for r in candidates if not r["live_demo_url"])
    asyncio.run(verify(bounded, health_file, platform / "public/thumbnails",
                       channel=os.getenv("ATLAS_BROWSER_CHANNEL") or None))
    if not mock:
        build_covers(candidates, root, platform / "public/thumbnails")
        build_project_covers(candidates, root, platform / "public/thumbnails")
    publish(root, platform, auto=os.getenv("AUTO_APPROVE_TRUSTED", "").lower() == "true")


if __name__ == "__main__":
    load_dotenv(PROJECT / ".env", override=False)
    if os.getenv("X_ADAPTER") in {"mock", "manual"}:
        raise SystemExit("Use src.cli with an isolated fixture root for mock or manual collection")
    root = PROJECT / "data"
    with httpx.Client(timeout=45) as http, run_lock(root):
        pipeline = Pipeline(os.environ.get("X_ADAPTER", "x_api_v2"), root, None, root / "exports/report.md", http)
        sync(pipeline, PROJECT / "platform")
