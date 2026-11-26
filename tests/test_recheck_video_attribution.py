from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from src.models import ReviewStatus
from src.recheck_attribution import (AUTHOR_MODEL, MOTION_RULES, RULES, VIDEO_AUTHOR_CHECK, apply_attribution,
                                     rules_out_video)
from src.recheck_video_attribution import verify_files
from src.storage import digest, encode, read_json, write_json


def media_fixture(tmp_path):
    root = tmp_path / "data"
    case = SimpleNamespace(world_id="world-1", author_handle="artist", original_post_url="https://x.com/artist/status/123")
    actor = root / "raw/apify/receipt.json"
    attachment = case.original_post_url + "/video/1"
    endpoint = "https://video.twimg.com/amplify_video/54/sample.mp4?tag=1"
    poster = "https://pbs.twimg.com/media/QF.jpg"
    media = {"type": "video", "expanded_url": attachment, "id_str": "54", "media_url_https": poster,
             "video_info": {"variants": [{"content_type": "video/mp4", "url": endpoint}]}}
    write_json(actor, [{"id": "123", "author": {"userName": "artist"}, "extendedEntities": {"media": [media]}}])
    out = root / "raw/x/video_evidence/123"
    out.mkdir(parents=True)
    video = out / "source.mp4"
    video.write_bytes(b"archived video")
    checksum = lambda p: sha256(p.read_bytes()).hexdigest()
    frames = []
    for i in range(3):
        path = out / f"{i}.jpg"
        path.write_bytes(f"frame {i}".encode())
        frames.append({"path": str(path.relative_to(tmp_path)), "seconds": i + 1., "sha256": checksum(path)})
    source = {"world_id": case.world_id, "source_url": case.original_post_url, "tweet_id": "123", "author_handle": "artist",
              "attachment_id": "54", "media_id": "54", "source": case.original_post_url, "attachment_url": attachment,
              "video_url": endpoint, "actor_file": str(actor.relative_to(tmp_path)), "actor_index": 0,
              "actor_file_sha256": checksum(actor), "video_path": str(video.relative_to(tmp_path)),
              "video_sha256": checksum(video), "poster_url": poster, "duration_seconds": 4, "frames": frames}
    return root, case, source


def test_sequence_is_tied_to_one_actor_attachment_with_three_ordered_verified_frames(tmp_path):
    root, case, source = media_fixture(tmp_path)
    assert len(verify_files(root, case, source)) == 3
    for variant in ({"tweet_id": "456"}, {"media_id": "55", "attachment_id": "55"}, {"source_url": "https://x.com/other/status/123"},
                    {"video_url": source["video_url"].replace("54", "99")}, {"actor_file_sha256": "tampered"},
                    {"video_sha256": "tampered"}, {"frames": list(reversed(source["frames"]))},
                    {"frames": [*source["frames"][:2], {**source["frames"][2], "sha256": "wrong"}]}):
        assert not verify_files(root, case, {**source, **variant})
    path = tmp_path / source["actor_file"]
    actor = read_json(path)
    actor[0]["isRetweet"] = True
    write_json(path, actor)
    assert not verify_files(root, case, {**source, "actor_file_sha256": sha256(path.read_bytes()).hexdigest()})


def test_existing_secondary_or_promotional_decision_blocks_motion_recovery():
    for prior in ({"perspective": "third_party"}, {"perspective": "product_promotion"},
                  {"model_relation": "compatible_or_promoted"}, {"author_check": {"attribution": "outside_creator"}},
                  {"author_check": {"attribution": "promotional", "model_used_on_this_build": True}}):
        assert rules_out_video({"proof": {"decision": "hold"}, "visual": prior})
    assert rules_out_video({"proof": {"decision": "reject"}})
    assert not rules_out_video({"proof": {"decision": "hold"}, "visual": {"frame_type": "ambiguous"}})


def test_cold_checkout_replays_corroborated_video_only_for_its_original_source(tmp_path):
    case = SimpleNamespace(world_id="world-1", author_handle="artist", original_post_url="https://x.com/artist/status/123",
                           source_kind="x_post", review_status=ReviewStatus.PENDING, models_used=[], evidence_quotes=[],
                           published_at="2026-11-24T12:00:00+00:00")
    quote = "My valley with Gemini 4."
    v = {"decision": "allow", "key": "motion-key", "sampled_frames": [{"seconds": 2, "sha256": "verified-frame"}], "rules": digest(MOTION_RULES), "text_key": "text-key",
         "quote": quote, "models": [{"term": "Gemini 4", "quote": quote}],
         "author_check": {"rules": digest(AUTHOR_MODEL + VIDEO_AUTHOR_CHECK), "visual_key": "motion-key", "confirmed": True}}
    entry = {"source": case.original_post_url, "key": "text-key", "proof": {"decision": "hold"},
             "policy": digest(encode([RULES, "mini"])), "video_visual": v}
    policy = {"model": "mini", "protected": set(), "decisions": {case.world_id: entry}}
    assert apply_attribution(case, tmp_path, policy) == "allow"
    assert case.models_used == ["Gemini 4"]
    entry["visual"] = {"perspective": "third_party"}
    assert apply_attribution(case, tmp_path, policy) == "hold"
