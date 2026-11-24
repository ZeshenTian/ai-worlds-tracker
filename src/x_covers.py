"""Cache original X attachments as directory covers when demo screenshots are unavailable."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from html import unescape
from http.client import HTTPException
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image, ImageOps

from .links import post_id
from .storage import read_json, run_lock, write_json


POST = re.compile(r"https://(?:www\.)?(?:x|twitter)\.com/(?:[A-Za-z0-9_]+|i/web)/status/(\d+)/?")
ATTACHMENTS = re.compile(r'"expanded_url"\s*:\s*"(https://(?:www\.)?(?:x|twitter)\.com/(?:[\w]+|i/web)/status/(\d+)/(?:photo|video)/(\d+))"|"media_url_https"\s*:\s*"([^"\s]+)"')
IMAGE_PATH = re.compile(r"/(?:media/[\w.-]+|(?:amplify_video_thumb|ext_tw_video_thumb)/[\w/-]+(?:\.[\w]+)?|tweet_video_thumb/[\w.-]+)")


def public_post_url(source):
    if not isinstance(source, str):
        return None
    try:
        parts = urlsplit(source)
        identifier = post_id(source)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username is not None or port is not None:
        return None
    path = parts.path.split("/status/", 1)[0]
    return f"https://x.com{path}/status/{identifier}"


def same_post_url(first, second):
    if not public_post_url(first) or not public_post_url(second):
        return False
    return post_id(first) == post_id(second)


def media_kind(url):
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.netloc != "pbs.twimg.com" or parsed.fragment
            or not IMAGE_PATH.fullmatch(parsed.path)):
        return None
    return "photo" if parsed.path.startswith("/media/") else "video_preview"


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            fields = dict(attrs)
            self.meta[fields.get("property") or fields.get("name")] = fields.get("content")


def page_metadata(html):
    parser = Metadata()
    head_end = html.lower().find("</head>")
    parser.feed(html[:head_end + 7] if head_end >= 0 else html)
    return parser.meta


def missing_reason(meta, identifier, entities=()):
    canonical = POST.fullmatch(meta.get("og:url") or "")
    if not canonical or canonical[1] != identifier:
        return "public_metadata_unavailable"
    image = urlsplit(meta.get("og:image") or "")
    if image.hostname == "pbs.twimg.com":
        if image.path.startswith("/card_img/"):
            return "link_card_only"
        if image.path.startswith("/profile_images/"):
            return "profile_image_only"
    preview = meta.get("og:image")
    if media_kind(preview) and any(owner != identifier and asset_path(url) == asset_path(preview)
                                   for owner, _, url, _ in entities):
        return "other_post_media_only"
    return "post_attachment_unconfirmed"


def attached_media(html):
    # Public X pages include attachment objects as JSON or as JSON escaped inside a hydration script.
    structured = re.sub(r'\\+"', '"', unescape(html)).replace(r"\/", "/")
    source = None
    attachments = []
    for match in ATTACHMENTS.finditer(structured):
        if match[1]:
            source = (match[1], match[2], int(match[3]), match.end())
        elif source:
            link, owner, order, offset = source
            candidate = match[4]
            if match.start() - offset < 2200 and media_kind(candidate):
                attachments.append((owner, order, candidate, link))
            source = None
    return attachments


def asset_path(value):
    return urlsplit(value).path.rsplit(".", 1)[0]


class ArticleCover(HTMLParser):
    """Read the cover inside X's article attachment link, scoped to the original post."""

    def __init__(self, identifier, preview):
        super().__init__()
        self.link_pattern = re.compile(rf"/[A-Za-z0-9_]+/article/{re.escape(identifier)}/media/[0-9]+")
        self.preview = preview
        self.link = None
        self.media = None

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "a":
            href = fields.get("href") or ""
            self.link = (f"https://x.com{href}" if fields.get("data-article-part") == "cover"
                         and self.link_pattern.fullmatch(href) else None)
        if tag == "img" and self.link and fields.get("alt") == "Article cover image":
            src = fields.get("src") or ""
            if media_kind(src) == "photo" and asset_path(src) == asset_path(self.preview):
                self.media = {"media_url": self.preview, "media_kind": "photo", "attachment_url": self.link}

    def handle_endtag(self, tag):
        if tag == "a":
            self.link = None


