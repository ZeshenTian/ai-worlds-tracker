"""Resolve a rotating slice of directory links against the creator's public X embed."""
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
from .ingest_x import collect_links
from .links import post_id
from .models import RawPost, RawTweetRecord
from .storage import read_json, write_json


class PostParagraph(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self.active = True
        if self.active and tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "p":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def resolve_seeds(root, http, known, limit):
    source = root / "state/catalog_seeds.json"
    if not source.exists():
        return
    path = root / "state/catalog_attempts.json"
    attempts = read_json(path) if path.exists() else {}
    raw = root / "raw/x"
    pending = [u for u in read_json(source)["seed_urls"]
               if post_id(u) not in known and not (raw / (post_id(u)+".json")).exists()]
    pending.sort(key=lambda u: attempts.get(post_id(u), ""))
    for url in pending[:limit]:
        identifier = post_id(url)
        try:
            response = http.get("https://publish.twitter.com/oembed", params={"url":url,"omit_script":"true"},timeout=12)
            response.raise_for_status()
            obj = response.json()
            if post_id(obj["url"]) != identifier:
                raise ValueError("Mismatched X post")
            parser = PostParagraph()
            parser.feed(obj["html"])
            text = "".join(parser.parts).strip()
            handle = urlsplit(obj["author_url"]).path.strip("/")
            created = datetime.fromtimestamp(((int(identifier) >> 22) + 1288834974657) / 1000, UTC)
            post = RawPost(tweet_id=identifier, author_handle=handle, text=text, published_at=created)
            if text:
                row = collect_links(RawTweetRecord(post=post), http, raw / "redirects")
                write_json(raw / (identifier + ".json"), row.model_dump(mode="json"))
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        attempts[identifier] = datetime.now(UTC).isoformat()
    write_json(path, attempts)
