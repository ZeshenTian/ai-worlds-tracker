"""Regenerate the frontier catalog's standalone trends report and playable ID index."""
from collections import Counter
from pathlib import Path
from statistics import median
from .storage import read_json, write_json
from .publish_catalog import family
from .model_era import MINIMUM, CUTOFF


def generate():
    rows = [w for w in read_json(Path("data/exports/ai_worlds.json")) if w["model_era"] == "frontier"]
    meta = read_json(Path("data/exports/meta.json"))
    probes = read_json(Path("data/state/embed_probe.json"))
    mirrors = read_json(Path("data/state/mirrors.json"))
    playable = sorted(w["world_id"] for w in rows if w["world_id"] in mirrors or
                      (w["demo_health_status"] not in {"broken", "login_required"} and
                       probes.get(w["live_demo_url"], {}).get("embeddable")))
    write_json(Path("platform/data/embeddable-ids.json"), playable)
    n = len(rows)
    covers = sum(bool(w["thumbnail_url"]) for w in rows)
    lines = ["# 前沿世界趋势报告", "", f"更新于 {meta['last_updated_at']}。统计范围为公开目录中的 {n:,} 个前沿世界。",
             "", "## 核心概览", "", "| 指标 | 数量 |", "|---|---:|"]
    for k,v in [("提供试玩入口",sum(bool(w["live_demo_url"]) for w in rows)),("已验证可玩",sum(w["demo_health_status"]=="verified_playable" for w in rows)),("WorldFeed 可嵌入（含镜像）",len(playable)),("开源且有仓库",sum(bool(w["repo_url"] and w["is_open_source"]) for w in rows)),("封面覆盖",f"{covers}（{covers/max(n,1):.1%}）")]:
        lines.append(f"| {k} | {v} |")
    def table(name, values, limit=None):
        lines.extend(["",f"## {name}","","| 分类 | 世界数 | 占比 |","|---|---:|---:|"])
        lines.extend(f"| {k} | {v} | {v/max(1,n):.1%} |" for k,v in Counter(values).most_common(limit))
    table("模型家族（多模型作品可重复计入不同家族）",(f for w in rows for f in sorted({family(m) if family(m) in {"Claude","GPT","Gemini"} else "其他" for m in w["models_used"]})))
    table("使用最多的 12 个模型",(m for w in rows for m in dict.fromkeys(w["models_used"])),12)
    table("主题",(w["theme_category"] for w in rows))
    table("前 15 项技术栈",(m for w in rows for m in dict.fromkeys(w["tech_stack"])),15)
    for name,key in [("作品类型","work_type"),("复现层级","reproducibility_level"),("工作流模式","generation_mode")]:
        table(name,(w[key] for w in rows))
    import re
    for label,pattern in [("参考图驱动",r"参考图|reference image"),("迭代调试",r"调试|debug"),("程序化生成",r"程序化|procedural")]:
        hits=sum(bool(re.search(pattern," ".join(w["workflow_steps"]+w["workflow_steps_en"]),re.I)) for w in rows)
        lines.append(f"\n工作流步骤中明确提及{label}的有 {hits} 个。")
    for label,key,unit in [("耗时","reported_time_minutes","分钟"),("成本","reported_cost_usd","美元")]:
        vals=[w[key] for w in rows if w[key] is not None]
        lines.append(f"\n{len(vals)} 个作品披露{label}"+(f"，中位数 {median(vals):g} {unit}。" if vals else "。"))
    lines+=["","## 采集口径与质量","",f"模型版本下限为 "+ "、".join(f"{k} {a}.{b}" for k,(a,b) in MINIMUM.items())+"。未标版本的家族按披露日期判断，日期分界为 "+"、".join(sorted(set(CUTOFF.values())))+"。收录作者展示的交互空间和代码生成的三维场景，排除聚合转载、广告、平面界面及缺乏引证的案例。"]
    for v in ["v1","v2"]:
        report=Path(f"reports/golden_eval_{v}.md")
        lines+=["",f"### [{v.upper()} 严格盲测]({report.name})","",*(l for l in report.read_text().splitlines() if l.startswith(("核心召回率","负样本泄漏率","严格验收")))]
    Path("reports/frontier_trends_report.md").write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    generate()
