# 图鉴与 WorldFeed 上线验收

2026-11-25 在本机对 `platform/out` 和 `feed/dist` 完成验收。四个 Workstream 已落地，第 5 节的后端测试、双严格盲测、两站生产构建与真实 Chrome 验收均通过。随后已通过 ChatGPT Sites 发布图鉴 v9 和 WorldFeed v2，两个正式域名均可公开访问。此次发布未触发 GitHub 定时同步。

[体验图鉴](http://127.0.0.1:8870/) · [直接玩 NOVA LANCER](http://127.0.0.1:8871/?w=world-3bc9b04773e624981797759d) · [图鉴首页截图](live/atlas-grid-desktop.png) · [WorldFeed 桌面实玩截图](live/worldfeed-topbar-desktop.png) · [前沿世界趋势报告](frontier_trends_report.md)

## 正式部署与分享卡片

[生成世界图鉴](https://generated-worlds-atlas.zeshentian1.chatgpt.site/) · [WorldFeed](https://worldfeed.zeshentian1.chatgpt.site/)

- 两站的初始 HTML 均包含 description、Open Graph 图片和 Twitter 大图卡标签。用 Twitterbot 和 Discordbot 的 User-Agent 分别匿名读取两个首页和对应 JPEG，均返回 HTTP 200。两张图片均为 1200 × 630，下载内容与本地裁图的 SHA-256 一致。
- 使用共享 Chrome 访问图鉴，点击 WorldFeed，再从 Feed 顶栏返回图鉴；另行打开图鉴首卡的作品链接，核对了挂载的世界 ID。首次访问曾命中旧首页缓存，随后使用无缓存请求验证了正式版本。
- 图鉴保留每日静态快照入口。兼容标记或目录时间未达到当前版本的快照会回退至已部署版本。图鉴发布副本使用 1,632 张被前沿目录引用的封面，对较大的缩略图进行压缩，以符合 Sites 源仓库单次推送大小限制。

## 产品和数据

| 项目 | 验收结果 |
|---|---|
| 后端公开目录 | 2,219 条，其中前沿 1,660 条、历史 559 条。两个前端均仅展示前沿作品。 |
| 图鉴 | 默认「全部」1,660 条，可切换「可试玩」331 条或「视频演示」1,329 条。每页 24 张网格卡片。「全部」优先显示最近四个能直达 WorldFeed 的作品，其余按发布日期倒序。类型、模型、主题、技术栈使用同款筛选按钮。原详情、投稿和趋势网页已从静态导出移除。 |
| 直接访问 | 可试玩作品中，可嵌入的直达对应 WorldFeed 世界，同时保留作者的官方入口和原帖。其余可试玩作品直达作者网站。视频演示主操作直达原帖，包括缺少官方试玩地址的镜像和已标记失效的入口。三种分支均已实际点击，并核对打开的地址。 |
| WorldFeed | 223 条，其中同源镜像 2 条、外部嵌入 221 条，纯外链和历史作品均为 0。图鉴可试玩 ID 与 Feed 的 223 个 ID 逐项一致。 |
| 试玩证据 | 图鉴有 332 条公开试玩入口，前沿目录中有 38 条带有 `verified_playable` 凭证。223 条是按镜像清单和嵌入探测结果生成的站内池，本次 Chrome 实测覆盖代表作品与切换路径。第三方站点的可用性仍会变化。 |
| 互动数据 | 85 个不同的前沿 GitHub 仓库均有带时间戳的星数缓存。Feed 内 38 条作品带仓库，均有数值；137 条有正数 X 点赞。心形按钮显示 X 点赞加本机点赞数，点击或按 L 可切换。带仓库的作品显示文字「源码」入口。 |
| 封面与归档分析 | 前沿作品中 1,632 条有封面，覆盖率 98.3%。独立趋势报告涵盖目录规模、模型、主题、技术栈、作品类型与复现层级、工作流与成本耗时、收录口径与质量。 |
| 作者入口例外 | 镜像作品 After the tide 有源码和原帖，作者资料中缺少独立试玩地址，因此保留镜像试玩与已知来源。 |

## 第 5 节执行记录

| 顺序 | 检查 | 结果 |
|---|---|---|
| 1 | `pytest -q` | 259 项通过。 |
| 2 | `python -m src.publish_catalog`、`python -m src.generate_trends_report`、`python -m src.fetch_github_stars` | 发布导出、趋势报告和可嵌入索引生成成功；85/85 个仓库命中缓存。`meta.json` 中 `GPT-62 Astra` 匹配为 0，标准名称为 `GPT-6.2 Astra`。 |
| 3 | `python -m src.eval_golden --benchmark config/golden_benchmark.yaml --report reports/golden_eval_v1.md --strict` | 核心 10/11（90.9%），核心原帖捕获 11/11，长尾 1/5。严格验收通过。[V1 结果](golden_eval_v1.md) |
| 4 | `python -m src.eval_golden --benchmark config/golden_benchmark_v2.yaml --report reports/golden_eval_v2.md --strict` | 核心 8/9（88.9%），核心原帖捕获 8/9。严格验收通过。两版负样本泄漏和聚合号名义上架均为 0。本轮未向种子配置写入盲测链接或作者。[V2 结果](golden_eval_v2.md) |
| 5 | 在 `platform/` 执行 `npm run lint`、`npm run build:static` | ESLint 0 个错误，1 条现有原生图片优化提示。静态导出成功，包含首页和 404，不含三个已退役的页面。构建器提示部分客户端资源超过 500 kB。 |
| 6 | 在 `feed/` 执行 `node scripts/build-feed-data.mjs`、`npm run build` | 两个镜像完整性校验、数据生成、TypeScript 检查和 Vite 生产构建均通过。 |
| 7 | 在 `feed/` 执行 `node scripts/verify-feed.mjs`，再执行 `node scripts/verify-feed.mjs --headless` | 真实 Google Chrome 158。先在 9227 共享窗口新标签验收，再使用一次临时 headless Chrome 进程测试两个视口。 |

## 浏览器实测

首轮验收使用了共享和 headless Chrome；最新的网格与顶栏改版在共享 Chrome 复验。四组都启用了系统深色偏好。两站仍为浅色，页面均无横向溢出。下表舞台高度是在同一构建的共享 Chrome 中另行读取的实际 iframe 边界。

| 视口 | 共享 Chrome | 临时 headless Chrome | 图鉴默认网格 | 3D 舞台高度 |
|---|---|---|---|---|
| 1440 × 900 | 页面及控制台错误 0 | 页面及控制台错误 0 | 4 列 | 852 px，94.7% |
| 390 × 844 | 页面及控制台错误 0 | 页面及控制台错误 0 | 1 列 | 796 px，94.3% |

- 图鉴默认先展示四个可以站内玩的作品，再接上其余作品；分页按同一顺序切片。本轮逐一通过 WorldFeed 打开首页前四项，均观察到可见的 canvas。筛选标签统一使用「全部」。Antigravity 及其平台标签已从技术栈和趋势统计中移除。三个分组按「有试玩链接且健康状态非 broken」「其余作品」「全部前沿作品」实时计算。切换分组同步 URL 并回到第一页；直接访问或刷新 `?tab=video` 仍显示 1,329 条。切换模型、主题或技术栈同步更新结果与可选项计数。各分组中 Claude 的计数也与源数据独立比对一致。
- 网格卡片检查了对应世界的试玩、官方入口和原帖。视频分组内的失效链接案例，主操作确实打开原帖。所测英文页面仅语言切换按钮含中文。
- WorldFeed 顶栏实测高 48 px。桌面 iframe 从 (0, 48) 开始，尺寸 1440 × 852；移动 iframe 同样从 (0, 48) 开始，尺寸 390 × 796。四角和中心的命中元素都是 iframe。世界名称、切换和作者链接位于顶栏，分享按钮已移除。窄屏优先收起作者与帮助，保留原始链接与图鉴入口；顶栏单行且可见控件均在视口内。
- 每个作品最多展示一个前沿模型，使用目录现有版本、日期规则。NOVA LANCER 显示 Claude Opus 5.5，After the tide 同时披露了 GPT-6 Astra 和 Gemini 4 Carbon，顶栏仅显示 Gemini 4 Carbon。
- 已核对顶栏方向按钮、方向键、J/K、顶栏滚轮、L 点赞、刷新后的点赞状态、G 原始链接、O 原帖和源码地址。桌面问号支持悬停、点击与 Esc 关闭。切换后旧 iframe 已从 DOM 卸载。同源镜像内输入 W 后可以用方向键切换；跨域 iframe 取得焦点后可点顶栏切换并恢复外层键盘控制。
- 在共享 Chrome 中另行延迟一个外部 iframe 的响应，确认慢加载提示在 4 秒后出现，地址指向作者原站，载入后提示消失。本轮桌面截图由共享 Chrome 从作者游戏菜单实际进入第一关后生成，画面内的护盾、分数和任务提示由游戏自身绘制。[查看桌面截图](live/worldfeed-topbar-desktop.png)

## 每日同步与上线步骤

1. 确认要发布的代码、数据和镜像资源进入仓库默认分支 `main` 后，在 GitHub Actions 设置里为工作流提供写入内容的权限。分支规则须允许同步工作流更新 `main` 以及 Atlas 的 `static-site` 产物分支。
2. 在仓库 Secrets 配置 `APIFY_API_KEY`、`FIRECRAWL_API_KEY`（兼容 `FIRECRAWL_TOKEN`）和 `MINIMAX_API_KEY`。日常筛选、提取默认用用户此前选用的 `MiniMax-M3`。Qwen 使用 `ALIBABA_TOKEN_PLAN_API_KEY` 和北京 Token Plan 专属兼容端点。GitHub 星数使用 Actions 自动提供的 `GITHUB_TOKEN`。
3. 在仓库 Variables 设置 `NEXT_PUBLIC_WORLDFEED_URL` 和 `VITE_ATLAS_URL` 为两站最终可访问的 HTTPS 地址。若部署到 Cloudflare Pages，设置两个不同的项目变量 `CLOUDFLARE_PAGES_PROJECT`（Atlas）、`CLOUDFLARE_FEED_PAGES_PROJECT`（Feed），并添加 `CLOUDFLARE_ACCOUNT_ID` 和有 Pages 发布权限的 `CLOUDFLARE_API_TOKEN` 至 Secrets。
4. 手动触发 **Sync worlds**，检查采集回执、探测和数据差异。工作流以 `kaito` 增量采集，页大小 20，单轮 Apify 预算 1.50 美元；前沿过滤开启，互动阈值 15，可信作者自动审核默认开启。随后刷新 GitHub 星数、嵌入探测、趋势报告和两站构建，并提交数据快照。1.50 美元仅是单轮 Apify 预算，其他服务各自计费。
5. 若采用 Cloudflare 托管，分别手动运行 **Deploy WorldFeed to Cloudflare Pages** 和 **Deploy to Cloudflare Pages**。构建目标分别是 `feed/dist` 和 `platform/out`。在正式域名打开带 `?w=` 的作品，从图鉴核对试玩、官方入口和原帖。若继续使用既有 ChatGPT Sites 域名，需要通过对应 Sites 项目发布。
6. 首次远端运行和域名验证完成后，设置仓库变量 `ENABLE_SCHEDULED_SYNC=true`。定时表达式为 `17 1 * * *`，即上海时间每日 09:17。每日工作流刷新两站构建并更新 Atlas 静态分支；两个 Cloudflare 发布工作流采用手动触发。本次已解析三份工作流及本地 composite action 的 YAML，核对了调度条件、模型变量、采集参数、构建和发布目录。远端 Secrets、分支权限和托管发布只在远端运行时生效。

## 工作区交付状态

分支为 `main`，暂存区为空。开始时已有 94 项修改、3 项删除和 2,949 项未跟踪记录。生成本报告后，`git status --short` 显示 103 项修改、15 项删除和 2,961 项未跟踪记录。该计数包含此前的开发和数据资产，不能作为本轮变更量。本轮主要涉及模型名称规范化、趋势与星数生成、图鉴与 Feed 两端、浏览器验收脚本及工作流配置。此段计数记录上线前的工作区。正式发布随后分别提交至两个 Sites 托管源仓库。
