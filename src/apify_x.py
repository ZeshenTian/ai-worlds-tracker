"""Budgeted X research against Apify's public pay-per-event tweet actor."""

import argparse
import calendar
from copy import copy
import json
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
from itertools import zip_longest
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml
from dotenv import dotenv_values

from .ingest_x import BaseXAdapter, collect_links
from .links import external_url
from .models import RawPost, RawTweetRecord
from .x_media import actor_attachments, attachment_keys
from .storage import digest, read_json, run_lock, write_json

SMART_ACTOR = "smart_albatross~x-tweet-scraper"
KAITO = "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest"
SAMURAI = "apisamurai~x-twitter-scraper"
ACTOR = "scrape.badger~twitter-tweets-scraper"
BASE = "https://api.apify.com/v2"
PRICES = {
    KAITO: Decimal("0.00025"),
    SAMURAI: Decimal("0.00025"),
    ACTOR: Decimal("0.00015"),
    SMART_ACTOR: Decimal("0.0002"),
    "apidojo~tweet-scraper": Decimal("0.0004"),
    "winterlock~x-tweet-scraper": Decimal("0.00034"),
}
LIMIT = Decimal("1.50")
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class RunLedger:
    def __init__(self, root, client, budget=LIMIT, actor=ACTOR, *, daily=False, frontier=False, recovery=False, auto_failover=True):
        self.auto_failover = auto_failover
        self.recovery = recovery
        self.daily = daily
        self.deadline = None
        self.client = client
        self.root = root
        self.actor = actor
        self.budget = Decimal(str(budget))
        self.frontier = frontier
        ceiling = Decimal("2.50") if recovery else Decimal("10.00") if frontier else LIMIT
        if not 0 < self.budget <= ceiling:
            raise ValueError(f"Budget must be greater than zero and at most US${ceiling}")
        self.path = root / "state/apify_x" / ("phase2_ledger.json" if recovery else "frontier_ledger.json" if frontier else "ledger.json")

    def get(self, url, **options):
        # Polling and dataset reads are safe to repeat after a transport interruption.
        for attempt in range(4):
            try:
                response = self.client.get(url, **options)
                if response.status_code not in {429, 502, 503, 504} or attempt == 3:
                    return response
                hint = response.headers.get("retry-after", "")
                delay = max(1, int(hint)) if hint.isdigit() else 2**attempt
            except httpx.TransportError:
                if attempt == 3:
                    raise
                delay = 2**attempt
            if self.deadline and time.monotonic() + delay >= self.deadline:
                raise TimeoutError("Pending Apify request saved for next sync")
            time.sleep(delay)
        raise RuntimeError("Unexpected retry state")

    def physical_item_count(self, dataset, run, cleaned_rows):
        """Read the terminal dataset's total, including rows omitted by clean=true."""
        if not self.frontier or run["status"] != "SUCCEEDED" or not dataset:
            return None
        try:
            # Apify documents up to five seconds of lag in dataset counters.
            # Use its response clock so local clock skew cannot release a reservation.
            ready_at = datetime.fromisoformat(run["finishedAt"]) + timedelta(seconds=5)
            for attempt in range(2):
                response = self.get(f"{BASE}/datasets/{dataset}")
                response.raise_for_status()
                data = response.json()["data"]
                now = parsedate_to_datetime(response.headers["date"])
                delay = (ready_at - now).total_seconds()
                if delay <= 0:
                    count = data["itemCount"]
                    if data["id"] == dataset and type(count) is int and count >= cleaned_rows:
                        return count
                    break
                if attempt or delay > 6:
                    break
                time.sleep(delay + 1)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, TimeoutError):
            pass
        return None

    def fetch(self, label, payload):
        wait_until = self.deadline or time.monotonic() + 480
        while True:
            try:
                return self._fetch_once(label, payload)
            except ValueError as exc:
                # A concurrent-run refusal creates no billable run. Wait for an
                # available account slot before attempting another reservation.
                match = re.search(r"limit of (\d+) concurrent Actor runs", str(exc))
                if not match:
                    raise
                capacity = int(match[1])
                while True:
                    if time.monotonic() + 20 > wait_until:
                        raise TimeoutError(
                            "Account at capacity; the pending query will resume later"
                        ) from exc
                    time.sleep(20)
                    active = 0
                    for status in ("RUNNING", "READY"):
                        response = self.get(
                            f"{BASE}/actor-runs",
                            params={"status": status, "limit": capacity},
                        )
                        response.raise_for_status()
                        active += sum(
                            row["status"] == status
                            for row in response.json()["data"]["items"]
                        )
                    if active < capacity:
                        break

    def _fetch_once(self, label, payload):
        # Serialize admission, then persist the remote run ID before polling. An
        # ambiguous create never starts another chargeable run automatically.
        limit = int(
            payload.get("maxItems")
            or payload.get("max_results")
            or len(payload.get("tweets", []))
        )
        if limit < 1:
            raise ValueError("Positive row cap required")
        request_key = digest(json.dumps([self.actor, label, payload], sort_keys=True))
        with run_lock(self.path.parent):
            book = read_json(self.path) if self.path.exists() else {}
            entry = book.get(request_key)
            if (
                entry
                and entry.get("status") == "REFUSED"
                and "concurrent Actor runs" in entry.get("reason", "")
                and time.time() - entry.get("refused_at", 0) >= 20
            ):
                entry = None
            if entry is None:
                day = datetime.now(UTC).date().isoformat()
                reservations = [
                    entry
                    for entry in book.values()
                    if (
                        entry.get("period") == day
                        if self.daily
                        else entry.get("period") is None
                    )
                ]
                # An active run retains its full provider-enforced cap. For a
                # completed frontier run keep the larger of its final receipt
                # and the public maximum price for its confirmed billed events.
                def committed(run):
                    maximum = Decimal(str(run.get("maximum_usd", 0)))
                    count = run.get("physical_item_count")
                    if not self.frontier or run["status"] != "SUCCEEDED" or count is None:
                        return maximum
                    events, settled = run.get("charged_events"), run.get("usage_usd")
                    if settled is None or not isinstance(events, dict) or run["actor"] not in (ACTOR, KAITO):
                        return maximum
                    if set(events) - {"apify-default-dataset-item"}:
                        return maximum
                    # usageTotalUsd can lag. Hidden or empty rows can also be
                    # billable, even when the entire cleaned search page is empty.
                    billable = max(count, sum(events.values()))
                    at_list = PRICES[run["actor"]] * billable
                    return max(Decimal(str(settled)), min(at_list, maximum))
                reserved = sum(map(committed, reservations), Decimal(0))
                price = PRICES[self.actor]
                ceiling = price * limit + (
                    Decimal("0.001") if self.actor == SMART_ACTOR else Decimal(0)
                )
                if reserved + ceiling > self.budget:
                    raise ValueError(
                        f"Apify hard budget reached: reserved {reserved}, requested {ceiling}"
                    )
                actor = self.get(f"{BASE}/acts/{self.actor}")
                actor.raise_for_status()
                current = actor.json()["data"]["pricingInfos"][-1]
                events = current.get("pricingPerEvent", {}).get("actorChargeEvents", {})
                expected = {
                    "tweet"
                    if self.actor.startswith("winterlock~")
                    else "apify-default-dataset-item": price
                }
                if self.actor == SAMURAI:
                    expected = {
                        "tweet": price,
                        "user": price,
                        "tweet-lookup": Decimal("0.0035"),
                    }
                if self.actor == SMART_ACTOR:
                    expected["apify-actor-start"] = Decimal("0.001")
                if current.get("pricingModel") != "PAY_PER_EVENT" or set(events) != set(
                    expected
                ):
                    raise ValueError(
                        "Actor pricing changed; review before starting a run"
                    )
                for name, event in events.items():
                    tiers = event.get("eventTieredPricingUsd", {})
                    prices = (
                        [event["eventPriceUsd"]]
                        if "eventPriceUsd" in event
                        else [t["tieredEventPriceUsd"] for t in tiers.values()]
                    )
                    if (
                        not prices
                        or max(Decimal(str(p)) for p in prices) > expected[name]
                    ):
                        raise ValueError(
                            "Actor event price changed; review before starting a run"
                        )
                entry = {
                    "label": label,
                    "period": day if self.daily else None,
                    "actor": self.actor,
                    "input": payload,
                    "maximum_usd": str(ceiling),
                    "status": "RESERVED",
                }
                book[request_key] = entry
                write_json(self.path, book)
                response = self.client.post(
                    f"{BASE}/acts/{self.actor}/runs",
                    # Bound a stalled primary on the one-off sweep so the fallback
                    # gets its turn when the upstream retries HTTP 503 for minutes.
                    params={"maxTotalChargeUsd": str(ceiling),
                            "timeout": 120 if self.frontier and self.actor == ACTOR else 480},
                    json=payload,
                    timeout=30,
                )
                if response.is_client_error:
                    reason = response.json().get("error", {}).get("message", "")[:400]
                    entry.update(
                        status="REFUSED",
                        maximum_usd="0",
                        reason=reason,
                        refused_at=time.time(),
                    )
                    write_json(self.path, book)
                    raise ValueError(
                        f"Apify refused to start ({response.status_code}): {reason}"
                    )
                response.raise_for_status()
                run = response.json()["data"]
                entry.update(
                    id=run["id"], status=run["status"], dataset=run["defaultDatasetId"]
                )
                write_json(self.path, book)
            if not entry.get("id"):
                raise ValueError(
                    f"Existing {entry['status']} attempt for {label}: {entry.get('reason', 'remote run ID unknown')}"
                )
            run_id, dataset = entry["id"], entry["dataset"]
        output = self.root / "raw/apify" / f"{run_id}.json"
        # A parallel receipt reconciliation can save the dataset between our
        # ledger read and this check. Poll the existing run if its status is stale.
        if output.exists() and entry["status"] in TERMINAL:
            if entry["status"] != "SUCCEEDED" or entry.get("incomplete"):
                raise ValueError(f"Partial Apify run {run_id}; cached rows retained")
            return [i for i in read_json(output) if i.get("status") != "empty"]
        while True:
            if self.deadline and time.monotonic() >= self.deadline:
                raise TimeoutError("Apify run saved; next sync will resume polling")
            response = self.get(
                f"{BASE}/actor-runs/{run_id}", params={"waitForFinish": 20}, timeout=32
            )
            response.raise_for_status()
            run = response.json()["data"]
            if run["status"] in TERMINAL:
                break
        response = self.get(
            f"{BASE}/datasets/{dataset}/items",
            params={"format": "json", "clean": "true", "limit": limit},
        )
        response.raise_for_status()
        items = response.json()
        incomplete = False
        if (
            (not items or len(items) < limit)
            and self.actor == ACTOR
            and run["status"] == "SUCCEEDED"
        ):
            diagnostic = self.get(f"{BASE}/actor-runs/{run_id}/log")
            diagnostic.raise_for_status()
            if re.search(
                r"(?i)temporarily unavailable|free plan limit|coordinator unavailable|"
                r"(?:request|provider|upstream) (?:failed|rejected)|rate limit exceeded|"
                r"\[page \d+\].*(?:API error|error fetching|HTTP 429)",
                diagnostic.text,
            ):
                incomplete = True
        count = self.physical_item_count(dataset, run, len(items))
        with run_lock(self.path.parent):
            book = read_json(self.path)
            book[request_key].update(
                status=run["status"],
                items=len(items),
                physical_item_count=count,
                incomplete=incomplete,
                charged_events=run.get("chargedEventCounts"),
                usage_usd=run.get("usageTotalUsd"),
            )
            write_json(self.path, book)
        if any(
            not isinstance(item, dict)
            or (
                "id" not in item
                and item.get("status") != "empty"
                and not item.get("noResults")
            )
            for item in items
        ):
            raise ValueError(f"Unexpected Apify dataset rows for {run_id}")
        write_json(output, items)
        real = [i for i in items if i.get("status") != "empty"]
        if run["status"] != "SUCCEEDED" or incomplete:
            persist(real, self.root)
            raise ValueError(
                f"Partial Apify run {run_id} ({run['status']}); saved {len(real)} rows"
            )
        return real


