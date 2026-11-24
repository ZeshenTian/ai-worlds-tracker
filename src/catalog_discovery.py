"""Discover original post URLs in public catalogs using Firecrawl."""
import argparse
import html
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import yaml

from .enrich_firecrawl import Firecrawl
from .links import post_id
from .storage import digest, read_json, run_lock, write_json

POST = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/"
    r"([A-Za-z0-9_]{1,15})/status/([0-9]+)(?![A-Za-z0-9_])", re.I
)


def catalog_posts(markdown: str) -> dict[str, str]:
    """Deduplicate status IDs across URL aliases and ignore navigation or profile links."""
    return {number: f"https://x.com/{user}/status/{number}"
            for user, number in POST.findall(html.unescape(markdown).replace(r"\/", "/"))}


def official_thread_queries(threads: list[dict]) -> list[str]:
    """Use X API v2 operators; the conversation includes nested replies."""
    queries = []
    for thread in threads:
        number = post_id(thread["url"])
        queries.extend((f"conversation_id:{number} -is:retweet", f"quotes_of_tweet_id:{number} -is:retweet"))
    return list(dict.fromkeys(queries))


def discover(config: dict, data_dir: Path, scraper: Firecrawl, max_age_hours: float = 24) -> dict:
    state_path = data_dir / "state/catalog_seeds.json"
    cache = data_dir / "raw/catalogs"
    now = datetime.now(UTC)
    with run_lock(cache):
        old = read_json(state_path) if state_path.exists() else {}
        seeds = {post_id(url): url for url in old.get("seed_urls", [])}
        initial_ids = set(seeds)
        previous = {s["url"]: s for s in old.get("catalogs", [])}
        sources = []
        errors = []
        for entry in config["catalogs"]:
            url = entry["url"]
            path = cache / (digest(url) + ".json")
            try:
                snapshot = read_json(path) if path.exists() else {}
                last = previous.get(url)
                if not snapshot and last and now - datetime.fromisoformat(last["checked_at"]) < timedelta(hours=max_age_hours):
                    # A CI checkout may retain the state file without the local raw cache.
                    sources.append({**last, "added_count": 0})
                    continue
                if not snapshot or now - datetime.fromisoformat(snapshot["checked_at"]) >= timedelta(hours=max_age_hours):
                    result = scraper.scrape(url)
                    if result.fetch_method != "firecrawl" or not result.markdown:
                        raise ValueError(f"Firecrawl returned {result.status}")
                    urls = catalog_posts(result.markdown)
                    if not urls:
                        raise ValueError("Firecrawl returned a directory without any X post URLs")
                    snapshot = {"checked_at": datetime.now(UTC).isoformat(), "post_urls": list(urls.values()),
                                "method": result.fetch_method, "status_code": result.status_code}
                    write_json(path, snapshot)
                before = len(seeds)
                for link in snapshot["post_urls"]:
                    seeds.setdefault(post_id(link), link)
                sources.append({**entry, "checked_at": snapshot["checked_at"], "method": snapshot["method"],
                                "post_count": len(snapshot["post_urls"]), "added_count": len(seeds) - before})
            except (ValueError, OSError, httpx.HTTPError) as error:
                errors.append({"url": url, "error": str(error)})
                if url in previous:
                    sources.append(previous[url])
        verified_candidates = config.get("verified_candidates")
        if verified_candidates and Path(verified_candidates).is_file():
            for record in read_json(Path(verified_candidates)):
                if record.get("source_kind") == "x_post" and record.get("evidence_quotes"):
                    link = record["original_post_url"]
                    seeds.setdefault(post_id(link), link)
        added = [seeds[number] for number in sorted(set(seeds) - initial_ids, key=int, reverse=True)]
        final = {"new_seed_urls": added, "seed_urls": [seeds[key] for key in sorted(seeds, key=int, reverse=True)], "catalogs": sources,
                 "official_thread_queries": official_thread_queries(config.get("official_threads", [])),
                 "errors": errors}
        write_json(state_path, final)
        return final


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/catalogs.yaml"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--max-age-hours", type=float, default=24)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text())
    key = os.environ.get("FIRECRAWL_API_KEY") or os.environ.get("FIRECRAWL_TOKEN")
    if not key:
        parser.error("FIRECRAWL_API_KEY or FIRECRAWL_TOKEN is required")
    with httpx.Client(timeout=70) as client:
        result = discover(config, args.data_dir, Firecrawl(key, client), args.max_age_hours)
    print(f"{len(result['seed_urls'])} unique X post URLs, {len(result['errors'])} source errors")
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
