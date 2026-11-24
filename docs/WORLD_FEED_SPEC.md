# World Feed（桌面端 TikTok 式 3D 世界消费流）实施规格书

> 本文档是一份**面向 AI 编程代理与开发者的独立可执行方案**。目标是在 `ai-worlds-tracker` 同仓库内新建独立前端站点 `feed/`，与现有检索工作台 `platform/` 共用上游数据快照、**独立构建与独立部署**，提供类似桌面端 TikTok 的「浅色极简 · 一条接一条刷着玩 AI 交互世界」体验。

---

## 1. 产品定位与范围边界

### 1.1 定位分工
- **`platform/`（现有站 · 图鉴工作台）**：图书馆 / 研究检索工具，适合分面筛选、表格对比、趋势分析。
- **`feed/`（本方案 · 世界消费流）**：大众消费入口，打开即进入全视口浅色剧场，像刷短视频一样按滚轮 / `↑↓` 快速浏览世界，支持一键就地激活 `<iframe>` 直接上手试玩。

### 1.2 范围边界（Non-Goals）
- **不包含** X 平台扩量抓取 / Apify 采集管线（由上游 `src/` 数据管线单独演进，`feed/` 只消费标准 JSON 快照与本地预处理产物）。
- **不包含**深色模式（全站固定**纯净浅色**视觉，不设暗黑主题）。
- **不包含**服务端数据库或登录体系（纯静态导出，收藏夹与语言偏好存浏览器 `localStorage`）。

---

## 2. 仓库结构与独立部署方案

采用 **Monorepo 同仓双站、独立部署** 架构：

```text
ai-worlds-tracker/
├── data/
│   ├── exports/ai_worlds.json        # 上游统一数据快照（只读输入）
│   └── state/
│       ├── embed_probe.json          # 新增：各 live_demo_url 的 iframe 可嵌入性探测缓存
│       └── mirrors.json              # 新增：已构建的开源同域镜像清单
├── platform/                         # 现有检索工作台（不动）
│   ├── data/worlds-en.json           # 复用：英文工作流/提示词翻译映射
│   └── public/thumbnails/            # 复用：现有 16:9 实景截图
├── feed/                             # 新增：独立桌面端 TikTok 世界流站点
│   ├── package.json                  # Vite + React 19 + TypeScript + lucide-react
│   ├── vite.config.ts
│   ├── vercel.json                   # 独立部署到 Vercel（Root Directory = feed）
│   ├── index.html
│   ├── scripts/
│   │   ├── probe-embeds.mjs          # 探测目标 URL 是否允许 iframe 嵌入
│   │   ├── build-mirrors.mjs         # 为允许商用的开源仓库构建同域静态镜像
│   │   └── build-feed-data.mjs       # 合并快照、探测结果、镜像与封面，输出 public/data/feed.json
│   ├── public/
│   │   ├── data/feed.json            # 编译期生成的静态消费流数据
│   │   ├── thumbnails/               # 同步自 platform/public/thumbnails/
│   │   └── mirrors/<world_id>/       # 开源世界同域静态镜像构建产物
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── styles/tokens.css         # 纯浅色设计令牌
│       ├── styles/feed.css           # 剧场布局、竖排操控栏、信息抽屉、响应式
│       ├── lib/i18n.ts               # 中英双语（共用 localStorage key: atlas-lang）
│       ├── lib/types.ts              # FeedItem 类型定义
│       ├── lib/storage.ts            # 收藏夹、已看记录、语言持久化
│       └── components/
│           ├── TopBar.tsx            # 极简 48px 顶栏（频道切换 + EN/中文 + 图鉴跳转）
│           ├── StageCard.tsx         # 主世界剧场（Browse 预览态 ↔ Playing 实时 iframe 态）
│           ├── ActionRail.tsx        # 帧外固定竖排操作条（↑↓ / 喜欢 / 详情 / 源码 / 外链 / 分享）
│           ├── InfoDrawer.tsx        # 右侧按需滑出抽屉（模型、技术栈、工作流、原文证据）
│           └── ShortcutsHint.tsx     # 底部极简操作提示条
└── .github/workflows/
    └── deploy-feed-pages.yml         # 新增（可选）：独立部署 feed/dist 到 Cloudflare Pages
```