def post_media(html, identifier, meta=None, entities=None):
    """Require an attachment belonging to this exact post, excluding avatars, cards and quoted posts."""
    meta = page_metadata(html) if meta is None else meta
    canonical = POST.fullmatch(meta.get("og:url") or "")
    if not canonical or canonical[1] != identifier:
        return None
    entities = attached_media(html) if entities is None else entities
    attachments = [(order, candidate, link) for owner, order, candidate, link in entities if owner == identifier]
    preview = meta.get("og:image")
    if not attachments:
        if media_kind(preview) == "photo" and 'data-article-part="cover"' in html:
            article = ArticleCover(identifier, preview)
            article.feed(html)
            return article.media
        return None
    _, url, attachment = min(attachments, key=lambda item: item[0])
    # Prefer X's display variant only when it represents the same original attachment.
    if media_kind(preview) and asset_path(preview) == asset_path(url):
        url = preview
    return {"media_url": url, "media_kind": media_kind(url), "attachment_url": attachment}


class ApprovedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if POST.fullmatch(req.full_url):
            allowed = POST.fullmatch(newurl) and post_id(newurl) == post_id(req.full_url)
        else:
            allowed = media_kind(req.full_url) and media_kind(newurl)
        if not allowed:
            raise ValueError("redirect left public post or its media CDN")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit):
    if not POST.fullmatch(url) and not media_kind(url):
        raise ValueError("unsupported media source")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AIWorldsCatalog/1.0)"})
    with build_opener(ApprovedRedirect()).open(request, timeout=15) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("response exceeds size limit")
        return data


def cache_recent(cache, days):
    try:
        age = datetime.now(UTC) - datetime.fromisoformat(cache["checked_at"])
        return timedelta(0) <= age < timedelta(days=days)
    except (KeyError, TypeError, ValueError):
        return False


def discover(root, source, *, refresh=False):
    identifier = post_id(source)
    signal_file = root / "raw/x/signals" / f"{identifier}.json"
    if signal_file.exists():
        signal = read_json(signal_file)
        url = signal.get("media_url")
        if (str(signal.get("tweet_id") or signal.get("id") or identifier) == identifier and media_kind(url)):
            return {"media_url": url, "media_kind": media_kind(url), "discovered_via": "cached_x_signal",
                    "source_url": source}
    cached_file = root / "raw/x/cover_sources" / f"{identifier}.json"
    cache = read_json(cached_file) if cached_file.exists() else {}
    if not refresh and same_post_url(cache.get("source_url"), source):
        if media_kind(cache.get("media_url")) or cache_recent(cache, 1):
            return cache
    now = datetime.now(UTC).isoformat()
    try:
        payload = fetch(public_post_url(source), 4_000_000)
        html = payload.decode("utf-8", errors="replace")
        meta = page_metadata(html)
        entities = attached_media(html)
        media = post_media(html, identifier, meta, entities)
        info = media or {"reason": missing_reason(meta, identifier, entities)}
    except (OSError, ValueError, HTTPException) as error:
        if (same_post_url(cache.get("source_url"), source) and (cache.get("media_url") or
                cache.get("reason") in {"link_card_only", "profile_image_only", "post_attachment_unconfirmed", "other_post_media_only"})):
            return cache
        info = {"reason": "source_unavailable", "error_type": type(error).__name__}
    info.update(source_url=source, discovered_via="public_x_post", checked_at=now)
    write_json(cached_file, info)
    return info


