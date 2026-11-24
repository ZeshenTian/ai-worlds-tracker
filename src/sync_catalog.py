"""Discover once per query, then process works missing from the durable ledger."""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
import httpx
import yaml

from .cli import FIXTURES, PROJECT, Mode, Pipeline
from .dedup import deduplicate
from .enrich_firecrawl import EnrichmentCache, Firecrawl, FixtureScraper
from .extract_structured import AnnotatedExtractor, OpenAIExtractor, extract_cases
from .ingest_x import MockXAdapter, OfficialXApiAdapter, ThirdPartyXAdapter, cache_posts, ingest
from .links import identity_url, post_id
from .models import RawTweetRecord, ReviewStatus
from .publish_catalog import publish
from .storage import run_lock
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
    else:
        raise ValueError("Choose an X discovery adapter")
    root = pipeline.root
    rows = pipeline.cases(missing_ok=True)
    known_sources = {url for c in rows for url in [c.original_post_url, *c.related_post_urls]}
    client = None if mock else pipeline.client
    raw = root / "raw/x"
    new_seeds = [post_id(url) for url in config.get("seed_urls", []) if url not in known_sources]
    cache_posts(adapter, new_seeds, raw, client, refresh=False)
    ingest(adapter, config, root, Mode.INCREMENTAL, 30, client)
    records = [RawTweetRecord.model_validate_json(path.read_bytes()) for path in raw.glob("*.json")]
    known_works = {identity_url(url) for c in rows for url in [c.repo_url, c.live_demo_url] if url}
    groups = [g for g in deduplicate(records) if g.original.original_url not in known_sources and
              not any(identity_url(url) in known_works for url in g.repo_urls + g.demo_urls)]
    if groups:
        if mock:
            scraper = FixtureScraper(FIXTURES / "pages.json")
        else:
            scraper = Firecrawl(os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_TOKEN", ""),
                                pipeline.client, os.getenv("GITHUB_TOKEN"))
        EnrichmentCache(root).enrich(groups, scraper)
        model = os.getenv("EXTRACTION_MODEL", "gpt-5-mini")

        def extractor():
            return (AnnotatedExtractor(FIXTURES / "extractions.json") if mock else
                    OpenAIExtractor(pipeline.required_env("OPENAI_API_KEY"), model))

        rows = extract_cases(groups, root, "mock" if mock else f"openai:{model}", extractor, rows)
    candidates = [c.model_dump(mode="json") for c in rows if c.review_status != ReviewStatus.REJECTED]
    asyncio.run(verify(candidates, root / "state/demo_health.json", platform / "public/thumbnails"))
    publish(root, platform, auto=os.getenv("AUTO_APPROVE_TRUSTED", "").lower() == "true")


if __name__ == "__main__":
    load_dotenv(PROJECT / ".env", override=False)
    if os.getenv("X_ADAPTER") in {"mock", "manual"}:
        raise SystemExit("Use src.cli with an isolated fixture root for mock or manual collection")
    root = PROJECT / "data"
    with httpx.Client(timeout=45) as http, run_lock(root):
        pipeline = Pipeline(os.environ.get("X_ADAPTER", "x_api_v2"), root, None, root / "exports/report.md", http)
        sync(pipeline, PROJECT / "platform")
