import json

import pytest

from src.models import RawPost, RawTweetRecord
from src.recheck_duplicates import attributed_repost, repair
from src.storage import read_json, write_json, write_text


KEY = "2080000000000000001"
MEDIA = "https://pbs.twimg.com/media/ExactVideo"
other_asset = "https://pbs.twimg.com/media/SeparateVideo"


def record(i, handle, text, refs=(), media=(KEY,), date=None, **fields):
    return RawTweetRecord(post=RawPost(tweet_id=str(i), author_handle=handle, text=text,
                                       published_at=date or f"2026-10-0{i}T10:00:00+00:00",
                                       media_keys=list(media), referenced_post_ids=list(refs)), **fields)


def test_creator_credit_is_directional_and_unknown_references_stay_in_review(tmp_path):
    maker = record(1, "Maker", "I built this 3D forest with a weather system.")
    credited = record(2, "Reporter", "A forest with changing seasons. Built by @Maker")
    uncertain = record(3, "Elsewhere", "This video is gorgeous!")
    quoted = record(4, "Reviewer", "Sharing this impressive demo.", ["1"])
    linked = record(5, "Archive", "Check this out: " + maker.original_url)
    for r in (maker, credited, uncertain, quoted, linked):
        write_json(tmp_path / "raw/x" / (r.post.tweet_id + ".json"), r.model_dump(mode="json"))
    write_json(tmp_path / "raw/x/signals/4.json", {"quoted_id":"1", "quoted_author":"maker"})
    rows = [
        {"world_id": r.post.tweet_id, "original_post_url":r.original_url, "author_handle":r.post.author_handle,
         "review_status":"pending", "possible_duplicate_urls":[other.original_url for other in
          (maker, credited, uncertain, quoted, linked) if other != r]}
        for r in (maker, credited, uncertain, quoted, linked)]
    path = tmp_path / "processed/cases.jsonl"
    write_text(path, "".join(json.dumps(r) + "\n" for r in rows))
    original = path.read_bytes()
    audit = tmp_path / "audit.json"
    dry = repair(tmp_path, tmp_path / "config.yaml", audit_path=audit)
    assert dry["credited_repost_pairs"] == 3
    assert path.read_bytes() == original
    assert {r["proof"] for r in read_json(audit)} == {"explicit_creator_credit", "creator_quote_report", "creator_post_report"}
    assert repair(tmp_path, tmp_path / "config.yaml", apply=True) == dry
    result = path.read_bytes().splitlines()
    assert json.loads(result[0]) == rows[0] | {"possible_duplicate_urls":[uncertain.original_url]}
    assert result[1:] == original.splitlines()[1:]
    assert repair(tmp_path, tmp_path / "config.yaml", apply=True)["changed"] == 0


@pytest.mark.parametrize("author_text,repost_text,source_keys,later_keys,refs,signal", [
    ("Amazing work.", "Built by @Maker", [KEY], [KEY], [], {}),
    ("I built the island.", "I created my own version. Built by @Maker", [KEY], [KEY], [], {}),
    ("I built this island.", "A remake based on the island. Built by @Maker", [KEY], [KEY], [], {}),
    ("I built this island.", "Built by @Maker and coded by @SomeoneElse", [KEY], [KEY], [], {}),
    ("I built three games.", "Built by @Maker", [KEY], [KEY], [], {}),
    ("I built this island.", "Best games in this roundup. Built by @Maker", [KEY], [KEY], [], {}),
    ("I built this island.", "Built by @Maker", [MEDIA, other_asset], [MEDIA], [], {}),
    ("I built this island.", "Built by @Maker", [MEDIA], [other_asset], [], {}),
    ("I built this island.", "Impressive work.", [KEY], [KEY], ["1"], {"quoted_id":"1", "quoted_author":"Other"}),
    ("I built this island.", "Impressive work.", [KEY], [KEY], [], {"quoted_id":"1", "quoted_author":"Maker"}),
    ("I built this island.", "Impressive work.", [KEY], [KEY], ["1","999"], {"quoted_id":"1", "quoted_author":"Maker"}),
    ("I built this island.", "Impressive work.", ["photo_0"], ["photo_0"], ["1"], {"quoted_id":"1"}),
    ("I built a remake.", "Built by @Maker", [KEY], [KEY], [], {}),
    ("If I built a game like this, I would add flying.", "Built by @Maker", [KEY], [KEY], [], {}),
    ("I built a game.", "I tweaked the project built by @Maker", [KEY], [KEY], [], {}),
    ('They wrote: "I built this world."', "Built by @Maker", [KEY], [KEY], [], {}),
    ("I built a game.", "My new demo. Credit to @Maker", [KEY], [KEY], [], {}),
    ("I built a game.", "Built by @Maker and @AnotherArtist", [KEY], [KEY], [], {}),
    ("I built a game.", "Music credit: @Maker", [KEY], [KEY], [], {}),
    ("I built a game.", "Built by @Maker", [KEY, MEDIA], ["2080000000000000002", MEDIA], [], {}),
    ("I built a game.", "Built by @Maker", [KEY, MEDIA], [KEY, other_asset], [], {}),
])
def test_ambiguous_reposts_are_preserved(author_text,repost_text,source_keys,later_keys,refs,signal):
    creator = record(1, "Maker", author_text)
    later = record(2, "Reporter", repost_text, refs)
    assert not attributed_repost(creator, later, set(source_keys), set(later_keys), signal, set())