### 为什么 `feed/` 用 Vite + React 纯静态 SPA？
- 消费流本质是全视口交互应用（路由仅需 `/?w=<world_id>&tab=<tab>`），不需要 SSR/Edge Worker，构建时间 < 2 秒、零水合风险，可直接部署到 **Vercel**、**Cloudflare Pages** 或 **GitHub Pages**。
- `feed/vercel.json` 示例：
  ```json
  {
    "buildCommand": "npm run build",
    "outputDirectory": "dist",
    "rewrites": [{ "source": "/((?!mirrors/|thumbnails/|data/|assets/).*)", "destination": "/index.html" }]
  }
  ```

---

## 3. 数据契约与三层体验分级

### 3.1 `feed/public/data/feed.json` 数据结构
由 `feed/scripts/build-feed-data.mjs` 从 `../data/exports/ai_worlds.json` 编译生成（自动兼容当前 59 条及未来扩量后的 300–1000+ 条）：

```ts
export type PlayTier = "mirror" | "embed" | "external";

export interface FeedItem {
  world_id: string;
  title: string;
  author: string;
  theme_category: string;
  models_used: string[];
  model_family: "Claude" | "GPT" | "Gemini" | "Other";
  tech_stack: string[];
  generation_mode: string;
  is_open_source: boolean;
  verified_playable: boolean;

  // 播放与嵌入分层
  tier: PlayTier;
  embed_url: string | null;       // tier="mirror" 时为 "/mirrors/<id>/index.html"；tier="embed" 时为 live_demo_url
  external_demo_url: string | null;
  repo_url: string | null;
  original_post_url: string;

  // 视觉预览（按优先级：视频 > 实景截图 > null）
  preview_video_url: string | null; // 预留给上游 X 视频 / 录屏 MP4/WebM
  thumbnail_url: string | null;     // "/thumbnails/<id>.webp"

  // 精简双语内容（已过滤裸模型名噪音）
  summary_zh: string;
  summary_en: string;
  workflow_steps_zh: string[];
  workflow_steps_en: string[];
  skills_zh: string[];
  skills_en: string[];
  evidence_quotes: string[];
  published_at: string | null;
}
```

### 3.2 三层消费体验（混合流策略）
1. **`tier = "mirror"`（最高优 · 开源同域静态镜像）**
   - 来源：仅针对已核实**宽松开源许可（MIT / Apache-2.0 / BSD / ISC）**且可纯静态构建的仓库（例如 `Summer Festival`、`Torchlight Depths`、`Da Vinci’s Living Codex`、`Papertrails` 等）。
   - `build-mirrors.mjs` 读取白名单配置 `feed/scripts/mirrors.config.json`，核对 LICENSE 后将静态产物输出至 `feed/public/mirrors/<world_id>/`。
   - 效果：100% 可内嵌、秒开、零跨域拦截、永不失效。
2. **`tier = "embed"`（可就地真玩外链）**
   - 来源：`probe-embeds.mjs` 对所有非 broken 的 `live_demo_url` 发送 HTTP HEAD/GET 检测响应头：
     - 若存在 `x-frame-options: deny | sameorigin`，标记 `embeddable: false`；
     - 若 `content-security-policy` 含 `frame-ancestors` 且未包含 `*` 或己方域名，标记 `embeddable: false`；
     - 若返回 `401 / 403 / 404 / 5xx` 或已知登录墙域名（如 `claude.ai`、`ai.studio`），标记 `embeddable: false`；
     - 其余标记 `embeddable: true`，进入 `tier = "embed"`。
   - 效果：刷流态展示实录视频/高清截图，点击「开始操控」即就地加载 `<iframe>` 真玩。
3. **`tier = "external"`（预览 + 外链直达）**
   - 来源：无法 `<iframe>` 嵌入、但具备 `preview_video_url` 或 `thumbnail_url` 的世界。
   - 效果：刷流态循环播放实录视频或展示高清实景封面，主按钮为 `↗ 打开原站试玩`。

