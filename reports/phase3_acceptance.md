# AI 交互世界图鉴 · 三阶段验收报告

线上复验完成于 2026 年 11 月 24 日 22:33（北京时间）。原域名公开 **889** 个案例，保留原有 59 个，净增 **830** 个。首次扩库已超过 700 个的阶段目标。每周新增 50–150 个及累计破千仍需后续运行记录验证。 [在线图鉴](https://generated-worlds-atlas.zeshentian1.chatgpt.site/) · [验收数据提交](https://github.com/ZeshenTian/ai-worlds-tracker/commit/096666955a4b2658e78b210f7d906ddfe9bd9156)

## 数据与试玩

| 指标 | 扩容前 | 本次验收 |
| --- | ---: | ---: |
| 公开案例 | 59 | 889 |
| 作者给出试玩入口 | 57 | 609 |
| 浏览器已确认可交互 | 6 | 38 |
| 有来源可追溯的作品封面 | 25（42.4%） | 859（96.6%） |
| 公开仓库链接 | — | 66 |
| 标记为开源 | — | 30 |

浏览器已对 609/609 个当前试玩网址留下检查记录。公开目录中，38 个通过实际操作验证，5 个要求登录，3 个标记失效，563 个尚未确认可操作，280 个没有独立试玩入口。在 563 个尚未确认可操作的入口里，269 个未识别出可操作场景，205 个的画布在操作后的变化未超过空闲动画，34 个受到访问限制，29 个超时。只有浏览器观察到操作反馈才计入“可试玩”。 [验活明细](../data/state/demo_health.json)

封面包括 421 张试玩页面截图、383 张 X 原帖媒体、44 张作者项目素材和 11 张项目海报。30 个案例留空。对头像、通用链接卡和未能归属给该作品的转帖画面均予以排除。 [原帖封面记录](../data/state/x_covers.json) · [项目配图记录](../data/state/primary_covers.json)

新增 830 个案例中，830 个有中英文摘要。267 个有来源支持的制作步骤，其中 267 个提供逐步对应的中英文。其余案例保留作者披露的信息。 [公开数据](../platform/data/worlds.json)

## 目前的信息源

最终按主来源统计，627 个以 X 原帖为主（70.5%），262 个以项目页为主。项目页包括 AIGameShare 作者作品 153 个、GitHub 作者仓库 53 个、Devpost 参赛项目 44 个、OpenAI Showcase 12 个。策展目录用于发现作品，同一作品经多条路径命中只计算一次。

| X 采集渠道 | 返回条数 | 渠道内不同顶层帖子 |
| --- | ---: | ---: |
| 试玩托管域名反查 | 273 | 195 |
| 作者回溯 | 543 | 528 |
| 官方主帖回复 | 151 | 151 |
| 官方主帖引用 | 155 | 155 |
| 作者自回复 | 100 | 100 |
| 回查上游原帖 | 17 | 17 |
| 生态账号提及 | 175 | 174 |
| 通用关键词 | 1,265 | 1,155 |
| 专题、多语关键词 | 567 | 522 |
| 小批量试采 | 190 | 170 |

历史检索覆盖 2026-05-24 至 2026-11-24（UTC）。共返回 3,436 条顶层记录，合并重复和被引原帖后得到 3,025 个不同帖子 ID。54 个监控账号中，53 个在作者检索通道有结果，@patchgg 当轮无返回。配置包含 6 条基础检索式、17 条 Apify 专用检索式、5 个官方发布主帖、10 条回复及引用检索。托管域包括 Claude Artifacts、ChatGPT Sites、Patch、AI Studio、GitHub Pages、Vercel、itch.io。体素与 WebGL/WebGPU 两组专题查询超时，部分线程或时间段无返回，完整回执保留这些缺口。 [监控账号和检索式](../config/seeds.yaml) · [逐通道回执](../research/expansion/apify_audit.json)

持续监控 17 个策展入口。最新一轮保留 3,150 个去重 X 原帖地址、700 个待取证的项目地址，目录错误 0 个。高产来源包括 Astra Atlas、Astra 的 PLAYABLE 清单、Claude Artifact Hall of Fame、Opus 游戏清单和 Fable、Gemini 系列目录。 [全部入口和官方主帖](../config/catalogs.yaml) · [每个入口的发现量](../data/state/catalog_seeds.json)

首批策展取证保留 388 个作品，包括 182 条 X 原帖、153 个 AIGameShare 作者作品和 53 个 GitHub 作者仓库。第二批从 2,133 个待查原帖中通过 X 官方 oEmbed 确认 2,077 个，最终保留 317 个作品、271 位作者。另一个补充渠道从三个 Devpost 活动的 118 个项目链接中保留 44 个。各批次与直采结果在总账中再次去重。 [首批审计](../research/expansion/catalog_audit.json) · [第二批逐目录审计](../research/expansion/x_catalog_extra_audit.json) · [Devpost 作品与原文](../research/expansion/devpost_worlds.json)

## 审核与日常更新

规则先对来源、链接、互动量和相关性做初筛，再抽取作者原文、模型、试玩与仓库。带链接的帖子以 10 赞、纯视频以 40 赞作为常规互动门槛。自动上架需要原文证据、明确模型和去重检查，并满足实测可玩、仓库存在，或可信作者／托管域且至少 40 赞中的一项。有原始资料的策展作品另走编辑审核。Godogen 的一条线索只推荐通用制作工具，核对原帖后已结束该条抓取。本轮还使用批量审核通过了 23 条，并保留决定及理由。 [审核规则](../src/publish_catalog.py) · [本轮批量决定](../research/expansion/batch_decisions.json)

公开快照有 869 个已通过审核、20 个沿用原种子库的公开记录。审核队列有 177 条，其中 157 条尚未公开。另有 57 位已有至少两件公开作品的作者进入监控推荐名单。 [审核队列](../data/exports/review_queue.csv) · [作者名单](../data/state/watch_suggestions.json)

采用每日更新。GitHub Actions 已启用，每天北京时间 09:17（UTC 01:17）刷新目录、增量抓 X、抽取、验活、补封面、发布静态快照。日常 Apify 上限为每 UTC 日 0.30 美元。每轮默认最多做 80 组相关性判断、12 组深度抽取、12 个入口验活。认证信息保存在仓库 Secrets。两次手动触发同一生产工作流均成功，验收时尚未跨过下一个定时点。 [第一次成功运行](https://github.com/ZeshenTian/ai-worlds-tracker/actions/runs/45405455869) · [第二次成功运行](https://github.com/ZeshenTian/ai-worlds-tracker/actions/runs/45408439115) · [定时配置](../.github/workflows/sync-worlds.yml)

## 费用记录

本次本地 Apify 历史回溯收到的计费回执合计 **0.522 美元**，含试采的 0.0225 美元。云端同步另计，验收时恢复的云端账本内有 79 个运行记录，其中 2 个尚无费用回执。首批 11 个 Firecrawl 目录请求成功，按标准抓取估算 11 积分，后续目录及外链富化另计。 [Apify 账本](../research/expansion/apify_audit.json) · [首批费用及口径](../research/expansion/catalog_audit.json)

模型费用留有分批记录。首批策展可计量 308 次，输入 591,105、输出 175,381 token。早期另有 344 条初审与 170 条复审缺少用量回执。第二批 X 策展 271 次，输入 489,626、输出 135,069 token，按该次模型公开单价估算 0.412 美元。另记录直采筛选与抽取 350 次，输入 656,639，输出 180,606 token，Devpost 取证 79 次，输入 160,607，输出 23,343 token。本次没有取得完整供应商账单，无法据此核定全流程总价。 [第二批用量明细](../research/expansion/x_catalog_extra_audit.json)

## 线上复验

同一公开域名已更新至 889 条。已用独立 Chromium 浏览器复验首页、可试玩筛选、表格切换、标题搜索、案例详情、趋势、语言切换和手机宽度。投稿入口通往站内表单，空数据由服务端拒绝。GitHub 静态副本提供 Issues 投稿入口。验收时 Python 测试 80 项通过，TypeScript 检查通过，静态构建生成 889 个案例详情页。公开数据逐条通过结构校验，并检查了案例 ID、原帖 ID、试玩网址去重和封面文件。 [在线图鉴](https://generated-worlds-atlas.zeshentian1.chatgpt.site/) · [趋势](https://generated-worlds-atlas.zeshentian1.chatgpt.site/trends) · [投稿](https://generated-worlds-atlas.zeshentian1.chatgpt.site/submit)

GitHub 数据提交为 `096666955a4b`，ChatGPT Sites 应用版本为 7。图鉴从静态发布分支加载，后续增量沿用原域名。发布切换期间观察到边缘缓存短暂返回上一版，随后在原域名验证到“38 / 889”的可试玩筛选结果。六个云端分片检查 260 条存量链接，另对最后一批网址在本机补验，最终所有公开试玩网址均有同网址的检查记录。可在独立窗口打开实测案例，核对原帖、作品截图和试玩状态。 [最终静态发布](https://github.com/ZeshenTian/ai-worlds-tracker/actions/runs/45414676351) · [六分片验活](https://github.com/ZeshenTian/ai-worlds-tracker/actions/runs/45411312554) · [Halls of History](https://generated-worlds-atlas.zeshentian1.chatgpt.site/worlds/world-c434c87acb4b3dfba1acf3aa)
