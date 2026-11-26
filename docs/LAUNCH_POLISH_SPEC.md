# Launch Polish, Full-Screen UI Simplification & Auto-Sync Spec (Codex-Executable)

> **Target Repo**: `/Users/zeshentian/Documents/ChatGPT/ai-worlds-tracker`
> **Audience**: Autonomous coding agent (GPT Codex / Claude Code / Antigravity)
> **Status**: User-approved final pre-launch spec (2026-11-25)
> **Goal**: Turn both **Atlas (`platform/`)** and **WorldFeed (`feed/`)** into ultra-clean, full-width / full-screen, frontier-only consumer products, export the retired `/trends` analytics into a standalone Markdown report, fix the last data typo, configure daily automated incremental sync, and ship cleanly.

---

## 0. Hard Product Decisions (Do Not Deviate)

1. **Frontier-Only in Both Frontends (Hide Legacy Completely)**:
   - Both `platform/` (Atlas) and `feed/` (WorldFeed) MUST show **ONLY `model_era === "frontier"`** worlds.
   - Remove ALL `Frontier Only / Include Archive` (`仅前沿 / 含归档`) toggles and `?archive=1` UI chrome from both products. (Keep legacy rows intact in backend `data/processed/cases.jsonl` and `data/exports/ai_worlds.json` for historical ledger integrity, never displayed in the UI.)
2. **Remove Top-Left Brand Icons in Both Products**:
   - Delete `<span className="brand-icon"><Aperture ... /></span>` in `platform/components/atlas-shell.tsx` (Header & Footer).
   - Delete `<span className="brand-icon"><Layers3 ... /></span>` in `feed/src/components/TopBar.tsx`.
   - Use clean typography-only wordmarks (`生成世界图鉴` / `Generated Worlds Atlas`, and `WorldFeed`).
3. **Strict Light Mode**:
   - Both products remain strictly **light mode** (pure-white clean aesthetic), including under `prefers-color-scheme: dark`.
4. **Alibaba Token Plan Rule**:
   - Any Qwen/Alibaba calls in code or workflows MUST use `ALIBABA_TOKEN_PLAN_API_KEY` + `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` (NEVER `DASHSCOPE_API_KEY`).

---

## 1. Workstream 1 — Final Data Cleanup & Standalone Trends Report

### 1.1 Fix Remaining Typo (`GPT-62 Astra` → `GPT-6.2 Astra`)
- In `src/model_era.py` `canonicalize_models_and_stack()`, add normalization for `GPT-62 Astra` / `GPT 62 Astra` → `GPT-6.2 Astra`.
- Add a unit test in `tests/test_model_era.py` covering `GPT-62 Astra` → `GPT-6.2 Astra`.
- Re-run `python -m src.publish_catalog` and verify `GPT-62 Astra` no longer appears in `data/exports/meta.json`.

### 1.2 Generate Standalone Trends Analysis Report (`reports/frontier_trends_report.md`)
Since `/trends` is being removed from the web UI, preserve all its analytical value in a clean, reproducible Markdown report:
- Create `src/generate_trends_report.py` that reads `data/exports/ai_worlds.json`, `data/exports/meta.json`, and `reports/golden_eval_v1.md` / `reports/golden_eval_v2.md`, filters strictly to `model_era == "frontier"`, and outputs `reports/frontier_trends_report.md` (Chinese primary with concise English labels where helpful) containing:
  1. **核心概览（Overview KPIs）**: total frontier worlds, live demo count, verified playable count, WorldFeed embeddable count, open-source repo count, cover coverage %, update timestamp.
  2. **模型家族与具体模型分布**: Claude / Gemini / GPT / 其他（collapsed long-tail）counts & shares, plus Top 12 canonical models (`Claude Fable 5.2`, `Claude Opus 5.5`, `GPT-6.2 Astra`, `Gemini 4 Neon`, etc.).
  3. **主题分布（Theme Distribution）**: counts & percentages across all themes.
  4. **技术栈占比（Top Tech Stacks）**: top 15 tech stacks by share (Three.js, WebGPU, Blender, WebGL, etc.).
  5. **作品类型与复现层级**: `interactive_world` vs `coded_3d_scene`, and `live_demo` / `full_repo` / `prompt_shared` / `video_only`.
  6. **工作流模式与成本/耗时披露统计**: summary of disclosed build times, API costs, and common workflow patterns (reference-driven, iterative debugging, procedural kit-of-parts, etc.).
  7. **采集口径与质量评估**: Frontier model definitions, exclusion rules, and latest V1 / V2 blind benchmark results.
