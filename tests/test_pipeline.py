import csv
import json

import httpx
from pydantic import ValidationError
import pytest
from typer.testing import CliRunner

from src.cli import FIXTURES, app
from src.dedup import deduplicate
from src.enrich_firecrawl import EnrichmentCache, Firecrawl
from src.extract_structured import AnnotatedExtractor, OpenAIExtractor, strict_schema
from src.ingest_x import MockXAdapter, OfficialXApiAdapter, collect_links
from src.links import external_url
from src.models import AIWorldCase, CaseGroup, RawPost, RawTweetRecord
from src.storage import read_rows


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("X_ADAPTER", "mock")
    runner = CliRunner()

    def invoke(*args):
        result = runner.invoke(app, [
            "--data-dir", str(tmp_path / "data"), "--report-path", str(tmp_path / "report.md"), *args,
        ])
        assert result.exit_code == 0, result.output or result.exception
        return result

    return invoke


def test_offline_exports_and_review(offline, tmp_path):
    offline("run-all", "--mode", "seed")
    root = tmp_path / "data"
    exports = root / "exports"
    payload = json.loads((exports / "ai_worlds.json").read_text())
    rows = {row["title"]: AIWorldCase.model_validate(row) for row in payload}
    assert len(rows) == 3
    moss = rows["Mosswood"]
    assert moss.author_handle == "forestlab"
    assert moss.related_post_urls == ["https://x.com/worlddigest/status/900002"]
    assert moss.repo_url == "https://github.com/forestlab/mosswood"
    assert moss.reported_cost_usd == 12.5
    assert moss.reported_time_minutes == 120
    assert rows["Voxel Tide"].cost_disclosure_status == "undisclosed"
    assert rows["Voxel Tide"].reported_cost_usd is None
    assert rows["Voxel Tide"].reported_time_minutes is None
    assert rows["Terra Blocks"].cost_disclosure_status == "partial"
    assert rows["Terra Blocks"].reported_cost_usd is None
    assert rows["Terra Blocks"].reported_time_minutes == 45
    files = [exports / "ai_worlds.json", exports / "ai_worlds.csv", exports / "review_queue.csv",
             tmp_path / "report.md"]
    assert "离线合成样本" in files[3].read_text()
    assert files[1].read_bytes().startswith(b"\xef\xbb\xbf")
    first_run = [path.read_bytes() for path in files]
    offline("run-all", "--mode", "seed")
    assert [path.read_bytes() for path in files] == first_run

    offline("review", moss.world_id, "approved")
    offline("extract")
    offline("export")
    reviewed = read_rows(root / "processed" / "cases.jsonl", AIWorldCase)
    assert next(row for row in reviewed if row.world_id == moss.world_id).review_status == "approved"
    with files[2].open(encoding="utf-8-sig", newline="") as queue:
        assert len(list(csv.DictReader(queue))) == 2


def test_no_external_requests_on_repeat(offline, tmp_path, monkeypatch):
    offline("run-all", "--mode", "search")
    root = tmp_path / "data"
    groups = read_rows(root / "processed" / "groups.jsonl", CaseGroup)

    def unexpected(*args, **kwargs):
        pytest.fail("Unexpected provider invocation for cached evidence")

    class Unavailable:
        github_catalog = unexpected
        scrape = unexpected

    monkeypatch.setattr(AnnotatedExtractor, "__call__", unexpected)
    offline("extract")
    EnrichmentCache(root).enrich(groups, Unavailable())
    assert len(list((root / "raw" / "firecrawl").glob("*.json"))) == 5
    previous = read_rows(root / "processed" / "cases.jsonl", AIWorldCase)
    assert len(previous) == 3


def test_schema_constraints(offline, tmp_path):
    offline("run-all")
    rows = read_rows(tmp_path / "data/processed/cases.jsonl", AIWorldCase)
    sample = rows[0].model_dump(mode="json")
    for update in [
        {"cost_disclosure_status": "undisclosed", "reported_cost_usd": 5},
        {"cost_disclosure_status": "partial", "reported_cost_usd": -1},
        {"is_open_source": "true"}, {"original_post_url": "https://x.com/other/status/123"},
        {"theme_category": "arbitrary"}, {"outside_schema": True},
    ]:
        with pytest.raises(ValidationError):
            AIWorldCase.model_validate(sample | update)
    post = RawPost(tweet_id="123", author_handle="maker", text="")
    with pytest.raises(ValidationError, match="only author"):
        RawTweetRecord(post=post, thread=[RawPost(tweet_id="124", author_handle="other", text="")])
    schema = strict_schema(AIWorldCase.model_json_schema())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(AIWorldCase.model_fields)
    assert "default" not in schema["properties"]["repo_url"]