def test_conflicting_time_author_or_project_blocks_resolution():
    original = record(1, "Maker", "I built the island.", demo_urls=["https://forest.example/games/island"])
    later = record(2, "Other", "Built by @Maker", demo_urls=["https://forest.example/games/city"])
    assert not attributed_repost(original, later, {KEY}, {KEY}, {}, set())
    later.demo_urls=[]
    later.post.published_at=original.post.published_at
    assert not attributed_repost(original,later,{KEY},{KEY},{},set())
    later.post.published_at=None
    assert not attributed_repost(original,later,{KEY},{KEY},{},set())
    other = record(3,"Maker","Reposting the island. Built by @Maker")
    assert not attributed_repost(original,other,{KEY},{KEY},{},set())
    assert not attributed_repost(original,record(3,"Other","Built by @Maker"),{KEY},{KEY},{},{"maker"})


def test_native_media_source_requires_a_real_cross_post_link_or_verified_source_id(tmp_path):
    from src.recheck_duplicates import media_origin_receipts
    creator = record(1, "Maker", "I made this 3D island.")
    later = record(2, "Reporter", "A look at the island.")
    source_link = creator.original_url + "/video/1"
    own_link = later.original_url + "/video/1"
    entry = {"type":"video", "id_str":KEY, "media_url_https":MEDIA + ".jpg"}
    def source(r, uid, media):
        return {"id":r.post.tweet_id, "username":r.post.author_handle, "user_id":uid,
                "extendedEntities":{"media":[media]}}
    original = source(creator, "19", entry | {"expanded_url":source_link})
    default = source(later, "38", entry | {"expanded_url":own_link})
    by_id = {"1":creator, "2":later}
    raw = tmp_path / "raw/apify/cache.json"
    def lookup(*other):
        write_json(raw, [original,*other])
        return media_origin_receipts(tmp_path, by_id)
    assert lookup(default) == {}
    linked = source(later,"38",entry | {"expanded_url":source_link})
    assert lookup(linked) == {("1","2"):("native_attachment_creator_permalink",source_link)}
    assert lookup(default,linked) == lookup(linked)
    wrong_handle = source(later,"38",entry | {"expanded_url":source_link.replace('Maker','Elsewhere')})
    assert lookup(wrong_handle) == {}
    native = source(later,"38",entry | {"source_status_id_str":"1", "source_user_id_str":"19", "expanded_url":own_link})
    result = lookup(native)
    assert result == {("1","2"):("native_attachment_source_status","1")}
    assert attributed_repost(creator,later,{KEY,MEDIA},{KEY,MEDIA},{},set(), result[("1","2")])
    mismatched_user=source(later,"38",entry | {"source_status_id_str":"1","source_user_id_str":"20","expanded_url":own_link})
    assert lookup(mismatched_user,linked) == {}
    extra_link=source(later,"38",entry | {"expanded_url":"https://x.com/Someone/status/9/video/1"})
    assert lookup(linked,extra_link) == {}
    missing_media=source(later,"38",{"id_str":"2099999999999999999","expanded_url":source_link})
    assert lookup(missing_media) == {}
    write_json(raw,[source(creator,"19",entry),linked])
    assert media_origin_receipts(tmp_path,by_id) == {}