### 3.3 默认排序与过滤规则
- **主推荐流（`For You / 推荐`）准入**：必须满足 `tier !== "external" || preview_video_url || thumbnail_url`（无图无视频且不可内嵌的纯文本条目不进入默认刷流，避免破坏刷流体验；可在 `全部` 或跳转 `图鉴工作台` 查看）。
- **排序优先级**：
  1. `tier === "mirror"` 且有实景图/视频（置顶保证打开第一屏 100% 惊艳且秒玩）；
  2. `verified_playable && tier === "embed"`；
  3. `tier === "embed"` 且有预览媒体；
  4. `tier === "external"` 且有预览视频；
  5. `tier === "external"` 且有实景截图。
- **频道筛选标签（顶栏单行胶囊）**：
  - `推荐`（全部入流世界）| `可直接玩`（`mirror` + `embed`）| `开源` | `Claude` | `GPT` | `Gemini` | `已收藏`

---

## 4. 视觉设计与极简文案规范

### 4.1 纯浅色视觉令牌（`tokens.css`）
与 `platform/` 浅色工作台保持同一产品家族，**严禁使用黑底/暗棕底**：
- 画布背景：`#F7F8FA`（柔和浅灰白，衬托居中 3D 视口）
- 顶栏 / 浮层 / 抽屉：`#FFFFFF`，描边 `1px solid #E6EAF0`
- 主剧场画框：居中圆角容器（`border-radius: 20px`、`border: 1px solid rgba(15, 23, 42, 0.08)`、`box-shadow: 0 12px 36px rgba(15, 23, 42, 0.06)`），桌面端尽量占满可用高度（`max-width: min(1160px, calc(100vw - 120px))`、`height: calc(100dvh - 104px)`，最小保持 16:9 观感）
- 文字色：主墨 `#111315`，次级 `#4B5563`，弱化 `#6B7280`
- 按钮与语义色：
  - 主按钮（开始操控 / 打开试玩）：碳黑 `#111315` 白字（悬浮 `#272B30`）
  - 可直接玩 / 镜像标识：翡翠绿 `#047857` / `#ECFDF5`
  - 开源标识 / 激活态：品牌蓝 `#1D4ED8` / `#EFF6FF`

### 4.2 界面结构与极简文案约束
1. **顶栏（48px，单行极简）**：
   - 左：`WorldFeed`（或 `世界流`）品牌标识
   - 中：频道胶囊切换（`推荐` / `可直接玩` / `开源` / `Claude` / `GPT` / `Gemini` / `收藏`）
   - 右：`EN / 中文` 切换按钮 + `图鉴 ↗`（外链到检索工作台）
2. **主舞台画框（中央）**：
   - 画面干净至上：**操控态（`PLAYING`）下不遮挡任何 3D 画面**，只在画框外顶部露出一条极轻的退出条（`操控中 · 点击右侧 ↑↓ 切世界 · [退出操控]`）。
   - 浏览态（`BROWSE`）左下角仅展示极简半透明浅色浮签（标题 + 作者 + 模型徽章），右下角放单一清晰主按钮（`▶ 开始操控试玩` 或 `↗ 原站试玩`）。
3. **右侧竖排悬浮操控栏（画框外 64px，永远不被 iframe 吞事件）**：
   - `↑` 上一个世界（首条禁用）
   - `↓` 下一个世界（末条循环或提示已到底）
   - 分隔线
   - `♡` 收藏（红心填充切换，写入 `localStorage`）
   - `ℹ` 详情抽屉（滑出查看工作流、技术栈、原文证据；无工作流时不显示空模块）
   - `{ }` 源码仓库（有 `repo_url` 时显示）
   - `↗` 新标签页全屏打开原站
   - `🔗` 复制当前世界直链（`/?w=<world_id>`，带轻量 Toast `已复制`）
4. **文案禁令**：
   - 禁止出现 `待复核 / 已复核`、`无实景图`、`纯静态`、`作者未披露` 等内部/消极文案；
   - 英文模式下 100% 不得出现中文字符（复用 `worlds-en.json` 或上游双语字段）。

---

## 5. 核心交互状态机与 WebGL 安全规范（关键防坑）

