from datetime import date
from decimal import Decimal

import httpx
import pytest

from src import apify_x as x
from src.models import RawTweetRecord
from src.storage import read_json


def tweet(identifier, *, root=None, author="maker", text="I built a world"):
    return {
        "id": str(identifier),
        "username": author,
        "full_text": text,
        "conversation_id": str(root or identifier),
        "created_at": "Tue Nov 24 08:30:00 +0000 2026",
        "favorite_count": 23,
        "urls": [
            {"url": "https://t.co/demo", "expanded_url": "https://example.org/game"}
        ],
        "media": [
            {
                "media_key": "m1",
                "preview_image_url": "https://pbs.twimg.com/media/example.jpg",
            }
        ],
    }


def test_public_research_audit_counts_sources_and_omits_private_payloads(tmp_path):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"data": {"status": "SUCCEEDED", "usageTotalUsd": 0.00015}}
            )
        )
    )
    ledger = x.RunLedger(tmp_path, client)
    rows = [tweet(17, text="private fixture body")]
    book = {}
    for label, run_id, period in [
        ("authors-maker", "runOne", None),
        ("self-roots-17", "runTwo", None),
        ("sync-broad-now", "dailyRun", "2026-11-24"),
    ]:
        book[label] = {
            "label": label,
            "id": run_id,
            "status": "SUCCEEDED",
            "input": {"query": "from:Maker"},
            "period": period,
        }
        x.write_json(tmp_path / f"raw/apify/{run_id}.json", rows)
    x.write_json(ledger.path, book)
    path = tmp_path / "audit.json"
    with client:
        x.coverage_report(
            ledger, audit_output=path, config={"watch_accounts": ["Silent"]}
        )
    audit = read_json(path)
    assert audit["deduplicated_post_ids"] == ["17"]
    assert audit["reported_usage_usd"] == "0.000300"
    assert audit["channels"]["linked_originals"]["distinct_returned"] == 1
    assert audit["author_coverage"]["Maker"]["author_query_distinct_posts"] == 1
    assert audit["author_coverage"]["Silent"]["all_channels_distinct_posts"] == 0
    assert audit["earliest_utc"] == "2026-11-24T08:30:00+00:00"
    assert len(audit["runs"]) == 2
    assert "private fixture body" not in path.read_text()


def test_parallel_report_can_save_dataset_before_collector_reads_status(tmp_path):
    payload = {"mode": "Advanced Search", "query": "3d", "max_results": 1}
    key = x.digest(x.json.dumps([x.ACTOR, "race", payload], sort_keys=True))

    def handler(request):
        assert request.method == "GET"
        if "/actor-runs/" in request.url.path:
            return httpx.Response(200, json={"data": {"status": "SUCCEEDED"}})
        return httpx.Response(200, json=[tweet(12)])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ledger = x.RunLedger(tmp_path, client)
        x.write_json(
            ledger.path,
            {
                key: {
                    "label": "race",
                    "id": "existing",
                    "dataset": "dataset1",
                    "status": "RUNNING",
                }
            },
        )
        x.write_json(tmp_path / "raw/apify/existing.json", [tweet(12)])
        assert ledger.fetch("race", payload) == [tweet(12)]


def test_persist_author_replies_and_signals(tmp_path):
    posts = [tweet(10), tweet(11, root=10), tweet(12, root=10, author="visitor")]
    for _ in range(2):
        assert x.persist(posts, tmp_path) == {"10", "11", "12"}
    path = tmp_path / "raw/x/10.json"
    record = RawTweetRecord.model_validate(read_json(path))
    assert [r.tweet_id for r in record.thread] == ["11"]
    assert record.thread_status == "partial"
    assert record.external_urls == ["https://example.org/game"]
    assert read_json(path.parent / "signals/10.json") == {
        "likes": 23,
        "media_url": "https://pbs.twimg.com/media/example.jpg",
    }


