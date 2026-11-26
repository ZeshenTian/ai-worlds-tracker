from pathlib import Path
import re
import json
import yaml
from src.eval_golden import evaluate, GROUPS
from src.storage import write_json


import pytest

@pytest.mark.parametrize("filename",["golden_benchmark.yaml","golden_benchmark_v2.yaml"])
def test_holdout_is_independent(filename):
    bench = yaml.safe_load((Path("config")/filename).read_text())
    ids = [str(r["tweet_id"]) for k in GROUPS for r in bench[k]]
    assert len(ids) == len(set(ids))
    seeds = Path("config/seeds.yaml").read_text()
    assert not any(re.search(r"(?<!\d)" + i + r"(?!\d)", seeds) for i in ids)
    provenance = json.loads(
        Path("research/expansion/frontier_author_provenance.json").read_text()
    )
    added = {a.lower() for a in yaml.safe_load(seeds)["watch_accounts"]} - set(
        provenance["original"]
    )
    phase2=json.loads(Path("research/expansion/frontier_phase2_author_provenance.json").read_text())
    new=set(phase2["added_from_public_catalog"])
    held={r["author"].lower().lstrip("@") for k in GROUPS for r in bench[k]}
    assert not new & held
    config=yaml.safe_load(seeds)
    watched={a.lower() for a in config.pop("watch_accounts")}
    from hashlib import sha256
    assert sha256(json.dumps(config,sort_keys=True,ensure_ascii=False).encode()).hexdigest()==phase2["other_seed_fields_sha256"]
    for author,url in phase2["original_source_urls"].items():
        assert re.fullmatch(rf"https://x\.com/{re.escape(author)}/status/\d+",url,re.I)
    assert watched-set(phase2["previous_watch"])==new
    assert added <= set(provenance["repeat_creators"]) | set(provenance["frontier_authors"]) | new
    catalog={row["world_id"]:row for row in json.loads(Path("data/exports/ai_worlds.json").read_text())}
    # The baseline receipt references immutable source IDs even when a work is later archived.
    for who, wid in phase2["added_from_public_catalog"].items():
        if wid in catalog:
            assert catalog[wid]["author_handle"].casefold()==who


def test_funnel_fixture(tmp_path):
    bench = dict(
        positive_core=[{"tweet_id": "101"}],
        negative_controls=[{"tweet_id": "102"}],
        secondary_leads=[{"tweet_id": "103", "author": "curator"}],
    )
    write_json(tmp_path / "raw/x/101.json", {})
    write_json(
        tmp_path / "exports/ai_worlds.json",
        [
            dict(
                original_post_url="https://x.com/me/status/101",
                review_status="approved",
                model_era="frontier",
                related_post_urls=["https://x.com/curator/status/103"],
                author_handle="me",
            ),
            dict(
                original_post_url="https://x.com/other/status/102",
                review_status="approved",
                model_era="legacy",
            ),
        ],
    )
    result = evaluate(bench, tmp_path)
    assert result["core_final_recall"] == result["core_raw_recall"] == 1
    assert (
        result["negative_leakage"] == 1
        and result["secondary_lead_leakage"] == 0
        and not result["strict_pass"]
    )


def test_gate_receipt_requires_positive_backing_file(tmp_path):
    bench = {"positive_core": [{"tweet_id": str(i)} for i in (701, 702)]}
    write_json(tmp_path / "exports/ai_worlds.json", [])
    for tid in ("701", "702"):
        write_json(tmp_path / "raw/x" / f"{tid}.json", {})
        write_json(tmp_path / "processed/extraction/gate_by_id" / f"{tid}.json",
                   {"accepted":True, "cache":f"{tid}.json"})
    write_json(tmp_path / "processed/extraction/gate/701.json", True)
    result = evaluate(bench, tmp_path)
    assert result["groups"]["positive_core"]["post_gate"] == 1
    assert [row["stage"] for row in result["items"]] == ["stuck_in_pending", "dropped_at_gate"]

def test_unicode_line_separator_in_original_quote(tmp_path):
    ledger = tmp_path / "processed/cases.jsonl"
    ledger.parent.mkdir()
    row = {"original_post_url": "https://x.com/example/status/501", "evidence_quotes": ["first\u2028second"]}
    ledger.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    write_json(tmp_path / "exports/ai_worlds.json", [])
    assert evaluate({"positive_core": [{"tweet_id": "501"}]}, tmp_path)["groups"]["positive_core"]["post_gate"] == 1