def is_source_post(item):
    """Some paid actor datasets include fee notices with negative IDs."""
    if not isinstance(item, dict) or item.get("type") == "mock_tweet":
        return False
    author = item.get("author") or {}
    return (str(item.get("id") or "").isdecimal()
            and int(item["id"]) > 0
            and isinstance(author, dict)
            and bool(item.get("username") or author.get("userName") or author.get("username"))
            and bool(item.get("full_text") or item.get("fullText") or item.get("text")))


def tweet_record(item):
    author = item.get("author") or {}
    created = item.get("created_at") or item.get("createdAt")
    if created and not re.match(r"^\d{4}-", created):
        created = parsedate_to_datetime(created)
    entities = (item.get("entities") or {}).get("urls") or item.get("urls") or []
    urls = {}
    for link in entities:
        if isinstance(link, str):
            if link.startswith(("http://", "https://")):
                urls[link] = link
        elif link.get("url") and (link.get("expanded_url") or "").startswith(
            ("https://", "http://")
        ):
            urls[link["url"]] = link["expanded_url"]
    media = actor_attachments(item)
    quoted = (
        item.get("quotedTweet") or item.get("quote") or item.get("quoted_tweet") or {}
    )
    refs = (
        item.get("quoted_status_id"),
        item.get("in_reply_to_status_id"),
        item.get("quoteId"),
        item.get("inReplyToId"),
        quoted.get("id"),
    )
    references = list(dict.fromkeys(str(i) for i in refs if i and str(i).isdigit()))
    display = None
    media_types = {entry.get("type") for entry in media if isinstance(entry, dict) and entry.get("type")}
    for entry in media:
        if isinstance(entry, str):
            display = display or entry
        elif isinstance(entry, dict):
            display = (
                display
                or entry.get("media_url_https")
                or entry.get("preview_image_url")
                or entry.get("url")
            )
    post = RawPost(
        tweet_id=str(item["id"]),
        author_handle=item.get("username")
        or author.get("userName")
        or author["username"],
        text=item.get("full_text") or item.get("fullText") or item["text"],
        published_at=created,
        conversation_id=str(
            item.get("conversation_id") or item.get("conversationId") or item["id"]
        ),
        expanded_urls=urls,
        media_keys=sorted(attachment_keys(media)),
        referenced_post_ids=references,
    )
    card_link = (item.get("card") or {}).get("url")
    external = (
        [card_link] if isinstance(card_link, str) and external_url(card_link) else []
    )
    return RawTweetRecord(
        post=post, external_urls=external, thread_status="not_searched"
    ), {
        "likes": item.get("favorite_count", item.get("likeCount", item.get("likes"))),
        "media_url": display,
        **({"has_video": bool(media_types & {"video", "animated_gif"})} if media_types else {}),
        **({"quoted_id":str(refs[0] or refs[2] or quoted.get("id"))} if (refs[0] or refs[2] or quoted.get("id")) else {}),
        **({"quoted_text": (quoted.get("full_text") or quoted.get("fullText") or quoted.get("text") or "")[:500],
            "quoted_author": quoted.get("username") or (quoted.get("author") or {}).get("userName") or (quoted.get("author") or {}).get("username")}
           if quoted else {}),
    }


