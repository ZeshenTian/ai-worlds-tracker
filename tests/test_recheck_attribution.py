from types import SimpleNamespace

import pytest

from src.models import ReviewStatus
from src.recheck_attribution import (AUTHOR_CHECK, AUTHOR_MODEL, RULES, VISUAL_RULES, ModelUse, Verdict, VisualVerdict, apply_attribution,
                                     evidence, grounded, original_frame, receipt_path, visual_grounding)
from src.storage import digest, encode, write_json


def work():
    return SimpleNamespace(world_id="world-test", author_handle="maker", original_post_url="https://x.com/maker/status/123",
        source_kind="x_post", review_status=ReviewStatus.APPROVED, models_used=["AI", "Asset library"],
        evidence_quotes=[], published_at="2026-11-24T00:00:00Z")


def packet(text):
    return {"author": "maker", "post": text, "thread": [], "own_quote": "", "has_attached_media": True}


def verdict(quote, term="", decision="allow"):
    return Verdict(index=0, decision=decision, quote=quote, models=[ModelUse(term=term, quote=quote)] if term else [])


def test_exact_grounding_preserves_whitespace_from_source():
    text = "My city\n\nwas built with Gemini 4."
    result = grounded(packet(text), verdict("My city was built with gemini 4.", "gemini 4"))
    assert result == {"decision": "allow", "quote": text, "models": [{"term": "Gemini 4", "quote": text}]}
    assert grounded(packet(text), verdict("Someone else built this", decision="reject"))["decision"] == "hold"
    assert grounded(packet("Someone else built this."), verdict("Someone else built this", decision="reject"))["decision"] == "reject"


@pytest.mark.parametrize(("post", "term"), [
    ("Our toolkit is compatible with Gemini.", "Gemini"),
    ("Codex / Claude Code 四大 Agent 全都能直接用！", "Codex"),
    ("用了 CC0 动作库，全部做完了。", "CC0 动作库"),
    ("I used AI to build this.", "AI"),
    ("Built a space game.", "Codex"),
    *[(f"I built this in {name}.", name) for name in
      ("/anatomy", "Unity 6", "3DGS", "Anime.js", "Godot", "Python", "Node.js DSP", "Blender 5.2.1", "Unreal Engine 5.8")],
])
def test_term_must_be_an_actual_model_disclosure(post, term):
    assert grounded(packet(post), verdict(post, term))["decision"] == "hold"


def test_self_quote_must_be_by_same_author_and_referenced(tmp_path):
    case = work()
    post = {"tweet_id": "123", "author_handle": "maker", "text": "Another update!", "referenced_post_ids": ["99"]}
    signal = {"quoted_id": "99", "quoted_author": "other", "quoted_text": "My game used GPT.", "has_video": True}
    write_json(tmp_path / "raw/x/123.json", {"post": post, "thread": []})
    path = tmp_path / "raw/x/signals/123.json"
    write_json(path, signal)
    assert evidence(tmp_path, case)["own_quote"] == ""
    assert evidence(tmp_path, case)["has_attached_media"]
    write_json(path, {**signal, "quoted_author": "maker"})
    assert evidence(tmp_path, case)["own_quote"] == "My game used GPT."
    write_json(path, {**signal, "quoted_id": "98", "quoted_author": "maker"})
    assert evidence(tmp_path, case)["own_quote"] == ""


def test_cold_checkout_preserves_valid_attribution_and_protects_archive(tmp_path):
    case = work()
    proof = {"decision": "allow", "models": [{"term": "Codex", "quote": "Built this with Codex."}],
             "quote": "Built this with Codex."}
    entry = {"source": case.original_post_url, "key": "previous-hash", "proof": proof,
             "policy": digest(encode([RULES, "mini"]))}
    policy = {"model": "mini", "protected": set(), "decisions": {case.world_id: entry}}
    assert apply_attribution(case, tmp_path, policy) == "allow"
    assert case.models_used == ["Codex"]
    assert case.evidence_quotes == ["Built this with Codex."]
    write_json(tmp_path / "raw/x/123.json", {"post": {"tweet_id": "123", "author_handle": "maker", "text": "Changed"}})
    assert apply_attribution(case, tmp_path, policy) == "hold"
    assert case.review_status == ReviewStatus.PENDING
    case.review_status = ReviewStatus.REJECTED
    assert apply_attribution(case, tmp_path, policy) == "reject"
    assert apply_attribution(case, tmp_path, {**policy, "protected": {case.world_id}}) == "unscoped"


def test_visual_record_needs_same_exact_x_post_and_local_thumbnail(tmp_path):
    root, case = tmp_path / "data", work()
    frame = tmp_path / "platform/public/thumbnails/world-test-x.webp"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"cached")
    cover = {"thumbnail_url": "/thumbnails/world-test-x.webp", "source_url": case.original_post_url,
             "media_url": "https://pbs.twimg.com/media/Abc.jpg", "source_sha256": "source"}
    assert original_frame({case.world_id: cover}, case, root) == (frame, cover)
    assert original_frame({case.world_id: {**cover, "source_url": "https://x.com/other/status/456"}}, case, root) is None
    frame.unlink()
    assert original_frame({case.world_id: cover}, case, root) is None


