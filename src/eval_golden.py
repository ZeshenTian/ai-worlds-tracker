"""Read-only holdout evaluation; discovery and publication never import this module."""

import argparse
from collections import defaultdict
from pathlib import Path
import re
import yaml
from .storage import read_json, write_json, write_text

GROUPS = (
    "positive_core",
    "positive_long_tail",
    "negative_controls",
    "secondary_leads",
    "borderline_review",
)


def index(rows):
    result = defaultdict(list)
    for row in rows:
        for url in [
            row.get("original_post_url", ""),
            *(row.get("related_post_urls") or []),
        ]:
            match = re.search(r"/status/(\d+)(?:[/?#]|$)", url)
            if match:
                result[match[1]].append(row)
    return result


def evaluate(benchmark, root):
    import json

    ledger_file = root / "processed/cases.jsonl"
    cases = {}
    if ledger_file.is_file():
        with ledger_file.open(encoding="utf-8") as source:
            cases = index(json.loads(line) for line in source if line.strip())
    published = index(read_json(root / "exports/ai_worlds.json"))
    from .recheck_attribution import apply_attribution, load_policy
    from .models import AIWorldCase
    policy = load_policy(root)
    rows, metrics = [], {}
    for group in GROUPS:
        hits = captures = passed_count = 0
        for item in benchmark.get(group, []):
            tid = str(item["tweet_id"])
            raw = (root / f"raw/x/{tid}.json").exists()
            signal = root / f"raw/x/signals/{tid}.json"
            gate = root / f"processed/extraction/gate_by_id/{tid}.json"
            cached = read_json(gate) if gate.exists() else {}
            decision = root / "processed/extraction/gate" / cached.get("cache", "")
            passed = bool(
                cases.get(tid)
                or (
                    cached.get("accepted")
                    and decision.is_file()
                    and read_json(decision) is True
                )
            )
            exports = [
                w for w in published.get(tid, []) if w["review_status"] != "rejected"
            ]
            frontier = any(w.get("model_era") == "frontier" for w in exports)
            if group == "secondary_leads":
                hit = any(
                    (w.get("author_handle") or "").lower().lstrip("@")
                    == item["author"].lower().lstrip("@")
                    for w in exports
                )
            else:
                hit = bool(exports) if group == "negative_controls" else frontier
            status = (
                "hit"
                if hit
                else "wrong_model_era"
                if exports and not frontier
                else "stuck_in_pending"
                if passed
                else "dropped_at_gate"
                if raw
                else "missed_at_crawl"
            )
            checks = set()
            if not hit:
                for case in cases.get(tid, []):
                    if case.get("review_status") == "rejected":
                        checks.add("已拒绝")
                    if case.get("possible_duplicate_urls"):
                        checks.add("疑似重复待核实")
                    if policy and case.get("world_id") in policy["decisions"]:
                        copy = AIWorldCase.model_validate(case)
                        verdict = apply_attribution(copy, root, policy)
                        if verdict == "hold":
                            checks.add("作者、模型用法或作品类型的证据不足")
                        elif verdict == "reject":
                            checks.add("未通过内容政策审核")
            rows.append(
                dict(
                    group=group,
                    tweet_id=tid,
                    raw=raw,
                    signal=signal.exists(),
                    likes=read_json(signal).get("likes") if signal.exists() else None,
                    post_gate=passed,
                    review_findings=sorted(checks),
                    ledger_statuses=sorted({w.get("review_status", "pending") for w in cases.get(tid, [])}),
                    gate_receipt=("accepted" if cached.get("accepted") else "declined") if gate.exists() else "absent",
                    published=bool(exports),
                    published_frontier=frontier,
                    hit=hit,
                    stage=status,
                )
            )
            hits += hit
            captures += raw
            passed_count += passed
        total = len(benchmark.get(group, []))
        metrics[group] = dict(raw=captures, post_gate=passed_count, final=hits, total=total)
    core, tail, neg, leads = [metrics[k] for k in GROUPS[:4]]

    def ratio(val, field):
        return val[field] / val["total"] if val["total"] else 0

    return dict(
        core_raw_recall=ratio(core, "raw"),
        core_final_recall=ratio(core, "final"),
        long_tail_raw_recall=ratio(tail, "raw"),
        long_tail_final_recall=ratio(tail, "final"),
        negative_leakage=ratio(neg, "final"),
        secondary_lead_leakage=leads["final"],
        groups=metrics,
        items=rows,
        strict_pass=ratio(core, "final") >= 0.85
        and not neg["final"]
        and not leads["final"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark", type=Path, default=Path("config/golden_benchmark.yaml")
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, default=Path("reports/golden_eval.md"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = evaluate(yaml.safe_load(args.benchmark.read_text()), args.data_dir)
    write_json(args.data_dir / "state" / (args.report.stem + ".json"), result)
    lines = [
        "# 盲测结果",
        "",
        "| 组别 | 原帖抓到 | 通过筛选或已提取 | 最终命中或泄漏 | 样本 |",
        "|---|---:|---:|---:|---:|",
    ]
    for k, v in result["groups"].items():
        lines.append(f"| {k} | {v['raw']} | {v['post_gate']} | {v['final']} | {v['total']} |")
    lines += [
        "",
        f"核心召回率 {result['core_final_recall']:.1%}，原帖捕获率 {result['core_raw_recall']:.1%}。",
        f"长尾召回率 {result['long_tail_final_recall']:.1%}，原帖捕获率 {result['long_tail_raw_recall']:.1%}。",
        f"负样本泄漏率 {result['negative_leakage']:.1%}，以聚合号名义发布 {result['secondary_lead_leakage']} 条。",
        f"严格验收{'通过' if result['strict_pass'] else '未通过'}。",
    ]
    print("\n".join(lines))
    lines += [
        "",
        "| 组别 | 帖子 | Raw | 信号 | 赞 | 通过筛选或已提取 | 筛选回执 | 案例审核状态 | 前沿公开 | 诊断 | 核查记录 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in result["items"]:
        lines.append(
            "| "
            + " | ".join(
                ((", ".join(r[k]) or "未提取") if k == "ledger_statuses"
                 else ("、".join(r[k]) or "—") if k == "review_findings" else str(r[k]))
                for k in (
                    "group",
                    "tweet_id",
                    "raw",
                    "signal",
                    "likes",
                    "post_gate",
                    "gate_receipt",
                    "ledger_statuses",
                    "published_frontier",
                    "stage",
                    "review_findings",
                )
            )
            + " |"
        )
    write_text(args.report, "\n".join(lines) + "\n")
    return int(args.strict and not result["strict_pass"])


if __name__ == "__main__":
    raise SystemExit(main())
