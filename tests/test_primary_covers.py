from io import BytesIO
from pathlib import Path

from PIL import Image

from src import primary_covers as covers
from src.storage import read_json, write_json


REPO = "https://github.com/author/game"
DEVPOST = "https://devpost.com/software/example"
PHOTO = "https://d112y698adiu2z.cloudfront.net/photos/production/software_photos/1/2/3/datas/original.jpg"


def parse(source, html):
    gallery = covers.ProjectGallery(source)
    gallery.feed(html)
    return gallery.candidates()


def test_repo_images_belong_to_this_readme_and_exclude_branding():
    html = """<img alt="gameplay screenshot" src="/author/game/raw/main/outside.png">
       <article class="markdown-body"><img alt="Brand logo" src="/author/game/raw/main/brand-logo.png">
       <img alt="Play online" src="https://img.shields.io/badge/play-now-green">
       <img alt="Gameplay screenshot" src="/other/game/raw/main/mismatched.png">
       <img alt="Actual gameplay screenshot" src="/author/game/raw/main/docs/arena.png"></article>"""
    selected = parse(REPO, html)
    assert len(selected) == 1
    assert selected[0]["media_url"] == "https://raw.githubusercontent.com/author/game/main/docs/arena.png"
    assert selected[0]["caption"] == "Actual gameplay screenshot"


def test_devpost_gallery_respects_photo_attribution():
    photo = f'<a data-lightbox="9" data-title="Inside the playable scene" href="{PHOTO}"><img class="software_photo_image" alt="screenshot 1"></a>'
    assert not parse(DEVPOST, photo)
    assert parse(DEVPOST, "<div id=gallery>" + photo + "</div>")[0]["caption"] == "Inside the playable scene"


def test_player_excludes_recommended_games_and_platform_logo():
    html = """<div class="game-player__next-island"><img class="game-player__start-thumbnail" src="/api/games/other/thumbnail"></div>
              <img src="/brand/logo.png"><div class="game-player__start-poster"><img class="game-player__start-thumbnail" alt="Example" src="/api/games/example/thumbnail"></div>"""
    got = parse("https://www.aigameshare.com/games/example", html)
    assert [r["media_url"] for r in got] == ["https://www.aigameshare.com/api/games/example/thumbnail"]


def test_showcase_rejects_other_projects_and_concept_art():
    parser = covers.ProjectGallery("https://developers.openai.com/showcase/example")
    parser.showcase_artifacts({"evidence": "exact", "artifacts": [
        {"type": "snapshot", "src": "/showcase/wrong/finished.webp", "alt": "Final screenshot"},
        {"type": "image", "src": "/showcase/example/ref.webp", "alt": "Generated concept art"},
        {"type": "snapshot", "src": "/showcase/example/final.webp", "alt": "Finished scene"}]})
    assert [r["media_url"] for r in parser.candidates()] == ["https://developers.openai.com/showcase/example/final.webp"]


def test_cached_author_cover_preserves_demo_images(monkeypatch, tmp_path):
    image = BytesIO()
    Image.new("RGB", (700, 400), "navy").save(image, "JPEG")
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    (thumbs / "protected.webp").write_bytes(b"existing screenshot")
    write_json(tmp_path / "state/demo_health.json", {"protected": {"thumbnail_url": "/thumbnails/protected.webp"}})
    html = f'<div id="gallery"><a data-lightbox="1" href="{PHOTO}"><img class="software_photo_image" alt="A game screenshot"></a></div>'
    requests = []
    def fake(client, url, source, page=False):
        requests.append(url)
        return html.encode() if page else image.getvalue()
    monkeypatch.setattr(covers, "download", fake)
    rows = [{"world_id": k, "original_post_url": DEVPOST, "source_kind": "primary_page", "author_name": "Ada"} for k in ("protected", "game")]
    first = covers.build(rows, tmp_path, thumbs)
    assert covers.build(rows, tmp_path, thumbs) == first
    assert requests == [DEVPOST, PHOTO]
    assert set(first) == {"game"}
    assert first["game"]["cover_source"] == "project_media"
    assert first["game"]["source_url"] == DEVPOST and first["game"]["author"] == "Ada"
    assert read_json(tmp_path / "state/primary_covers.json") == first
    assert (thumbs / "protected.webp").read_bytes() == b"existing screenshot"
    with Image.open(thumbs / Path(first["game"]["thumbnail_url"]).name) as art:
        assert (art.format, art.size) == ("WEBP", (1152, 648))


def test_project_posters_keep_original_caption_separate_from_screenshot_label():
    item = {"discovered_via": "author_game_player", "caption": "Pulsar Drift"}
    assert covers.cover_metadata(item) == {
        "cover_source": "project_poster", "caption": "作品页面海报", "author_caption": "Pulsar Drift",
    }


def test_author_gallery_video_requires_an_embedded_video_in_the_same_gallery():
    iframe = '<iframe src="https://www.youtube.com/embed/abcdefghijk"></iframe>'
    assert not parse(DEVPOST, iframe)
    media = parse(DEVPOST, '<div id="gallery">' + iframe + '</div>')
    assert media[0]["media_url"] == "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"
    assert covers.cover_metadata(media[0])["cover_source"] == "project_poster"


def test_project_screenshot_folders_keep_files_scoped_to_repo_directory():
    gallery = covers.ProjectGallery(REPO)
    folder = REPO + "/tree/main/docs/screenshots"
    gallery.feed(f'<a href="{folder}">Screenshots</a>')
    assert gallery.folders == [folder]
    links = covers.ScreenshotFolder(gallery, folder)
    links.feed(f'<a href="{REPO}/blob/main/docs/screenshots/level.png">Level</a>'
               f'<a href="{REPO}/blob/main/assets/unrelated.png">Other</a>')
    assert [item["media_url"] for item in gallery.candidates()] == [
        "https://raw.githubusercontent.com/author/game/main/docs/screenshots/level.png"]
