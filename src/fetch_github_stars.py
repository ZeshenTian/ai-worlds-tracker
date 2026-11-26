"""Fetch missing repository counts. Use --refresh for a scheduled update."""
import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import httpx
from .storage import read_json, write_json


def fetch(refresh=False):
    path = Path("data/state/github_stars.json")
    cache = read_json(path) if path.exists() else {}
    repos = set()
    for w in read_json(Path("data/exports/ai_worlds.json")):
        m = re.match(r"https://github\.com/([\w.-]+/[\w.-]+)(?:[/?#]|$)", w["repo_url"] or "", re.I)
        if w["model_era"] == "frontier" and m:
            repos.add(m[1].removesuffix(".git").lower())
    token = os.getenv("GITHUB_TOKEN")
    with httpx.Client(headers={"Authorization": f"Bearer {token}"} if token else {}, timeout=10, follow_redirects=True) as client:
        for repo in sorted(repos):
            if repo in cache and not refresh:
                continue
            try:
                response = client.get("https://api.github.com/repos/" + repo)
                if response.status_code in (403, 429):
                    break
                if response.status_code == 404:
                    stars = None
                else:
                    response.raise_for_status()
                    stars = response.json()["stargazers_count"]
                cache[repo] = dict(stars=stars, fetched_at=datetime.now(UTC).isoformat())
            except (httpx.HTTPError, ValueError, KeyError):
                continue
    write_json(path, cache)
    print(f"{len(repos)} repositories, {len(repos.intersection(cache))} cached")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    fetch(parser.parse_args().refresh)