def test_x_pagination_and_thread_filter():
    lookup = {"id": "100", "author_id": "1", "conversation_id": "100", "text": "short",
              "note_tweet": {"text": "full https://t.co/example",
                             "entities": {"urls": [{"url": "https://t.co/example", "expanded_url": "https://example.org/demo"}]}}}
    calls = []

    def response(request):
        calls.append(request)
        assert "note_post" in request.url.params["post.fields"]
        if request.url.path.endswith("/tweets/100"):
            return httpx.Response(200, json={"data": lookup, "includes": {"users": [{"id": "1", "username": "creator"}]}})
        assert request.url.path == "/2/tweets/search/all"
        assert request.url.params["query"] == "conversation_id:100 from:creator is:reply"
        base = {"id": "101", "conversation_id": "100", "text": "reply"}
        if "next_token" not in request.url.params:
            return httpx.Response(200, json={"data": [base | {"author_id": "2"}], "meta": {"next_token": "second"}})
        return httpx.Response(200, json={"data": [base | {"author_id": "1", "id": "102"}]})

    with httpx.Client(transport=httpx.MockTransport(response)) as http:
        row = OfficialXApiAdapter("fake", http, archive=True).fetch_tweet_with_thread("100")
    assert len(calls) == 3
    assert row.post.expanded_urls["https://t.co/example"] == "https://example.org/demo"
    assert [post.tweet_id for post in row.thread] == ["102"]


