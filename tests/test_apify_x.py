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
    from src.cli import app
    import src.cli as cli

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
