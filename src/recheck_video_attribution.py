"""Verify authenticated, sampled X video attachments for unresolved first-party spatial works."""
from collections import Counter
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from openai import APIError, OpenAI
from pydantic import ValidationError

from .links import post_id
from .models import ReviewStatus
from .qualify_candidates import PROMO, record_usage
from .recheck_attribution import (MOTION_RULES, VISUAL_RULES, VisualVerdict, complete_batches, corroborated, evidence,
                                  in_scope, receipt_path, rules_out_video, save_visual, small_frame, visual_eligible,
                                  visual_grounding)
from .storage import digest, encode, read_json, write_json
from .x_media import actor_attachments


class SequenceVerdict(VisualVerdict):
    motion_support: bool


def file_hash(path):
    with path.open("rb") as stream:
        fingerprint = sha256()
        for block in iter(lambda: stream.read(262144), b""):
            fingerprint.update(block)
    return fingerprint.hexdigest()


def local_path(root, relative, allowed):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        return None
    path = (root.parent / relative).resolve()
    return path if path.is_relative_to(allowed.resolve()) and path.is_file() else None


@lru_cache(maxsize=3)
def actor_page(path, _mtime):
    return read_json(path), file_hash(path)


def actor_confirms(root, case, record):
    path = local_path(root, record.get("actor_file"), root / "raw/apify")
    if not path:
        return False
    items, checksum = actor_page(path, path.stat().st_mtime_ns)
    if checksum != record.get("actor_file_sha256") or record.get("attachment_id") != record.get("media_id"):
        return False
    index = record.get("actor_index")
    if not isinstance(index, int) or not 0 <= index < len(items):
        return False
    item = items[index]
    author = (item.get("author") or {}).get("userName") or item.get("username") or ""
    if (item.get("isRetweet") or item.get("is_retweet") or str(item.get("id")) != record["tweet_id"]
            or author.casefold() != case.author_handle.casefold()):
        return False
    origin = record.get("attachment_url")
    if not isinstance(origin, str) or "/video/" not in origin:
        return False
    try:
        if post_id(origin) != record["tweet_id"]:
            return False
    except ValueError:
        return False
    for media in actor_attachments(item):
        if (not isinstance(media, dict) or media.get("type") != "video" or media.get("expanded_url") != origin
                or media.get("media_url_https") != record.get("poster_url")
                or str(media.get("id_str")) != str(record.get("media_id"))):
            continue
        variants = (media.get("video_info") or {}).get("variants", [])
        if any(v.get("content_type") == "video/mp4" and v.get("url") == record["video_url"] for v in variants):
            return True
    return False


def verify_files(root, case, record):
    if (case.world_id != record.get("world_id") or record.get("source_url") != case.original_post_url
            or str(record.get("tweet_id")) != post_id(case.original_post_url)
            or str(record.get("author_handle", "")).casefold() != case.author_handle.casefold()
            or urlsplit(record.get("video_url") or "").hostname != "video.twimg.com" or not actor_confirms(root, case, record)):
        return None
    accepted_dir = root / "raw/x/video_evidence"
    video = local_path(root, record.get("video_path"), accepted_dir)
    frames = record.get("frames") or []
    if not video or len(frames) != 3 or file_hash(video) != record.get("video_sha256"):
        return None
    duration = record.get("duration_seconds")
    if not isinstance(duration, (int, float)) or not 0 < duration:
        return None
    checked = []
    for frame in frames:
        path = local_path(root, frame.get("path"), accepted_dir)
        seconds = frame.get("seconds")
        if (not path or not isinstance(seconds, (int, float)) or not 0 <= seconds < duration
                or (checked and seconds <= checked[-1][1]) or file_hash(path) != frame.get("sha256")):
            return None
        checked.append((path, seconds, frame["sha256"]))
    return checked


