from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

from PIL import Image
import pytest

from src import x_covers
from src.storage import read_json, write_json


POST = "https://x.com/creator/status/123"
PHOTO = "https://pbs.twimg.com/media/actual.jpg"


def page(canonical=POST, owner="123", media=PHOTO, image=PHOTO):
    return f"""<html><head><meta property="og:url" content="{canonical}">
       <meta property="og:image" content="{image}"></head><body>
       <script>const tweet={{"media":[{{"expanded_url":"https://x.com/creator/status/{owner}/photo/1",
       "media_url_https":"{media}"}}]}}</script></body></html>"""


def image_data():
    encoded = BytesIO()
    Image.new("RGB", (320, 480), "teal").save(encoded, "JPEG")
    return encoded.getvalue()


def test_metadata_requires_own_post_attachment_and_ignores_external_card_preview():
    assert x_covers.post_media(page(owner="234"), "123") is None
    assert x_covers.post_media(page(canonical="https://x.com/creator/status/234"), "123") is None
    original = x_covers.post_media(page(image="https://pbs.twimg.com/media/other.jpg"), "123")
    assert original["media_url"] == PHOTO
    assert original["attachment_url"].endswith("/123/photo/1")
    same_image = "https://pbs.twimg.com/media/actual?format=webp&name=large"
    assert x_covers.post_media(page(image=same_image), "123")["media_url"] == same_image


@pytest.mark.parametrize("url", [
    "http://pbs.twimg.com/media/photo.jpg", "https://pbs.twimg.com/profile_images/123/me.jpg",
    "https://pbs.twimg.com/card_img/123/share.jpg", "https://pbs.twimg.com.evil.test/media/photo.jpg",
    "https://pbs.twimg.com@evil.test/media/photo.jpg", "https://pbs.twimg.com:443/media/photo.jpg",
    "https://pbs.twimg.com/media/../profile_images", "file:///media/photo.jpg",
])
def test_only_original_x_cdn_media_is_eligible(url):
    assert not x_covers.media_kind(url)


def test_cached_signal_creates_case_fallback_once_without_changing_demo_state(monkeypatch, tmp_path):
    root = tmp_path / "data"
    thumbs = tmp_path / "thumbnails"
    health = {"case": {"demo_health_status": "no_demo", "thumbnail_url": None}}
    write_json(root / "state/demo_health.json", health)
    write_json(root / "raw/x/signals/123.json", {"tweet_id": "123", "media_url": PHOTO})
    calls = []

    def fetch(url, limit):
        calls.append(url)
        return image_data()

    monkeypatch.setattr(x_covers, "fetch", fetch)
    rows = [{"world_id": "case", "original_post_url": POST}]
    state = x_covers.build(rows, root, thumbs)
    assert x_covers.build(rows, root, thumbs) == state
    assert calls == [PHOTO]
    assert read_json(root / "state/demo_health.json") == health
    entry = state["case"]
    assert entry["discovered_via"] == "cached_x_signal"
    assert entry["source_url"] == POST
    assert (entry["source_width"], entry["source_height"]) == (320, 480)
    with Image.open(thumbs / Path(entry["thumbnail_url"]).name) as asset:
        assert (asset.format, asset.size) == ("WEBP", (1152, 648))


def test_public_source_discovery_is_cached_and_preserves_existing_screenshots(monkeypatch, tmp_path):
    root = tmp_path / "data"
    thumbs = tmp_path / "thumbnails"
    thumbs.mkdir()
    (thumbs / "world.webp").write_bytes(b"existing screenshot")
    write_json(root / "state/demo_health.json", {"world": {"thumbnail_url": "/thumbnails/world.webp"}})
    calls = []

    def fetch(url, limit):
        calls.append(url)
        return page().encode()

    monkeypatch.setattr(x_covers, "fetch", fetch)
    rows = [{"world_id": "world", "original_post_url": POST}]
    assert x_covers.build(rows, root, thumbs) == {}
    assert not calls
    assert x_covers.build(rows, root, thumbs, check_all=True) == {}
    assert x_covers.build(rows, root, thumbs, check_all=True) == {}
    assert calls == [POST]
    assert (thumbs / "world.webp").read_bytes() == b"existing screenshot"
    assert not (thumbs / "world-x.webp").exists()