- Run `python -m src.generate_trends_report` and verify `reports/frontier_trends_report.md` is cleanly formatted and accurate.

### 1.3 Cache GitHub Stars & X Likes for Feed Display (`data/state/github_stars.json`)
- Add a small helper script `src/fetch_github_stars.py` (or integrate into `feed/scripts/build-feed-data.mjs`) that:
  - Reads unique GitHub `owner/repo` paths from frontier items' `repo_url` (only ~35–60 repos).
  - Fetches `stargazers_count` from GitHub API (`https://api.github.com/repos/<owner>/<repo>`, using `GITHUB_TOKEN` if available, caching results in `data/state/github_stars.json` with `fetched_at` so repeated builds make 0 network requests; gracefully skips on rate-limit/offline).
  - Also reads each X post's community `likes` count from `data/raw/x/signals/<tweet_id>.json` when building `feed/public/data/feed.json`.

---

## 2. Workstream 2 — Redesign `platform/` (生成世界图鉴 · Atlas) into a Clean Full-Width Catalog

### 2.1 Delete Retired Pages, Components & Chrome
Delete these completely (update imports, links, and tests accordingly):
- **Delete `/submit`**: Remove `platform/app/submit/`, `platform/app/api/submit/` (if present), `platform/lib/submissions.ts` (if unused), and remove the `+ 提交` CTA from `platform/components/atlas-shell.tsx`.
- **Delete `/trends`**: Remove `platform/app/trends/` and `platform/components/trends-view.tsx`, remove `趋势` nav link from `Header` and `方法说明 /trends#method` from `Footer`.
- **Delete `/worlds/[id]` Detail Pages**: Remove `platform/app/worlds/[id]/` and `platform/components/world-detail-view.tsx` (static build will now be ultra-fast with zero redundant detail pages!).
- **Delete Right-Side 1/3 `QuickInspector` Drawer**: Remove `QuickInspector`, `wb-inspector`, `has-inspector`, `has-inspector-auto`, `open-inspector-btn`, and `inspectorMode` from `platform/components/world-catalog.tsx` and `platform/app/globals.css`.
- **Delete Left Faceted Sidebar**: Remove `<aside className="wb-sidebar">`, `wb-sidebar-scrim`, `wb-mobile-filter-btn`, and all sidebar CSS from `platform/components/world-catalog.tsx` and `platform/app/globals.css`.
- **Delete Era Switcher**: Remove `platform/lib/era-filter.ts` (or lock catalog strictly to `worlds.filter(isFrontier)`) and remove `era-segments` UI.

### 2.2 Clean Minimal Header (`platform/components/atlas-shell.tsx`)
- Left: Clean text wordmark (`生成世界图鉴` / `Generated Worlds Atlas`), **NO icon**.
- Center: Existing clean `CommandSearch` input (update `CommandSearch` so selecting a search result filters the catalog or opens its demo/post URL directly instead of navigating to deleted `/worlds/[id]`).
- Right: ONLY **2 controls**:
  1. Link to **WorldFeed** (`刷世界 ↗` / `WorldFeed ↗`)
  2. **Language toggle (`EN` / `中文`)**
- Minimal footer: Clean text wordmark (no icon) + brief copyright/update timestamp (no broken `/trends#method` link).

### 2.3 Full-Width Top Horizontal Filter Bar (`platform/components/world-catalog.tsx`)
Replace the deleted left sidebar and deleted KPI chips (`可试玩`, `开源`, `有封面图`, `含工作流`, `发布月份`) with a **clean, cohesive, full-width horizontal filter toolbar** at the top of the page:
1. **Model Filter (5-item segmented/pill group — unified style)**:
   - `全部` / `All`
   - `Claude`
   - `GPT`
   - `Gemini`
   - `其他` / `Other` — **MUST group ALL non-Claude/GPT/Gemini models together** (including DeepSeek, Grok, Kimi, MiniMax, Qwen, Step, Marble, Hermes, GLM, etc.)! Update `family()` / filter matching in `platform/lib/worlds.ts` and `world-catalog.tsx` so clicking `其他` matches every frontier world with a model outside `{Claude, GPT, Gemini}`.