@pytest.mark.parametrize(("facet", "value"), [
    ("frame_type", "title_card_or_promo"), ("frame_type", "flat_2d_or_ui"),
    ("perspective", "third_party"), ("perspective", "product_promotion"),
    ("model_relation", "compatible_or_promoted"), ("observation", ""),
])
def test_image_cannot_override_attribution_or_2d_only_evidence(facet, value):
    post = "Codex + Three.js: my little valley"
    fields = dict(frame_type="spatial_render", perspective="creator_caption", model_relation="used_for_pictured_work",
                  observation="A rendered valley shows nested cliffs, shadows and a terrain mesh.")
    proof = VisualVerdict(**verdict(post, "Codex").model_dump(), **fields)
    assert visual_grounding(packet(post), proof)["decision"] == "allow"
    assert visual_grounding(packet(post), proof.model_copy(update={facet: value}))["decision"] == "hold"


def test_visual_receipt_does_not_resurrect_rejected_or_use_stale_evidence(tmp_path):
    case = work()
    initial = {"post": {"tweet_id": "123", "author_handle": "maker", "text": "My city in Codex"}}
    write_json(tmp_path / "raw/x/123.json", initial)
    policy = {"model": "mini", "protected": set(), "decisions": {}}
    key = receipt_path(tmp_path, case, evidence(tmp_path, case), policy).stem
    visual = {"text_key": key, "key": "frame-key", "rules": digest(VISUAL_RULES), "decision": "allow",
              "author_check": {"confirmed": True, "visual_key": "frame-key", "rules": digest(AUTHOR_MODEL + AUTHOR_CHECK)}, "quote": "My city in Codex",
              "models": [{"term": "Codex", "quote": "My city in Codex"}]}
    entry = {"source": case.original_post_url, "key": key, "policy": digest(encode([RULES, "mini"])),
             "proof": {"decision": "hold", "quote": "", "models": []}, "visual": visual}
    policy["decisions"][case.world_id] = entry
    assert apply_attribution(case, tmp_path, policy) == "allow"
    entry["visual"] = {**visual, "rules": "previous image rule"}
    assert apply_attribution(case, tmp_path, policy) == "hold"
    entry.update(visual=visual, proof={"decision": "reject", "quote": "somebody else's game", "models": []})
    assert apply_attribution(case, tmp_path, policy) == "reject"


def test_both_stages_run_once_then_replay_offline(tmp_path, monkeypatch):
    from PIL import Image
    import src.recheck_attribution as module
    case = work()
    root = tmp_path / "data"
    original = "My Codex model of a valley."
    write_json(root / "raw/x/123.json", {"post": {"tweet_id": "123", "author_handle": "maker", "text": original}})
    write_json(root / "state/attribution_policy.json", {"model": "mini", "protected": [], "baseline_ref": "release"})
    frame = tmp_path / "platform/public/thumbnails/world-test-x.webp"
    frame.parent.mkdir(parents=True)
    Image.new("RGB", (48, 32), "green").save(frame)
    write_json(root / "state/x_covers.json", {case.world_id: {"thumbnail_url": "/thumbnails/world-test-x.webp",
        "source_url": case.original_post_url, "media_url": "https://pbs.twimg.com/media/Abc.jpg", "source_sha256": "frame"}})
    calls = []
    def parse(**kwargs):
        calls.append(kwargs["text_format"])
        if kwargs["text_format"] is module.Verdicts:
            result = module.Verdicts(items=[verdict(original, decision="hold")])
        elif kwargs["text_format"] is module.Authorships:
            result = module.Authorships(items=[module.Authorship(index=0, attribution="own_build", media="spatial_3d",
                model_used_on_this_build=True, evidence=original, reasoning="The speaker identifies the model as their own.")])
        else:
            result = module.VisualVerdicts(items=[module.VisualVerdict(**verdict(original, "Codex").model_dump(),
                frame_type="spatial_render", perspective="author_or_team_build", model_relation="used_for_pictured_work",
                observation="The frame shows sloping valley walls casting shadows on a mesh.")])
        return SimpleNamespace(output_parsed=result, usage=None, status="completed")
    monkeypatch.setattr(module, "OpenAI", lambda **_: SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    policy = module.load_policy(root)
    first = module.prepare(root, policy, [case])
    assert calls == [module.Verdicts, module.VisualVerdicts, module.Authorships]
    assert first["text"]["hold"] == first["original_frames"]["allow"] == 1
    assert apply_attribution(case, root, module.load_policy(root)) == "allow"
    assert case.models_used == ["Codex"]
    repeat = module.prepare(root, policy, [case])
    assert repeat["text"]["durable"] == repeat["original_frames"]["durable"] == 1
    assert len(calls) == 3
    (root / "raw/x/123.json").unlink()
    frame.unlink()
    assert apply_attribution(case, root, module.load_policy(root)) == "allow"
