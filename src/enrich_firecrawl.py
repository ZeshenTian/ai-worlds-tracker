from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
import os
import time
from urllib.parse import quote, urlsplit

import httpx

from .links import external_url, repo_root
from .models import CaseGroup, EnrichedLinkContent
from .storage import digest, read_json, write_json


def retry_rate_limit(call: Callable[[], httpx.Response]) -> httpx.Response:
    for attempt in range(4):
        try:
            response = call()
        except httpx.TransportError:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
            continue
        if response.status_code != 429 or attempt == 3:
            return response
        hint = response.headers.get("retry-after", "")
        delay = min(30, int(hint)) if hint.isdigit() else 2**attempt
        time.sleep(delay)
    raise RuntimeError("unreachable retry state")


class DocumentText(HTMLParser):
    """Read the publisher's visible document text without executing page scripts."""

    def __init__(self):
        super().__init__()
        self.ignored = 0
        self.lines = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignored:
            self.ignored -= 1

    def handle_data(self, data):
        if not self.ignored and data.strip():
            self.lines.append(data.strip())


class Firecrawl:
    def __init__(self, key: str, client: httpx.Client, token: str | None = None, *,
                 public_fallback: bool = False):
        key = key or os.environ.get("FIRECRAWL_TOKEN", "")
        self.client = client
        self.public_fallback = public_fallback
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}
        self.github_headers = {"Accept": "application/vnd.github+json"}
        if token:
            self.github_headers["Authorization"] = f"Bearer {token}"

    def scrape(self, url: str) -> EnrichedLinkContent:
        if not external_url(url):
            raise ValueError(f"Firecrawl cannot scrape this URL: {url}")
        response = retry_rate_limit(lambda: self.client.post(
            "https://api.firecrawl.dev/v2/scrape", headers=self.headers,
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True,
                  "timeout": 30000, "blockAds": True},
        ))
        if self.public_fallback and response.status_code in {401, 403}:
            return self.public_document(url, response.status_code)
        if response.status_code in {404, 410}:
            return EnrichedLinkContent(url=url, status="not_found", status_code=response.status_code)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise ValueError(f"Firecrawl did not return content for {url}")
        data = payload["data"]
        metadata = data.get("metadata") or {}
        destination = metadata.get("url") or metadata.get("sourceURL") or url
        if not all(external_url(link) for link in (destination, metadata.get("sourceURL") or url)):
            return EnrichedLinkContent(url=url, status="excluded_redirect")
        status = metadata.get("statusCode")
        if status in {404, 410}:
            return EnrichedLinkContent(url=url, status="not_found", status_code=status)
        if status is not None and status >= 400:
            raise ValueError(f"Target page for {url} returned HTTP {status}")
        return EnrichedLinkContent(url=url, final_url=destination, markdown=data.get("markdown") or "",
                                   status_code=status, fetch_method="firecrawl",
                                   firecrawl_status_code=response.status_code)

    def public_document(self, url: str, firecrawl_status: int) -> EnrichedLinkContent:
        """Fetch only provider-owned public document endpoints, without credentials."""
        parts = urlsplit(url)
        path = parts.path.strip("/")
        if parts.hostname == "github.com" and repo_root(url):
            owner, repo, *rest = path.split("/")
            if not rest:
                target = f"https://api.github.com/repos/{owner}/{repo}"
                method = "github_api"
            elif len(rest) >= 3 and rest[0] == "blob":
                target = "https://raw.githubusercontent.com/" + "/".join([owner, repo, *rest[1:]])
                method = "github_raw"
            else:
                raise ValueError(f"Unsupported GitHub document URL: {url}")
        elif parts.hostname == "developers.openai.com" and path.startswith(("showcase/", "blog/")):
            target = f"https://developers.openai.com/{path}"
            method = "publisher_html"
        else:
            raise ValueError(f"Firecrawl returned {firecrawl_status}; no public document fallback for {url}")
        response = retry_rate_limit(lambda: self.client.get(target, follow_redirects=False))
        if response.status_code in {404, 410}:
            return EnrichedLinkContent(url=url, final_url=target, status="not_found",
                                       status_code=response.status_code, fetch_method=method,
                                       firecrawl_status_code=firecrawl_status)
        response.raise_for_status()
        if method == "github_api":
            repo_data = response.json()
            if repo_data.get("private") is not False:
                raise ValueError(f"Expected a public repository: {url}")
            content = repo_data.get("description") or repo_data["full_name"]
        elif method == "publisher_html":
            parser = DocumentText()
            parser.feed(response.text)
            content = "\n".join(parser.lines)
        else:
            content = response.text
            if "text/html" in response.headers.get("content-type", ""):
                raise ValueError(f"Expected a text document at {target}")
        return EnrichedLinkContent(url=url, final_url=target, markdown=content, status_code=200,
                                   fetch_method=method, firecrawl_status_code=firecrawl_status)

    def github_catalog(self, url: str) -> dict:
        if not repo_root(url) or urlsplit(url).path.strip("/").count("/") != 1:
            raise ValueError(f"Expected a GitHub repository root: {url}")
        api_url = f"https://api.github.com/repos{urlsplit(url).path}"
        response = retry_rate_limit(lambda: self.client.get(api_url, headers=self.github_headers))
        if response.status_code == 404:
            return {"exists": False, "files": []}
        response.raise_for_status()
        details = response.json()
        if details.get("private") is not False:
            raise ValueError(f"Expected a public repository: {url}")
        branch = quote(details["default_branch"], safe="")
        tree_url = f"{api_url}/git/trees/{branch}?recursive=1"
        listing = retry_rate_limit(lambda: self.client.get(tree_url, headers=self.github_headers))
        if listing.status_code == 409:
            return {"exists": True, "files": [], "tree_url": tree_url, "empty": True}
        listing.raise_for_status()
        tree = listing.json()
        files = []
        root = details["html_url"]
        workflow_names = {"claude.md", "skill.md", "agents.md", "prompts.md"}
        design_docs = {"architecture.md", "experiment.md", "postmortem.md", "workflow.md"}
        for entry in tree["tree"]:
            path = entry["path"]
            name = path.rsplit("/", 1)[-1].casefold()
            if entry["type"] != "blob" or set(path.split("/")) & {"node_modules", "vendor", ".venv"}:
                continue
            if "/" not in path and (name == "readme" or name.startswith("readme.")):
                kind = "readme"
            elif name in workflow_names or (path.startswith("docs/") and name in design_docs):
                kind = "workflow"
            elif path.startswith(".github/workflows/") and name.endswith((".yaml", ".yml")):
                kind = "automation"
            else:
                continue
            files.append({"url": f"{root}/blob/{branch}/{quote(path)}", "kind": kind,
                          "path": path, "blob_sha": entry["sha"]})
        return {"exists": True, "files": files, "owner": details["owner"]["login"],
                "license": (details.get("license") or {}).get("spdx_id"), "tree_url": tree_url,
                "tree_sha": tree.get("sha"), "truncated": tree.get("truncated", False),
                "default_branch": details["default_branch"]}

