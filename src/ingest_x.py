from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

import httpx

from .links import external_url, post_id, repo_root, urls_in
from .models import RawPost, RawTweetRecord
from .storage import digest, read_json, write_json


FIELDS = {
    "post.fields": "conversation_id,created_at,entities,attachments,note_post",
    "expansions": "author_id,referenced_posts",
}
LEGACY_FIELDS = {
    "tweet.fields": "author_id,conversation_id,created_at,entities,attachments,referenced_tweets,note_tweet",
    "expansions": "author_id",
}
DEMO_LABEL = re.compile(r"(?:play(?:able)?(?: demo)?|live demo|try (?:it|the demo)|demo|试玩|演示)\W{0,12}$", re.I)


class BaseXAdapter(ABC):
    @abstractmethod
    def fetch_tweet_with_thread(self, tweet_id: str) -> RawTweetRecord:
        ...

    @abstractmethod
    def search_recent(self, query: str, max_results: int) -> list[str]:
        ...


    def incremental_ids(self, query: str, since_id: str | None, bootstrap_limit: int) -> list[str]:
        raise ValueError("This adapter does not implement incremental search")


class MockXAdapter(BaseXAdapter):
    def __init__(self, fixture_path: Path):
        records = (RawTweetRecord.model_validate(item) for item in read_json(fixture_path))
        self.records = {record.post.tweet_id: record for record in records}

    def fetch_tweet_with_thread(self, tweet_id: str) -> RawTweetRecord:
        if tweet_id not in self.records:
            raise ValueError(f"Fixture does not contain X post {tweet_id}")
        return self.records[tweet_id]

    def search_recent(self, query: str, max_results: int) -> list[str]:
        return list(self.records)[:max_results]


    def incremental_ids(self, query: str, since_id: str | None, bootstrap_limit: int) -> list[str]:
        ids = sorted(self.records, key=int, reverse=True)
        return [i for i in ids if int(i) > int(since_id)] if since_id else ids[:bootstrap_limit]


def api_tweet(item: dict, users: dict[str, str]) -> RawPost:
    note = item.get("note_post") or item.get("note_tweet") or {}
    urls = {}
    for entity_set in (item.get("entities") or {}, note.get("entities") or {}):
        for entity in entity_set.get("urls", []):
            destination = entity.get("unwound_url") or entity.get("expanded_url")
            if destination:
                urls[entity["url"]] = destination
    return RawPost(
        tweet_id=item["id"],
        author_handle=users[item["author_id"]],
        text=note.get("text") or item["text"],
        published_at=item.get("created_at"),
        conversation_id=item.get("conversation_id"),
        expanded_urls=urls,
        media_keys=(item.get("attachments") or {}).get("media_keys", []),
        referenced_post_ids=[row["id"] for row in
                             (item.get("referenced_posts") or item.get("referenced_tweets") or [])],
    )