def test_actor_budget_and_resumed_result(tmp_path):
    starts = []

    def handler(request):
        if request.url.path.endswith("/runs"):
            starts.append(request)
            assert Decimal(request.url.params["maxTotalChargeUsd"]) == Decimal(".00015")
            return httpx.Response(
                201,
                json={
                    "data": {
                        "id": "remote1",
                        "status": "RUNNING",
                        "defaultDatasetId": "dataset1",
                    }
                },
            )
        if "/actor-runs/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "status": "SUCCEEDED",
                        "chargedEventCounts": {"apify-default-dataset-item": 1},
                    }
                },
            )
        if "/datasets/" in request.url.path:
            return httpx.Response(200, json=[tweet(123)])
        return httpx.Response(
            200,
            json={
                "data": {
                    "pricingInfos": [
                        {
                            "pricingModel": "PAY_PER_EVENT",
                            "pricingPerEvent": {
                                "actorChargeEvents": {
                                    "apify-default-dataset-item": {
                                        "eventPriceUsd": 0.00015
                                    }
                                }
                            },
                        }
                    ]
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ledger = x.RunLedger(tmp_path, client, budget=Decimal(".00015"))
        payload = {"mode": "Advanced Search", "query": "3d", "max_results": 1}
        assert (
            ledger.fetch("one", payload) == ledger.fetch("one", payload) == [tweet(123)]
        )
        with pytest.raises(ValueError, match="budget"):
            ledger.fetch("two", payload)
    assert len(starts) == 1


def test_incremental_full_page_keeps_high_watermark_pending(tmp_path, monkeypatch):
    class Ledger:
        root = tmp_path
        deadline = None

    batches = iter([[tweet(14), tweet(13)], [tweet(12)], []])
    terms = []
    monkeypatch.setattr(x, "discover_queries", lambda _: {"broad": ["game"]})
    monkeypatch.setattr(x, "thread_queries", lambda *_: [])

    def search(ledger, term, label, size):
        terms.append(term)
        return next(batches)

    monkeypatch.setattr(x, "search", search)
    for i in range(3):
        x.incremental(Ledger(), {}, date(2026, 11, 24), 2)
        state = read_json(tmp_path / "state/apify_x/cursors.json")["queries"][
            x.digest("game")
        ]
        if i == 0:
            assert state.get("since_id") is None and state["max_id"] == "12"
        else:
            assert state["since_id"] == "14"
    assert "max_id:12" in terms[1] and "since_id:14" in terms[2]


def test_failed_incremental_page_preserves_cursor_until_replay(tmp_path, monkeypatch):
    class Ledger:
        root = tmp_path
        deadline = None

    monkeypatch.setattr(x, "discover_queries", lambda _: {"broad": ["first", "second"]})
    monkeypatch.setattr(x, "thread_queries", lambda *_: [])
    calls = []

    def fetch(ledger, query, label, size):
        calls.append(query)
        if query.startswith("first"):
            raise ValueError("partial provider response")
        return [tweet(15)]

    monkeypatch.setattr(x, "search", fetch)
    x.incremental(Ledger(), {}, date(2026, 11, 24), 2)
    state = read_json(tmp_path / "state/apify_x/cursors.json")["queries"]
    assert (
        state[x.digest("first")]["error"] and "since_id" not in state[x.digest("first")]
    )
    assert state[x.digest("second")]["since_id"] == "15" and len(calls) == 2


def test_standard_cli_selects_apify(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from src import cli
    from src.cli import app

    calls = []

    def fake(ledger, config, date_value, page_size):
        calls.append((ledger, config, date_value, page_size))

    monkeypatch.setenv("APIFY_API_KEY", "test-fake-token")
    monkeypatch.setattr(cli, "apify_incremental", fake)
    seed = tmp_path / "config.yaml"
    seed.write_text("search_queries: [browser]\n")
    result = CliRunner().invoke(
        app,
        [
            "--source",
            "apify",
            "--data-dir",
            str(tmp_path),
            "--seed-file",
            str(seed),
            "ingest",
            "--mode",
            "incremental",
            "--limit",
            "20",
        ],
    )
    assert result.exit_code == 0, result.output
    ledger, config, _, limit = calls[0]
    assert (
        ledger.daily
        and ledger.root == tmp_path
        and config["search_queries"] == ["browser"]
        and limit == 20
    )


def test_base_adapter_fetches_only_author_replies(tmp_path):
    class Ledger:
        root = tmp_path

        def fetch(self, label, payload):
            if payload["mode"] == "Get Tweet by ID":
                return [tweet(123)]
            return [tweet(124, root=123), tweet(125, root=123, author="another")]

    adapter = x.ApifyXAdapter(Ledger())
    result = adapter.fetch_tweet_with_thread("123")
    assert isinstance(adapter, x.BaseXAdapter)
    assert result.post.tweet_id == "123" and result.thread_status == "searched"
    assert [p.tweet_id for p in result.thread] == ["124"]


def test_terminal_partial_run_retains_rows_without_advancing(tmp_path):
    calls = []

    def mock(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/runs"):
            return httpx.Response(
                201,
                json={
                    "data": {"id": "r1", "status": "RUNNING", "defaultDatasetId": "d1"}
                },
            )
        if "/actor-runs/" in request.url.path:
            return httpx.Response(200, json={"data": {"status": "TIMED-OUT"}})
        if "/datasets/" in request.url.path:
            return httpx.Response(200, json=[tweet(789)])
        event = {"eventPriceUsd": 0.00015}
        return httpx.Response(
            200,
            json={
                "data": {
                    "pricingInfos": [
                        {
                            "pricingModel": "PAY_PER_EVENT",
                            "pricingPerEvent": {
                                "actorChargeEvents": {
                                    "apify-default-dataset-item": event
                                }
                            },
                        }
                    ]
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(mock)) as http:
        ledger = x.RunLedger(tmp_path, http)
        for _ in range(2):
            with pytest.raises(ValueError, match="Partial"):
                ledger.fetch(
                    "partial",
                    {"max_results": 10, "query": "3D", "mode": "Advanced Search"},
                )
    assert (tmp_path / "raw/x/789.json").exists()
    assert sum(p.endswith("/runs") for p in calls) == 1


def test_daily_reservations_ignore_prior_utc_date(tmp_path):
    from src.storage import write_json

    ledger_path = tmp_path / "state/apify_x/ledger.json"
    write_json(
        ledger_path,
        {
            "previous": {
                "period": "2022-02-02",
                "maximum_usd": "0.30",
                "status": "SUCCEEDED",
            }
        },
    )

    class StopAfterPricing(Exception):
        pass

    def stub(request):
        assert request.url.path.endswith(x.ACTOR)
        raise StopAfterPricing()

    with httpx.Client(transport=httpx.MockTransport(stub)) as c:
        ledger = x.RunLedger(tmp_path, c, budget=Decimal(".00015"), daily=True)
        with pytest.raises(StopAfterPricing):
            ledger.fetch(
                "next-day",
                {"max_results": 1, "query": "test", "mode": "Advanced Search"},
            )
    assert len(read_json(ledger_path)) == 1


def test_self_reply_can_arrive_before_original(tmp_path):
    x.persist([tweet(11, root=10), tweet(12, root=10, author="visitor")], tmp_path)
    x.persist([tweet(10)], tmp_path)
    record = RawTweetRecord.model_validate(read_json(tmp_path / "raw/x/10.json"))
    assert [r.tweet_id for r in record.thread] == ["11"]
    assert read_json(tmp_path / "state/apify_x/thread_orphans.json") == {}


def test_adaptive_splits_saturated_half_open_windows(monkeypatch):
    windows = []
    def capture(ledger, query, label, limit, **kwargs):
        bounds = query.split(" since:")[1]
        windows.append(bounds)
        return [tweet(1)] * (9 if len(windows) == 1 else 3)

    monkeypatch.setattr(x, "search", capture)
    x.search_adaptive(None, "spatial game", date(2026, 1, 1), date(2026, 1, 5), limit=10)
    assert set(windows) == {"2026-01-01 until:2026-01-05", "2026-01-01 until:2026-01-03",
                            "2026-01-03 until:2026-01-05"}


@pytest.mark.parametrize("partial", [False, True])
def test_official_search_falls_back_once(tmp_path, partial):
    calls = []
    class Ledger:
        root = tmp_path
        actor = x.ACTOR
        def fetch(self, label, payload):
            calls.append((self.actor, payload))
            if self.actor == x.KAITO:
                return [tweet(719)]
            if partial:
                raise ValueError("Partial Apify run")
            return []

    result = x.search(Ledger(), "conversation_id:123", "official-fixture", 12, fallback_empty=True)
    assert result[0]["id"] == "719"
    assert [actor for actor, _ in calls] == [x.ACTOR, x.KAITO]
    assert calls[-1][1]["searchTerms"] == ["conversation_id:123"]
    assert (tmp_path / "raw/x/719.json").exists()


def test_quoted_promotion_and_aggregator_never_reach_model(tmp_path):
    from src.qualify_candidates import qualify
    from src.dedup import deduplicate
    ad = tweet(610, text="A quote about my scene")
    ad["quotedTweet"] = {"id": "608", "text": "Black Friday deal, 50% OFF", "author": {"userName": "sponsor"}}
    other = tweet(620, author="curator", text="Made this clip (dev: @maker) #3D")
    x.persist([ad, other], tmp_path)
    signal = read_json(tmp_path / "raw/x/signals/610.json")
    assert signal["quoted_text"] == ad["quotedTweet"]["text"]
    assert signal["quoted_author"] == "sponsor"
    for tid in ("610", "620"):
        row = RawTweetRecord.model_validate(read_json(tmp_path / f"raw/x/{tid}.json"))
        assert qualify(deduplicate([row]), tmp_path, model="offline", limit=100,
                       config={"excluded_aggregator_accounts":["Curator"]}) == []
    leads = read_json(tmp_path / "state/aggregator_leads.json")
    assert leads["620"]["credited_dev"] == "maker"


def test_actor_charge_placeholders_do_not_enter_raw_or_count_as_results(tmp_path):
    fee_row = {"id": -1, "type": "mock_tweet", "text": "provider billing notice"}
    assert not x.is_source_post(fee_row)
    assert x.persist([fee_row, tweet(731)], tmp_path) == {"731"}


def test_malformed_link_does_not_discard_a_search_window(tmp_path):
    row = tweet(732, text="Built a world. Broken URL https://[invalid and https://example.org/world")
    assert x.persist([row], tmp_path) == {"732"}
    parsed = read_json(tmp_path / "raw/x/732.json")
    assert "https://example.org/world" in parsed["external_urls"]


def test_frontier_guard_reserves_dataset_cost_when_immediate_receipt_lags(tmp_path):
    from src.storage import write_json
    ledger = x.RunLedger(tmp_path, None, frontier=True, budget=Decimal(".00015"))
    write_json(ledger.path, {"old": {"actor":x.ACTOR, "period":None, "status":"SUCCEEDED",
        "maximum_usd":".00015", "items":1, "physical_item_count":1,
        "charged_events":{"apify-default-dataset-item":0}, "usage_usd":0}})
    with pytest.raises(ValueError, match="hard budget reached"):
        ledger.fetch("second", {"mode":"Advanced Search", "query":"example", "max_results":1})


@pytest.mark.parametrize("physical_count,allow_second", [(2, False), (None, False), (1, True)])
def test_frontier_guard_includes_clean_filtered_rows(tmp_path, physical_count, allow_second):
    starts = []
    def handler(request):
        path = request.url.path
        if path.endswith("/runs"):
            run = {"id": f"r{len(starts)}", "defaultDatasetId": f"d{len(starts)}", "status": "RUNNING"}
            starts.append(run)
            return httpx.Response(201, json={"data": run})
        if path.endswith("/items"):
            assert request.url.params["clean"] == "true"
            return httpx.Response(200, json=[])
        if "/datasets/" in path:
            if physical_count is None:
                return httpx.Response(404)
            return httpx.Response(200,
                                  headers={"Date": "Wed, 01 Apr 2026 00:00:15 GMT"},
                                  json={"data": {"id": path.rsplit("/", 1)[-1], "cleanItemCount": 0,
                                                 "itemCount": physical_count}})
        if "/actor-runs/" in path:
            return httpx.Response(200, json={"data": {
                "status": "SUCCEEDED", "finishedAt": "2026-04-01T00:00:00Z",
                "chargedEventCounts": {"apify-default-dataset-item": 0}, "usageTotalUsd": 0}})
        assert path.endswith(x.KAITO)
        return httpx.Response(200, json={"data": {"pricingInfos": [{
            "pricingModel": "PAY_PER_EVENT", "pricingPerEvent": {"actorChargeEvents": {
                "apify-default-dataset-item": {"eventPriceUsd": 0.00025}}}}]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ledger = x.RunLedger(tmp_path, client, actor=x.KAITO, frontier=True, budget=Decimal(".00050"))
        assert ledger.fetch("first", {"maxItems": 2}) == []
        original = next(iter(read_json(ledger.path).values()))
        assert original["items"] == 0 and original["physical_item_count"] == physical_count
        if allow_second:
            assert ledger.fetch("second", {"maxItems": 1}) == []
        else:
            with pytest.raises(ValueError, match="hard budget reached"):
                ledger.fetch("second", {"maxItems": 1})
    assert len(starts) == (2 if allow_second else 1)


def test_frontier_ignores_stale_physical_count(monkeypatch, tmp_path):
    dates = iter(["Wed, 01 Apr 2026 00:00:03 GMT", "Wed, 01 Apr 2026 00:00:07 GMT"])
    counts = iter([0, 2])
    monkeypatch.setattr(x.time, "sleep", lambda _: None)
    def handler(request):
        return httpx.Response(200, headers={"Date": next(dates)},
                              json={"data": {"id": "dataset1", "itemCount": next(counts)}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ledger = x.RunLedger(tmp_path, client, frontier=True)
        run = {"status": "SUCCEEDED", "finishedAt": "2026-04-01T00:00:00Z"}
        assert ledger.physical_item_count("dataset1", run, 0) == 2

def test_saturated_day_cursor_stops_on_ignored_pagination(tmp_path, monkeypatch):
    from datetime import date
    from types import SimpleNamespace
    from src import apify_x as x
    queries=[]
    monkeypatch.setattr(x,"tweet_record",lambda item:(SimpleNamespace(post=SimpleNamespace(published_at=datetime(2026,11,10,tzinfo=__import__('datetime').UTC))),{}))
    def fake(ledger,q,label,limit,**opts):
        queries.append(q)
        return [{"id":str(n)} for n in range(100,110)]
    from datetime import datetime
    monkeypatch.setattr(x,"search",fake)
    x.search_adaptive(None,"3d world",date(2026,11,10),date(2026,11,11),10)
    assert len(queries)==2 and "max_id:99" in queries[-1]

def test_phase2_budget_and_ledger_separate(tmp_path):
    from src import apify_x as x
    from decimal import Decimal
    import pytest
    with pytest.raises(ValueError):
        x.RunLedger(tmp_path,None,budget=Decimal("2.51"),frontier=True,recovery=True)
    l=x.RunLedger(tmp_path,None,budget=Decimal("2.50"),frontier=True,recovery=True)
    assert l.path.name=="phase2_ledger.json"

def test_gap_retry_replays_only_failed_and_scoped_authors(tmp_path,monkeypatch):
    from datetime import date
    from src import apify_x as x
    from src.storage import write_json, read_json
    ledger=x.RunLedger(tmp_path,None,frontier=True,recovery=True,budget=1,actor=x.KAITO)
    audit=tmp_path/"audit.json"
    authors=tmp_path/"authors.json"
    seed={"watch_accounts":["historical","existing"]}
    write_json(audit,{"runs":[dict(run_id="old-fail",status="FAILED",search_terms=["shader 3D"],requested_limit=15),
                             dict(run_id="old-ok",status="SUCCEEDED",search_terms=["generic"],requested_limit=15)],
                      "saturated_minimum_windows":[]})
    write_json(authors,{"added_from_public_catalog":{"historical":"old-world","removed":"old-other"}})
    requests=[]
    monkeypatch.setattr(x,"search",lambda ledger,q,label,cap: requests.append(q))
    x.retry_gaps(ledger,seed,date(2026,11,1),date(2026,11,25),audit,authors)
    assert len(requests)==2 and "shader 3D" in requests and any("from:historical" in q for q in requests)
    assert all("from:existing" not in q and "from:removed" not in q and q!="generic" for q in requests)
    result=read_json(ledger.path.parent/"phase2_recovery.json")
    assert result["repair_labels"]=={"repair-old-fail":"old-fail"}
