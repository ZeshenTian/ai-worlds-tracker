from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from src.enrich_firecrawl import EnrichmentCache
from src.ingest_x import OfficialXApiAdapter, discovery_queries, ingest
from src.models import AIWorldCase, RawPost, RawTweetRecord, ReviewStatus
from src.publish_catalog import publish, trusted
from src.storage import read_json, write_rows

BASE = Path(__file__).resolve().parents[1] / "research/seed_snapshot/worlds.json"


def test_incremental_cursor_and_retry(tmp_path):
    cfg = {"search_queries":["new worlds"], "watch_accounts":["Maker"]}
    assert discovery_queries(cfg)["account:maker"] == "from:Maker (has:videos OR has:links) -is:retweet -is:reply"
    posts = []
    searches = []
    fail = True
    class Adapter(OfficialXApiAdapter):
        def fetch_tweet_with_thread(self, tweet_id):
            nonlocal fail
            if fail and tweet_id == "104":
                fail = False
                raise ValueError("transient")
            posts.append(tweet_id)
            return RawTweetRecord(post=RawPost(tweet_id=tweet_id,author_handle="Maker",text="world"))
    def respond(req):
        params = dict(req.url.params)
        searches.append(params)
        if "since_id" not in params:
            ids, next_token = ["101","100"], {}
        elif params["since_id"] == "101":
            ids, next_token = (["105","104"], {"next_token":"p2"}) if "next_token" not in params else (["103","102"], {})
        else:
            ids, next_token = [], {}
        return httpx.Response(200,json={"data":[{"id":i} for i in ids],"meta":next_token})
    cfg.pop("watch_accounts")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        ad = Adapter("test", client)
        ingest(ad,cfg,tmp_path,"incremental",2,None)
        with pytest.raises(ValueError):
            ingest(ad,cfg,tmp_path,"incremental",2,None)
        path = tmp_path / "state/sync_state.json"
        assert read_json(path)["query:new worlds"]["last_tweet_id"] == "101"
        assert len(searches) == 3
        ingest(ad,cfg,tmp_path,"incremental",2,None)
        assert len(searches) == 3
        assert read_json(path)["query:new worlds"]["last_tweet_id"] == "105"
        ingest(ad,cfg,tmp_path,"incremental",2,None)
        assert searches[-1]["since_id"] == "105"
        assert sorted(posts) == ["100","101","102","103","104","105"]


def test_health_and_publication_gate(tmp_path):
    old = read_json(BASE)[0]
    new = {**old,"world_id":"new","author_handle":"Maker","original_post_url":"https://x.com/Maker/status/22",
           "live_demo_url":"https://example.org/world","demo_health_status":"verified_playable"}
    case = AIWorldCase.model_validate(new)
    for changes in ({"live_demo_url":None}, {"demo_health_status":"no_demo"}, {"thumbnail_url":"/not-a-preview"}):
        with pytest.raises(ValidationError):
            AIWorldCase.model_validate({**new,**changes})
    cache = EnrichmentCache(tmp_path)
    assert trusted(case,{"watch_accounts":["maker"]},cache)
    assert trusted(case,{"watch_accounts":["unrelated"]},cache)
    case.author_handle = "ai_for_success"
    case.original_post_url = "https://x.com/ai_for_success/status/22"
    write_rows(tmp_path / "processed/cases.jsonl",[case])
    public = tmp_path / "platform"
    publish(tmp_path,public)
    assert not any(row["world_id"] == "new" for row in read_json(public / "data/worlds.json"))
    publish(tmp_path,public,auto=True)
    assert any(row["world_id"] == "new" for row in read_json(public / "data/worlds.json"))
    case.review_status = ReviewStatus.REJECTED
    write_rows(tmp_path / "processed/cases.jsonl",[case])
    publish(tmp_path,public,auto=True)
    assert not any(row["world_id"] == "new" for row in read_json(public / "data/worlds.json"))


def test_empty_checkpoint_pages_through_next_interval(tmp_path):
    params = []
    def respond(request):
        query = dict(request.url.params)
        params.append(query)
        if len(params) == 1:
            return httpx.Response(200, json={"meta":{"result_count":0}})
        if "next_token" not in query:
            return httpx.Response(200, json={"data":[{"id":"12"}],"meta":{"next_token":"page2"}})
        return httpx.Response(200, json={"data":[{"id":"11"}]})
    class Adapter(OfficialXApiAdapter):
        def fetch_tweet_with_thread(self, tweet_id):
            return RawTweetRecord(post=RawPost(tweet_id=tweet_id,author_handle="Maker",text="world"))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        ad = Adapter("test",client)
        for _ in range(2):
            ingest(ad,{"watch_accounts":["maker"]},tmp_path,"incremental",1,None)
    assert len(params) == 3
    assert params[1]["start_time"] == params[2]["start_time"]
    assert read_json(tmp_path / "state/sync_state.json")["account:maker"]["last_tweet_id"] == "12"


def test_sync_reuses_processed_works_and_keeps_discoveries_pending(tmp_path, monkeypatch):
    from src.cli import Pipeline
    from src.sync_catalog import sync
    from src.extract_structured import AnnotatedExtractor
    from src.enrich_firecrawl import FixtureScraper
    from src.storage import read_rows

    async def verified_elsewhere(*args):
        return {}

    monkeypatch.setattr("src.sync_catalog.verify", verified_elsewhere)
    root = tmp_path / "data"
    platform = tmp_path / "platform"
    with httpx.Client() as http:
        pipeline = Pipeline("mock",root,None,tmp_path/"unused.md",http)
        sync(pipeline,platform)
        seen = {row.world_id:row.first_seen_at for row in read_rows(root / "processed/cases.jsonl",AIWorldCase)}
        def no_repeat(*args):
            pytest.fail("Repeated a paid-equivalent extraction or scrape")
        monkeypatch.setattr(AnnotatedExtractor,"__call__",no_repeat)
        monkeypatch.setattr(FixtureScraper,"scrape",no_repeat)
        sync(pipeline,platform)
    assert seen == {row.world_id:row.first_seen_at for row in read_rows(root / "processed/cases.jsonl",AIWorldCase)}
    assert not any(row["title"]=="Mosswood" for row in read_json(platform / "data/worlds.json"))
