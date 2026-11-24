from io import BytesIO
from pathlib import Path

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
