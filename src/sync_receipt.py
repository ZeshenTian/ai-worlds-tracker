"""Summarize confirmed provider charges from the CI run ledger."""
import argparse
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path

from .storage import read_json, write_json


def receipt(ledger):
    totals = defaultdict(Decimal)
    counts = defaultdict(int)
    unreported = defaultdict(int)
    for entry in ledger.values():
        day = entry.get("period")
        if not day or not entry.get("id"):
            continue
        counts[day] += 1
        amount = entry.get("usage_usd")
        if amount is None:
            unreported[day] += 1
        else:
            totals[day] += Decimal(str(amount))
    return {day: {"runs": count, "reported_usd": str(totals[day]), "unreported_runs": unreported[day]}
            for day, count in sorted(counts.items())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("data/state/apify_x/ledger.json"))
    parser.add_argument("--out", type=Path, default=Path("data/state/sync_spend.json"))
    args = parser.parse_args()
    result = receipt(read_json(args.ledger)) if args.ledger.exists() else {}
    previous = read_json(args.out) if args.out.exists() else {}
    write_json(args.out, {**previous, **result})
    print(json.dumps(result))
