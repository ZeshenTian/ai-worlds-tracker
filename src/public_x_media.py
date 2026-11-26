"""Verify a cached public X post's primary media entity. No network access is needed for replay."""
from hashlib import sha256
from html.parser import HTMLParser
import gzip
import json
import re
from urllib.parse import urlsplit

from .storage import read_json
from .x_covers import page_metadata
from .x_media import asset_key


JS_STRING = re.compile(r'"(?:\\.|[^"\\])*"')


class ScriptText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.inside = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False

    def handle_data(self, data):
        if self.inside and "tweet_result_by_rest_id" in data:
            self.parts.append(data)


def exact_post_url(url, handle, identifier, *, attachment=False):
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc not in {"x.com","www.x.com","twitter.com","www.twitter.com"}:
        return False
    expected = rf"/{re.escape(handle)}/status/{re.escape(identifier)}"
    if attachment:
        expected += r"/(?:photo|video)/1"
    return re.fullmatch(expected + r"/?", parts.path, re.I) is not None


def parse_native(html, handle, identifier):
    if not exact_post_url(page_metadata(html).get("og:url"), handle, identifier):
        return
    parser = ScriptText()
    parser.feed(html)
    receipts = []
    for part in parser.parts:
        for token in JS_STRING.finditer(part):
            if 'tweet_result_by_rest_id' not in token[0]:
                continue
            try:
                payload = json.loads(json.loads(token[0]))
            except (ValueError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            wrapper = (payload.get("data") or {}).get("tweet_result_by_rest_id") or {}
            obj = wrapper.get("result") or {}
            if wrapper.get("rest_id") != identifier or obj.get("rest_id") != identifier:
                continue
            # Quoted posts and conversation siblings are deliberately outside this exact GraphQL path.
            author = ((obj.get("core") or {}).get("user_results") or {}).get("result") or {}
            user = (author.get("core") or {}).get("screen_name") or ""
            if user.casefold() != handle.casefold() or not str(author.get("rest_id","")).isdecimal():
                continue
            media = obj.get("media_entities2") or []
            if len(media) != 1:
                return
            item = media[0]
            media_id = str(item.get("id_str") or "")
            cdn = asset_key(item.get("media_url_https"))
            if not re.fullmatch(r"\d{12,20}", media_id) or not cdn:
                continue
            source = (item.get("source_user_results") or {}).get("result") or {}
            receipts.append({
                "post_id": identifier, "author":user, "user_id":author["rest_id"],
                "media_id":media_id, "media_url":cdn, "expanded_url":item.get("expanded_url"),
                "source_status_id":item.get("source_status_id_str"),
                "source_user_id":source.get("rest_id"),
                "source_author":(source.get("core") or {}).get("screen_name"),
            })
    if receipts and all(r == receipts[0] for r in receipts):
        return receipts[0]


def cached_native_entities(root, by_id):
    result = {}
    for meta in (root / "raw/x/public_media_origin").glob("*/page.json"):
        identifier = meta.parent.name
        record = by_id.get(identifier)
        if record is None:
            continue
        receipt = read_json(meta)
        handle = record.post.author_handle
        if (receipt.get("post_id") != identifier or receipt.get("provider") != "page" or receipt.get("status") != 200
                or receipt.get("body_file") != "page.body.gz" or not exact_post_url(receipt.get("request_url"),handle,identifier)):
            continue
        try:
            with gzip.open(meta.with_name("page.body.gz"), "rb") as f:
                body = f.read(4_000_001)
        except (FileNotFoundError, OSError, EOFError):
            continue
        fingerprint = sha256(body).hexdigest()
        if len(body) > 4_000_000 or fingerprint != receipt.get("sha256"):
            continue
        data = parse_native(body.decode("utf-8", errors="replace"), handle, identifier)
        if data:
            result[identifier] = {**data,"page_url":receipt["request_url"],"response_sha256":fingerprint}
    return result


def origins(entities):
    result = {}
    for later in entities.values():
        target = later.get("source_status_id")
        original = entities.get(target)
        if not original or target == later["post_id"]:
            continue
        handle = original["author"]
        if ((later.get("source_author") or "").casefold() != handle.casefold()
                or later.get("source_user_id") != original["user_id"]
                or later["media_id"] != original["media_id"] or later["media_url"] != original["media_url"]
                or not exact_post_url(later["expanded_url"], handle, target, attachment=True)
                or not exact_post_url(original["expanded_url"], handle, target, attachment=True)
                or original.get("source_status_id") not in {None, target}
                or original.get("source_user_id") not in {None, original["user_id"]}
                or (original.get("source_author") and original["source_author"].casefold() != handle.casefold())):
            continue
        result[(target, later["post_id"])] = {
            "media_id":original["media_id"], "media_url":original["media_url"], "source_user_id":original["user_id"],
            "attachment_url":later["expanded_url"], "original_page":original["page_url"],
            "original_sha256":original["response_sha256"], "report_page":later["page_url"], "report_sha256":later["response_sha256"],
        }
    return result
