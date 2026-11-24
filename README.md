# AI 生成交互世界案例库

查询平台收录 59 个由 AI 构建的交互世界。支持全文搜索、组合筛选、原文取证和工作流拆解。[在线图鉴](https://generated-worlds-atlas.zeshentian1.chatgpt.site) · [提交新世界](https://github.com/ZeshenTian/ai-worlds-tracker/issues/new?template=new-world.yml)

## 2026 年 11 月 24 日首发数据

保留第一阶段 37 条记录，补录 10 条 Gemini、12 条 GPT。按作品去重后，Claude 涉及 35 条、Gemini 12 条、GPT 13 条，其中一例使用两个家族。每项都能回溯作者原帖或署名作品页。原始 37 条的不可变副本在 research/seed_snapshot/worlds.json。

- 57 个非空试玩入口均经 Chromium 检查。6 个确认可操作，2 个要求登录，49 个仍待核验，另有 2 个作品未提供入口。经复核的 25 张 16:9 实景封面用于卡片及详情页。
- 通过认证 Firecrawl 实际读取 37 个唯一页面，包含 8 个仓库首页、15 份仓库文件和 14 个第一方作品页或技术复盘。37 个目标均返回 HTTP 200。GitHub API 提供目录和许可证；5 个官方页面另用出版方 HTML 核对逐字引文。每个字段的来源和抓取方式保存在 [取证记录](research/expansion/repo_evidence.json)。
- 原文能支持精确制作时间的有 4 例。美元费用在这批样本中均未获得明确证实。约数、包含停顿的会话总时长保留在文字证据中。
- [公共快照](data/exports/ai_worlds.json)、[统计元数据](data/exports/meta.json)、[待审核队列](data/exports/review_queue.csv)和[逐案验活结果](data/state/demo_health.json)随代码一同保存。原始种子沿用第一版上架状态，自动发现的新条目须按审核策略发布。

## 运行、部署与投稿

本地需要 Node.js 22.13+。在 platform/ 执行 npm ci 和 npm run build:static，再用 python3 -m http.server 8000 --directory out 预览。静态输出包含所有详情页及前端交互，通过 GitHub Issue Form 收集来源、试玩与源码链接。维护者核验后，可将 X 原帖加入 config/seeds.yaml 的 seed_urls，在下一次同步纳入处理。

**Vercel** 打开仓库部署按钮，保留仓库根目录和预置的 vercel.json 设置，选择 Deploy。若希望接收本仓库后续 main 分支提交，从 Vercel 的 Import Git Repository 选择本仓库并部署。[一键部署](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FZeshenTian%2Fai-worlds-tracker) · [部署按钮文档](https://vercel.com/docs/deploy-button)

**Cloudflare Pages** 在 Workers & Pages 新建 Pages 项目并连接本仓库。生产分支 main，根目录 platform，构建命令 npm run build:static，输出 out，Node 版本 22。后续对 main 的更新会触发重新部署。使用 Direct Upload 项目时，也可以在 GitHub Secrets 配置 CLOUDFLARE_API_TOKEN（Pages Edit）、CLOUDFLARE_ACCOUNT_ID，并在 Variables 设置 CLOUDFLARE_PAGES_PROJECT，然后点 Run workflow 一键发布。[Pages 部署工作流](https://github.com/ZeshenTian/ai-worlds-tracker/actions/workflows/deploy-pages.yml) · [Pages Git 集成说明](https://developers.cloudflare.com/pages/get-started/git-integration/)

## 手动同步和每 6 小时更新

1. 在 GitHub → Settings → Secrets and variables → Actions 添加 X_BEARER_TOKEN、OPENAI_API_KEY 和 FIRECRAWL_API_KEY（也支持 FIRECRAWL_TOKEN）。X 应用需要近期检索及主帖读取权限，模型账号需要支持 Structured Outputs。GitHub 提供同名内置 GITHUB_TOKEN。
2. 在仓库工作流权限中允许写入内容。进入 Actions → Sync worlds → Run workflow 可手动同步。每 6 小时的定时采集目前关闭。如需启用，添加仓库变量 ENABLE_SCHEDULED_SYNC=true；计划运行在 UTC 00、06、12、18 时的第 17 分钟。
3. 默认严格审核。新候选进入 review_queue.csv。运行 Review a world，输入 world_id 并选择 approved 或 rejected，工作流将决定和新快照一起提交。可设置 AUTO_APPROVE_TRUSTED=true 启用信任策略。仅对白名单监控作者或登记的第一方目录生效，同时要求有原文证据、模型、可验证试玩或经 GitHub 确认存在的仓库，并通过数据校验；拒绝记录保留。
4. 自动同步依次处理新增种子、各检索式和账号的增量结果、作者自回复、外链富化、结构化抽取、浏览器验活与导出。每路首次最多取最新 30 条，此后传 since_id 并读完所有新结果页。首次未命中的旧帖可加入 seed_urls 回补；近期检索受 X 的回溯窗口约束。状态含 last_tweet_id 和 last_synced_at，缓存含已读主帖、回复、网页及抽取结果。正常重试复用已落盘结果，GitHub 清退缓存后部分请求可能重新发生。

本地实跑使用 x_api_v2 或 third_party 配置，先执行 uv sync --frozen 和 uv run playwright install chromium，再运行 uv run python -m src.sync_catalog。仅复现二期取证与快照可用以下命令。首次收录时间按本库的登记时间排序，种子使用首次站点建档时间。

```sh
uv run python -m src.research_evidence
uv run python -m src.verify_demos --input data/exports/ai_worlds.json
uv run python -m src.publish_catalog --curate
```

下面保留第一阶段独立采集与离线研究的使用方法。

## 安装与离线验收

要求 Python 3.11+ 和 macOS 或 Linux。

```bash
uv sync --python 3.11
X_ADAPTER=mock uv run pytest
X_ADAPTER=mock uv run python -m src.cli run-all --mode seed
```

也可用 `python3.11 -m venv .venv` 建立环境，激活后运行 `python -m pip install . "pytest>=8"`。此时所有示例中的 `uv run` 可以省略。

离线模式使用 `tests/fixtures/`，无需密钥。默认将三份数据文件写入 `data/mock/exports/`，报告写入 `reports/step1_summary.md`。真实环境默认使用 `data/` 和 `reports/live/step1_summary.md`。

## 复现首批真实样本

`research/seed_snapshot/` 保存了公开 X 嵌入接口返回的 39 条主帖、作者与项目链接的手工标注、以及项目页的 HTTP 检查记录。37 条进入审核队列。两条指定参考帖保留在原始采集记录中。

- [Gemini 4 Neon 静态图像动画](https://x.com/ai_for_success/status/2123467103110078747) 的公开正文证实了静态图分层和景深生成，交互式世界仍待确认。
- [Three.js Grassworks 演示更新](https://x.com/Bk23544/status/2123791331541807385) 的公开正文说明了草地演示升级，生成模型参与情况仍待确认。

首批候选以 Claude 为主，另有 Gemini 和 GPT 案例。模型和费用以作者原文或作者署名的项目页为准。试玩链接的 HTTP 状态与项目页标题作可用性线索，交互功能待复核。公开嵌入只提供主帖，部分正文有截断。[Claude 候选目录](https://github.com/fengyiqicoder/awesome-fable-5.2/blob/main/all/3d-worlds.md)、[Gemini 候选目录](https://www.bestxbuilds.com/builds/loa-threejs)、[Void Explorer 作者复盘](https://developers.openai.com/blog/how-to-build-games-with-astra)。

```bash
export X_ADAPTER=manual
uv run python -m src.cli --data-dir data/replay import-x research/seed_snapshot/posts.json
uv run python -m src.cli --data-dir data/replay dedup
uv run python -m src.cli --data-dir data/replay extract \
  --annotations research/seed_snapshot/annotations.json \
  --evidence-file research/seed_snapshot/links.json
uv run python -m src.cli --data-dir data/replay export
```

这组命令无需密钥，可复现 `data/replay/exports/` 与 `reports/live/step1_summary.md`。可在子命令之前传入 `--data-dir`、`--report-path`，将结果写入独立位置。

## 运行线上数据管线

复制 `.env.example` 到 `.env`，再选择 X 数据源。

| 配置 | 用途 |
|---|---|
| `X_ADAPTER=x_api_v2`、`X_BEARER_TOKEN` | 读取 X 主帖、按会话 ID 查找作者自回复 |
| `X_THREAD_ARCHIVE=true` | 使用 X 全量历史搜索补齐旧会话，需对应账号权限 |
| `X_ADAPTER=third_party`、`X_THIRD_PARTY_BASE_URL`、`X_THIRD_PARTY_API_KEY` | 对接第三方 JSON 接口 |
| `X_ADAPTER=manual` | 导入已保存的 X 主帖或作者线程 JSON/JSONL |
| `FIRECRAWL_API_KEY` | 抓取外链正文 |
| `OPENAI_API_KEY`、`EXTRACTION_MODEL` | Structured Outputs 抽取，默认 `gpt-5-mini` |
| `GITHUB_TOKEN` | 可选，提高 GitHub 根目录和许可证元数据查询额度 |

将新种子 URL 逐行加入 `config/seeds.yaml` 的 `seed_urls`。搜索模式使用 `search_queries`，并用第一条完整检索式约束 `watch_accounts` 中的作者。每条检索式默认最多取 30 条，使用 `--limit` 调整。近期搜索只覆盖 X API 的时间窗口，超出窗口的线程会标记为 `recent_only`。追加种子时会复用缓存。用 `ingest --refresh` 更新近期检索和线程缓存，可能产生新的 API 请求。

```bash
uv run python -m src.cli ingest --mode seed
uv run python -m src.cli ingest --mode search --limit 20
uv run python -m src.cli dedup
uv run python -m src.cli enrich
uv run python -m src.cli extract
uv run python -m src.cli export
uv run python -m src.cli run-all --mode seed
```

第三方适配器使用 `Authorization: Bearer …`。网关的 `GET /tweets/{id}` 返回一个 `RawTweetRecord`，`GET /search/recent?query=…&max_results=…` 返回 `{"tweet_ids":["123"]}`。供应商接口格式不同时可在适配器中转换。

手工导入接受 `RawTweetRecord` 数组或 JSONL。每条含 `post` 和可选的同作者 `thread`，帖子最少提供 `tweet_id`、`author_handle`、`text`。可在帖子上提供 `expanded_urls`，也可用 `import-x --expand-short-links` 解析剩余的 t.co 链接。导入后在手工模式运行 `run-all`，会从去重继续执行 Firecrawl 和模型抽取。

## 输出与复核

- `raw/x/` 保存帖子和线程缓存，`raw/firecrawl/` 按 URL 保存正文与 GitHub 工作流文档。Firecrawl 请求只包含非 X 外链。
- `processed/cases.jsonl` 按世界 ID 增量更新。证据未变时复用抽取缓存。多个帖子共享仓库或明确的试玩地址时归为一组，优先选仓库作者，再用时间与归属线索排序。仅有媒体或文本相似性的候选会留下待核标记。
- `exports/ai_worlds.json` 含结构化案例，`ai_worlds.csv` 和 `review_queue.csv` 使用 UTF-8 BOM。审核队列包含待审核案例。执行 `review WORLD_ID approved` 或 `review WORLD_ID rejected` 会更新审核结果并重新导出。
- 金额只接受能在作者来源中核对的明确美元数值，耗时统一为分钟。金额及耗时均有值记为 `disclosed`，仅一项有值记为 `partial`，两项皆无证据记为 `undisclosed`。公开仓库和作者明确宣称开源分别有独立的字段证据。

接口参考 [X 最近搜索](https://docs.x.com/x-api/posts/search-recent-posts)、[X 历史搜索](https://docs.x.com/x-api/posts/search-all-posts)、[Firecrawl Scrape](https://docs.firecrawl.dev/api-reference/endpoint/scrape) 和 [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)。
