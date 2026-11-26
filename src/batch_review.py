"""Atomically apply one decision to an explicit list of pending IDs."""
import argparse
from pathlib import Path

from .models import AIWorldCase, ReviewStatus
from .publish_catalog import PROJECT, publish
from .recheck_attribution import record_manual_reviews
from .storage import read_rows, run_lock, write_rows


def review_batch(root, platform, ids, decision):
    with run_lock(root):
        ledger = root / "processed/cases.jsonl"
        rows = read_rows(ledger, AIWorldCase)
        wanted = set(ids)
        eligible = {w.world_id for w in rows if w.review_status in (ReviewStatus.PENDING, decision)}
        if not wanted or wanted - eligible:
            raise ValueError(f"Invalid or conflicting selection: {sorted(wanted - eligible)}")
        for case in rows:
            if case.world_id in wanted:
                case.review_status = decision
        record_manual_reviews(root, (case for case in rows if case.world_id in wanted))
        write_rows(ledger, rows)
        publish(root, platform)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("decision", choices=["approved","rejected"])
    p.add_argument("ids", type=Path, help="Text file with one world_id per line")
    args = p.parse_args()
    review_batch(PROJECT/"data", PROJECT/"platform", args.ids.read_text().split(), ReviewStatus(args.decision))