class OfficialXApiAdapter(BaseXAdapter):
    def __init__(self, token: str, client: httpx.Client, *, archive: bool = False):
        self.client = client
        self.headers = {"Authorization": f"Bearer {token}"}
        self.archive = archive
        self.fields = FIELDS

    def get(self, endpoint: str, params: dict) -> dict:
        url = f"https://api.x.com/2/{endpoint}"
        response = self.client.get(url, params={**params, **self.fields}, headers=self.headers)
        if response.status_code == 400 and self.fields is FIELDS and any(
            key in response.text for key in ("post.fields", "note_post", "referenced_posts")
        ):
            self.fields = LEGACY_FIELDS
            response = self.client.get(url, params={**params, **self.fields}, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def search(self, endpoint: str, query: str, limit: int | None = None, since_id: str | None = None):
        next_token = None
        seen_tokens = set()
        count = 0
        while True:
            size = 100 if limit is None else min(100, max(10, limit - count))
            params = {"query": query, "max_results": size}
            if since_id:
                params["since_id"] = since_id
            if next_token:
                params["next_token"] = next_token
            result = self.get(f"tweets/search/{endpoint}", params)
            for item in result.get("data", []):
                yield item, result.get("includes", {}).get("users", [])
                count += 1
                if limit is not None and count >= limit:
                    return
            next_token = result.get("meta", {}).get("next_token")
            if not next_token:
                return
            if next_token in seen_tokens:
                raise ValueError("X API repeated a pagination token")
            seen_tokens.add(next_token)

    def incremental_page(self, query, since_id, limit, token=None, start_time=None):
        bootstrap = not since_id and not start_time
        params = {"query": query, "max_results": min(100, max(10, limit)) if bootstrap else 100}
        if since_id:
            params["since_id"] = since_id
        elif start_time:
            params["start_time"] = start_time
        if token:
            params["next_token"] = token
        result = self.get("tweets/search/recent", params)
        if result.get("errors"):
            raise ValueError("Incomplete X search response")
        ids = [item["id"] for item in result.get("data", [])]
        # The first run deliberately starts from the newest bounded window.
        if bootstrap:
            return ids[:limit], None
        return ids, result.get("meta", {}).get("next_token")

    def fetch_tweet_with_thread(self, tweet_id: str) -> RawTweetRecord:
        result = self.get(f"tweets/{tweet_id}", {})
        if not result.get("data"):
            raise ValueError(f"X lookup returned no data for {tweet_id}")
        item = result["data"]
        users = {user["id"]: user["username"] for user in result.get("includes", {}).get("users", [])}
        post = api_tweet(item, users)
        conversation = post.conversation_id or tweet_id
        query = f"conversation_id:{conversation} from:{post.author_handle} is:reply"
        endpoint = "all" if self.archive else "recent"
        cutoff = datetime.now(UTC) - timedelta(days=7)
        timestamp = post.published_at
        recent_only = not self.archive and (
            not timestamp or timestamp.replace(tzinfo=timestamp.tzinfo or UTC) < cutoff
        )
        thread = []
        for reply, _ in self.search(endpoint, query):
            if reply["id"] != tweet_id and reply["author_id"] == item["author_id"]:
                thread.append(api_tweet(reply, users))
        return RawTweetRecord(post=post, thread=thread, thread_status="recent_only" if recent_only else "searched")

    def search_recent(self, query: str, max_results: int) -> list[str]:
        return [item["id"] for item, _ in self.search("recent", query, max_results)]


    def incremental_ids(self, query: str, since_id: str | None, bootstrap_limit: int) -> list[str]:
        return [item["id"] for item, _ in self.search("recent", query, None if since_id else bootstrap_limit, since_id)]


class ThirdPartyXAdapter(BaseXAdapter):
    def __init__(self, base_url: str, key: str, client: httpx.Client):
        if urlsplit(base_url).scheme != "https":
            raise ValueError("X_THIRD_PARTY_BASE_URL must be HTTPS")
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.headers = {"Authorization": f"Bearer {key}"}

    def get(self, path: str, params: dict | None = None):
        response = self.client.get(f"{self.base_url}/{path}", params=params, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def fetch_tweet_with_thread(self, tweet_id: str) -> RawTweetRecord:
        return RawTweetRecord.model_validate(self.get(f"tweets/{tweet_id}"))

    def search_recent(self, query: str, max_results: int) -> list[str]:
        payload = self.get("search/recent", {"query": query, "max_results": max_results})
        ids = [str(item) for item in payload["tweet_ids"][:max_results]]
        if any(not re.fullmatch(r"[0-9]+", item) for item in ids):
            raise ValueError("Third-party endpoint returned an invalid tweet ID")
        return ids


    def incremental_ids(self, query: str, since_id: str | None, bootstrap_limit: int) -> list[str]:
        if not since_id:
            return self.search_recent(query, bootstrap_limit)
        params = {"query": query, "max_results": 100, "since_id": since_id}
        ids = []
        tokens = set()
        while True:
            page = self.get("search/recent", params)
            batch = [str(i) for i in page["tweet_ids"]]
            if any(not re.fullmatch(r"[0-9]+", i) for i in batch):
                raise ValueError("Invalid tweet ID")
            ids.extend(i for i in batch if int(i) > int(since_id))
            token = page.get("next_token")
            if not token:
                if "next_token" not in page and len(batch) >= 100:
                    raise ValueError("Third-party adapter must declare pagination for full pages")
                return ids
            if token in tokens:
                raise ValueError("Repeated third-party pagination token")
            tokens.add(token)
            params["next_token"] = token


def expand_short(url: str, client: httpx.Client, cache: Path) -> str:
    path = cache / f"{digest(url)}.json"
    if path.exists():
        return read_json(path)
    # Ask t.co for the destination and only follow redirects on t.co itself.
    for _ in range(5):
        if urlsplit(url).hostname != "t.co":
            break
        response = client.head(url, follow_redirects=False)
        if response.status_code in {403, 405}:
            with client.stream("GET", url, follow_redirects=False) as fallback:
                target = fallback.headers.get("location") if fallback.is_redirect else None
        else:
            target = response.headers.get("location") if response.is_redirect else None
        if not target:
            return url
        url = urljoin(url, target)
    if urlsplit(url).hostname != "t.co":
        write_json(path, url)
    return url


def collect_links(record: RawTweetRecord, client: httpx.Client | None, redirects: Path) -> RawTweetRecord:
    posts = [record.post, *record.thread]
    external = list(filter(None, map(external_url, record.external_urls + record.demo_urls)))
    demo = list(filter(None, map(external_url, record.demo_urls)))
    for post in posts:
        found = urls_in(post.text)
        found.extend((url, -1) for url in post.expanded_urls if url not in {item[0] for item in found})
        for url, position in found:
            expanded = post.expanded_urls.get(url, url)
            if client is not None:
                try:
                    short_host = urlsplit(expanded).hostname
                except ValueError:
                    continue
                if short_host == "t.co":
                    expanded = expand_short(expanded, client, redirects)
            clean = external_url(expanded)
            if clean:
                external.append(clean)
                if position >= 0 and DEMO_LABEL.search(post.text[max(0, position - 80):position]) and not repo_root(clean):
                    demo.append(clean)
    return record.model_copy(update={
        "external_urls": list(dict.fromkeys(external)),
        "demo_urls": list(dict.fromkeys(demo)),
    })


def discovery_queries(seeds: dict) -> dict[str, str]:
    queries = {f"query:{q}": q for q in seeds.get("search_queries", [])}
    for account in seeds.get("watch_accounts", []):
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", account):
            raise ValueError(f"Invalid watch account {account}")
        queries[f"account:{account.lower()}"] = f"from:{account} (has:videos OR has:links) -is:retweet -is:reply"
    return queries


def ingest(adapter: BaseXAdapter, seeds: dict, root: Path, mode: str, limit: int,
           client: httpx.Client | None, *, refresh: bool = False) -> list[RawTweetRecord]:
    raw = root / "raw" / "x"
    if mode == "incremental":
        state_path = root / "state" / "sync_state.json"
        state = read_json(state_path) if state_path.exists() else {}
        records = {}
        for key, query in discovery_queries(seeds).items():
            entry = state.setdefault(key, {})
            if not entry.get("search_complete") and isinstance(adapter, OfficialXApiAdapter):
                if entry.get("last_synced_at") and not entry.get("last_tweet_id") and not entry.get("start_time"):
                    # Cover recent-search indexing latency after a previously empty result.
                    start = max(datetime.fromisoformat(entry["last_synced_at"]) - timedelta(minutes=1),
                                datetime.now(UTC) - timedelta(days=7) + timedelta(minutes=1))
                    entry["start_time"] = start.isoformat(timespec="seconds").replace("+00:00", "Z")
                while True:
                    ids, token = adapter.incremental_page(query, entry.get("last_tweet_id"), limit,
                                                          entry.get("next_token"), entry.get("start_time"))
                    if any(not re.fullmatch(r"[0-9]+", i) for i in ids):
                        raise ValueError("Search returned invalid tweet ID")
                    if token and token in entry.get("page_tokens", []):
                        raise ValueError("Repeated X pagination token")
                    entry.setdefault("pending_ids", []).extend(ids)
                    if token:
                        entry.setdefault("page_tokens", []).append(token)
                    entry.update(next_token=token, search_complete=not token)
                    write_json(state_path, state)
                    if not token:
                        break
            elif "pending_ids" not in entry:
                ids = adapter.incremental_ids(query, entry.get("last_tweet_id"), limit)
                if any(not re.fullmatch(r"[0-9]+", i) for i in ids):
                    raise ValueError("Search returned invalid tweet ID")
                entry.update(pending_ids=list(dict.fromkeys(ids)), search_complete=True)
                write_json(state_path, state)
            ids = entry["pending_ids"]
            for record in cache_posts(adapter, ids, raw, client, refresh=False):
                records[record.post.tweet_id] = record
            high = max([int(entry.get("last_tweet_id") or 0), *map(int, ids)])
            entry.update(last_tweet_id=str(high) if high else None, last_synced_at=datetime.now(UTC).isoformat())
            for field in ("pending_ids", "page_tokens", "next_token", "search_complete", "start_time"):
                entry.pop(field, None)
            write_json(state_path, state)
        return list(records.values())
    if mode == "seed":
        ids = [post_id(url) for url in seeds["seed_urls"]]
    else:
        ids = []
        for query in discovery_queries(seeds).values():
            path = raw / "search" / f"{digest(json.dumps([query, limit]))}.json"
            if refresh or not path.exists():
                write_json(path, adapter.search_recent(query, limit))
            ids.extend(read_json(path))
    return cache_posts(adapter, ids, raw, client, refresh=refresh)


def cache_posts(adapter: BaseXAdapter, ids: list[str], raw: Path, client: httpx.Client | None,
                *, refresh: bool) -> list[RawTweetRecord]:
    output = []
    failures = []
    for identifier in dict.fromkeys(ids):
        path = raw / f"{identifier}.json"
        try:
            if refresh or not path.exists():
                saved = raw / "responses" / f"{identifier}.json"
                if refresh or not saved.exists():
                    record = adapter.fetch_tweet_with_thread(identifier)
                    if record.post.tweet_id != identifier:
                        raise ValueError(f"Adapter returned the wrong post for {identifier}")
                    write_json(saved, record.model_dump(mode="json"))
                record = RawTweetRecord.model_validate(read_json(saved))
                record = collect_links(record, client, raw / "redirects")
                write_json(path, record.model_dump(mode="json"))
            output.append(RawTweetRecord.model_validate(read_json(path)))
        except (ValueError, httpx.HTTPError) as error:
            failures.append(f"{identifier}: {error}")
    if failures:
        raise ValueError(f"Cached {len(output)} post(s). Ingest failures:\n" + "\n".join(failures))
    return output


def import_records(path: Path, root: Path, client: httpx.Client | None) -> list[RawTweetRecord]:
    content = path.read_text(encoding="utf-8")
    payload = json.loads(content) if content.lstrip().startswith("[") else [
        json.loads(line) for line in content.split("\n") if line.strip()
    ]
    records = [RawTweetRecord.model_validate(item) for item in payload]
    raw = root / "raw" / "x"
    for record in records:
        normalized = collect_links(record, client, raw / "redirects")
        write_json(raw / f"{record.post.tweet_id}.json", normalized.model_dump(mode="json"))
    return records