def persist(items, root):
    raw = root / "raw/x"
    seen = set()
    replies = defaultdict(dict)
    pending = list(items)
    with run_lock(root / "state/apify_x/writes"):
        orphan_path = root / "state/apify_x/thread_orphans.json"
        orphans = read_json(orphan_path) if orphan_path.exists() else {}
        for item in pending:
            if (
                item.get("status") == "empty"
                or item.get("noResults")
                or item.get("isRetweet")
                or item.get("is_retweet")
                or not is_source_post(item)
            ):
                continue
            quoted = (
                item.get("quote") or item.get("quotedTweet") or item.get("quoted_tweet")
            )
            if isinstance(quoted, dict) and quoted.get("author") and quoted.get("id"):
                pending.append(quoted)
            row, signal = tweet_record(item)
            if row.post.tweet_id in seen:
                continue
            seen.add(row.post.tweet_id)
            path = raw / f"{row.post.tweet_id}.json"
            if path.exists():
                previous = RawTweetRecord.model_validate(read_json(path))
                row.thread = previous.thread
                row.post.published_at = (
                    row.post.published_at or previous.post.published_at
                )
                if (
                    row.post.conversation_id == row.post.tweet_id
                    and previous.post.conversation_id
                ):
                    row.post.conversation_id = previous.post.conversation_id
                row.post.media_keys = list(
                    dict.fromkeys(previous.post.media_keys + row.post.media_keys)
                )
                row.post.referenced_post_ids = list(
                    dict.fromkeys(
                        previous.post.referenced_post_ids + row.post.referenced_post_ids
                    )
                )
                row.thread_status = previous.thread_status
                row.external_urls = list(
                    dict.fromkeys(previous.external_urls + row.external_urls)
                )
                row.demo_urls = previous.demo_urls
                if len(previous.post.text) > len(row.post.text):
                    row.post.text = previous.post.text
                row.post.expanded_urls = (
                    previous.post.expanded_urls | row.post.expanded_urls
                )
            row = collect_links(row, None, raw / "redirects")
            write_json(path, row.model_dump(mode="json"))
            signals = raw / "signals" / path.name
            old = read_json(signals) if signals.exists() else {}
            write_json(
                signals,
                old | {k: v if v is not None else old.get(k) for k, v in signal.items()},
            )
            if row.post.conversation_id != row.post.tweet_id:
                replies[row.post.conversation_id][row.post.tweet_id] = row.post
        for tid in seen & orphans.keys():
            for reply_id in orphans.pop(tid):
                cached = raw / f"{reply_id}.json"
                if cached.exists():
                    reply = RawTweetRecord.model_validate(read_json(cached)).post
                    if reply.conversation_id == tid:
                        replies[tid][reply_id] = reply
        for conversation, group in replies.items():
            path = raw / f"{conversation}.json"
            if not path.exists():
                orphans[conversation] = sorted(
                    set(orphans.get(conversation, [])) | set(group)
                )
                continue
            row = RawTweetRecord.model_validate(read_json(path))
            thread = {p.tweet_id: p for p in row.thread}
            for post in group.values():
                if post.author_handle.casefold() == row.post.author_handle.casefold():
                    thread[post.tweet_id] = post
            if thread:
                row.thread = sorted(thread.values(), key=lambda p: int(p.tweet_id))
                if row.thread_status not in {"searched", "complete"}:
                    row.thread_status = "partial"
                row = collect_links(row, None, raw / "redirects")
                write_json(path, row.model_dump(mode="json"))
        write_json(orphan_path, orphans)
    return seen


def restore_quote_signals(root):
    """Upgrade earlier cached receipts and resolve quote IDs whose original is available locally."""
    raw = root / "raw/x"
    for path in (root/"raw/apify").glob("*.json"):
        for item in read_json(path):
            quote = item.get("quotedTweet") or item.get("quoted_tweet") or item.get("quote") or {}
            quote_id = item.get("quoted_status_id") or item.get("quoteId") or quote.get("id")
            if not quote_id or not str(quote_id).isdigit() or not str(item.get("id")).isdigit():
                continue
            target = raw/"signals"/(str(item["id"])+".json")
            if not target.exists():
                continue
            old = read_json(target)
            text = quote.get("full_text") or quote.get("fullText") or quote.get("text")
            author = quote.get("username") or (quote.get("author") or {}).get("userName")
            source = raw/(str(quote_id)+".json")
            if not text and source.exists():
                post = read_json(source)["post"]
                text, author = post["text"], post["author_handle"]
            new = old | {"quoted_id":str(quote_id)}
            if text:
                new.update(quoted_text=text[:500], quoted_author=author)
            if new != old:
                write_json(target,new)


def discover_queries(config):
    models = "(Claude OR Gemini OR Codex OR GPT OR Opus OR Fable OR Sonnet)"
    broad = [
        models + ' ("3D world" OR "browser game" OR "playable demo")',
        models + ' (threejs OR "three.js" OR WebGPU) (built OR made OR playable)',
        models
        + ' (diorama OR "walking simulator" OR "voxel world" OR "procedural world")',
        models + " (游戏 OR 试玩 OR 三维 OR 漫游 OR 交互场景)",
    ]
    accounts = list(
        dict.fromkeys(
            [
                *config.get("watch_accounts", []),
                *(
                    urlsplit(u).path.strip("/").split("/")[0]
                    for u in config.get("seed_urls", [])
                ),
            ]
        )
    )
    accounts = [h for h in accounts if re.fullmatch(r"[A-Za-z0-9_]{1,15}", h, re.ASCII)]
    authored = [
        "("
        + " OR ".join("from:" + author for author in accounts[n : n + 6])
        + ") (3D OR game OR world OR scene OR diorama OR 游戏)"
        for n in range(0, len(accounts), 6)
    ]
    official = [
        f'(to:{handle} OR url:x.com/{handle}/status) (game OR 3D OR world OR playable OR "three.js")'
        for handle in (
            "OpenAI",
            "OpenAIDevs",
            "GoogleDeepMind",
            "AnthropicAI",
            "GoogleAI",
        )
    ]
    for item in config.get("official_threads", []):
        url = item["url"]
        tweet_id = urlsplit(url).path.strip("/").split("/")[-1]
        if tweet_id.isdigit():
            official.extend(
                [
                    f"conversation_id:{tweet_id} filter:replies",
                    f"quoted_tweet_id:{tweet_id} filter:quote",
                ]
            )
    extra = [
        q.replace("-is:retweet", "-filter:retweets")
        .replace("-is:reply", "-filter:replies")
        .replace("has:videos", "filter:videos")
        .replace("has:links", "filter:links")
        for q in [*config.get("apify_queries", []), *config.get("search_queries", [])]
    ]
    return {
        "broad": list(dict.fromkeys(config.get("frontier_queries", []) + broad + extra)),
        "authors": authored,
        "official": official,
    }


def search(ledger, query, label, limit, *, fallback_empty=False):
    payload = {
        "mode": "Advanced Search",
        "query": query,
        "query_type": "Latest",
        "max_results": limit,
    }
    if getattr(ledger, "actor", ACTOR) == KAITO:
        payload = {"searchTerms":[query], "queryType":"Latest", "maxItems":limit}
    failure = ""
    try:
        items = ledger.fetch(label, payload)
    except (TimeoutError, ValueError) as exc:
        if (getattr(ledger, "actor", ACTOR) == KAITO or not getattr(ledger, "auto_failover", True)
                or not re.search("partial apify|timed-out|failed|refused|at capacity", str(exc), re.I)):
            raise
        items, failure = [], str(exc)
    if failure or (fallback_empty and getattr(ledger, "actor", ACTOR) != KAITO and getattr(ledger, "auto_failover", True) and not any(is_source_post(i) for i in items)):
        backup = copy(ledger)
        backup.actor = KAITO
        items = backup.fetch(label + "-failover-kaito", {"searchTerms":[query], "queryType":"Latest","maxItems":limit})
    items = [item for item in items if is_source_post(item)]
    records = persist(items, ledger.root)
    print(
        f"{label}: {len(items)} returned, {len(records)} unique including quoted posts",
        flush=True,
    )
    return items


