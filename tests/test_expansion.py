from pathlib import Path

import pytest
from src.batch_review import review_batch
from src.models import AIWorldCase, ReviewStatus
from src.publish_catalog import import_catalog_batch, trusted
from src.storage import read_json, write_json, write_rows
from src.enrich_firecrawl import EnrichmentCache

SEED = Path(__file__).resolve().parents[1] / "research/seed_snapshot/worlds.json"


def source_row():
    return next(row.copy() for row in read_json(SEED) if row.get("author_handle") and row["models_used"] and row["evidence_quotes"])


def test_provenance_and_social_threshold(tmp_path):
    case = AIWorldCase.model_validate(source_row())
    case.repo_url = None
    case.demo_health_status = "unverified"
    case.possible_duplicate_urls = []
    cfg = {"watch_accounts": [case.author_handle]}
    cache = EnrichmentCache(tmp_path)
    assert not trusted(case, cfg, cache, 39)
    assert trusted(case, cfg, cache, 40)
    case.review_status = ReviewStatus.REJECTED
    assert not trusted(case, cfg, cache, 100)


def test_editorial_import_requires_original_and_preserves_decision(tmp_path):
    row = source_row()
    row.update(summary_en="A described world", evidence_source_urls=[row["original_post_url"]], possible_duplicate_urls=[])
    path = tmp_path / "batch.json"
    write_json(path, [row, row])
    cases = {}
    import_catalog_batch(cases, path)
    assert len(cases) == 1
    cases[row["world_id"]].review_status = ReviewStatus.REJECTED
    import_catalog_batch(cases, path)
    assert cases[row["world_id"]].review_status == ReviewStatus.REJECTED
    row["evidence_source_urls"] = []
    write_json(path,[row])
    with pytest.raises(ValueError):
        import_catalog_batch({},path)


def test_batch_unknown_id_leaves_decisions_unchanged(tmp_path):
    case = AIWorldCase.model_validate(source_row())
    ledger = tmp_path / "processed/cases.jsonl"
    write_rows(ledger,[case])
    before = ledger.read_bytes()
    with pytest.raises(ValueError):
        review_batch(tmp_path,tmp_path/"site",[case.world_id,"missing-id"],ReviewStatus.REJECTED)
    assert ledger.read_bytes() == before


def test_identical_demo_keeps_first_world_and_adds_creator_credit():
    from src.publish_catalog import merge_duplicate_demos
    first = AIWorldCase.model_validate(source_row())
    first.review_status = ReviewStatus.APPROVED
    first.live_demo_url = "https://example.org/distinct-world/"
    later = first.model_copy(deep=True)
    later.world_id = first.world_id + "-later"
    later.original_post_url = "https://x.com/Maker/status/777"
    later.author_handle = "Maker"
    later.live_demo_url = first.live_demo_url.rstrip("/")
    merge_duplicate_demos({later.world_id:later, first.world_id:first}, {first.world_id})
    assert later.review_status == ReviewStatus.REJECTED
    assert later.original_post_url in first.related_post_urls
    assert first.original_post_url in later.possible_duplicate_urls


def test_cover_requires_the_credited_project_or_x_post():
    from src.publish_catalog import cover_matches
    case = AIWorldCase.model_validate(source_row())
    assert cover_matches(case, case.original_post_url.replace("x.com","twitter.com"), "x_media")
    assert not cover_matches(case, "https://x.com/A/status/123", "x_media")
    assert not cover_matches(case, "https://example.org/other", "project_media")


def test_imported_browser_check_must_match_demo_and_be_newer(tmp_path, monkeypatch):
    from src.import_demo_checks import merge_checks
    from src.storage import read_json
    case = AIWorldCase.model_validate(source_row())
    case.live_demo_url = "https://example.org/new-world"
    first = {"checked_at":"2026-11-23T01:30:00+00:00","live_demo_url":case.live_demo_url,
             "demo_health_status":"unverified","thumbnail_url":None}
    ledger = tmp_path/"processed/cases.jsonl"
    write_rows(ledger,[case])
    state = tmp_path/"state/demo_health.json"
    write_json(state,{case.world_id:first})
    checks = tmp_path/"shard"
    monkeypatch.setattr("src.import_demo_checks.publish",lambda *args,**kwargs: None)
    for replace in ({"live_demo_url":"https://example.org/old-world"}, {"checked_at":"2026-11-20T01:30:00+00:00"}):
        write_json(checks/"health.json",{case.world_id:{**first,**replace}})
        assert merge_checks(tmp_path,tmp_path/"platform",[checks]) == 0
        assert read_json(state)[case.world_id] == first
    write_json(checks/"health.json",{case.world_id:{**first,"checked_at":"2026-11-24T02:30:00+00:00"}})
    assert merge_checks(tmp_path,tmp_path/"platform",[checks]) == 1

@pytest.mark.parametrize("stack", ["ThreeJS, Codex, browser game", list("ThreeJS, Codex, browser game")])
def test_optional_technology_tags_preserve_whole_names(stack):
    row = source_row()
    row.update(models_used=["Codex"], tech_stack=stack)
    assert AIWorldCase.model_validate(row).tech_stack == ["Three.js"]
