"""Budgeted X research against Apify's public pay-per-event tweet actor."""

import argparse
import calendar
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import re
import time
from itertools import zip_longest
from urllib.parse import urlsplit

from dotenv import dotenv_values
import httpx
import yaml

from .ingest_x import BaseXAdapter, collect_links
from .links import external_url
from .models import RawPost, RawTweetRecord
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
    def __init__(self, root, client, budget=LIMIT, actor=ACTOR, *, daily=False):
        self.daily = daily
        self.deadline = None
        self.client = client
        self.root = root
        self.actor = actor
        self.budget = Decimal(str(budget))
        if not 0 < self.budget <= LIMIT:
            raise ValueError("Budget must be greater than zero and at most US$1.50")
        self.path = root / "state/apify_x/ledger.json"

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

    def fetch(self, label, payload):
        wait_until = self.deadline or time.monotonic() + 480
        while True:
            try:
                return self._fetch_once(label, payload)
            except ValueError as exc:
                # An account concurrency refusal creates no run and incurs no charge.
                if "concurrent Actor runs" not in str(exc):
                    raise
                if time.monotonic() + 20 > wait_until:
                    raise TimeoutError(
                        "Apify concurrency limit; the pending query will resume later"
                    ) from exc
                time.sleep(20)

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
                reserved = sum(
                    (Decimal(str(v.get("maximum_usd", 0))) for v in reservations),
                    Decimal(0),
                )
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
                    params={"maxTotalChargeUsd": str(ceiling), "timeout": 480},
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
        if output.exists():
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
        with run_lock(self.path.parent):
            book = read_json(self.path)
            book[request_key].update(
                status=run["status"],
                items=len(items),
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
    media = (item.get("extendedEntities") or {}).get("media") or item.get("media") or []
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
    display, media_keys = None, []
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
            key = entry.get("media_key") or entry.get("id_str")
            if key:
                media_keys.append(str(key))
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
        media_keys=media_keys,
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
    }


def persist(items, root):
    raw = root / "raw/x"
    seen = set()
    replies = defaultdict(dict)
    pending = list(items)
    with run_lock(root / "state/apify_x/writes"):
        for item in pending:
            if (
                item.get("status") == "empty"
                or item.get("noResults")
                or item.get("isRetweet")
                or item.get("is_retweet")
                or not item.get("id")
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
                {k: v if v is not None else old.get(k) for k, v in signal.items()},
            )
            if row.post.conversation_id != row.post.tweet_id:
                replies[row.post.conversation_id][row.post.tweet_id] = row.post
        for conversation, group in replies.items():
            path = raw / f"{conversation}.json"
            if not path.exists():
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
    return seen


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
        "broad": list(dict.fromkeys(broad + extra)),
        "authors": authored,
        "official": official,
    }


def search(ledger, query, label, limit):
    payload = {
        "mode": "Advanced Search",
        "query": query,
        "query_type": "Latest",
        "max_results": limit,
    }
    items = ledger.fetch(label, payload)
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


def daily_threads(ledger, since, until, maximum=8):
    return [
        (f"{q} since:{since} until:{until}", f"self-replies-{tid}-{until}", 18)
        for q, tid in thread_queries(ledger, maximum)
    ]


def history(ledger, config, anchor):
    final = anchor + timedelta(days=1)
    year = anchor.year if anchor.month > 6 else anchor.year - 1
    month = (anchor.month - 7) % 12 + 1
    start = date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))
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
        with ThreadPoolExecutor(max_workers=3) as pool:
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
                    ledger, term, f"sync-{source}-{key[:12]}-{upper}", page_size
                )
            except TimeoutError:
                return
            except (httpx.HTTPError, ValueError) as exc:
                cursor["error"] = str(exc)
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


def coverage_report(ledger):
    """Reconcile existing runs and receipts with read-only API calls."""
    book = read_json(ledger.path) if ledger.path.exists() else {}
    directory = ledger.root / "raw/apify"
    channels = defaultdict(
        lambda: {"runs": 0, "statuses": Counter(), "post_ids": set(), "dates": []}
    )
    dates_by_id, all_ids = {}, set()
    total = Decimal(0)
    notes, updates, rows_by_month = {}, {}, Counter()

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
        actual = [
            row
            for row in items
            if isinstance(row, dict)
            and row.get("id")
            and (row.get("username") or row.get("author"))
        ]
        entry["items"] = len(items)
        entry["posts_returned"] = len(actual)
        return key, entry, actual

    with ThreadPoolExecutor(max_workers=3) as pool:
        for key, entry, actual in pool.map(inspect, book.items()):
            updates[key] = entry
            label = entry["label"]
            channel = label.split("-")[0]
            if channel in {"winterlock", "pilot"}:
                channel = "pilot"
            if channel == "targeted":
                channel = "authors"
            if channel == "self":
                channel = "self_replies"
            bucket = channels[channel]
            bucket["runs"] += 1
            bucket["statuses"][entry["status"]] += 1
            if entry["status"] != "SUCCEEDED" or not actual:
                notes[label] = {
                    "status": entry["status"],
                    "posts": len(actual),
                    "reason": entry.get("reason") or entry.get("status_message"),
                }
            unique = persist(actual, ledger.root) if actual else set()
            bucket["post_ids"].update(unique)
            all_ids.update(unique)
            for item in actual:
                record, _ = tweet_record(item)
                if record.post.published_at:
                    stamp = record.post.published_at.date().isoformat()
                    dates_by_id[record.post.tweet_id] = stamp
                    bucket["dates"].append(stamp)
            total += Decimal(str(entry.get("usage_usd") or 0))
    with run_lock(ledger.path.parent):
        latest = read_json(ledger.path)
        for key, item in updates.items():
            # Another collector may have finished this run during the GET request.
            if latest[key].get("status") not in TERMINAL or item["status"] in TERMINAL:
                latest[key].update(item)
        write_json(ledger.path, latest)
    for stamp in dates_by_id.values():
        rows_by_month[stamp[:7]] += 1
    summary = {
        "checked_at": datetime.now(UTC).isoformat(),
        "unique_ids": len(all_ids),
        "dated_top_level_posts": len(dates_by_id),
        "published_months": dict(sorted(rows_by_month.items())),
        "earliest": min(dates_by_id.values(), default=None),
        "latest": max(dates_by_id.values(), default=None),
        "reported_usage_usd": str(total.quantize(Decimal("0.000001"))),
        "hard_limit_usd": str(LIMIT),
        "channels": {},
        "gaps": notes,
    }
    for name, bucket in channels.items():
        bucket["unique_ids"] = len(bucket.pop("post_ids"))
        timestamps = bucket.pop("dates")
        bucket["date_range"] = [
            min(timestamps, default=None),
            max(timestamps, default=None),
        ]
        summary["channels"][name] = bucket
    write_json(ledger.root / "state/apify_x/coverage.json", summary)
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
        choices=["pilot", "history", "incremental", "threads", "report"],
        required=True,
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=Path("config/seeds.yaml"))
    parser.add_argument(
        "--date", type=date.fromisoformat, default=datetime.now(UTC).date()
    )
    parser.add_argument("--budget-usd", type=Decimal, default=LIMIT)
    parser.add_argument("--page-size", type=int, default=100)
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
        ledger = RunLedger(
            args.data_dir, client, args.budget_usd, daily=args.mode == "incremental"
        )
        if args.mode == "report":
            coverage_report(ledger)
        elif args.mode == "history":
            history(ledger, config, args.date)
        elif args.mode == "incremental":
            ledger.deadline = time.monotonic() + 360
            incremental(ledger, config, args.date, args.page_size)
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