2. **Theme Filter (compact horizontal pills or styled popover/chip row synchronized with toolbar UI)**:
   - `全部主题` + 7 concrete themes (`自然生态` / `城市微缩` / `奇幻世界` / `科幻空间` / `物理模拟` / `体素沙盒` / `历史重建`, localized in EN).
3. **Tech Stack Filter (compact horizontal chips or synced dropdown pill — top 8–10 stacks like `Three.js`, `WebGPU`, `WebGL`, `Blender`, `Single-file HTML`, etc.)**:
   - Styled identically to the rest of the toolbar (NO unstyled native browser `<select>`).
4. **Toolbar Right Side — Synchronized Controls**:
   - **Sort**: Lock sorting strictly to **Latest (`published_at` descending)**! Delete the `<select>` sort dropdown, delete `featured` hardcoded array, delete `精选` / `最近收录` / `名称` options completely!
   - **View Switcher (`网格 | 列表 | 表格`)**: Keep the clean segmented pill switch, visually unified in height, border radius, font weight, and active state with the filter bar.
   - Show concise result count (`共 1,660 个` / `1,660 worlds`) and active filter clear button (`重置` / `Reset`) when filtered.

### 2.4 Direct-Action Cards, Full-Width Grid & Seamless WorldFeed Routing
- **Grid Layout**: Expand `.world-grid` to full horizontal viewport width (`max-width: 1680px` centered or fluid with `24px–32px` padding):
  - `>= 1440px`: **4 columns**
  - `1024px–1439px`: **3 columns**
  - `640px–1023px`: **2 columns**
  - `< 640px`: **1 column**
- **WorldFeed Playable Flag**: During `publish_catalog.py` (or a small build-time export to `platform/data/embeddable-ids.json` derived from `data/state/embed_probe.json` + `data/state/mirrors.json`), expose which frontier `world_id`s are live-playable inside WorldFeed (`tier === "mirror" || tier === "embed"`).
- **WorldFeed Base URL**: Configure via `NEXT_PUBLIC_WORLDFEED_URL` (with sensible production fallback / relative dev override).
- **Card Actions (Zero dead links to `/worlds/[id]`)**:
  - **If live-playable in WorldFeed (`mirror` or `embed`, currently ~223 frontier worlds)**:
    - Card thumbnail, title, and primary button **「试玩 / Play」** link directly to `${WORLDFEED_URL}/?w=${world.world_id}` (opens straight into the live full-screen 3D world in WorldFeed!).
    - Also display **「官方入口 / Official ↗」** (`live_demo_url`) and **「原帖 / Post」** (`original_post_url`) (+ optional **「源码 / Code」** when `repo_url` exists).
  - **If non-embeddable (`external`) with a `live_demo_url`**:
    - Card thumbnail, title, and primary button **「访问 / Visit ↗」** link directly to `live_demo_url` (`target="_blank" rel="noopener noreferrer"`), plus **「原帖 / Post」** (+ optional `源码`).
  - **If video/post-only (no `live_demo_url`)**:
    - Card thumbnail, title, and action link directly to `original_post_url` (+ optional `源码`).
  - Apply the same clean direct-action behavior to `list` and `table` views.

### 2.5 Natural Page-by-Page Pagination (Replace "Load More")
- Delete `加载更多` (`loadMore`) and `显示全部` (`showAll`) buttons completely.
- Implement clean numbered pagination (`PAGE_SIZE = 24` items per page, synced to URL `?page=N`):
  - Controls: `← 上一页` / `Prev`, numbered page buttons with ellipsis (`1 ... 4 5 6 ... 70`), `下一页 →` / `Next`, plus compact status (`第 1 / 70 页 · 共 1,660 个`).
  - Reset `page` to `1` whenever search query or any filter changes.
  - Smoothly scroll back to top of catalog when switching pages.

