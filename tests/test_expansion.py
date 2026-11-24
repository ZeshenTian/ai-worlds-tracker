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
