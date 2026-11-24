"""Collect project images from author-published galleries, player pages and repository READMEs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from PIL import Image

from .storage import read_json, run_lock, write_json
from .x_covers import cache_recent, render


SOURCES = {
    "github.com": r"/[\w.-]+/[\w.-]+/?",
    "devpost.com": r"/software/[\w-]+/?",
    "developers.openai.com": r"/showcase/[\w-]+/?",
    "www.aigameshare.com": r"/games/[\w-]+/?",
}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
UNRELATED = re.compile(r"logo|badge|shields\.io|favicon|avatar|brand[-_ ]mark|wireframe|flowchart|architecture diagram|system diagram|pitch deck|concept art|open.graph|cover-generated|placeholder|software logo|qr.?code", re.I)
RENDER = re.compile(r"screen.?shot|game.?play|in.game|preview|playthrough|captur|racing|level|world|scene|截图|画面|実行画面|スクリーンショット", re.I)


def source_host(url):
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    pattern = SOURCES.get(parts.netloc)
    if parts.scheme == "https" and pattern and re.fullmatch(pattern, parts.path):
        return parts.netloc
    return None


def allowed_image(url, source):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username is not None or parts.fragment or ".." in unquote(parts.path).split("/"):
        return False
    owner = source_host(source)
    path = urlsplit(source).path.rstrip("/")
    if owner == "github.com":
        repo, image_path = path.lower(), parts.path.lower()
        return ((parts.netloc == "raw.githubusercontent.com" and image_path.startswith(repo + "/"))
                or (parts.netloc == "github.com" and (image_path.startswith(repo + "/raw/")
                                                     or image_path.startswith("/user-attachments/assets/")))
                or parts.netloc in {"user-images.githubusercontent.com", "private-user-images.githubusercontent.com"})
    if owner == "devpost.com":
        return ((parts.netloc == "d112y698adiu2z.cloudfront.net" and parts.path.startswith("/photos/production/software_photos/"))
                or (parts.netloc == "i.ytimg.com" and re.fullmatch(r"/vi/[\w-]{11}/hq(?:default|[123])\.jpg", parts.path) is not None)
                or (parts.netloc == "i.vimeocdn.com" and parts.path.startswith("/video/")))
    if owner == "developers.openai.com":
        return ((parts.netloc == "cdn.openai.com" and parts.path.startswith("/devhub" + path + "/"))
                or (parts.netloc == owner and parts.path.startswith(path + "/")))
    return (owner == "www.aigameshare.com" and parts.netloc == owner
            and re.fullmatch(r"/api/games/[\w-]+/thumbnail", parts.path) is not None)


def download(client, url, source, *, page=False):
    limit = 4_000_000 if page else 15_000_000
    for redirect in range(5):
        if page:
            first_page = url.rstrip("/") == source.rstrip("/") and source_host(url)
            gallery = (source_host(source) == "github.com" and url.startswith(source.rstrip("/") + "/tree/")
                       and re.search(r"/(?:screenshots?|screen-captures?|gameplay-shots)/?$", urlsplit(url).path, re.I))
            canonical_repo = (redirect and source_host(source) == source_host(url) == "github.com"
                              and urlsplit(url).path.strip("/").split("/")[-1].casefold() == urlsplit(source).path.strip("/").split("/")[-1].casefold())
            permitted = first_page or gallery or canonical_repo
        else:
            permitted = allowed_image(url, source)
        if not permitted:
            raise ValueError("URL is outside the project or its media host")
        with client.stream("GET", url, follow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(str(response.url), response.headers["location"])
                continue
            response.raise_for_status()
            payload = bytearray()
            for chunk in response.iter_bytes():
                payload.extend(chunk)
                if len(payload) > limit:
                    raise ValueError("project asset exceeds byte limit")
            return bytes(payload)
    raise ValueError("too many redirects")


def unpack_props(value):
    if isinstance(value, list):
        if len(value) == 2 and value[0] in (0, 1):
            return unpack_props(value[1])
        return [unpack_props(item) for item in value]
    if isinstance(value, dict):
        return {key: unpack_props(item) for key, item in value.items()}
    return value


class ProjectGallery(HTMLParser):
    def __init__(self, source, title=""):
        super().__init__()
        self.title = title
        self.readme_heading = ""
        self.source = source
        self.original_source = source
        self.vimeo = []
        self.host = source_host(source)
        self.stack = []
        self.items = []
        self.folders = []

    def include(self, url, caption, kind, rank):
        if not url:
            return
        url = urljoin(self.source, url)
        if self.host == "github.com" and url.startswith(self.source.rstrip("/") + "/raw/"):
            repo_path = urlsplit(self.source).path.rstrip("/")
            tail = url.split("/raw/", 1)[1].removeprefix("refs/heads/")
            url = f"https://raw.githubusercontent.com{repo_path}/{tail}"
        caption = " ".join((caption or "").split())[:400]
        label = urlsplit(url).path + " " + caption
        if allowed_image(url, self.source) and not UNRELATED.search(label):
            self.items.append({"media_url": url, "caption": caption or None, "discovered_via": kind, "rank": rank,
                               "media_page_url": self.source})

    def showcase_artifacts(self, node):
        if isinstance(node, list):
            for item in node:
                self.showcase_artifacts(item)
        elif isinstance(node, dict):
            for art in node.get("artifacts", []) if isinstance(node.get("artifacts"), list) else []:
                if not isinstance(art, dict) or art.get("type") not in {"snapshot", "image", "video"}:
                    continue
                url = art.get("poster") if art["type"] == "video" else art.get("src")
                alt = art.get("alt") or ""
                notes = f"{alt} {node.get('evidenceNote', '')}"
                if re.search(r"generated (?:menu|concept|image|material)|material atlas|concept art|north.star|diagram|reference image", notes, re.I):
                    continue
                if art["type"] == "image" and not re.search(r"capture|screenshot|finished|current|final|scene|view", notes, re.I):
                    continue
                score = 60 + 15 * bool(re.search(r"finished|final|current|recorded.+gameplay", notes, re.I)) + 5 * (art["type"] == "video")
                self.include(url, alt, "official_showcase", score)
            for val in node.values():
                self.showcase_artifacts(val)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        parents = [attr for _, attr in self.stack]
        if self.host == "github.com" and tag == "meta" and attrs.get("property") == "og:url":
            canonical = attrs.get("content")
            if (source_host(canonical) == "github.com" and urlsplit(canonical).path.strip("/").split("/")[-1].casefold()
                    == urlsplit(self.original_source).path.strip("/").split("/")[-1].casefold()):
                self.source = canonical.rstrip("/")
        if self.host == "developers.openai.com" and tag == "astro-island":
            props = attrs.get("props", "")
            if "iterationSteps" in props:
                try:
                    self.showcase_artifacts(unpack_props(json.loads(props)))
                except (ValueError, RecursionError):
                    pass
        if self.host == "github.com" and re.fullmatch(r"h[1-6]", tag):
            self.readme_heading = ""
        if self.host == "github.com" and tag == "a":
            ref = urljoin(self.source, attrs.get("href", ""))
            prefix = self.source.rstrip("/") + "/tree/"
            blob = self.source.rstrip("/") + "/blob/"
            in_readme = any(t == "article" and "markdown-body" in a.get("class", "") for t, a in self.stack)
            filename = unquote(urlsplit(ref).path).rsplit("/", 1)[-1]
            if (ref.startswith(blob) and re.search(r"\.(?:png|jpe?g|webp|gif)$", filename, re.I)
                    and RENDER.search(ref.rsplit("/blob/", 1)[-1]) and in_readme):
                self.include(ref.replace("/blob/", "/raw/", 1), attrs.get("title") or filename, "repository_linked_screenshot", 3)
            if ref.startswith(prefix) and re.search(r"/(?:screenshots?|screen-captures?|gameplay-shots)/?$", urlsplit(ref).path, re.I):
                if ref not in self.folders:
                    self.folders.append(ref)
        if self.host == "devpost.com" and tag == "iframe" and any(a.get("id") == "gallery" for a in parents):
            video = urlsplit(attrs.get("src") or "")
            clip = re.fullmatch(r"/embed/([\w-]{11})", video.path)
            if video.scheme == "https" and video.netloc in {"www.youtube.com", "www.youtube-nocookie.com"} and clip:
                self.include(f"https://i.ytimg.com/vi/{clip[1]}/hqdefault.jpg", attrs.get("title"), "project_gallery_video_preview", 2)
                for variant in ("hq2", "hq1", "hq3"):
                    self.include(f"https://i.ytimg.com/vi/{clip[1]}/{variant}.jpg", attrs.get("title"), "project_gallery_video_still", 1)
            elif video.netloc == "player.vimeo.com" and video.scheme == "https" and re.fullmatch(r"/video/\d+", video.path):
                self.vimeo.append(video.path.rsplit("/", 1)[1])
        if tag == "img":
            src, alt = attrs.get("src"), attrs.get("alt", "")
            if self.host == "github.com" and any(t == "article" and "markdown-body" in a.get("class", "") for t, a in self.stack):
                actual = attrs.get("data-canonical-src") or src
                section = re.search(r"screenshots?|gallery|captures|截图|画廊|スクリーンショット", self.readme_heading, re.I)
                title = re.sub(r"[^\w]", "", self.title).casefold()
                label = re.sub(r"[^\w]", "", alt).casefold()
                same_title = len(label) >= 3 and (label in title or (title and title in label))
                art = actual and re.search(r"(?:/|[-_])(?:cover|poster|keyart|key-art|banner)[./\-_]", actual, re.I)
                if actual and (section or RENDER.search(f"{alt} {actual}") or len(alt.split()) > 3):
                    self.include(actual, alt, "repository_readme", 5 + int(bool(RENDER.search(alt))))
                elif actual and same_title and art:
                    self.include(actual, alt, "repository_project_poster", 2)
            elif self.host == "devpost.com" and any(a.get("id") == "gallery" for a in parents):
                anchor = next((a for t, a in reversed(self.stack) if t == "a" and "data-lightbox" in a), {})
                if anchor and "software_photo_image" in attrs.get("class", ""):
                    caption = anchor.get("data-title") or alt
                    score = 12 if RENDER.search(anchor.get("data-title", "")) else 7
                    self.include(anchor.get("href") or src, caption, "devpost_gallery", score)
            elif self.host == "www.aigameshare.com" and any("game-player__start-poster" in a.get("class", "").split() for a in parents):
                if "game-player__start-thumbnail" in attrs.get("class", "").split():
                    self.include(src, alt, "author_game_player", 5)
        if tag not in VOID:
            self.stack.append((tag, attrs))

    def handle_data(self, data):
        if self.host == "github.com" and any(re.fullmatch(r"h[1-6]", t) for t, _ in self.stack):
            self.readme_heading = (self.readme_heading + data)[-200:]

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def include_vimeo(self, client):
        for clip in self.vimeo[:2]:
            response = client.get("https://vimeo.com/api/oembed.json", params={"url": f"https://vimeo.com/{clip}", "width": 1280}, follow_redirects=False)
            if response.status_code == 200 and len(response.content) < 100000:
                info = response.json()
                if str(info.get("video_id")) == clip:
                    self.include(info.get("thumbnail_url"), info.get("title"), "project_gallery_video_preview", 2)

    def candidates(self):
        unique = {}
        for item in sorted(self.items, key=lambda entry: -entry["rank"]):
            unique.setdefault(item["media_url"], item)
        return list(unique.values())


class ScreenshotFolder(HTMLParser):
    def __init__(self, gallery, folder):
        super().__init__()
        self.gallery = gallery
        self.folder = folder

    def handle_starttag(self, tag, attributes):
        if tag != "a":
            return
        href = urljoin(self.folder, dict(attributes).get("href", ""))
        prefix = self.folder.replace("/tree/", "/blob/", 1).rstrip("/") + "/"
        if href.startswith(prefix):
            filename = unquote(urlsplit(href).path).rsplit("/", 1)[-1]
            if re.fullmatch(r"[^/]+\.(?:png|jpe?g|webp|gif)", filename, re.I):
                self.gallery.include(href.replace("/blob/", "/raw/", 1), filename, "repository_screenshot_gallery", 6)


def cover_metadata(entry):
    if entry.get("discovered_via") in {"author_game_player", "project_gallery_video_preview", "repository_project_poster"}:
        return {"cover_source": "project_poster", "caption": "作品页面海报",
                "author_caption": entry.get("author_caption") or entry.get("caption")}
    caption = entry.get("caption")
    if not caption and entry.get("discovered_via") == "project_gallery_video_still":
        caption = "作者演示视频画面"
    return {"cover_source": "project_media", "caption": caption}


def build(rows, root, thumbnails, *, jobs=5, refresh=False):
    state_path = root / "state/primary_covers.json"
    thumbnails.mkdir(parents=True, exist_ok=True)
    cache_dir = root / "raw/project_covers"
    with run_lock(root / "state/.project-covers"), httpx.Client(timeout=16) as client:
        state = read_json(state_path) if state_path.exists() else {}
        def process(row):
            key, source = row["world_id"], row["original_post_url"]
            if (row.get("source_kind") != "primary_page" or not re.fullmatch(r"[\w-]{1,128}", key, re.ASCII)
                    or not source_host(source)):
                return key, None
            target = thumbnails / f"{key}-project.webp"
            if (thumbnails / f"{key}.webp").is_file() or (thumbnails / f"{key}-x.webp").is_file():
                return key, None
            old = state.get(key, {})
            same = old.get("source_url") == source
            if same and not refresh and old.get("thumbnail_url") == "/thumbnails/" + target.name and target.is_file():
                needs_poster_label = old.get("discovered_via") == "author_game_player" and old.get("cover_source") != "project_poster"
                needs_video_caption = old.get("discovered_via") == "project_gallery_video_still" and not old.get("caption")
                if needs_poster_label or needs_video_caption:
                    return key, {**old, **cover_metadata(old)}
                if old.get("discovered_via") != "devpost_gallery" or "source_format" in old:
                    return key, None
            excluded = old.get("excluded_media", []) if same else []
            cache = cache_dir / f"{key}.json"
            memo = read_json(cache) if cache.exists() else {}
            try:
                cached = memo.get("candidates") or (memo.get("version") == 5 and cache_recent(memo, 1))
                if source_host(source) == "devpost.com" and (memo.get("version") or 0) < 5:
                    cached = False
                if not refresh and memo.get("source_url") == source and cached:
                    candidates = memo["candidates"]
                else:
                    parser = ProjectGallery(source, row.get("title") or "")
                    parser.feed(download(client, source, source, page=True).decode("utf-8", errors="replace"))
                    if parser.vimeo and not parser.candidates():
                        parser.include_vimeo(client)
                    if not parser.candidates() and parser.folders:
                        folder = parser.folders[0]
                        collection = ScreenshotFolder(parser, folder)
                        collection.feed(download(client, folder, parser.source, page=True).decode("utf-8", errors="replace"))
                    candidates = parser.candidates()
                    write_json(cache, {"version": 5, "source_url": source, "checked_at": datetime.now(UTC).isoformat(), "candidates": candidates})
                preferred = old.get("preferred_media") if same else None
                if preferred:
                    candidates = sorted(candidates, key=lambda x: x["media_url"] != preferred)
                for item in candidates[:12]:
                    if item["media_url"] in excluded:
                        continue
                    try:
                        data = download(client, item["media_url"], item.get("media_page_url", source))
                        with Image.open(BytesIO(data)) as original:
                            w, h = original.size
                            image_format = original.format
                            frame_index = min(120, getattr(original, "n_frames", 1) // 3)
                            if min(w, h) < 170 or max(w, h) < 440 or max(w, h) > min(w, h) * 4.5:
                                continue
                        w, h = render(data, target, frame_index=frame_index)
                    except (OSError, EOFError, ValueError, httpx.HTTPError, Image.DecompressionBombError):
                        continue
                    metadata = cover_metadata(item)
                    checksum = sha256(data).hexdigest()
                    if same and old.get("source_sha256") == checksum and old.get("visually_classified"):
                        metadata = {"cover_source": old["cover_source"], "caption": old.get("caption"),
                                    "author_caption": old.get("author_caption"), "visually_classified": True}
                    return key, {**{k: v for k, v in item.items() if k != "rank"}, "source_url": source,
                                 "thumbnail_url": f"/thumbnails/{target.name}", **metadata,
                                 "checked_at": datetime.now(UTC).isoformat(), "source_width": w, "source_height": h,
                                 "source_sha256": checksum, "source_format": image_format, "source_frame": frame_index,
                                 "excluded_media": excluded, "preferred_media": preferred,
                                 "author": row.get("author_name") or row.get("author_handle")}
            except (ValueError, httpx.HTTPError, OSError) as error:
                print(key, type(error).__name__, flush=True)
            if not same and old:
                target.unlink(missing_ok=True)
                return key, {}
            return key, None

        unique = {row["world_id"]: row for row in rows}
        for key, row in unique.items():
            previous = state.get(key)
            if not previous or not re.fullmatch(r"[\w-]{1,128}", key, re.ASCII):
                continue
            owned = thumbnails / f"{key}-project.webp"
            if previous.get("source_url") != row["original_post_url"]:
                state.pop(key)
                owned.unlink(missing_ok=True)
                write_json(state_path, state)
            elif previous.get("thumbnail_url") and not owned.is_file():
                previous["thumbnail_url"] = None
                write_json(state_path, state)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for key, entry in pool.map(process, unique.values()):
                if entry is not None:
                    if entry:
                        state[key] = entry
                        print(key, entry["discovered_via"], flush=True)
                    else:
                        state.pop(key, None)
                    write_json(state_path, state)
        if not state_path.exists():
            write_json(state_path, state)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append")
    parser.add_argument("--data-dir", default=Path("data"), type=Path)
    parser.add_argument("--thumbnails", default=Path("platform/public/thumbnails"), type=Path)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=5)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    rows = [r for path in args.input or [args.data_dir / "exports/ai_worlds.json"] for r in read_json(path)]
    state = build(rows, args.data_dir, args.thumbnails, jobs=args.jobs, refresh=args.refresh)
    print(sum(bool(row.get("thumbnail_url")) for row in state.values()), "project media covers")


if __name__ == "__main__":
    main()
