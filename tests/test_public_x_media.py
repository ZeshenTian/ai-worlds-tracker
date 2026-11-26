from hashlib import sha256
import gzip
import json

from src.models import RawPost, RawTweetRecord
from src.public_x_media import cached_native_entities, origins, parse_native
from src.recheck_duplicates import attributed_repost
from src.storage import read_json, write_json


MEDIA_ID = "2176543210987654321"
CDN = "https://pbs.twimg.com/media/IslandXYZ"
ATTACHMENT = "https://x.com/Maker/status/1/video/1"


def page(identifier, handle, *, source=None, conflicting=False, primary=True, canonical=None, wrong_account=False):
    source_user = {"rest_id":"98" if wrong_account else "19","core":{"screen_name":"Maker"}}
    item = {"id_str":MEDIA_ID, "media_url_https":CDN+".jpg","type":"video","expanded_url":ATTACHMENT}
    if source:
        item.update(source_status_id_str=source,source_user_results={"result":source_user})
    user = {"rest_id":"19" if identifier=="1" else "38","core":{"screen_name":handle}}
    obj = {"rest_id":identifier,"core":{"user_results":{"result":user}},"media_entities2":[item]}
    wrapper = {"data":{"tweet_result_by_rest_id" if primary else "quoted_status_result":{"rest_id":identifier,"result":obj}}}
    js = "fn(" + json.dumps(json.dumps(wrapper)) + ");"
    if conflicting:
        item["id_str"]="2188888888888888888"
        js += "fn(" + json.dumps(json.dumps(wrapper)) + ");"
    canonical = canonical or f"https://x.com/{handle}/status/{identifier}"
    return f'<meta property="og:url" content="{canonical}"><script>{js}</script>'


def test_public_corroboration_requires_both_primary_posts_exact_media_and_native_author(tmp_path):
    a,b = ("1","Maker"),("2","Curator")
    docs={i:page(i,h,source="1" if i=="2" else None) for i,h in (a,b)}
    by={}
    for i,h in (a,b):
        by[i]=RawTweetRecord(post=RawPost(tweet_id=i,author_handle=h,text="Opus 5.5 作品",published_at=f"2026-10-0{i}T00:00:00+00:00"))
        base=tmp_path/"raw/x/public_media_origin"/i
        body=docs[i].encode()
        meta={"status":200,"provider":"page","request_url":by[i].original_url,"post_id":i,
              "body_file":"page.body.gz","sha256":sha256(body).hexdigest()}
        write_json(base/"page.json",meta)
        (base/"page.body.gz").write_bytes(gzip.compress(body))
    native=cached_native_entities(tmp_path,by)
    assert set(native)=={"1","2"}
    assert list(origins(native))==[("1","2")]
    source=("public_x_native_source_status",ATTACHMENT)
    assert attributed_repost(by["1"],by["2"],{MEDIA_ID,CDN},{MEDIA_ID,CDN},{},set(),source,independent_allow=True)
    assert not attributed_repost(by["1"],by["2"],{MEDIA_ID,CDN},{MEDIA_ID,CDN},{},set(),source)
    assert not attributed_repost(by["1"],by["2"],{MEDIA_ID,CDN},{MEDIA_ID,CDN},{},set(),("explicit_creator_credit",""),independent_allow=True)
    for change in ({"source_user_id":"999"},{"source_author":"Different"},{"media_id":"2199999999999999999"},
                   {"media_url":CDN+"Different"},{"source_status_id":"2"},{"expanded_url":"https://x.com/Curator/status/2/video/1"}):
        assert not origins(native | {"2":native["2"] | change})
    p=tmp_path/"raw/x/public_media_origin/2/page.json"
    write_json(p,read_json(p)|{"sha256":"0"*64})
    assert set(cached_native_entities(tmp_path,by))=={"1"}


def test_embedded_conversation_threads_different_accounts_and_conflicting_projections_are_not_primary_evidence():
    assert not parse_native(page("2","Curator",source="1",primary=False),"Curator","2")
    assert not parse_native(page("2","Curator",source="1"),"Maker","2")
    assert not parse_native(page("2","Curator",source="1",conflicting=True),"Curator","2")
    assert not parse_native(page("2","Curator",source="1",canonical="https://x.com/Curator/status/999"),"Curator","2")