class FixtureScraper:
    def __init__(self, path: Path):
        values = read_json(path)
        self.pages = values["pages"]
        self.catalogs = values["repositories"]

    def scrape(self, url: str) -> EnrichedLinkContent:
        return EnrichedLinkContent(url=url, **self.pages[url])

    def github_catalog(self, url: str) -> dict:
        return self.catalogs[url]


class EnrichmentCache:
    def __init__(self, root: Path):
        self.root = root / "raw" / "firecrawl"

    def page_path(self, url: str) -> Path:
        return self.root / f"{digest(url)}.json"

    def catalog_path(self, url: str) -> Path:
        return self.root / "repositories" / f"{digest(url)}.json"

    def urls_for(self, group: CaseGroup) -> list[tuple[str, str]]:
        result = {}
        for url in group.external_urls:
            clean = external_url(url)
            if clean:
                repository = repo_root(clean)
                if repository:
                    result[repository] = "repository"
                    path = urlsplit(clean).path.lower()
                    if "/blob/" in path or "/releases/" in path:
                        result.setdefault(clean, "page")
                else:
                    result[clean] = "page"
        for url in list(result):
            path = self.catalog_path(url)
            if result[url] == "repository" and path.exists():
                for item in read_json(path)["files"]:
                    clean = external_url(item["url"])
                    if clean:
                        result[clean] = item["kind"]
        return list(result.items())

    def enrich(self, groups: list[CaseGroup], scraper: Firecrawl | FixtureScraper) -> None:
        urls = {url: kind for group in groups for url, kind in self.urls_for(group)}
        failures = []
        for url, kind in urls.items():
            if kind != "repository" or self.catalog_path(url).exists():
                continue
            try:
                write_json(self.catalog_path(url), scraper.github_catalog(url))
            except (ValueError, httpx.HTTPError, KeyError) as error:
                failures.append(f"{url} [catalog]: {error}")
        urls = {url: kind for group in groups for url, kind in self.urls_for(group)}
        for url, kind in urls.items():
            path = self.page_path(url)
            if path.exists():
                continue
            try:
                catalog_path = self.catalog_path(url)
                catalog = read_json(catalog_path) if kind == "repository" and catalog_path.exists() else {}
                if catalog.get("exists") is False:
                    result = EnrichedLinkContent(url=url, status="not_found")
                else:
                    result = scraper.scrape(url)
                result.kind = kind
                result.repository_owner = catalog.get("owner")
                result.repository_license = catalog.get("license")
                write_json(path, result.model_dump(mode="json"))
            except (ValueError, httpx.HTTPError, KeyError) as error:
                failures.append(f"{url}: {error}")
        if failures:
            raise ValueError("Enrichment failures:\n" + "\n".join(failures))

    def evidence(self, group: CaseGroup) -> list[EnrichedLinkContent]:
        pages = []
        for url, _ in self.urls_for(group):
            path = self.page_path(url)
            if not path.exists():
                raise ValueError(f"No enrichment cache for {url}. Run enrich first.")
            pages.append(EnrichedLinkContent.model_validate(read_json(path)))
        return pages