def test_source_id_mismatch_or_unmatched_media_never_creates_cover(monkeypatch, tmp_path):
    root = tmp_path / "data"
    write_json(root / "raw/x/signals/123.json", {"tweet_id": "234", "media_url": PHOTO})
    calls = []
    def fetch(url, limit):
        calls.append(url)
        return page(owner="234").encode()
    monkeypatch.setattr(x_covers, "fetch", fetch)
    rows = [{"world_id": "case", "original_post_url": POST}]
    assert x_covers.build(rows, root, tmp_path / "thumbs") == {}
    assert x_covers.build(rows, root, tmp_path / "thumbs") == {}
    assert calls == [POST]


def test_changed_source_removes_stale_cover(monkeypatch, tmp_path):
    root = tmp_path / "data"
    thumbs = tmp_path / "covers"
    thumbs.mkdir()
    old = thumbs / "case-x.webp"
    old.touch()
    write_json(root / "state/x_covers.json", {"case": {"source_url": POST, "thumbnail_url": "/thumbnails/case-x.webp"}})
    assert x_covers.build([{"world_id": "case", "original_post_url": "https://author.example.org/case"}],
                          root, thumbs) == {}
    assert not old.exists()


def test_query_and_attachment_links_use_the_canonical_post_for_network_access():
    assert x_covers.public_post_url(POST + "/video/1?lang=en") == POST
    assert x_covers.public_post_url("https://evil.test/creator/status/123") is None


def test_missing_attachments_report_link_cards_profile_images_and_gates_separately():
    assert x_covers.missing_reason({}, "123") == "public_metadata_unavailable"
    assert x_covers.missing_reason({"og:url": POST, "og:image": "https://pbs.twimg.com/card_img/7/card"}, "123") == "link_card_only"
    assert x_covers.missing_reason({"og:url": POST, "og:image": "https://pbs.twimg.com/profile_images/7/me"}, "123") == "profile_image_only"


def test_handle_or_platform_alias_for_same_post_does_not_fetch_cached_cover(tmp_path, monkeypatch):
    root, thumbs = tmp_path / "data", tmp_path / "covers"
    thumbs.mkdir()
    (thumbs / "item-x.webp").touch()
    write_json(root / "state/x_covers.json", {"item": {"source_url": POST, "thumbnail_url": "/thumbnails/item-x.webp"}})
    monkeypatch.setattr(x_covers, "fetch", lambda *args: pytest.fail("unexpected fetch of the same post"))
    new_url = "https://twitter.com/Creator/status/123?lang=en"
    result = x_covers.build([{"world_id": "item", "original_post_url": new_url}], root, thumbs)
    assert result["item"]["source_url"] == new_url


def test_cli_accepts_multiple_incremental_batches(monkeypatch, tmp_path):
    import sys
    a, b = tmp_path / "first.json", tmp_path / "second.json"
    write_json(a, [{"world_id": "one", "original_post_url": "https://example.org/one"}])
    write_json(b, [{"world_id": "two", "original_post_url": "https://example.org/two"}])
    received = []
    def capture(rows, root, thumbnails, **options):
        received.extend(row["world_id"] for row in rows)
        return {}
    monkeypatch.setattr(x_covers, "build", capture)
    monkeypatch.setattr(sys, "argv", ["x_covers", "--input", str(a), "--input", str(b)])
    x_covers.main()
    assert received == ["one", "two"]


def test_another_posts_picture_in_social_metadata_is_recorded_as_a_gap():
    html = page(owner="234")
    entities = x_covers.attached_media(html)
    meta = x_covers.page_metadata(html)
    assert not x_covers.post_media(html, "123", meta, entities)
    assert x_covers.missing_reason(meta, "123", entities) == "other_post_media_only"
    focal = html.replace("creator/status/234/photo/1", "i/web/status/123/photo/1")
    assert x_covers.post_media(focal, "123")["media_url"] == PHOTO


def test_article_cover_under_the_focal_author_media_link_must_match_the_displayed_image():
    head = f'<meta property="og:url" content="{POST}"><meta property="og:image" content="{PHOTO}">'
    anchor = '<a data-article-part="cover" href="/creator/article/123/media/456">'
    img = f'<img alt="Article cover image" src="{PHOTO}">'
    assert x_covers.post_media(head + anchor + img + '</a>', '123') == {
        'media_url': PHOTO, 'media_kind': 'photo', 'attachment_url': 'https://x.com/creator/article/123/media/456'}
    assert not x_covers.post_media(head + anchor.replace('/123/', '/125/') + img + '</a>', '123')
    assert not x_covers.post_media(head + anchor + '</a>' + img, '123')
    assert not x_covers.post_media(head + anchor + img.replace('actual', 'other') + '</a>', '123')


