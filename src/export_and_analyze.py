from collections import Counter
import csv
from io import StringIO
from pathlib import Path
import re

from .models import AIWorldCase, ReviewStatus
from .storage import write_text


WORKFLOW_PATTERNS = {
    "提供地图、图像或历史资料作为参考": r"地图|图纸|文献|参考|单张图像",
    "用代码生成世界或场景元素": r"生成地形|生成.*场景|三维街区|代码生成|生成 WebGL",
    "组合生成资产与程序化场景": r"Tripo3D|GLB|3DGS|Blender",
    "迭代调试与浏览器复核": r"检查截图|截图检查|重跑测试|Playwright|迭代",
}


REVIEW_FIELDS = [
    "world_id", "title", "author_handle", "original_post_url", "repo_url", "models_used",
    "cost_disclosure_status", "evidence_quotes", "review_status",
]


def csv_value(value):
    if isinstance(value, list):
        value = " | ".join(value)
    if isinstance(value, str) and re.match(r"^\s*[=+\-@]|^[\t\r\n]", value):
        return "'" + value
    return value


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows({field: csv_value(row[field]) for field in fields} for row in rows)
    write_text(path, buffer.getvalue(), encoding="utf-8-sig")


def cell(value) -> str:
    return "—" if value is None else str(value).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")


def distribution(title: str, counts: Counter, total: int) -> list[str]:
    return ["", f"## {title}", "", "| 项目 | 案例数 | 占比 |", "|---|---:|---:|", *(
        f"| {cell(name)} | {count} | {count / total:.1%} |" for name, count in
        sorted(counts.items(), key=lambda entry: (-entry[1], str(entry[0])))
    ), *([] if counts else ["| 无记录 | 0 | — |"])]


def report(rows: list[AIWorldCase], is_mock: bool, excluded: int, manual: bool) -> str:
    total = len(rows)
    known = sum(case.is_open_source is not None for case in rows)
    opened = sum(case.is_open_source is True for case in rows)
    rate = f"{opened}/{known}（{opened / known:.1%}）" if known else "无明确记录"
    coverage = "离线合成样本，仅供验收。" if is_mock else "基于已入库案例。待审核案例也计入统计。"
    if manual:
        coverage = ("基于公开 X 嵌入正文与公开项目链接的人工标注。未采集作者回复，部分主帖正文被截断。"
                    "试玩链接已检查 HTTP 响应，交互功能待复核。样本来自偏向 Claude Fable 5.2 的目录，"
                    "频次仅反映这批样本。")
    lines = [
        "# AI 生成交互世界 · 阶段一分析", "", coverage, "",
        f"- 样本总数 {total}，排除 {excluded} 条拒绝记录。",
        f"- 开源率 {rate}，分母为有明确开源状态的案例，未知 {total - known} 条。",
        f"- 待审核 {sum(case.review_status == ReviewStatus.PENDING for case in rows)} 条。",
        f"- 标记疑似重复 {sum(bool(case.possible_duplicate_urls) for case in rows)} 条。",
        "- 各项占比以入库样本数为分母。多选项的占比可超过 100%。",
    ]
    for title, field in [
        ("可复现度", "reproducibility_level"), ("主题", "theme_category"),
        ("生成模式", "generation_mode"), ("模型", "models_used"), ("技术栈", "tech_stack"),
        ("Skill 与 Prompt", "skills_or_prompts_used"), ("工作流步骤", "workflow_steps"),
        ("成本与耗时披露", "cost_disclosure_status"),
    ]:
        counts = Counter()
        for row in rows:
            value = getattr(row, field)
            counts.update(dict.fromkeys(value, 1) if isinstance(value, list) else [value])
        lines.extend(distribution(title, counts, total))
    pattern_counts = Counter()
    for case in rows:
        workflow = " ".join(case.workflow_steps + case.skills_or_prompts_used)
        pattern_counts.update(label for label, pattern in WORKFLOW_PATTERNS.items() if re.search(pattern, workflow))
    lines.extend(distribution("工作流模式", pattern_counts, total))
    lines.extend(["", "## 作者披露的费用与耗时", "",
                  "| 案例 | 费用（USD） | 耗时（分钟） | 原帖 |", "|---|---:|---:|---|"])
    disclosures = [case for case in rows if case.reported_cost_usd is not None or case.reported_time_minutes is not None]
    lines.extend(
        f"| {cell(case.title)} | {cell(case.reported_cost_usd)} | {cell(case.reported_time_minutes)} | "
        f"[原帖]({case.original_post_url}) |" for case in disclosures
    )
    if not disclosures:
        lines.append("| 无明确披露 | — | — | — |")
    if manual:
        lines.extend(["", "部分原帖使用 $ 记号但未明确写明币种，原文保留在证据字段中，USD 数值保持为空。"])
    return "\n".join(lines) + "\n"


def export_cases(rows: list[AIWorldCase], export_dir: Path, report_path: Path, *, is_mock: bool, manual: bool = False) -> None:
    from json import dumps

    active = [row for row in rows if row.review_status != ReviewStatus.REJECTED]
    serialized = [row.model_dump(mode="json") for row in active]
    queue = [row.model_dump(mode="json") for row in rows if row.review_status == ReviewStatus.PENDING]
    write_text(export_dir / "ai_worlds.json", dumps(serialized, ensure_ascii=False, indent=2) + "\n")
    write_csv(export_dir / "ai_worlds.csv", serialized, list(AIWorldCase.model_fields))
    write_csv(export_dir / "review_queue.csv", queue, REVIEW_FIELDS)
    write_text(report_path, report(active, is_mock, len(rows) - len(active), manual))