def render(data, target, *, frame_index=0):
    with Image.open(BytesIO(data)) as image:
        image.seek(frame_index)
        if image.format not in {"JPEG", "PNG", "WEBP", "GIF"}:
            raise ValueError("unsupported attachment format")
        width, height = image.size
        if min(width, height) < 96 or width * height > 36_000_000:
            raise ValueError("unsupported attachment dimensions")
        frame = ImageOps.exif_transpose(image).convert("RGB")
        cover = ImageOps.pad(frame, (1152, 648), method=Image.Resampling.LANCZOS, color="#101519")
        with NamedTemporaryFile(dir=target.parent, suffix=".webp", delete=False) as stream:
            temp = Path(stream.name)
        try:
            cover.save(temp, "WEBP", quality=82)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    return width, height


def build(rows, root, thumbnails, *, check_all=False, refresh=False, jobs=3):
    state_file = root / "state/x_covers.json"
    thumbnails.mkdir(parents=True, exist_ok=True)
    with run_lock(root / "state/.x-covers"):
        state = read_json(state_file) if state_file.exists() else {}
        health_file = root / "state/demo_health.json"
        health = read_json(health_file) if health_file.exists() else {}

        def process(row):
            key = row["world_id"]
            source = row["original_post_url"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key) or not public_post_url(source):
                return key, None
            screenshot = f"/thumbnails/{key}.webp"
            has_demo_cover = ((health.get(key, {}).get("thumbnail_url") == screenshot
                               or row.get("thumbnail_url") == screenshot) and (thumbnails / f"{key}.webp").is_file())
            if has_demo_cover and not check_all:
                return key, None
            previous = state.get(key, {})
            filename = f"{key}-x.webp"
            target = thumbnails / filename
            if (not refresh and previous.get("source_url") == source and previous.get("thumbnail_url") == f"/thumbnails/{filename}"
                    and target.is_file()):
                return key, None
            media = discover(root, source, refresh=refresh)
            if has_demo_cover or not media.get("media_url"):
                return key, None
            try:
                data = fetch(media["media_url"], 12_000_000)
                width, height = render(data, target)
            except (OSError, ValueError, HTTPException, Image.DecompressionBombError) as error:
                print(f"{key} media unavailable ({type(error).__name__})", flush=True)
                return key, None
            entry = {**media, "source_url": source, "thumbnail_url": f"/thumbnails/{filename}",
                     "checked_at": datetime.now(UTC).isoformat(), "source_sha256": sha256(data).hexdigest(),
                     "source_width": width, "source_height": height}
            return key, entry

        # One state writer and atomic image replacement keep uploads and retries consistent.
        unique = {row["world_id"]: row for row in rows}
        for key, row in unique.items():
            if key in state and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key):
                target = thumbnails / f"{key}-x.webp"
                previous_url = state[key].get("source_url")
                if previous_url != row["original_post_url"] and same_post_url(previous_url, row["original_post_url"]):
                    state[key]["source_url"] = row["original_post_url"]
                    write_json(state_file, state)
                if state[key].get("source_url") != row["original_post_url"] or not target.is_file():
                    del state[key]
                    write_json(state_file, state)
                    target.unlink(missing_ok=True)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for key, entry in pool.map(process, unique.values()):
                if entry:
                    state[key] = entry
                    write_json(state_file, state)
                    print(key, entry["media_kind"], flush=True)
        if not state_file.exists():
            write_json(state_file, state)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--input", type=Path, action="append", help="Case JSON. Repeat to cover several batches.")
    parser.add_argument("--thumbnails", type=Path, default=Path("platform/public/thumbnails"))
    parser.add_argument("--check-all", action="store_true", help="Check post metadata even when a demo screenshot exists.")
    parser.add_argument("--refresh", action="store_true", help="Revalidate cached public sources.")
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=3)
    args = parser.parse_args()
    rows = [row for path in args.input or [args.data_dir / "exports/ai_worlds.json"] for row in read_json(path)]
    state = build(rows, args.data_dir, args.thumbnails, check_all=args.check_all, refresh=args.refresh, jobs=args.jobs)
    print(f"{len(state)} X media covers cached")


if __name__ == "__main__":
    main()