---

## 3. Workstream 3 — Redesign `feed/` (WorldFeed) into a Live Full-Screen Playable 3D Feed

### 3.1 Playable-Only Frontier Pool (Zero Static-Only Cards)
1. **Frontier + Live-Playable Only (`feed/scripts/build-feed-data.mjs`)**:
   - Filter `rows` strictly to **`w.model_era === "frontier"` AND (`tier === "mirror"` OR `tier === "embed"`)** (currently **223** truly playable in-stage frontier worlds — ZERO static-only `external` cards so every single swipe enters a real live 3D world!).
   - Attach `x_likes: number` (from `data/raw/x/signals/<tweet_id>.json`, default `0`) and `github_stars: number | null` (from `data/state/github_stars.json` when `repo_url` is a GitHub repo) to every item in `feed.json`.
   - Rank order: `mirror` first → `verified_playable` `embed` next → remaining `embed` sorted by `published_at` descending.
   - Ensure `public/data/feed.json` preserves clean `embed_url`, `external_demo_url` (official demo), `original_post_url`, and `repo_url`.

### 3.2 Ultra-Minimal Top Bar (`feed/src/components/TopBar.tsx`)
- Delete `<nav>` channel tabs (`For You`, `Playable`, `Claude`, `GPT`, `Gemini`, `Saved`) completely!
- Delete the `仅前沿 / 含归档` button completely!
- Delete `<span className="brand-icon"><Layers3 ... /></span>` completely!
- Left: Clean text wordmark `WorldFeed` (clicking resets to first world).
- Right: ONLY **2 controls**:
  1. Language toggle (`EN` / `中文`)
  2. Atlas link (`图鉴 ↗` / `Atlas ↗` pointing to `VITE_ATLAS_URL` or `https://generated-worlds-atlas.zeshentian1.chatgpt.site/`)
- Make `.topbar` ultra-slim (`44px–48px` height, translucent pure-white glass) so **~94%+ of the viewport** belongs to the live 3D world!

### 3.3 Live Auto-Mount Full-Screen 3D Stage (NO Static Screenshot Gate & NO "Enter World" Button!)
- **Remove the `browse` vs `playing` gate completely** (`StageCard.tsx` & `App.tsx`) — NO static screenshot cover blocking the user, NO "Click to Enter World" button, and NO `playbar` exit bar!
- **Immediate Live 3D Rendering**:
  - The moment a user lands on (or swipes to) a world, **immediately mount the live `<iframe data-world-embed src={item.embed_url} />`** filling the entire stage (`height: calc(100dvh - 48px)`, full width minus only the slim floating right rail on desktop; edge-to-edge on mobile).
  - Use `item.thumbnail_url` ONLY as a subtle blurred/clean backdrop underneath the iframe with a minimal loading spinner, and **fade it out smoothly (`opacity: 0`, `pointer-events: none`) the instant `iframe.onLoad` fires** — giving a seamless, real-time, non-screenshot feel!
  - Always unmount the previous world's iframe cleanly on switch (only 1 live WebGL/WebGPU iframe mounted at a time so GPU memory stays healthy).
  - If an external iframe has not fired `onLoad` after `4s` (slow site or runtime block), show a tiny unobtrusive recovery pill at the bottom-center: `加载较慢？按 G 打开官方入口 ↗` / `Slow to load? Press G for Official Site ↗`.
- **Delete `InfoDrawer` (`feed/src/components/InfoDrawer.tsx`)** and all `Saved/Favorites` tab logic completely.
- Show a crisp, lightweight bottom-left floating title pill (pointer-events-none except links): Title · Author · canonical Model pill.

### 3.4 Frictionless `WASD` Play + `↑`/`↓` World Switching + Shortcuts (`feed/src/App.tsx`, `ActionRail.tsx`)
Design navigation honestly around real browser cross-origin iframe rules so it feels effortless:
1. **Same-Origin `mirror` Worlds**:
   - Inject a tiny `keydown` listener inside mirrored HTML (or via `iframe.contentWindow` when same-origin) so **`WASD` moves the player inside the 3D world while `ArrowUp` / `ArrowDown` STILL immediately switch to the previous/next world** without leaving the game!