def review_sequences(root, policy, rows, *, cache_only=False, workers=8):
    manifest = root / "raw/x/video_evidence/manifest.json"
    if not manifest.is_file():
        return {}
    records = read_json(manifest).get("records", [])
    counts, jobs, additions = Counter(), [], {}
    indexed = {c.world_id: c for c in rows if in_scope(c, policy) and c.review_status != ReviewStatus.REJECTED}
    seen = Counter(x.get("world_id") for x in records)
    for source in records:
        wid = source.get("world_id")
        entry = policy["decisions"].get(wid, {})
        case = indexed.get(wid)
        poster = entry.get("visual", {})
        if (not case or seen[wid] != 1 or rules_out_video(entry) or (poster and poster.get("rules") != digest(VISUAL_RULES))
                or (poster.get("decision") == "allow" and corroborated(poster))):
            counts["outside_scope"] += 1
            continue
        packet = evidence(root, case)
        if (not packet or not visual_eligible(case, packet) or PROMO.search(packet["post"] + " " + packet["own_quote"])
                or entry["key"] != receipt_path(root, case, packet, policy).stem):
            counts["ineligible_source"] += 1
            continue
        frames = verify_files(root, case, source)
        if not frames:
            counts["unverified_media"] += 1
            continue
        signature = digest(encode([MOTION_RULES, policy["model"], entry["key"], source["video_sha256"],
                                   [(seconds, sha) for _, seconds, sha in frames]]))
        previous = entry.get("video_visual", {})
        metadata = {"actor_file_sha256": source["actor_file_sha256"], "rights": source.get("rights")}
        if previous.get("key") == signature:
            if any(previous.get(k) != v for k, v in metadata.items()):
                additions[wid] = {**previous, **metadata}
            counts["durable"] += 1
            continue
        cache = root / "processed/extraction/attribution_video" / f"{signature}.json"
        if cache.is_file():
            additions[wid] = {**read_json(cache), **metadata}
            counts["cached"] += 1
        else:
            jobs.append((case, source, packet, entry["key"], frames, signature, cache))
    save_visual(root, additions, policy, field="video_visual")
    if cache_only or not jobs:
        return {**counts, "missing_receipt": len(jobs)}
    client = OpenAI(timeout=90, max_retries=2)
    def check(batch):
        (case, source, packet, text_key, frames, key, cache), = batch
        content = [{"type": "input_text", "text": encode({"index": 0, **packet})}]
        try:
            for path, seconds, _ in frames:
                content += [{"type": "input_text", "text": f"Time {seconds:.3f} seconds"},
                            {"type": "input_image", "detail": "low", "image_url": small_frame(path)}]
            response = client.responses.parse(model=policy["model"], instructions=MOTION_RULES, store=False,
                input=[{"role": "user", "content": content}], text_format=SequenceVerdict, max_output_tokens=1300)
            record_usage(root, policy["model"], "temporal_attribution_review", response)
            item = response.output_parsed
        except (APIError, ValidationError, ValueError, OSError) as error:
            print(f"Sequence review deferred ({type(error).__name__})", flush=True)
            return Counter(deferred=1), {}
        if response.status != "completed" or item is None or item.index != 0:
            return Counter(deferred=1), {}
        proof = visual_grounding(packet, item)
        if not item.motion_support:
            proof = {"decision": "hold", "quote": proof["quote"], "models": []}
        result = {**proof, "visual_observation": item.observation, "perspective": item.perspective,
                  "model_relation": item.model_relation, "frame_type": item.frame_type, "motion_support": item.motion_support,
                  "key": key, "text_key": text_key, "rules": digest(MOTION_RULES),
                  "source_url": case.original_post_url, "attachment_url": source["attachment_url"],
                  "media_id": source["media_id"], "video_url": source["video_url"], "source_sha256": source["video_sha256"],
                  "actor_file": source["actor_file"], "actor_file_sha256": source["actor_file_sha256"],
                  "actor_index": source["actor_index"], "duration_seconds": source["duration_seconds"],
                  "rights": source.get("rights"),
                  "sampled_frames": [{"seconds": t, "sha256": sha} for _, t, sha in frames]}
        write_json(cache, result)
        return Counter({proof["decision"]: 1}), {case.world_id: result}

    print(f"Reviewing {len(jobs)} authenticated video sequences", flush=True)
    return complete_batches(jobs, 1, workers, check, counts,
                            lambda changes: save_visual(root, changes, policy, field="video_visual"))
