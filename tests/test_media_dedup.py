import json

from src.apify_x import tweet_record
from src.dedup import deduplicate
from src.models import RawPost, RawTweetRecord
from src.recheck_duplicates import repair
from src.storage import write_json, write_text
from src.x_media import attachment_keys, load_media_evidence


def post(identifier, text, keys=(), **fields):
    return RawTweetRecord(post=RawPost(tweet_id=str(identifier), author_handle=f"creator{identifier}",
                                       text=text, media_keys=list(keys)), **fields)


def test_media_identity_and_source_positions(tmp_path):
    a = post(101, "flying", ["0", "photo_0"])
    b = post(102, "sailing", ["0", "photo_0"])
    c = post(103, "swimming", ["0"])
    d = post(104, "climbing", ["3_1111111111111111111"])
    e = post(105, "spinning", ["1111111111111111111"])
    link = "https://pbs.twimg.com/media/SharedImage"
    receipt = {"id": "101", "username": "creator101", "text": "flying", "media": [
        {"media_key": "0", "url": "https://pbs.twimg.com/media/FirstPhoto.jpg"},
        {"media_key": "photo_1", "id_str": "1111111111111111112", "media_url_https": link + ".jpg?name=small"}],
        "quote": {"id": "102", "media": [link + "?format=jpg&name=large"]}}
    record, _ = tweet_record(receipt)
    assert "0" not in record.post.media_keys and "photo_1" not in record.post.media_keys
    assert "1111111111111111112" in record.post.media_keys
    assert not attachment_keys(["https://pbs.twimg.com/profile_images/123/a.jpg", "https://other.com/media/abc"])
    write_json(tmp_path / "raw/apify/page.json", [receipt])
    write_json(tmp_path / "raw/x/signals/103.json", {"media_url": "https://pbs.twimg.com/media/Other.jpg"})
    groups = deduplicate([a, b, c, d, e], media_evidence=load_media_evidence(tmp_path))
    assert [g.possible_duplicate_urls for g in groups] == [
        [b.original_url], [a.original_url], [], [e.original_url], [d.original_url]]


def test_replay_repairs_pending_without_losing_other_duplicate_evidence(tmp_path):
    a = post(111, "A handmade exploration of a cavern hidden on an island.", ["0", "photo_0"])
    b = post(112, "Tall windmills rotate slowly.", ["0"])
    c = post(113, a.post.text, ["0"])
    d = post(114, "Playing the original recording.", ["photo_0", "x-media-one"])
    a.post.media_keys.append("x-media-one")
    e = post(115, "Shared website, different raw links.", ["0"])
    f = post(116, "Another race", ["x-media-one"])
    for r in (a, b, c, d, e, f):
        write_json(tmp_path / "raw/x" / f"{r.post.tweet_id}.json", r.model_dump(mode="json"))
    missing = "https://x.com/archived/status/109"
    first = {"original_post_url": a.original_url, "world_id": "a", "author_handle": a.post.author_handle,
             "summary": "First line\u2028second line",
             "live_demo_url": "https://island.example/play", "review_status": "pending",
             "possible_duplicate_urls": [b.original_url, c.original_url, d.original_url, e.original_url, missing]}
    approved = {"original_post_url": e.original_url, "world_id": "e", "review_status": "approved",
                "live_demo_url": "https://island.example/play", "possible_duplicate_urls": [b.original_url]}
    rejected = {"original_post_url": b.original_url, "world_id": "b", "review_status": "rejected",
                "possible_duplicate_urls": [a.original_url]}
    path = tmp_path / "processed/cases.jsonl"
    initial = [first, approved, rejected, {"original_post_url": missing, "review_status": "pending"}]
    write_text(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in initial))
    before = path.read_bytes()
    expected = {"pending_x": 2, "missing_source": 1, "changed": 1, "removed": 1, "added": 1}
    assert repair(tmp_path, tmp_path / "seeds.yaml") == expected
    assert path.read_bytes() == before
    assert not (tmp_path / ".pipeline.lock").exists()
    assert repair(tmp_path, tmp_path / "seeds.yaml", apply=True) == expected
    output = path.read_bytes()
    rows = [json.loads(line) for line in output.splitlines()]
    assert rows[0] == first | {"possible_duplicate_urls": [c.original_url, d.original_url, e.original_url, missing, f.original_url]}
    assert output.splitlines()[1:] == before.splitlines()[1:]
    assert repair(tmp_path, tmp_path / "seeds.yaml", apply=True)["changed"] == 0
    assert path.read_bytes() == output

def test_original_upload_is_not_blocked_by_later_repost(tmp_path):
    from types import SimpleNamespace
    from src.reconcile_sources import canonical_originals
    from src.models import ReviewStatus
    older=post(8001,"I built a 3D greenhouse with a coding model.",["8327789123456789012"])
    later=post(8010,"Here's the greenhouse clip.",["8327789123456789012"])
    rows=[]
    for r,other in [(older,later),(later,older)]:
        write_json(tmp_path/"raw/x"/f"{r.post.tweet_id}.json",r.model_dump(mode="json"))
        rows.append(SimpleNamespace(world_id=r.post.tweet_id,original_post_url=r.original_url,source_kind="x_post",
                 live_demo_url=None,repo_url=None,review_status=ReviewStatus.PENDING,
                 possible_duplicate_urls=[other.original_url],related_post_urls=[]))
    canonical_originals(tmp_path,rows,[])
    assert rows[0].possible_duplicate_urls==[] and rows[0].related_post_urls==[later.original_url]
    assert rows[1].possible_duplicate_urls==[older.original_url] and not rows[1].related_post_urls
    assert not canonical_originals(tmp_path,rows,[])