### 5.1 双态交互状态机（解决滚轮与键盘劫持）

```text
           [点击画面 / Space / Enter / 点"开始操控"]
  ┌────────┐ ─────────────────────────────────────────► ┌──────────────┐
  │ BROWSE │                                            │ LOADING_EMBED│
  └────────┘ ◄───────────────────────────────────────── └──────┬───────┘
       ▲       [点击"退出操控" / 点右侧 ↑↓ / 点画框外]             │ iframe onLoad
       │                                                       ▼
       │                                                ┌──────────────┐
       └─────────────────────────────────────────────── │   PLAYING    │
               [点击右侧 ↑↓ / 顶栏退出按钮 / Esc*]        └──────────────┘
```

- **刷流态（`BROWSE`，默认进入）**：
  - 显示 `<video autoPlay muted loop playsInline poster={thumbnail_url}>`（若有视频）或高清 `<img>`（若仅有截图），零 WebGL 开销。
  - **滚轮切条防抖**：监听 `wheel` 事件，累加 `deltaY`，超过阈值（如 `60px`）触发一次切条并进入 `420ms` 冷却锁，彻底防止 macOS 触控板惯性一次滑过 5 个世界！
  - **键盘快捷键**：`ArrowDown` / `J` 下一条；`ArrowUp` / `K` 上一条；`Space` / `Enter` 进入操控态（`external` 类则新标签页打开）；`I` 开关详情抽屉；`L` 收藏。
- **操控态（`PLAYING`）**：
  - 仅在此时把 `<iframe src={item.embed_url}>` 挂载进当前画框，且把鼠标滚轮、拖拽、WASD 完整交给 3D 世界。
  - **重要陷阱提醒**：当焦点进入跨域 `<iframe>` 后，父页面的 `keydown(Escape)` 不会触发！因此**必须在画框外侧（顶部轻条 + 右侧操控栏）始终提供一键可点的「退出操控」和「↑ / ↓ 切世界」按钮**，确保用户永远不会被困在 3D 场景里。

### 5.2 单活 `<iframe>` 与 GPU 显存保护（铁律）
- 整个 DOM 树在任意时刻**最多只允许存在 1 个 `<iframe data-world-embed>`**。
- 用户切换上一条/下一条时，**立即卸载旧 `<iframe>`**（清空挂载，释放 WebGL/WebGPU Context），并自动回到新条目的 `BROWSE` 状态（可选：在右上角提供一个「自动进入试玩」开关，默认关闭，开启后 `mirror`/`embed` 条目切入 600ms 后自动激活，但切走仍严格单活卸载）。
- 相邻条目（`index - 1`、`index + 1`）只预加载封面 `<img>` 或 `<video preload="metadata">`，绝不预挂载 iframe。

### 5.3 `<iframe>` 安全属性与失败兜底
- 统一配置：
  ```html
  <iframe
    src="{item.embed_url}"
    title="{item.title}"
    sandbox="allow-scripts allow-same-origin allow-pointer-lock allow-popups allow-forms"
    allow="fullscreen; autoplay; xr-spatial-tracking; accelerometer; gyroscope"
    referrerPolicy="no-referrer"
  />
  ```
- **静默拦截兜底**：部分站点虽然响应头没写 `X-Frame-Options`，但用 JS 检测 `window.top !== window.self` 导致白屏或卡住。因此在 `LOADING_EMBED` 超过 4 秒后，以及在 `PLAYING` 态画框外顶部条，始终提供一个轻量按钮：`画面异常？在新标签页打开 ↗`。

### 5.4 URL 直链与移动端降级
- 切换世界或频道时通过 `window.history.replaceState` 同步 `/?w=<world_id>&tab=<tab>`；首次打开带 `?w=<world_id>` 时直接定位到该条目。
- 窄屏 / 移动端（`<= 768px`）：右侧竖排操作栏转为底部紧凑工具条，支持上下触摸滑动（`touchstart`/`touchend` 纵向位移 > `50px`）切换世界，详情抽屉改为底部半屏抽屉，保证零横向溢出。

---

## 6. 分阶段实施步骤（供执行 AI 按序落地）