def thread_queries(ledger, maximum):
    raw = ledger.root / "raw/x"
    seeds_path = ledger.root / "state/catalog_seeds.json"
    urls = read_json(seeds_path).get("seed_urls", []) if seeds_path.exists() else []
    seed_ids = {urlsplit(url).path.strip("/").split("/")[-1] for url in urls}
    candidates = []
    for path in raw.glob("[0-9]*.json"):
        record = RawTweetRecord.model_validate(read_json(path))
        post = record.post
        if post.conversation_id not in {None, post.tweet_id} or not re.search(
            r"(?i)game|playable|browser|three\.?js|webgpu|游戏|世界|diorama", post.text
        ):
            continue
        signals = raw / "signals" / path.name
        likes = (read_json(signals).get("likes") or 0) if signals.exists() else 0
        priority = (post.tweet_id in seed_ids, bool(record.demo_urls), likes)
        candidates.append((priority, post.tweet_id, post.author_handle))
    return [
        (f"conversation_id:{tid} from:{author} filter:replies", tid)
        for _, tid, author in sorted(candidates, reverse=True)[:maximum]
    ]


def hydrate_thread_roots(ledger):
    """Recover originals explicitly linked by a creator's own reply with a demo."""
    root = ledger.root
    catalog = root / "state/catalog_seeds.json"
    known = {
        urlsplit(u).path.strip("/").split("/")[-1]
        for u in (read_json(catalog).get("seed_urls", []) if catalog.exists() else [])
    }
    candidates = {}
    for path in (root / "raw/apify").glob("*.json"):
        for post in read_json(path):
            author = post.get("username") or ""
            parent = str(post.get("conversation_id") or "")
            if (
                not author
                or not parent.isdigit()
                or parent in known
                or (root / "raw/x" / f"{parent}.json").exists()
                or author.casefold()
                != (post.get("in_reply_to_screen_name") or "").casefold()
            ):
                continue
            urls = [
                link.get("expanded_url") or ""
                for link in post.get("urls", [])
                if isinstance(link, dict)
            ]
            if not any(
                re.search(
                    r"(?i)https?://[^/]*(?:chatgpt\.site|patch\.gg|github\.io|itch\.io|vercel\.app|threeui\.com|drop3\.app|playdrop\.ai)(?:/|$)|"
                    r"https?://(?:claude\.ai/artifact/|ai\.studio/|github\.com/)",
                    u,
                )
                for u in urls
            ):
                continue
            candidates[parent] = max(
                candidates.get(parent, 0), post.get("favorite_count") or 0
            )
    ids = sorted(candidates, key=lambda tid: (-candidates[tid], tid))[:100]
    if ids:
        group = ",".join(sorted(ids))
        rows = ledger.fetch(
            f"self-roots-{digest(group)[:16]}",
            {"mode": "Get a Few Tweets", "tweets": group, "max_results": len(ids)},
        )
        found = persist(rows, root)
        print(
            f"Recovered {len(found.intersection(ids))} of {len(ids)} linked original posts",
            flush=True,
        )


def daily_threads(ledger, since, until, maximum=8):
    return [
        (f"{q} since:{since} until:{until}", f"self-replies-{tid}-{until}", 18)
        for q, tid in thread_queries(ledger, maximum)
    ]


def six_month_start(anchor):
    year = anchor.year if anchor.month > 6 else anchor.year - 1
    month = (anchor.month - 7) % 12 + 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def history(ledger, config, anchor):
    final = anchor + timedelta(days=1)
    start = six_month_start(anchor)
    qs = discover_queries(config)
    cursor = start
    jobs = []
    while cursor < final:
        end = min(cursor + timedelta(days=31), final)
        for idx in (0, 2):
            query = qs["broad"][idx] + f" since:{cursor} until:{end} -filter:retweets"
            jobs.append((query, f"broad-{cursor}-{end}-{idx}", 85))
        cursor = end
    for source, queries, limit in [
        ("topical", qs["broad"][4:], 40),
        ("authors", qs["authors"], 48),
        ("official", qs["official"], 35),
    ]:
        for query in queries:
            jobs.append(
                (
                    query + f" since:{start} until:{final} -filter:retweets",
                    f"{source}-{digest(query)[:12]}-{start}-{final}",
                    limit,
                )
            )
    errors = {}

    def execute(jobs):
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs = {
                pool.submit(search, ledger, query, label, limit): label
                for query, label, limit in jobs
            }
            for future in as_completed(runs):
                try:
                    future.result()
                except (ValueError, httpx.HTTPError, TimeoutError) as exc:
                    errors[runs[future]] = str(exc)

    execute(jobs)
    execute(daily_threads(ledger, start, final))
    write_json(ledger.root / "state/apify_x/history_errors.json", errors)
    if errors:
        print(
            f"{len(errors)} incomplete history searches; see history_errors.json",
            flush=True,
        )