def test_cdn_outage_only_defers_its_own_host_and_retries_skipped_images_next_run(tmp_path, monkeypatch):
    root, thumbs = tmp_path / "data", tmp_path / "thumbs"
    rows = []
    for index in range(8):
        source = f"https://x.com/creator/status/{index}"
        write_json(root / "raw/x/signals" / f"{index}.json", {
            "tweet_id": str(index), "media_url": f"https://pbs.twimg.com/media/pic{index}.jpg",
        })
        rows.append({"world_id": f"case-{index}", "original_post_url": source})
    # This post requires an independent fetch of the original X page.
    rows.append({"world_id": "metadata-only", "original_post_url": POST})
    requests = []
    def outage(url, limit):
        requests.append(url)
        if url == POST:
            return b"<html></html>"
        raise URLError(TimeoutError("TLS handshake timed out"))
    monkeypatch.setattr(x_covers, "fetch", outage)
    assert x_covers.build(rows, root, thumbs, jobs=1) == {}
    assert requests == [f"https://pbs.twimg.com/media/pic{i}.jpg" for i in range(3)] + [POST]
    receipts = root / "raw/x/cover_failures"
    assert len(list(receipts.glob("*.json"))) == 3
    assert not list(thumbs.iterdir())

    requests.clear()
    def recover(url, limit):
        requests.append(url)
        return image_data()
    monkeypatch.setattr(x_covers, "fetch", recover)
    restored = x_covers.build(rows, root, thumbs, jobs=1)
    assert set(restored) == {f"case-{i}" for i in range(3, 8)}
    assert len(requests) == 5
    restored = x_covers.build(rows[:3], root, thumbs, jobs=1, refresh=True)
    assert len(restored) == 8
    assert not list(receipts.glob("*.json"))


@pytest.mark.parametrize("retry", ["expired", "new_attachment"])
def test_missed_attachment_retries_after_expiry_or_url_change(tmp_path, monkeypatch, retry):
    root, thumbs = tmp_path / "data", tmp_path / "thumbs"
    signal = root / "raw/x/signals/123.json"
    write_json(signal, {"tweet_id": "123", "media_url": PHOTO})
    rows = [{"world_id": "case", "original_post_url": POST}]
    def missing(url, limit):
        raise HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr(x_covers, "fetch", missing)
    assert x_covers.build(rows, root, thumbs) == {}
    calls = []
    def recovered(url, limit):
        calls.append(url)
        return image_data()
    monkeypatch.setattr(x_covers, "fetch", recovered)
    assert x_covers.build(rows, root, thumbs) == {}
    assert not calls
    expected = PHOTO
    if retry == "expired":
        receipt, = (root / "raw/x/cover_failures").glob("*.json")
        write_json(receipt, {"checked_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat()})
    else:
        expected = PHOTO.replace("actual", "new")
        write_json(signal, {"tweet_id": "123", "media_url": expected})
    recovered_case = x_covers.build(rows, root, thumbs)["case"]
    assert calls == [expected]
    assert recovered_case["media_url"] == expected
    assert recovered_case["source_url"] == POST


def test_missing_attachment_status_does_not_disable_host(monkeypatch):
    def missing(url, limit):
        raise HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr(x_covers, "fetch", missing)
    network = x_covers.CoverRequests()
    for _ in range(5):
        with pytest.raises(HTTPError):
            network.fetch(PHOTO, 1024)
    monkeypatch.setattr(x_covers, "fetch", lambda url, limit: b"ok")
    assert network.fetch(PHOTO, 1024) == b"ok"


def test_daily_project_cache_and_hourly_media_retry_have_separate_lifetimes():
    four_hours_ago = {"checked_at": (datetime.now(UTC) - timedelta(hours=4)).isoformat()}
    assert x_covers.cache_recent(four_hours_ago, 1)
    assert not x_covers.cache_recent(four_hours_ago, days=0, hours=1)