### Milestone 1：数据管线衔接与脚手架（`feed/`）
1. 在 `feed/` 初始化 Vite + React 19 + TypeScript + `lucide-react` 工程。
2. 实现 `feed/scripts/probe-embeds.mjs`：读取 `../data/exports/ai_worlds.json`，并发探测所有 `live_demo_url` 的 `X-Frame-Options` 与 `CSP frame-ancestors`，结果缓存写入 `../data/state/embed_probe.json`（支持 `--refresh` 刷新）。
3. 实现 `feed/scripts/build-feed-data.mjs`：合并 `ai_worlds.json`、`worlds-en.json`、`embed_probe.json`、`mirrors.json`，同步缩略图到 `feed/public/thumbnails/`，输出 `feed/public/data/feed.json`。

### Milestone 2：开源世界同域静态镜像构建（`build-mirrors.mjs`）
1. 创建 `feed/scripts/mirrors.config.json`（显式白名单，初始先纳入已核实 MIT 许可且易静态构建的 2–4 个公开仓库，例如单页 HTML / 标准 Vite Three.js 项目）。
2. 实现 `feed/scripts/build-mirrors.mjs`：校验 LICENSE 文件确认为宽松开源许可 → 拉取指定 commit → 构建静态产物到 `feed/public/mirrors/<world_id>/` → 更新 `../data/state/mirrors.json` 记录 commit SHA、许可证明与路径。
3. 镜像入口强制使用相对路径（`base: "./"`），确保挂载在 `/mirrors/<world_id>/` 下资源加载零 404。

### Milestone 3：浅色桌面端世界流前端实现
1. 按第 4 节实现 `tokens.css` 与 `feed.css`（纯浅色、自定义细滚动条、尊重 `prefers-reduced-motion`）。
2. 实现 `TopBar`、`StageCard`（双态状态机 + 单活 iframe + 4s 兜底条）、`ActionRail`（帧外竖排操控 + 收藏 + 分享直链）、`InfoDrawer`（右滑详情抽屉）、`i18n.ts`（ZH/EN 实时切换，英文态零中文）。
3. 实现滚轮惯性防抖、键盘快捷键（`↑/↓/J/K/Space/I/L`）、触摸上下滑切条与 `/?w=<world_id>` 直链恢复。

### Milestone 4：自动化验证与独立部署配置
1. 补充 `feed/vercel.json` 与 `.github/workflows/deploy-feed-pages.yml`（指向 `feed/dist`）。
2. 编写端到端 Playwright 验证脚本 `feed/scripts/verify-feed.mjs`，启动本地静态服务并在真实 Chrome 下验证所有验收项并输出桌面（`1440×900`）与移动（`390×844`）截图。

---

## 7. 验收标准（Definition of Done）

执行本方案的 AI 必须逐条实测通过以下检查后方可交付：

- [ ] **构建与类型检查**：`cd feed && npm run build` 0 报错，输出完整静态目录 `feed/dist/`。
- [ ] **单活 `<iframe>` 铁律**：在 Chrome 中进入某世界操控态后，DOM 中 `iframe[data-world-embed]` 数量严格为 `1`；点击右侧 `↓` 切到下一条后，旧 iframe 立即卸载（数量归 `0`），不会残留后台 WebGL 上下文。
- [ ] **滚轮与帧外逃生**：在 `BROWSE` 态下一次触控板滑动只切 1 条；在 `PLAYING` 态下点击右侧 `↓` 或顶部「退出操控」可 100% 稳定切出，不被 3D iframe 困住。
- [ ] **三层降级准确**：`mirror` 项加载同域 `/mirrors/<id>/` 无 404；`embed` 项可就地加载并带 4s 兜底链接；`external` 项清晰展示实景预览并一键新标签页打开。
- [ ] **中英双语零残留**：切换 `EN` 后页面所有可见文本与详情抽屉无中文字符（`<html lang="en">`），刷新与直链跳转保持所选语言。
- [ ] **零报错与响应式**：桌面 `1440×900` 与移动 `390×844` 均 0 console/page error、0 横向溢出（`scrollWidth <= clientWidth`），直链 `/?w=<world_id>` 刷新可准确定位到目标世界。