def missing_authors(ledger, config, anchor):
    """Check watchlist authors who were absent from a capped group search."""
    book = read_json(ledger.path) if ledger.path.exists() else {}
    found = set()
    for entry in book.values():
        if not entry.get("id") or not entry["label"].startswith(
            ("authors-", "targeted-author")
        ):
            continue
        path = ledger.root / "raw/apify" / f"{entry['id']}.json"
        if path.exists():
            for item in read_json(path):
                if item.get("username"):
                    found.add(item["username"].casefold())
    start = six_month_start(anchor)
    end = anchor + timedelta(days=1)
    missing = [
        h
        for h in config.get("watch_accounts", [])
        if h.casefold() not in found and re.fullmatch(r"[A-Za-z0-9_]{1,15}", h)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {
            pool.submit(
                search,
                ledger,
                f"from:{handle} (3D OR game OR world OR playable OR threejs OR 游戏) since:{start} until:{end} -filter:retweets",
                f"authors-gap-{handle}-{start}-{end}",
                25,
            ): handle
            for handle in missing
        }
        for job in as_completed(jobs):
            try:
                job.result()
            except (ValueError, httpx.HTTPError, TimeoutError) as exc:
                print(f"Author search for {jobs[job]} incomplete: {exc}", flush=True)


def targeted(ledger, anchor):
    """Look for public play links and gaps in the broad six-month sample."""
    start = six_month_start(anchor)
    end = anchor + timedelta(days=1)
    domain = (
        "(url:patch.gg OR url:chatgpt.site OR url:claude.ai/artifact OR url:ai.studio)"
    )
    demo = "(game OR world OR walking OR explore OR diorama OR village OR 试玩)"
    creators = "(from:BlendiByl OR from:prasenx OR from:Dimillian OR from:CapyCola OR from:ai_for_success OR from:jacalulu)"
    terms = [
        ("domain-high-likes", f"{domain} {demo} min_faves:20", start, end, 180),
        (
            "authors-high-likes",
            f"{creators} {demo} filter:links min_faves:10",
            start,
            end,
            140,
        ),
        (
            "domain-project-hosts",
            "(url:github.io OR url:vercel.app OR url:itch.io) (threejs OR diorama OR WebGPU) (Gemini OR Claude OR Codex) min_faves:15",
            start,
            end,
            100,
        ),
    ]
    for host, models in [
        ("claude.ai/artifact", "(Claude OR Fable OR Opus)"),
        ("chatgpt.site", "(GPT OR Astra OR Codex)"),
        ("patch.gg", "(Fable OR Gemini OR Claude OR Codex)"),
        ("ai.studio", "Gemini"),
    ]:
        query = f"url:{host} {models} (3D OR game OR world OR playable) min_faves:5"
        terms.append(("domain-" + host.split("/")[0], query, start, end, 150))
    # Sample the initial partial month and the mid-period independently.
    midpoint = start + timedelta(days=75)
    for month in [start, midpoint.replace(day=1)]:
        edge = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        terms.append(
            (
                "broad-gap",
                '"three.js" (Gemini OR Claude OR Codex OR GPT)',
                month,
                edge,
                65,
            )
        )
    errors = {}
    for channel, query, lower, upper, size in terms:
        label = f"{channel}-{lower}-{upper}"
        try:
            search(
                ledger,
                query + f" since:{lower} until:{upper} -filter:retweets",
                label,
                size,
            )
        except (ValueError, httpx.HTTPError, TimeoutError) as exc:
            errors[label] = str(exc)
            if "hard budget reached" in str(exc):
                break
    write_json(ledger.root / "state/apify_x/targeted_errors.json", errors)


def paginate_day(ledger, query, label, limit, items, start, end):
    """Continue below the oldest in-window hit; an actor may ignore dates or max_id."""
    cursor = None
    for page in range(1, 4):
        if len(items) < int(0.9 * limit):
            break
        ids = []
        for item in items:
            if not isinstance(item, dict) or not str(item.get("id", "")).isdecimal():
                continue
            record, _ = tweet_record(item)
            stamp = record.post.published_at if record else None
            if stamp and start <= stamp.astimezone(UTC).date() < end:
                ids.append(int(item["id"]))
        if ids:
            next_cursor = min(ids) - 1
        elif cursor is None:
            # Some quote searches return a full page outside the requested date.
            # The first Snowflake of the following UTC day is an exclusive upper bound.
            midnight = datetime.fromisoformat(str(end)).replace(tzinfo=UTC)
            next_cursor = ((int(midnight.timestamp()) * 1000 - 1288834974657) << 22) - 1
        else:
            break
        if cursor is not None and next_cursor >= cursor:
            break
        cursor = next_cursor
        items = search(
            ledger, f"{query} max_id:{cursor}", f"{label}-page-{page}-{cursor}", limit
        )


def search_adaptive(ledger, query, start, end, limit=120, min_days=1, *, layer="topical", fallback_empty=False, defer=False):
    """Search half-open UTC date ranges; split saturated pages down to the configured floor."""
    label = f"{layer}-{digest(query)[:12]}-{start}-{end}"
    items = search(ledger, f"{query} since:{start} until:{end}", label, limit, fallback_empty=fallback_empty)
    days = (end-start).days
    if days == min_days == 1 and len(items) >= int(0.9 * limit):
        paginate_day(ledger, f"{query} since:{start} until:{end}", label, limit, items, start, end)
    if len(items) >= int(0.9 * limit) and days > min_days:
        mid = start + timedelta(days=days//2)
        windows = ((mid,end),(start,mid))
        if defer:
            return windows
        for lo, hi in windows:
            search_adaptive(ledger,query,lo,hi,limit,min_days,layer=layer,fallback_empty=fallback_empty)


def frontier_backfill(ledger, config, since, anchor):
    end = anchor + timedelta(days=1)
    if since >= end:
        raise ValueError("Backfill start must not follow the anchor")
    jobs = []
    for q in config["frontier_queries"]:
        start = since
        if '"Opus 5.5"' in q:
            start = min(start, date(2026,9,20))
        elif '"Gemini 4"' in q:
            start = min(start, date(2026,10,12))
        jobs.append(("topical",q,start,120,1,False))
    excluded = {a.lower() for a in config.get("excluded_aggregator_accounts", [])}
    accounts = [a for a in config["watch_accounts"] if a.lower() not in excluded]
    for i in range(0,len(accounts),5):
        terms = " OR ".join("from:"+a for a in accounts[i:i+5])
        jobs.append(("authors", f"({terms}) (filter:videos OR filter:links) -filter:retweets -filter:replies",since,100,2,False))
    official = "(from:Google OR from:GoogleAI OR from:GoogleDeepMind OR from:OpenAI OR from:OpenAIDevs OR from:claudeai OR from:AnthropicAI) (3D OR threejs OR three.js OR WebGPU OR world OR game OR physics OR path-traced OR arcade) -filter:retweets"
    jobs.append(("official",official,since,120,1,False))
    for thread in config.get("official_threads", []):
        if "kimi" in thread["model"].lower():
            continue
        tid = thread["post_id"]
        for q in (f"conversation_id:{tid} filter:replies",f"quoted_tweet_id:{tid} filter:quote"):
            jobs.append(("official",q,since,120,1,True))
    # Reconnect to existing runs before admitting new queries after an interruption.
    if ledger.path.exists():
        for entry in read_json(ledger.path).values():
            if entry.get("id") and entry["status"] not in TERMINAL:
                resume = copy(ledger)
                resume.actor = entry["actor"]
                try:
                    persist(resume.fetch(entry["label"], entry["input"]), ledger.root)
                except ValueError as error:
                    print(f"Resumed run: {error}",flush=True)

    def execute(job):
        layer, query, lo, hi, cap, days, fallback = job
        try:
            windows = search_adaptive(ledger,query,lo,hi,cap,days,layer=layer,fallback_empty=fallback,defer=True)
            return [(layer,query,a,b,cap,days,fallback) for a,b in windows or ()], None
        except (ValueError,TimeoutError,httpx.HTTPError) as exc:
            print(f"Deferred {layer} query: {exc}",flush=True)
            return [], {"query":query,"layer":layer,"since":str(lo),"until":str(hi),"reason":str(exc)}

    wave = [(layer,q,start,end,cap,days,fb) for layer,q,start,cap,days,fb in jobs]
    gaps = []
    first = True
    with ThreadPoolExecutor(max_workers=2) as pool:
        while wave:
            children = []
            for more,gap in pool.map(execute,wave):
                children.extend(more)
                if gap:
                    gaps.append(gap)
            if first:
                try:
                    hydrate_thread_roots(ledger)
                except (ValueError,TimeoutError,httpx.HTTPError) as exc:
                    gaps.append({"layer":"linked_originals","reason":str(exc)})
                first = False
            wave = children
    try:
        hydrate_thread_roots(ledger)
    except (ValueError,TimeoutError,httpx.HTTPError) as exc:
        gaps.append({"layer":"linked_originals","reason":str(exc)})
    write_json(ledger.path.parent/"frontier_gaps.json", gaps)


def retry_gaps(ledger, config, since, anchor, audit_path, provenance_path):
    book_file = ledger.path.parent / "frontier_ledger.json"
    old = (
        {v.get("id"): v for v in read_json(book_file).values() if v.get("id")}
        if book_file.exists()
        else {}
    )
    if audit_path.is_file():
        audit = read_json(audit_path)
    elif old:
        fallback_runs, saturated = [], []
        for rid, source in old.items():
            payload = source["input"]
            terms = (
                [payload["query"]]
                if payload.get("query")
                else payload.get("searchTerms", [])
            )
            limit = payload.get("maxItems") or payload.get("max_results")
            fallback_runs.append(
                {
                    "run_id": rid,
                    "status": source["status"],
                    "search_terms": terms,
                    "requested_limit": limit,
                    "incomplete": source.get("incomplete", False),
                }
            )
            if limit and source.get("posts_returned", 0) >= int(limit * 0.9):
                saturated.append(rid)
        audit = {"runs": fallback_runs, "saturated_minimum_windows": saturated}
    else:
        raise FileNotFoundError(f"No source audit or frontier ledger: {audit_path}")
    historical = read_json(provenance_path)["added_from_public_catalog"]
    context = ledger.path.parent
    manifest = context / "phase2_recovery.json"
    if manifest.is_file():
        state = read_json(manifest)
        anchor = date.fromisoformat(state["anchor"])
    else:
        state = {
            "anchor": str(anchor),
            "before_ids": sorted(
                p.stem for p in (ledger.root / "raw/x").glob("*.json")
            ),
        }
        write_json(manifest, state)
    jobs = []
    repairs = {}
    for run in audit["runs"]:
        rid = run["run_id"]
        terms = run["search_terms"]
        if (
            run["status"] in {"FAILED", "TIMED-OUT"}
            or run.get("incomplete")
            or old.get(rid, {}).get("incomplete")
        ):
            if len(terms) != 1:
                raise ValueError("Cannot reconstruct failed source query: " + rid)
            label = "repair-" + rid
            jobs.append((label, terms[0], run["requested_limit"], None))
            repairs[label] = rid
        if terms and rid in audit["saturated_minimum_windows"]:
            match = re.search(r"since:([\d-]+) until:([\d-]+)", terms[0])
            dates = [date.fromisoformat(s) for s in match.groups()] if match else []
            if dates and dates[1] - dates[0] == timedelta(days=1):
                jobs.append(
                    (
                        "saturated-" + rid,
                        terms[0],
                        run["requested_limit"],
                        (rid, *dates),
                    )
                )
    watched = {h.casefold() for h in config["watch_accounts"]}
    names = sorted(set(historical) & watched)
    for offset in range(0, len(names), 5):
        handles = " OR ".join("from:" + name for name in names[offset : offset + 5])
        query = f"({handles}) (filter:videos OR filter:links) -filter:retweets -filter:replies since:{since} until:{anchor + timedelta(days=1)}"
        jobs.append(("authors-new-" + digest(query)[:12], query, 32, None))

    def replay(job):
        label, query, cap, day = job
        try:
            if day:
                rid, start, end = day
                page = ledger.root / "raw/apify" / (rid + ".json")
                items = (
                    read_json(page)
                    if page.exists()
                    else search(ledger, query, label, cap)
                )
                paginate_day(ledger, query, label, cap, items, start, end)
            else:
                search(ledger, query, label, cap)
        except (ValueError, TimeoutError, httpx.HTTPError) as error:
            return {"label": label, "reason": str(error)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        errors = [e for e in pool.map(replay, jobs) if e]
    state.update(
        repair_labels=repairs, historical_authors=names, jobs=len(jobs), deferred=errors
    )
    state["new_post_ids"] = sorted(
        {p.stem for p in (ledger.root / "raw/x").glob("*.json")}
        - set(state["before_ids"])
    )
    write_json(manifest, state)
    print(
        f"Recovery: {len(repairs)} prior runs, {len(names)} historical authors, {len(state['new_post_ids'])} new raw IDs, {len(errors)} deferred",
        flush=True,
    )


def incremental(ledger, config, anchor, page_size):
    """Advance one page per query, rotating fairly even across interrupted CI jobs."""
    path = ledger.root / "state/apify_x/cursors.json"
    channels = discover_queries(config)
    channels["self-replies"] = [q for q, _ in thread_queries(ledger, 2)]
    staggered = [
        pair
        for group in zip_longest(
            *[[(source, q) for q in qs] for source, qs in channels.items()]
        )
        for pair in group
        if pair is not None
    ]
    with run_lock(path.parent / "incremental"):
        state = read_json(path) if path.exists() else {}
        queries = state.setdefault("queries", {})
        # Last-attempt time is saved before network I/O, so one expensive query
        # cannot monopolize every short scheduled invocation.
        ordered = sorted(
            staggered,
            key=lambda pair: queries.get(digest(pair[1]), {}).get("attempted_at", ""),
        )
        for source, query in ordered:
            if ledger.deadline and time.monotonic() >= ledger.deadline:
                break
            key = digest(query)
            cursor = queries.setdefault(key, {})
            now = datetime.now(UTC)
            if "upper" not in cursor:
                if anchor < now.date():
                    bound = datetime.combine(
                        anchor + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                    )
                else:
                    bound = now
                # Bound by a Twitter Snowflake rather than a moving date during pagination.
                cursor["upper"] = str(
                    ((int(bound.timestamp() * 1000) - 1288834974657) << 22) - 1
                )
                cursor["floor"] = (
                    date.fromisoformat(cursor.get("through", str(anchor)))
                    - timedelta(days=1)
                ).isoformat()
                cursor["candidate_high"] = cursor.get("since_id", "0")
            cursor["attempted_at"] = now.isoformat()
            write_json(path, state)
            lower = (
                f"since_id:{cursor['since_id']}"
                if int(cursor.get("since_id") or 0)
                else f"since:{cursor['floor']}"
            )
            upper = cursor.get("max_id") or cursor["upper"]
            term = f"{query} {lower} max_id:{upper} -filter:retweets"
            try:
                items = search(
                    ledger,
                    term,
                    f"sync-{source}-{key[:12]}-{upper}-{cursor.get('retry', 0)}",
                    page_size,
                )
            except TimeoutError:
                return
            except (httpx.HTTPError, ValueError) as exc:
                cursor["error"] = str(exc)
                if str(exc).startswith("Partial Apify run"):
                    # Only retry a known terminal/partial run; ambiguous starts are never
                    # reissued. Keep both ID bounds until a complete page is durable.
                    cursor["retry"] = cursor.get("retry", 0) + 1
                write_json(path, state)
                if "hard budget reached" in str(exc):
                    break
                continue
            ids = [int(row["id"]) for row in items if row.get("id")]
            if any(
                i > int(upper) or i <= int(cursor.get("since_id") or 0) for i in ids
            ):
                cursor["error"] = "Upstream returned records outside the cursor bounds"
            else:
                cursor.pop("error", None)
                high = max([int(cursor["candidate_high"]), *ids])
                if len(ids) < page_size:
                    queries[key] = {
                        "since_id": str(high),
                        "through": anchor.isoformat(),
                        "attempted_at": cursor["attempted_at"],
                    }
                else:
                    cursor.update(candidate_high=str(high), max_id=str(min(ids) - 1))
            write_json(path, state)


def coverage_report(ledger, *, audit_output=None, config=None):
    """Reconcile existing runs and receipts with read-only API calls."""
    book = read_json(ledger.path) if ledger.path.exists() else {}
    if audit_output:
        book = {k: v for k, v in book.items() if v.get("period") is None}
    directory = ledger.root / "raw/apify"
    channels = defaultdict(
        lambda: {
            "runs": 0,
            "statuses": Counter(),
            "returned_rows": 0,
            "returned_ids": set(),
            "post_ids": set(),
            "dates": [],
        }
    )
    dates_by_id, all_ids = {}, set()
    total = Decimal(0)
    notes, updates, rows_by_month = {}, {}, Counter()
    public_runs, public_gaps = [], []
    author_runs, author_hits, all_author_hits = (
        defaultdict(set),
        defaultdict(set),
        defaultdict(set),
    )
    author_plans = {}

    def inspect(pair):
        key, entry = pair
        if not entry.get("id"):
            return key, entry, []
        run_id = entry["id"]
        response = ledger.get(f"{BASE}/actor-runs/{run_id}")
        response.raise_for_status()
        run = response.json()["data"]
        entry = {
            **entry,
            "status": run["status"],
            "actor_id": run.get("actId"),
            "usage_usd": run.get("usageTotalUsd"),
            "charged_events": run.get("chargedEventCounts"),
            "status_message": run.get("statusMessage"),
        }
        path = directory / f"{run_id}.json"
        if path.exists():
            items = read_json(path)
        else:
            response = ledger.get(
                f"{BASE}/datasets/{entry['dataset']}/items",
                params={"clean": "true", "format": "json", "limit": 1000},
            )
            response.raise_for_status()
            items = response.json()
            if not isinstance(items, list):
                raise ValueError(f"Expected dataset rows for {run_id}")
            if run["status"] in TERMINAL:
                write_json(path, items)
        actual = [row for row in items if is_source_post(row)]
        entry["placeholder_rows"] = sum(row.get("type") == "mock_tweet" for row in items if isinstance(row, dict))
        entry["items"] = len(items)
        if ledger.frontier and entry.get("physical_item_count") is None:
            entry["physical_item_count"] = ledger.physical_item_count(entry.get("dataset"), run, len(items))
        entry["posts_returned"] = len(actual)
        return key, entry, actual

    with ThreadPoolExecutor(max_workers=2) as pool:
        for key, entry, actual in pool.map(inspect, book.items()):
            updates[key] = entry
            label = entry["label"]
            channel = label.split("-")[0]
            if channel in {"winterlock", "pilot"}:
                channel = "pilot"
            if channel == "targeted":
                channel = "authors"
            if channel == "authoring":
                channel = "topical"
            request = entry.get("input", {})
            query = request.get("query") or " ".join(request.get("searchTerms", []))
            mode = entry.get("input", {}).get("mode")
            if channel == "topical" and "url:" in query:
                channel = "domain"
            if channel in {"official", "claude"}:
                if mode == "Get Quotes" or "quoted_tweet_id:" in query:
                    channel = "official_quotes"
                elif mode == "Get Replies" or "conversation_id:" in query:
                    channel = "official_replies"
                else:
                    channel = "official_mentions"
            if channel == "self":
                channel = (
                    "linked_originals"
                    if label.startswith("self-roots-")
                    else "self_replies"
                )
            if channel == "authors":
                for handle in re.findall(
                    r"\bfrom:([A-Za-z0-9_]+)", query, re.IGNORECASE
                ):
                    name = handle.casefold()
                    author_plans[name] = handle
                    if entry.get("id"):
                        author_runs[name].add(entry["id"])
            bucket = channels[channel]
            bucket["runs"] += 1
            bucket["returned_rows"] += len(actual)
            bucket["returned_ids"].update(str(row["id"]) for row in actual)
            bucket["statuses"][entry["status"]] += 1
            if entry["status"] != "SUCCEEDED" or not actual:
                notes[label] = {
                    "status": entry["status"],
                    "posts": len(actual),
                    "reason": entry.get("reason") or entry.get("status_message"),
                }
            if entry.get("id"):
                receipt = entry.get("usage_usd")
                public_runs.append(
                    {
                        "run_id": entry["id"],
                        "actor_id": entry.get("actor_id"),
                        "channel": channel,
                        "label": label,
                        "status": entry["status"],
                        "search_terms": [query]
                        if query
                        else entry.get("input", {}).get("searchTerms", []),
                        "provider_mode": mode,
                        "requested_limit": entry.get("input", {}).get("max_results")
                        or entry.get("input", {}).get("maxItems"),
                        "returned_rows": len(actual),
                        "provider_rows": entry.get("items"),
                        "placeholder_rows": entry.get("placeholder_rows", 0),
                        "usage_usd": f"{Decimal(str(receipt)):.6f}"
                        if receipt is not None
                        else None,
                    }
                )
            if not actual or entry["status"] != "SUCCEEDED" or entry.get("incomplete"):
                reason = (
                    "not_admitted"
                    if not entry.get("id")
                    else "actor_partial"
                    if entry.get("incomplete")
                    else "terminal_error"
                    if entry["status"] in TERMINAL - {"SUCCEEDED"}
                    else "in_progress"
                    if entry["status"] not in TERMINAL
                    else "no_posts_returned"
                )
                public_gaps.append(
                    {
                        "channel": channel,
                        "label": label,
                        "status": entry["status"],
                        "reason": reason,
                        "returned_rows": len(actual),
                    }
                )
            unique = persist(actual, ledger.root) if actual else set()
            bucket["post_ids"].update(unique)
            all_ids.update(unique)
            bounds = re.search(r"since:(\d{4}-\d{2}-\d{2}) until:(\d{4}-\d{2}-\d{2})", query)
            outside = 0
            for item in actual:
                record, _ = tweet_record(item)
                author = record.post.author_handle.casefold()
                all_author_hits[author].add(record.post.tweet_id)
                if channel == "authors":
                    author_hits[author].add(record.post.tweet_id)
                if record.post.published_at:
                    stamp = record.post.published_at.astimezone(UTC).isoformat()
                    if bounds and not bounds[1] <= stamp[:10] < bounds[2]:
                        outside += 1
                    dates_by_id[record.post.tweet_id] = stamp
                    bucket["dates"].append(stamp[:10])
            if entry.get("id") and bounds:
                public_runs[-1]["outside_requested_dates"] = outside
            total += Decimal(str(entry.get("usage_usd") or 0))
    with run_lock(ledger.path.parent):
        latest = read_json(ledger.path)
        for key, item in updates.items():
            # Another collector may have finished this run during the GET request.
            if latest[key].get("status") not in TERMINAL or item["status"] in TERMINAL:
                latest[key].update(item)
        write_json(ledger.path, latest)
        history_errors = ledger.path.parent / "history_errors.json"
        if history_errors.exists():
            errors = read_json(history_errors)
            for entry in updates.values():
                label = entry["label"]
                if (
                    entry["status"] == "SUCCEEDED"
                    and entry.get("posts_returned")
                    and not entry.get("incomplete")
                    and errors.get(label, "").startswith(
                        f"Partial Apify run {entry.get('id')}; cached rows retained"
                    )
                ):
                    del errors[label]
            write_json(history_errors, errors)
    for stamp in dates_by_id.values():
        rows_by_month[stamp[:7]] += 1
    summary = {
        "checked_at": datetime.now(UTC).isoformat(),
        "unique_ids": len(all_ids),
        "dated_top_level_posts": len(dates_by_id),
        "published_months": dict(sorted(rows_by_month.items())),
        "earliest": min((d[:10] for d in dates_by_id.values()), default=None),
        "latest": max((d[:10] for d in dates_by_id.values()), default=None),
        "reported_usage_usd": str(total.quantize(Decimal("0.000001"))),
        "hard_limit_usd": str(ledger.budget),
        "missing_receipts": sum(r["usage_usd"] is None for r in public_runs),
        "channels": {},
        "gaps": notes,
    }
    for name, bucket in channels.items():
        bucket["distinct_returned"] = len(bucket.pop("returned_ids"))
        bucket["unique_ids"] = len(bucket.pop("post_ids"))
        timestamps = bucket.pop("dates")
        bucket["date_range"] = [
            min(timestamps, default=None),
            max(timestamps, default=None),
        ]
        summary["channels"][name] = bucket
    coverage_name = "frontier_coverage.json" if ledger.frontier else "coverage.json"
    write_json(ledger.root / "state/apify_x" / coverage_name, summary)
    if audit_output:
        for handle in (config or {}).get("watch_accounts", []):
            author_plans.setdefault(handle.casefold(), handle)
        audit = {k: v for k, v in summary.items() if k != "gaps"}
        audit.update(
            {
                "earliest_utc": min(dates_by_id.values(), default=None),
                "latest_utc": max(dates_by_id.values(), default=None),
                "deduplicated_post_ids": sorted(all_ids, key=int),
                "runs": sorted(public_runs, key=lambda run: run["label"]),
                "remaining_gaps": sorted(public_gaps, key=lambda gap: gap["label"]),
                "author_coverage": {
                    handle: {
                        "author_query_run_ids": sorted(author_runs[name]),
                        "author_query_distinct_posts": len(author_hits[name]),
                        "all_channels_distinct_posts": len(all_author_hits[name]),
                    }
                    for name, handle in sorted(author_plans.items())
                },
                "measurement": {
                    "returned_rows": "Top-level post rows, before downstream content screening and deduplication.",
                    "distinct_returned": "Unique top-level post IDs within this channel.",
                    "unique_ids": "Distinct normalized IDs, including embedded original quoted posts. Overlapping channels are deduplicated for the overall total.",
                    "dates": "Publication timestamps for dated top-level posts. Each month counts distinct top-level IDs.",
                    "author_coverage": "Per public handle: admitted author-search runs, distinct observed author-search results and distinct results across all channels. A group query can return zero rows for an individual handle.",
                    "coverage": "Six-month sample with per-run result caps. Empty searches and failed runs limit coverage.",
                    "usage_usd": "Apify run-receipt usageTotalUsd, denominated in USD. Rejected admissions without run IDs did not create a chargeable run.",
                },
            }
        )
        if ledger.frontier:
            path = ledger.path.parent/"frontier_gaps.json"
            audit["deferred_queries"] = read_json(path) if path.exists() else []
            saturated = []
            for run in public_runs:
                term = " ".join(run["search_terms"])
                bounds = re.search(r"since:(\d{4}-\d{2}-\d{2}) until:(\d{4}-\d{2}-\d{2})", term)
                cap = run["requested_limit"]
                if not bounds or not cap or run["returned_rows"] < int(cap * 0.9):
                    continue
                days = (date.fromisoformat(bounds[2]) - date.fromisoformat(bounds[1])).days
                if days <= (2 if run["channel"] == "authors" else 1):
                    saturated.append(run["run_id"])
            audit["saturated_minimum_windows"] = sorted(saturated)
            audit["measurement"]["coverage"] = (
                "Frontier queries, grouped author timelines, official release threads and linked roots. "
                "Minimum-duration windows at or above 90% of the cap can still omit posts. "
                "See saturated_minimum_windows, remaining_gaps and deferred_queries."
            )
        if getattr(ledger, "recovery", False):
            recovery = read_json(ledger.path.parent/"phase2_recovery.json")
            audit["deferred_queries"] = recovery["deferred"]
            audit["phase1_recoveries"] = {rid: next((r["run_id"] for r in public_runs if r["label"]==label and r["status"]=="SUCCEEDED"),None)
                                          for label,rid in recovery["repair_labels"].items()}
            audit["historical_creators_targeted"] = len(recovery["historical_authors"])
            audit["new_post_ids"] = recovery["new_post_ids"]
        write_json(audit_output, audit)
    print(
        f"Apify captured {len(all_ids)} unique posts. Run receipts total US${total:.6f}.",
        flush=True,
    )
    return summary


def api_token():
    token = os.getenv("APIFY_API_KEY")
    if not token:
        token = dotenv_values(Path.home() / ".config/ai-keys/keys.env").get(
            "APIFY_API_KEY"
        )
    if not token:
        raise ValueError("APIFY_API_KEY missing")
    return token


class ApifyXAdapter(BaseXAdapter):
    def __init__(self, ledger):
        self.ledger = ledger

    def fetch_tweet_with_thread(self, tweet_id):
        if not re.fullmatch(r"[0-9]+", tweet_id):
            raise ValueError("Invalid numeric X post ID")
        path = self.ledger.root / "raw/x" / f"{tweet_id}.json"
        if not path.exists():
            rows = self.ledger.fetch(
                f"lookup-{tweet_id}",
                {"mode": "Get Tweet by ID", "id": tweet_id, "max_results": 1},
            )
            persist(rows, self.ledger.root)
        if not path.exists():
            raise ValueError(f"X post unavailable: {tweet_id}")
        record = RawTweetRecord.model_validate(read_json(path))
        root = record.post.conversation_id or tweet_id
        term = f"conversation_id:{root} from:{record.post.author_handle} filter:replies"
        replies = search(
            self.ledger, term, f"thread-{root}-{datetime.now(UTC).date()}", 20
        )
        fresh = RawTweetRecord.model_validate(read_json(path))
        by_id = {reply.tweet_id: reply for reply in fresh.thread}
        for item in replies:
            reply, _ = tweet_record(item)
            if (
                reply.post.tweet_id != tweet_id
                and reply.post.conversation_id == root
                and reply.post.author_handle.lower() == fresh.post.author_handle.lower()
            ):
                by_id[reply.post.tweet_id] = reply.post
        fresh.thread = sorted(by_id.values(), key=lambda post: int(post.tweet_id))
        fresh.thread_status = "partial" if len(replies) >= 20 else "searched"
        return collect_links(fresh, None, path.parent / "redirects")

    def search_recent(self, query, max_results):
        now = datetime.now(UTC)
        bounded = (
            query
            + f" since:{now.date() - timedelta(days=7)} until:{now.date() + timedelta(days=1)}"
        )
        rows = search(
            self.ledger,
            bounded,
            f"recent-{now.strftime('%Y%m%dT%H')}-{digest(query)[:12]}",
            max_results,
        )
        return [str(r["id"]) for r in rows if r.get("id")]

    def incremental_ids(self, query, since_id, bootstrap_limit):
        if not since_id:
            return self.search_recent(query, bootstrap_limit)
        ids = []
        upper = ((int(datetime.now(UTC).timestamp()) * 1000 - 1288834974657) << 22) - 1
        while upper > int(since_id):
            bound = f"{query} since_id:{since_id} max_id:{upper}"
            rows = search(
                self.ledger, bound, f"page-{digest(bound)[:32]}", bootstrap_limit
            )
            found = [int(row["id"]) for row in rows]
            if any(i > upper or i <= int(since_id) for i in found):
                raise ValueError("Apify ignored an incremental ID boundary")
            ids.extend(map(str, found))
            if len(found) < bootstrap_limit:
                break
            upper = min(found) - 1
        return list(dict.fromkeys(ids))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[
            "pilot",
            "history",
            "frontier",
            "targeted",
            "author-gaps",
            "retry-gaps",
            "incremental",
            "threads",
            "thread-roots",
            "report",
        ],
        required=True,
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=Path("config/seeds.yaml"))
    parser.add_argument(
        "--date", type=date.fromisoformat, default=datetime.now(UTC).date()
    )
    parser.add_argument("--since", type=date.fromisoformat, default=date(2026,11,1))
    parser.add_argument("--actor", choices=["auto","badger","kaito"], default="auto")
    parser.add_argument("--source-audit", type=Path, default=Path("research/expansion/apify_frontier_audit.json"))
    parser.add_argument("--author-provenance", type=Path, default=Path("research/expansion/frontier_phase2_author_provenance.json"))
    parser.add_argument("--budget-usd", type=Decimal)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument(
        "--audit-output",
        type=Path,
        help="Write a redacted research capture audit in report mode",
    )
    args = parser.parse_args()
    if args.page_size < 1 or args.page_size > 500:
        parser.error("--page-size must be 1–500")
    token = api_token()
    config = yaml.safe_load(args.config.read_text())
    catalogs = args.config.parent / "catalogs.yaml"
    if catalogs.exists():
        config["official_threads"] = yaml.safe_load(catalogs.read_text()).get(
            "official_threads", []
        )

    with httpx.Client(
        headers={"Authorization": "Bearer " + token}, timeout=45
    ) as client:
        campaign = args.mode == "frontier" or (args.mode == "report" and args.audit_output and "frontier" in args.audit_output.stem)
        recovery = args.mode == "retry-gaps" or bool(args.mode == "report" and args.audit_output and "phase2" in args.audit_output.stem)
        campaign = recovery or campaign
        actor = KAITO if args.actor == "kaito" or (recovery and args.actor == "auto") else ACTOR
        budget = args.budget_usd if args.budget_usd is not None else (Decimal("2.50") if recovery else Decimal("5.00") if campaign else LIMIT)
        ledger = RunLedger(args.data_dir, client, budget, daily=args.mode=="incremental", frontier=bool(campaign), recovery=recovery, actor=actor, auto_failover=args.actor=="auto")
        if args.mode == "report":
            coverage_report(ledger, audit_output=args.audit_output, config=config)
        elif args.mode == "retry-gaps":
            retry_gaps(ledger, config, args.since, args.date, args.source_audit, args.author_provenance)
        elif args.mode == "frontier":
            frontier_backfill(ledger, config, args.since, args.date)
        elif args.mode == "targeted":
            targeted(ledger, args.date)
        elif args.mode == "author-gaps":
            missing_authors(ledger, config, args.date)
        elif args.mode == "history":
            history(ledger, config, args.date)
        elif args.mode == "incremental":
            ledger.deadline = time.monotonic() + 360
            incremental(ledger, config, args.date, args.page_size)
        elif args.mode == "thread-roots":
            hydrate_thread_roots(ledger)
        elif args.mode == "threads":
            for q, label, limit in daily_threads(
                ledger, args.date - timedelta(days=183), args.date + timedelta(days=1)
            ):
                search(ledger, q, label, limit)
        else:
            start = args.date - timedelta(days=184)
            q = f'"three.js" (Gemini OR Claude OR Codex) since:{start} until:{args.date + timedelta(days=1)} -filter:retweets'
            search(ledger, q, f"pilot-badger-{args.date}", 150)


if __name__ == "__main__":
    main()
