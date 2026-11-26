"""Recheck the editorial evidence for the public catalog: python -m src.research_evidence."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import json
import os
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from dotenv import load_dotenv

from .enrich_firecrawl import EnrichmentCache, Firecrawl
from .links import repo_root
from .models import EnrichedLinkContent
from .storage import digest, read_json, write_json, write_text


# Each claim is accepted only when all its excerpts occur in the fetched source.
# An empty/absent build-time or cost field is never inferred from rendering time.
REPO_NOTES = {
    "starknightt/summer-festival": {
        "PROMPTS.md": (
            ["The prompts given to Claude Code to build this game, in order and verbatim.",
             "threejs-gameplay-systems", "webgpu-threejs-tsl", "blender through the mcp"],
            {"workflow_steps": ["作者公开了发给 Claude Code 的两轮原始提示，先构建海边祭典，再根据试玩提出五项修订。"],
             "skills_or_prompts_used": ["threejs-gameplay-systems", "webgpu-threejs-tsl", "Blender MCP"]}),
    },
    "tornikegomareli/matrix": {
        "docs/experiment.md": (
            ["The model planned the change, wrote it, ran it", "The conversation ran for about 22 hours, pauses included"],
            {"workflow_steps": ["作者提出目标并检查每轮结果，模型规划、编写、运行并回报检查结果。作者记载对话大约持续 22 小时，包含中途停顿。"],
             "skills_or_prompts_used": ["Claude Code"]}),
    },
    "coding-nanami/davinci-mechanics": {
        "README.md": (
            ["Everything is generated in code: the geometry, the paper, the ink lines",
             "minifies the inline CSS and scripts into `dist/index.html`"],
            {"workflow_steps": ["用代码生成几何体、纸页与墨线，在单页源文件中维护场景，再把内联样式和脚本压缩到发布版本。"]}),
    },
    "leonxlnx/room-at-dawn": {
        "README.md": (
            ["furniture, cloth, plants and trees are generated procedurally with seeded randomness",
             "re-bake the lighting (CPU, ~20–30 min)"],
            {"workflow_steps": ["用固定随机种子生成家具、布料和植物，再用 CPU 烘焙光照。README 所列 20 至 30 分钟指光照重新烘焙的时长。"]}),
    },
    "cola5939/pixel-dioramas": {
        "README.md": (
            ["Small pixel-art dioramas sculpted, baked and rendered with Ink Studio.", "场景在构建时预先烘焙进页面"],
            {"workflow_steps": ["在 Ink Studio 雕刻与烘焙雨夜面摊，把场景预先打包进可离线打开的 WebGL 单页。"],
             "skills_or_prompts_used": ["Ink Studio"]}),
    },
    "xikhar/papertrails": {
        ".github/workflows/pages.yml": (
            ["npm ci", "npm run build", "actions/upload-pages-artifact@v3", "actions/deploy-pages@v4"],
            {"workflow_steps": ["仓库的 Pages 工作流在 main 分支更新时安装依赖、构建项目，并把 dist 目录发布到 GitHub Pages。"]}),
    },
    "nifftyswiggle/leageofanimals-game": {
        "js/main.js": (
            ["this.initThree();", "this.city.generateCity();", "this.initRain();"],
            {"workflow_steps": ["从游戏入口复现初始化顺序：建立 Three.js 场景和物理系统，生成城市，再加入天空、降雨与玩家。"]}),
    },
    "kevintngo/dungeon-game": {
        "build.js": (
            ["index.html stays the readable source.", "goes through terser."],
            {"workflow_steps": ["作者保留可读的单页源代码，通过 Node 构建脚本压缩着色器和 JavaScript，生成 dist/index.html。"],
             "tech_stack": ["Node.js", "Terser"]}),
    },
}


AUTHOR_BUILD_NOTES = {
    "world-48aa5afb3651d9cd35786d63": {
        "https://developers.openai.com/showcase/void-explorer": (
            ["Model AURORA in Blender and integrate the spacecraft into the game.",
             "Connect landing, walking, and reboarding into one planetary expedition."],
            {"workflow_steps": ["将 Blender 制作的 AURORA 飞船接入游戏，把着陆、步行与重登飞船连成同一次地面探险。"]}),
        "https://developers.openai.com/blog/how-to-build-games-with-astra": (
            ["collected 90 frame intervals", "small local physics world"],
            {"workflow_steps": ["作者用 Rapier 在局部物理世界处理步行；更换飞船模型前后，用同一项 Playwright 测试采集 90 个帧间隔，并比较绘制调用与三角形数。"],
             "tech_stack": ["Rapier"]}),
    },
}


def normalized(text):
    return " ".join(text.split())


def fetch_page(url, api, cache, *, direct_after=None):
    provider = "firecrawl" if direct_after is None else "primary"
    path = cache / provider / (digest(url) + ".json")
    if path.exists():
        return EnrichedLinkContent.model_validate(read_json(path))
    page = api.scrape(url) if direct_after is None else api.public_document(url, direct_after)
    write_json(path, page.model_dump(mode="json"))
    return page


def verified_sources(url, kind, quotes, api, cache, **details):
    page = fetch_page(url, api, cache)
    try:
        accept(page, quotes)
    except ValueError:
        if page.fetch_method != "firecrawl":
            raise
        # GitHub's rendered Markdown and source file can differ (inline code, escapes,
        # or an empty file viewer). Attribute exact excerpts to the text that contains them.
        raw = fetch_page(url, api, cache, direct_after=page.firecrawl_status_code)
        accept(raw, quotes)
        return [source(page, kind, [], quote_check="checked_against_primary", **details),
                source(raw, kind, quotes, **details)]
    return [source(page, kind, quotes, **details)]


def check_case(row, api, cache, prior):
    sources, patch = [], {}
    repo = row.get("repo_url")
    catalog = {}
    if repo:
        catalog_path = cache / "repositories" / (digest(repo) + ".json")
        if catalog_path.exists():
            catalog = read_json(catalog_path)
        else:
            try:
                catalog = api.github_catalog(repo)
                catalog["checked_at"] = datetime.now(UTC).isoformat()
            except httpx.HTTPStatusError as exc:
                response = exc.response
                limited = response.status_code == 429 or (response.status_code == 403 and
                          (response.headers.get("x-ratelimit-remaining") == "0" or "rate limit" in response.text.lower()))
                previous = prior.get("cases", {}).get(row["world_id"], {}).get("repository", {})
                expected = repo.replace("https://github.com/", "https://api.github.com/repos/") + "/"
                if not limited or not previous.get("tree_url", "").lower().startswith(expected.lower()):
                    raise
                catalog = dict(previous)
                catalog.setdefault("checked_at", prior["checked_at"])
                catalog["refresh_status_code"] = response.status_code
                catalog["refresh_note"] = "GitHub rate limit; reused the previously verified public tree."
            write_json(catalog_path, catalog)
        if not catalog["exists"]:
            raise ValueError(f"Repository does not exist: {repo}")
        # Only a verified MIT license is classified here. No license is an unknown.
        sources.extend(verified_sources(repo, "repository", [], api, cache))
        if catalog.get("license") == "MIT":
            patch["is_open_source"] = True
            sources.append({"kind": "license", "url": repo.replace("https://github.com/", "https://api.github.com/repos/"),
                            "method": "github_api", "field": "license.spdx_id", "quotes": ["MIT"]})
        key = urlsplit(repo).path.strip("/").lower()
        notes = REPO_NOTES.get(key, {})
        docs = {item["path"]: item for item in catalog["files"]}
        for path in notes.keys() - docs.keys():
            docs[path] = {"url": f"{repo}/blob/{quote(catalog['default_branch'], safe='')}/{quote(path)}",
                          "kind": "source_code"}
        for path, item in docs.items():
            quotes, new_fields = notes.get(path, ([], {}))
            sources.extend(verified_sources(item["url"], item["kind"], quotes, api, cache,
                                            blob_sha=item.get("blob_sha")))
            for field, values in new_fields.items():
                patch.setdefault(field, []).extend(values)
            if quotes:
                patch.setdefault("evidence_quotes", []).extend(quotes)
    primary = row.get("original_post_url", "")
    if primary.startswith("https://developers.openai.com/showcase/"):
        # The author-reviewed case already contains the individual build summary. Recheck
        # its original excerpts here against the publisher's current document as well.
        quotes = row["evidence_quotes"]
        sources.extend(verified_sources(primary, "publisher_build_process", quotes, api, cache))
    for url, (quotes, new_fields) in AUTHOR_BUILD_NOTES.get(row["world_id"], {}).items():
        sources.extend(verified_sources(url, "author_build_process", quotes, api, cache))
        for field, values in new_fields.items():
            patch.setdefault(field, []).extend(values)
        patch.setdefault("evidence_quotes", []).extend(quotes)
    return row["world_id"], {"patch": patch, "sources": sources, "repository": catalog}


def source(page, kind, quotes, **details):
    return {"kind": kind, "url": page.url, "retrieved_url": page.final_url,
            "method": page.fetch_method, "status_code": page.status_code,
            "firecrawl_status_code": page.firecrawl_status_code, "quotes": quotes,
            **{k: v for k, v in details.items() if v is not None}}


def accept(page, quotes):
    if page.status != "ok" or not page.markdown.strip():
        raise ValueError(f"{page.url}: {page.status}, empty or missing document")
    haystack = normalized(page.markdown)
    for excerpt in quotes:
        if normalized(excerpt) not in haystack:
            raise ValueError(f"Source changed; review excerpt {excerpt!r} at {page.url}")


def share_evidence_cache(cases, run_cache, data_root):
    """Make verified research documents available to normal pipeline runs."""
    destination = EnrichmentCache(data_root)
    for entry in cases.values():
        catalog = entry["repository"]
        for source in entry["sources"]:
            url, kind = source["url"], source["kind"]
            if source["method"] != "firecrawl":
                continue
            page = EnrichedLinkContent.model_validate(read_json(run_cache / "firecrawl" / (digest(url) + ".json")))
            page.kind = kind if kind in {"repository", "readme", "workflow"} else "page"
            if kind == "repository":
                url = repo_root(url) or url
                page.url = url
                page.repository_owner = catalog.get("owner")
                page.repository_license = catalog.get("license")
                write_json(destination.catalog_path(url), catalog)
            write_json(destination.page_path(url), page.model_dump(mode="json"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-id", help="Reuse the checked pages from this run after an interruption.")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    root = args.root
    load_dotenv(root / ".env", override=False)
    expansion = root / "research/expansion"
    ledger = root / "data/processed/cases.jsonl"
    if ledger.exists():
        with ledger.open(encoding="utf-8") as source:
            rows = [json.loads(line) for line in source if line.strip()]
    else:
        rows = json.loads((root / "research/seed_snapshot/worlds.json").read_text())
    for name in ("gpt.json", "gemini.json"):
        rows += json.loads((expansion / name).read_text())
    relevant = {r["world_id"]: r for r in rows if r.get("repo_url") or r["world_id"] in AUTHOR_BUILD_NOTES or
                r["original_post_url"].startswith("https://developers.openai.com/showcase/")}
    key = os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_TOKEN", "")
    run_id = args.run_id or ("authenticated" if key else "keyless")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id) or run_id in {".", ".."}:
        parser.error("Invalid run ID")
    cache = root / "data/state/research_evidence" / run_id
    target = args.output or expansion / "repo_evidence.json"
    prior = read_json(target) if target.exists() else {}
    cases, errors = {}, {}
    with httpx.Client(timeout=55, follow_redirects=True) as http:
        api = Firecrawl(key, http, os.environ.get("GITHUB_TOKEN"),
                        public_fallback=True)
        mode = "authenticated" if api.headers else "keyless"
        mode_file = cache / "mode.json"
        if mode_file.exists() and read_json(mode_file) != mode:
            parser.error("Use a new run ID when changing authentication mode")
        write_json(mode_file, mode)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(check_case, row, api, cache, prior): row for row in relevant.values()}
            for task in as_completed(futures):
                row = futures[task]
                try:
                    world_id, entry = task.result()
                    cases[world_id] = entry
                    write_json(cache / "cases" / f"{world_id}.json", entry)
                    print(f"Checked {row['title']} ({len(cases)}/{len(relevant)})", flush=True)
                except (ValueError, httpx.HTTPError, KeyError) as exc:
                    errors[row["world_id"]] = str(exc)
                    print(f"Unverified {row['title']}: {exc}", flush=True)
    write_json(cache / "errors.json", errors)
    if errors:
        raise SystemExit(f"{len(errors)} unverified cases; resume with --run-id {run_id}")
    methods = Counter(s["method"] for case in cases.values() for s in case["sources"])
    output = {"checked_at": datetime.now(UTC).isoformat(), "firecrawl_authentication": mode,
              "source_counts": dict(methods), "cases": dict(sorted(cases.items()))}
    share_evidence_cache(cases, cache, root / "data")
    write_text(target, json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"Verified {len(cases)} cases. Source methods {dict(methods)}")


if __name__ == "__main__":
    main()
