"""Attachment identities used to compare X posts across scraper formats."""
from collections import defaultdict
import re
from urllib.parse import urlsplit

from .storage import read_json
from .x_covers import media_kind


POSITIONAL_KEY = re.compile(r"(?:\d{1,3}|(?:photo|video|animated_gif|media)_\d+)", re.I)
V2_KEY = re.compile(r"(?:3|7|13|16)_(\d{12,20})")


def asset_key(value):
    if not media_kind(value):
        return None
    path = re.sub(r"\.(?:jpe?g|png|webp|gif)$", "", urlsplit(value).path, flags=re.I)
    return "https://pbs.twimg.com" + path


def stable_key(value):
    if value is None:
        return None
    key = str(value).strip()
    if not key or POSITIONAL_KEY.fullmatch(key):
        return None
    if "://" in key:
        return asset_key(key)
    match = V2_KEY.fullmatch(key)
    return match[1] if match else key


def actor_attachments(item):
    extended = item.get("extendedEntities") or item.get("extended_entities") or {}
    return extended.get("media") or item.get("media") or []


def attachment_keys(attachments):
    keys = set()
    for item in attachments:
        if isinstance(item, str):
            values = [asset_key(item)]
        elif isinstance(item, dict):
            values = [stable_key(item.get(field)) for field in ("media_key", "id_str", "id")]
            values.extend(asset_key(item.get(field)) for field in
                          ("media_url_https", "media_url", "preview_image_url", "url"))
        else:
            continue
        keys.update(key for key in values if key)
    return keys


def load_media_evidence(root, signals=None):
    """Restore all saved attachments, including positions beyond the cover image."""
    result = defaultdict(set)
    if signals is None:
        signals = {p.stem: read_json(p) for p in (root / "raw/x/signals").glob("*.json")}
    for identifier, signal in signals.items():
        if key := asset_key(signal.get("media_url")):
            result[identifier].add(key)
    for path in (root / "raw/apify").glob("*.json"):
        items = read_json(path)
        while items:
            item = items.pop()
            if not isinstance(item, dict) or item.get("isRetweet") or item.get("is_retweet"):
                continue
            identifier = str(item.get("id", ""))
            if not identifier.isdecimal():
                continue
            keys = attachment_keys(actor_attachments(item))
            if keys:
                result[identifier].update(keys)
            quote = item.get("quotedTweet") or item.get("quote") or item.get("quoted_tweet")
            if isinstance(quote, dict):
                items.append(quote)
    return result


def record_keys(record, evidence):
    keys = {key for raw in record.post.media_keys if (key := stable_key(raw))}
    return keys.union(evidence.get(record.post.tweet_id, ()))