def test_firecrawl_recovers_after_shared_connection_outage(monkeypatch):
    clock = [0.0]
    calls = []
    monkeypatch.setattr("src.enrich_firecrawl.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("src.enrich_firecrawl.time.sleep", lambda _delay: None)

    def respond(request):
        calls.append(request)
        if clock[0] == 0:
            raise httpx.ConnectTimeout("unreachable", request=request)
        return httpx.Response(200, json={"success": True, "data": {"markdown": "World demo"}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        api = Firecrawl("fake", http)
        for n in range(2):
            with pytest.raises(httpx.ConnectTimeout):
                api.scrape(f"https://example.org/world/{n}")
        with pytest.raises(ValueError, match="temporarily unavailable"):
            api.scrape("https://example.org/world/next")
        assert len(calls) == 4
        clock[0] = 46.0
        assert api.scrape("https://example.org/world/next").markdown == "World demo"


def test_firecrawl_boundary_rate_limit_and_redirect(monkeypatch):
    monkeypatch.setattr("src.enrich_firecrawl.time.sleep", lambda _: None)
    calls = []

    def response(request):
        calls.append(json.loads(request.content)["url"])
        if len(calls) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"success": True, "data": {"markdown": "ignored",
                                                                   "metadata": {"url": "https://mobile.twitter.com/user"}}})

    with httpx.Client(transport=httpx.MockTransport(response)) as http:
        api = Firecrawl("fake", http)
        for url in ["https://x.com/maker/status/123", "https://twitter.com./test", "https://www.x.com/", "https://t.co/post"]:
            with pytest.raises(ValueError):
                api.scrape(url)
        assert api.scrape("https://example.com/game").status == "excluded_redirect"
    assert calls == ["https://example.com/game", "https://example.com/game"]
    assert external_url("https://example.com/game?seed=42&utm_medium=x#demo") == "https://example.com/game?seed=42"


def test_text_duplicates_are_marked_without_automatic_merge(tmp_path):
    adapter = MockXAdapter(FIXTURES / "tweets.json")
    original = collect_links(adapter.fetch_tweet_with_thread("900004"), None, tmp_path)
    duplicate = RawTweetRecord(post=original.post.model_copy(update={"tweet_id": "900005", "author_handle": "reposter"}))
    groups = deduplicate([original, duplicate])
    assert len(groups) == 2
    assert groups[0].possible_duplicate_urls == ["https://x.com/reposter/status/900005"]



def test_openai_request_uses_strict_case_schema(monkeypatch, offline, tmp_path):
    import openai
    from types import SimpleNamespace

    offline("run-all")
    sample = read_rows(tmp_path / "data/processed/cases.jsonl", AIWorldCase)[0]
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(status="completed", output_text=sample.model_dump_json())

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
    assert OpenAIExtractor("fake", "gpt-5-mini")({"identity": {}})["world_id"] == sample.world_id
    params = requests[0]
    assert params["store"] is False
    output = params["text"]["format"]
    assert output["name"] == "AIWorldCase"
    assert output["strict"] is True
    assert "reported_cost_usd" in output["schema"]["required"]


def test_exact_duplicate_prefers_creator_over_excluded_curator():
    demo = "https://example.org/sculpture"
    curator = RawTweetRecord(post=RawPost(tweet_id="451", author_handle="Gallery", text="A sculpture"), demo_urls=[demo])
    creator = RawTweetRecord(post=RawPost(tweet_id="452", author_handle="Maker", text="I sculpted this"), demo_urls=[demo])
    (group,) = deduplicate([curator, creator], excluded_authors=["gallery"])
    assert group.original == creator
    assert group.related_post_urls == [curator.original_url]


@pytest.mark.parametrize("author,linked,promo,usable", [
    ("Maker", True, False, True),
    ("elsewhere", True, False, False),
    ("Maker", False, False, False),
    ("Maker", True, True, True),
])
def test_creator_self_quote_provenance(tmp_path, author, linked, promo, usable):
    from src.extract_structured import prepare_case
    from src.qualify_candidates import qualify
    from src.storage import write_json
    from src.sync_catalog import rank_groups

    text = "I built this hillside world with Fable 5.2." + (" #ad" if promo else "")
    signal = {"quoted_id": "721", "quoted_text": text, "quoted_author": author}
    record = RawTweetRecord(post=RawPost(tweet_id="722", author_handle="maker",
        text="Here is a new view of the same hillside.", referenced_post_ids=["721"] if linked else []))
    group = CaseGroup(original=record, fingerprint="x:722")
    write_json(tmp_path / "raw/x/signals/722.json", signal)
    assert bool(rank_groups([group], {}, frontier_only=True, signals={"722": signal})) == usable

    proposal = json.loads((FIXTURES / "extractions.json").read_text())["900001"]
    proposal.update(models_used=["Fable 5.2"], evidence_quotes=[text, "An invented quote"])
    seen = []
    def extract(packet):
        seen.append(packet)
        return proposal
    case = prepare_case(group, [], tmp_path, "test", lambda: extract)
    assert ("same_author_quoted_post" in seen[0]) == usable
    assert case.models_used == (["Fable 5.2"] if usable else [])
    assert case.evidence_quotes == ([text] if usable else [])
    assert case.evidence_source_urls == (["https://x.com/Maker/status/721"] if usable else [])
    assert (case.review_status == "rejected") == promo
    if promo:
        assert qualify([group], tmp_path, model="offline", limit=12, config={}) == []


def test_retry_invalid_cached_proposal_and_ground_native_workflow(tmp_path):
    from src.extract_structured import prepare_case
    from src.storage import read_json, write_json

    statement = "I built a 3D scene with Fable 5.2."
    group = CaseGroup(original=RawTweetRecord(post=RawPost(
        tweet_id="801", author_handle="maker", text=statement)), fingerprint="x:801")
    write_json(tmp_path / "raw/x/signals/801.json", {"has_video": True})
    proposal = json.loads((FIXTURES / "extractions.json").read_text())["900001"]
    proposal.update(reproducibility_level="unverified", workflow_steps=[{
        "evidence_quote": statement, "step": "作者制作了 3D 场景。"}])
    calls = []
    def extract(packet):
        calls.append(packet["identity"]["world_id"])
        return proposal

    case = prepare_case(group, [], tmp_path, "standard", lambda: extract)
    assert case.workflow_steps == ["作者制作了 3D 场景。"]
    assert case.reproducibility_level == "video_only"
    path, = (tmp_path / "processed/extraction").glob("*.json")
    corrupted = read_json(path)
    corrupted["workflow_steps"][0]["evidence_quote"] = "outside the author's words"
    write_json(path, corrupted)
    second = prepare_case(group, [], tmp_path, "standard", lambda: extract)
    assert second == case
    assert len(calls) == 2