2. **Cross-Origin `embed` Worlds (Browser Security-Aware UX)**:
   - **Before clicking inside the canvas**: The live 3D world is ALREADY running full-screen in real time, AND focus remains on the outer WorldFeed window → **`ArrowUp` / `ArrowDown`**, **`J` / `K`**, and **mouse wheel** switch worlds immediately!
   - **While playing inside a cross-origin iframe (`WASD` + mouse look)**:
     - Browser Same-Origin Policy delivers keyboard/wheel events to the active cross-origin iframe (outer window cannot intercept `ArrowUp`/`ArrowDown` while iframe owns focus).
     - Therefore, keep the **slim right-side floating `ActionRail` (`~56px` wide) and slim top bar permanently OUTSIDE the iframe (`pointer-events: auto`)**:
       - Clicking **`↑` / `↓`** on the floating rail OR scrolling the mouse wheel while hovering over the rail / top bar immediately unmounts the current iframe, calls `window.focus()`, and switches to the next live world (and restores keyboard `↑`/`↓` control right away!).
       - Pressing **`Esc`** exits Pointer Lock (standard browser behavior); add a subtle `window.blur` / `pointerlockchange` awareness so clicking the thin border/rail or top bar restores outer keyboard focus cleanly.
3. **Minimal Floating Right Rail & Keyboard Shortcuts** (active whenever outer window has focus):
   - **`↑` / `↓` (or `J` / `K` / wheel)**: Previous / Next live world (+ compact index `1 / 223`).
   - **`L` (Like)**: Toggle Like (also via rail heart button), persisted in `localStorage` (`worldfeed-liked-ids`), displays `(item.x_likes || 0) + (liked ? 1 : 0)` with animated heart pop + brief toast.
   - **`G` (Official Demo)**: Opens `item.external_demo_url` (author's official live site) in a new tab (`target="_blank" rel="noopener noreferrer"`), with dedicated rail button (`官方 ↗` / `Official ↗`).
   - **`O` (Original Post)**: Opens `item.original_post_url` (X post / project page) in a new tab, with rail button.
   - **GitHub Source (shown only when `item.repo_url` exists)**: Opens `item.repo_url` in a new tab and displays the cached **GitHub Stars count (`★ 259`)** cleanly on the rail!
   - **`S` (Share)**: Copies clean direct link `/?w=<world_id>` to clipboard.
- Update `ShortcutsHint.tsx` to a tiny unobtrusive bottom hint:
  - ZH: `WASD 游玩 · ↑↓ / 滚轮 切世界 · L 点赞 · G 官方入口 · O 原帖`
  - EN: `WASD Play · ↑↓ / Wheel Switch · L Like · G Official · O Post`

---

## 4. Workstream 4 — Daily Automated Incremental Sync & Deployment Readiness

### 4.1 Update `.github/workflows/sync-worlds.yml`
Upgrade the scheduled daily workflow so once `ENABLE_SCHEDULED_SYNC=true` is toggled in GitHub repo variables, the whole pipeline runs hands-free every day:
1. Keep schedule `cron: "17 1 * * *"` and `workflow_dispatch`.
2. In the Apify collection step:
   - Run `uv run python -m src.apify_x --mode incremental --actor kaito --page-size 20 --budget-usd 1.50`.
3. In the `sync_catalog` step:
   - Pass `ATLAS_FRONTIER_ONLY: "true"`, `ATLAS_MIN_LIKES: "15"`, `AUTO_APPROVE_TRUSTED: ${{ vars.AUTO_APPROVE_TRUSTED || 'true' }}`, `ALIBABA_TOKEN_PLAN_API_KEY: ${{ secrets.ALIBABA_TOKEN_PLAN_API_KEY }}` (and remove any `DASHSCOPE_API_KEY` usage).
4. After `sync_catalog`:
   - Run `uv run python -m src.generate_trends_report` to refresh `reports/frontier_trends_report.md`.
   - Run `uv run python -m src.fetch_github_stars` to refresh cached GitHub stars.
   - Rebuild `feed/` data & embeds (`cd feed && npm ci && node scripts/probe-embeds.mjs && node scripts/build-feed-data.mjs && npm run build`) and commit updated `data/`, `reports/frontier_trends_report.md`, `platform/data/`, `platform/public/thumbnails/`, and `feed/public/` outputs.
5. Check `.github/workflows/deploy-pages.yml` and `.github/workflows/deploy-feed-pages.yml` to verify both workflows build cleanly after our route deletions (`/submit`, `/trends`, `/worlds/[id]` removed).

---

## 5. Verification & Acceptance Checklist

Run all checks in order:
```bash
# 1. Backend tests + typo fix + trends report + GitHub stars cache
pytest -q
python -m src.publish_catalog
python -m src.generate_trends_report
python -m src.fetch_github_stars

# 2. Verify zero GPT-62 Astra typo & both V1/V2 blind benchmarks still pass strict
python -m src.eval_golden --benchmark config/golden_benchmark.yaml --report reports/golden_eval_v1.md --strict
python -m src.eval_golden --benchmark config/golden_benchmark_v2.yaml --report reports/golden_eval_v2.md --strict

# 3. Build Atlas (platform/) — lint 0 errors, static export succeeds cleanly
cd platform && npm run lint && npm run build:static

# 4. Build WorldFeed (feed/) — data build + Vite build + real Chrome verification
cd ../feed && node scripts/build-feed-data.mjs && npm run build
```

### Mandatory Headless Chrome Verification (Write summary to `reports/launch_polish_acceptance.md`)
Verify BOTH built static sites (`platform/out` and `feed/dist`) in headless Chrome (desktop 1440×900 + mobile 390×844, plus `prefers-color-scheme: dark`):
- [ ] **Atlas (`platform/out`)**:
  - Zero console/page errors; zero horizontal overflow on desktop & mobile.
  - Pure light mode even under dark OS preference.
  - No top-left icon; no `/submit` button; no `/trends` link; no archive toggle; no left sidebar; no right 1/3 inspector drawer; no `/worlds/[id]` links; no `可试玩/开源/有封面图/发布月份` chips; no `<select>` sort dropdown; no `加载更多` button.
  - Top horizontal bar shows unified **Model (`全部/Claude/GPT/Gemini/其他`)**, **Theme**, **Tech Stack**, and **Grid/List/Table** controls.
  - Default sort is newest first (`published_at` desc); **Pagination** works cleanly (Page 1 → Page 2 updates grid and URL `?page=2`).
  - Clicking cards opens Demo/Post directly; bilingual ZH/EN switching has zero untranslated Chinese in EN mode.
- [ ] **WorldFeed (`feed/dist`)**:
  - Zero console/page errors; pure light mode even under dark OS preference.
  - Pool contains ONLY frontier `mirror` + `embed` playable worlds (0 `external` static-only items, 0 `legacy` items).
  - No top-left icon; no top channel tabs; no `Saved` tab; no `仅前沿/含归档` toggle; no `InfoDrawer`; no static "Click to Enter World" button or `playbar` exit bar.
  - Top bar has ONLY text `WorldFeed`, language switch, and `Atlas` link.
  - Live `<iframe data-world-embed>` auto-mounts immediately on load & switch, filling `>= 88%` viewport height on desktop, and unmounts the previous iframe cleanly on switch.
  - Pressing `ArrowDown`/`ArrowUp` (and same-origin `mirror` arrow bridge) or clicking floating rail `↑`/`↓` switches live worlds smoothly; `L` toggles Like + updates count + persists across reload; `G` opens official demo URL; `O` opens original post; GitHub `★ stars` badge renders on repos with `repo_url`.
  - Clicking "Play / 试玩" on an embeddable card in Atlas links to WorldFeed `/?w=<world_id>`, while "Official / 官方入口" and "Post / 原帖" remain directly accessible.
- [ ] **Report & CI**:
  - `reports/frontier_trends_report.md` exists and accurately summarizes all 1,660 frontier worlds.
  - `.github/workflows/sync-worlds.yml` validated (valid YAML, Token Plan env, `kaito` actor, rebuilds both products).
  - Provide a clean `git status` summary and exact deployment/GitHub Actions activation checklist (do NOT push to remote unless explicitly instructed by the user).
