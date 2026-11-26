# Frontier 3D Worlds Collection & Filtering Spec (Codex-Executable)

> **Target Repo**: `/Users/zeshentian/Documents/ChatGPT/ai-worlds-tracker`
> **Audience**: Autonomous coding agent (GPT Codex / Claude Code / Antigravity)
> **Status**: User-approved requirements (2026-11-25)

---

## 0. Problem Statement & Baseline Diagnosis

The 2026-11-24 snapshot (`data/exports/ai_worlds.json`, 898 worlds) suffers from two structural flaws:

1. **58% legacy noise**: Only 377 of 898 worlds (42%) come from current frontier models (`GPT-6.2 Astra`, `Claude Fable 5.2`, `Claude Opus 5.5/5.6`, `Gemini 4` series). The remaining 521 are older models (`GPT-6.0`, `GPT-5.x`, `Fable 5.0/5.1`, `Marble`, etc.).
2. **0 / 11 blind recall on fresh frontier X posts**: Evaluated against `config/golden_benchmark.yaml`, the current snapshot hits **0 / 11** core frontier posts and **0 / 5** long-tail posts. Root causes confirmed in code and receipts:
   - `config/seeds.yaml` lacks dedicated queries for `GPT-6.2 Astra` / `Astra 6.2` / `GPT 6.2 Astra`, `Opus 5.6`, `Gemini 4 Neon` / `Neon 4`, and uses `min_faves:10–30` which misses low-like gems.
   - `data/state/watch_suggestions.json` has **57 repeat creators** (with 2–6 worlds each) not merged into `watch_accounts`, and `src/apify_x.py` ran `max_workers=3` which triggered Apify `REFUSED` concurrent-run failures on official release threads (`2119867114450268322`, etc.).
   - `src/qualify_candidates.py` hard-drops tweets without external links when `likes < 40` (line 26), rejects Class B pure-code 3D visual clips in `RULES` (line 15), and `src/sync_catalog.py` caps each run at `ATLAS_GATE_LIMIT=80` / `ATLAS_EXTRACT_LIMIT=12` — causing tweets already crawled into `data/raw/x/` (e.g. `2123506487792410706`, `2125140294530453981`) to never reach `cases.jsonl`.

---

## 1. Non-Negotiable Rules & Product Policies

1. **Blind Benchmark Integrity**:
   - **NEVER** add any URL or `tweet_id` from `config/golden_benchmark.yaml` into `config/seeds.yaml` `seed_urls`, hardcoded query lists, or test fixtures that bypass discovery.
   - Only merge authors into `watch_accounts` from existing DB data (`data/state/watch_suggestions.json` and authors already present in `data/exports/ai_worlds.json`), never by scraping handles out of `config/golden_benchmark.yaml`.
2. **Frontier Model Definition (`model_era: "frontier" | "legacy"`)**:
   - **Explicit Frontier (`>=`)**:
     - GPT line: `GPT-6.2` / `GPT 6.2` / `Astra 6.2` / `GPT-6.2 Astra` / `GPT-6.2 Sol` (and any `GPT >= 6.2` or `Astra >= 6.2`, e.g., `6.3`, `7.0`).
     - Claude Fable line: `Fable 5.2` (and any `Fable >= 5.2`).
     - Claude Opus line: `Opus 5.5`, `Opus 5.6` (and any `Opus >= 5.5`).
     - Gemini line: `Gemini 4`, `Gemini 4 Neon`, `Neon 4`, `Gemini 4 Hydrogen`, `Gemini 4 Carbon`, `Gemini 4 Argon` (and any `Gemini >= 4`).
   - **Explicit Legacy**:
     - `GPT-6` / `GPT-6.0` / `GPT-6.1` / `GPT-5*` / `GPT-4*`, `Fable 5` / `Fable 5.0` / `Fable 5.1`, `Opus 4*` / `Sonnet 4*` / `Haiku*`, `Gemini 2*` / `Gemini 3*`, `World Labs` / `Marble`, `Kimi*`, `Qwen*`, `DeepSeek*` (unless explicitly paired with a frontier model above).
   - **Date-Inferred Frontier (User-Approved Rule)**:
     - If `models_used` contains ONLY a generic model family name without a version number (`"Claude"`, `"Claude Code"`, `"Gemini"`, `"Antigravity"`, `"GPT"`, `"ChatGPT"`, `"Codex"`, `"Astra"`) AND NO explicit legacy model is present:
       - For Claude / Gemini generic names: `published_at >= 2026-11-10` → `"frontier"`, else `"legacy"`.
       - For GPT / ChatGPT / Codex / Astra generic names: `published_at >= 2026-11-17` → `"frontier"`, else `"legacy"`.
       - If `published_at` is missing/null → `"legacy"`.
3. **Archive Preservation (Option A)**:
   - Keep ALL legacy rows in `data/processed/cases.jsonl` and `data/exports/ai_worlds.json` tagged with `model_era: "legacy"`.
   - Default views in both `platform/` (Atlas) and `feed/` (WorldFeed) show **`model_era === "frontier"` ONLY**, with an optional UI toggle (`含历史归档 / Include Archive`) to inspect legacy entries.
4. **Work Inclusion & Exclusion Policy (A + B Only)**:
   - **INCLUDE Class A (`interactive_world`)**: Playable/navigable/interactive 3D worlds, games, single-HTML WebGL/WebGPU spaces, engine worlds (Three.js, WebGPU, Babylon, PlayCanvas, Unity, Unreal, Godot, Blender+Web) — whether live URL or screen-recorded video.
   - **INCLUDE Class B (`coded_3d_scene`)**: AI-coded 3D renderings, procedural geometry/architecture, custom GLSL/TSL shaders, path-traced physics animations built via AI code/agents.
   - **EXCLUDE**:
     - Class C (`tool_listicle`): GitHub repo roundups, tool directories, generic tutorials/tips without a concrete 3D world/scene.
     - Pure diffusion video-gen / auto-editing (Sora, Veo, Runway, Kling, Seedance, AI video + auto-edit without 3D code/engine).
     - **Sponsored / PR promotional posts**: Posts containing `【PR】`, `#PR`, `#ad`, `#sponsored`, or pitching commercial promo deals (e.g. Black Friday `% OFF`, affiliate links, sponsored tool launch promos).
     - **Secondary workflow-breakdown / aggregator accounts** (e.g., `@rewind02`, bio `"Running distribution via AI UGC"`): Do NOT publish other developers' works under an aggregator handle. Reject from direct ingestion; optionally log credited original devs (`dev: <handle>`) into `data/state/aggregator_leads.json`.
5. **Secrets & Budget Safety**:
   - Read keys only from environment or `~/.config/ai-keys/keys.env` (`APIFY_API_KEY`, `OPENAI_API_KEY`, `FIRECRAWL_API_KEY`). Never print or commit keys.
   - Apify budget guardrails: one-off `--mode frontier` backfill capped at `--budget-usd 5.00` (hard ceiling `10.00`); daily `--mode incremental` keeps default `$1.50`.
   - Keep all UI strictly **light mode** (no dark themes).

---

## 2. Workstream 1 — Deterministic `model_era` & Schema Upgrade

### 2.1 Create `src/model_era.py`
Implement a pure, deterministic classifier:
- `classify_model_era(models_used: list[str], published_at: str | None) -> Literal["frontier", "legacy"]`
- Helper regex rules:
  - Frontier explicit patterns (case-insensitive):
    - `r"\b(?:gpt[-\s]?|astra[-\s]?)(?:6\.[2-9]|[7-9](?:\.\d+)?)\b"` or `r"\b6\.[2-9]\s*astra\b"`
    - `r"\bfable[-\s]?(?:5\.[2-9]|[6-9](?:\.\d+)?)\b"`
    - `r"\bopus[-\s]?(?:5\.[5-9]|[6-9](?:\.\d+)?)\b"`
    - `r"\bgemini[-\s]?(?:[4-9](?:\.\d+)?)\b"` or `r"\b(?:neon|hydrogen|carbon|argon)\s*4\b"` or `r"\bgemini\s*4\s*(?:neon|hydrogen|carbon|argon)\b"`
    - Note: Handle standalone `"Neon 4"` (e.g. `@fingvo`) and `"Gemini 4 Neon High"` (e.g. `@camperaigg`) and `"GPT 6.2 Astra (High)"` (e.g. `@chetanankola`) and `"Astra 6.2"` (e.g. `@MengTo`).
  - Legacy explicit patterns:
    - `r"\b(?:gpt[-\s]?(?:4|5|6(?:\.[01])?(?!\.\d)))\b"` (careful: `"GPT-6"` or `"GPT-6.0"` or `"GPT-6.1"` is legacy; `"GPT-6.2"` is frontier!)
    - `r"\bfable[-\s]?(?:5(?:\.[01])?)\b"` (when not `5.2+`)
    - `r"\bopus[-\s]?(?:[34](?:\.\d+)?|5\.[0-4])\b"`
    - `r"\b(?:sonnet|haiku)[-\s]?[34](?:\.\d+)?\b"`
    - `r"\bgemini[-\s]?[123](?:\.\d+)?\b"`
    - `r"\b(?:marble|kimi)\b"`
  - Generic family patterns (only applied when NO explicit frontier and NO explicit legacy match):
    - Claude/Gemini generic (`claude`, `claude code`, `gemini`, `antigravity`): frontier if `published_at >= "2026-11-10"`.
    - GPT generic (`gpt`, `chatgpt`, `codex`, `astra`): frontier if `published_at >= "2026-11-17"`.
  - Precedence:
    1. If ANY model in `models_used` matches **explicit frontier** → `"frontier"`.
    2. Else if ANY model matches **explicit legacy** → `"legacy"`.
    3. Else apply **date-inferred** rule on generic family names.
    4. Else → `"legacy"`.

### 2.2 Update `src/models.py`
Add two fields to `AIWorldCase` with safe defaults (so all existing 1,081 rows in `data/processed/cases.jsonl` remain valid):
```python
model_era: Literal["frontier", "legacy"] = "legacy"
work_type: Literal["interactive_world", "coded_3d_scene"] = "interactive_world"
```
Also update `src/extract_structured.py` `extraction_schema()`:
- Pop `"model_era"` from LLM extraction schema (it MUST be computed deterministically by `classify_model_era`, never guessed by LLM).
- Keep `"work_type"` in LLM extraction schema so extraction labels Class A vs Class B.

### 2.3 Update `src/publish_catalog.py`
- In `publish()`:
  - Compute `case.model_era = classify_model_era(case.models_used, case.published_at)` on every case before writing `cases.jsonl`, `ai_worlds.json`, `worlds.json`.
  - Update `meta.json` to include:
    - `frontier_total`: count of public cases with `model_era == "frontier"`
    - `legacy_total`: count of public cases with `model_era == "legacy"`
    - `frontier_model_family_counts`: family counts restricted to `frontier` cases
  - Update `trusted()` auto-approve rule:
    - Do not require `likes >= 40` for `frontier` cases that have verified `models_used`, `evidence_quotes`, and non-empty `tech_stack` (allow `likes >= 1` for watched authors or live demos, and `likes >= 15` for other frontier cases with video/code evidence; keep `likes >= 40` for legacy).
  - Exclude any handle listed in `config/seeds.yaml` `excluded_aggregator_accounts` from `watch_suggestions.json` and from `trusted()` auto-approval.

### 2.4 Unit Tests (`tests/test_model_era.py`)
Test all 15+ model strings & date boundary cases (including `"GPT-6.2 Astra"`, `"GPT 6.2 Astra (High)"`, `"Astra 6.2"`, `"GPT-6 Astra"`, `"Fable 5.2"`, `"Fable 5.1"`, `"Opus 5.5"`, `"Opus 5.6"`, `"Opus 4.6"`, `"Gemini 4 Neon"`, `"Neon 4"`, `"Gemini 3 Pro"`, `"Marble"`, `"Claude"` on `2026-11-24` vs `2026-10-15`, `"Codex"` on `2026-11-20` vs `2026-11-05`).

---

## 3. Workstream 2 — Fix Qualifier False Negatives & Enforce Exclusion Rules

### 3.1 Update `src/qualify_candidates.py`
1. **Deterministic Pre-Filters (before LLM gate)**:
   - **Aggregator exclusion**: Load `excluded_aggregator_accounts` from `config/seeds.yaml` (case-insensitive, initially `["rewind02"]`). Skip matching authors from `qualify()`, and if post text matches `r"\(dev:\s*@?([A-Za-z0-9_]{1,30})\)"`, append `{source_tweet_id, aggregator, credited_dev, text_snippet}` into `data/state/aggregator_leads.json`.
   - **Sponsored / PR exclusion**: Deterministically reject tweets (or embedded quoted tweet text if stored/available) containing explicit promo markers:
     - `r"【\s*PR\s*】|#PR\b|#ad\b|#sponsored\b|\bpaid partnership\b|\bBlack Friday deal\b|\b\d{2}%\s*OFF\b"` (case-insensitive).
     - Note: Also pass quoted tweet text (if present in `raw/apify/*.json` or `raw/x/*.json`) into the pre-filter and LLM gate context so quote-tweet ads like Higgsfield's Black Friday deal are caught!
2. **Frontier-Aware Likes Floor (replace hard `minimum = 40`)**:
   - Define `has_frontier_signal(text: str, published_at) -> bool`: matches explicit frontier aliases (`GPT-6.2`, `GPT 6.2`, `Astra 6.2`, `Fable 5.2`, `Opus 5.5`, `Opus 5.6`, `Gemini 4`, `Neon 4`, `Hydrogen`, `Carbon`) OR (published `>= 2026-11-10` AND mentions `Claude`/`Gemini`/`GPT`/`Codex` + 3D/code cue like `three.js`/`threejs`/`three js`/`WebGPU`/`WebGL`/`Blender`/`Unreal`/`Unity`/`GLSL`/`shader`/`single HTML`/`one HTML`).
   - If `has_frontier_signal(...)` OR author is in `watch_accounts`: **`minimum = 0`** (do NOT drop low-like gems like 1–6 likes!).
   - Otherwise: `minimum = 10 if g.external_urls else 30`.
3. **Update `RULES` Prompt**:
   - Explicitly accept **both**:
     - **Class A**: interactive / playable / navigable 3D world, game, or spatial web experience (live link or video recording).
     - **Class B**: AI-coded 3D scene, procedural architecture/carvings, shader/WebGPU/Three.js/Blender/Unreal/Unity 3D render or physics animation built with AI code/agents.
   - Explicitly reject:
     - Class C: GitHub repo roundups, library lists, generic tutorials without a concrete 3D scene.
     - Pure diffusion video generation / AI auto-editing without 3D code or 3D engine pipeline.
     - Sponsored / PR / promotional posts (`【PR】`, `#ad`, product discount/launch promos).
     - Secondary workflow-breakdown reposts summarizing another developer's work.
4. **Preserve Quoted Tweet Context (`src/apify_x.py` & `src/models.py`)**:
   - In `src/apify_x.py` `persist()`, save `quoted_text` (truncated to 500 chars) and `quoted_author` inside `raw/x/signals/<tweet_id>.json` (zero breaking change to `RawTweetRecord` schema!).
   - In `src/qualify_candidates.py`, read `signals/<tweet_id>.json` and include `[Quoted @<author>: <quoted_text>]` in the pre-filter + LLM gate context so quote-tweet promos (like `@mattshumer_` quoting `@higgsfield`'s Black Friday ad) are accurately detected and rejected!

### 3.2 Update `src/extract_structured.py` & `src/sync_catalog.py`
- Update `EXTRACTION_RULES` in `src/extract_structured.py`:
  - Allow both `work_type: "interactive_world"` (Class A) and `work_type: "coded_3d_scene"` (Class B).
  - Instruct extractor to set `review_status = "rejected"` if the post is sponsored/PR, a secondary breakdown of another dev's project, a tool listicle, or pure diffusion video-gen.
- Update `src/sync_catalog.py`:
  - Prioritize **frontier-signal** unseen groups BEFORE older backlog when sorting `groups` before `qualify()` and before `ATLAS_EXTRACT_LIMIT`.
  - Raise defaults: `ATLAS_GATE_LIMIT` default `"300"` (was `"80"`), `ATLAS_EXTRACT_LIMIT` default `"60"` (was `"12"`).
  - Support optional `--frontier-only` flag (or `ATLAS_FRONTIER_ONLY=true` env var) so backlog extraction skips legacy-era raw tweets.

---

## 4. Workstream 3 — Frontier-First Exhaustive X Crawler Upgrade

### 4.1 Update `config/seeds.yaml`
1. Add `excluded_aggregator_accounts`:
   ```yaml
   excluded_aggregator_accounts:
     - rewind02
   ```
2. **Merge existing high-yield authors into `watch_accounts`**:
   - Merge all 57 handles from `data/state/watch_suggestions.json` plus any author who already has `>= 1` frontier world in `data/exports/ai_worlds.json` (deduplicated case-insensitively, excluding `excluded_aggregator_accounts` and invalid handles).
   - Verify via script/test that NO account was added solely from `config/golden_benchmark.yaml`.
3. **Add `frontier_queries` section** (dedicated high-recall queries run in `Latest` mode with **NO `min_faves`** on core model+3D queries, and date window `since:2026-11-01` by default — or `2026-09-20` for Opus 5.5 and `2026-10-12` for Gemini 4):
   ```yaml
   frontier_queries:
     # GPT-6.2 Astra (hyphen, space, and Astra-first aliases)
     - '("GPT-6.2" OR "GPT 6.2" OR "Astra 6.2" OR "6.2 Astra") (threejs OR "three.js" OR "three js" OR WebGPU OR WebGL OR "single HTML" OR "one HTML" OR 3D OR world OR game OR FPS OR shader OR Blender OR Unreal OR Unity OR terrain OR diorama) -filter:retweets'
     # Claude Fable 5.2 (EN + ZH + JA)
     - '("Fable 5.2") (threejs OR "three.js" OR "three js" OR WebGPU OR WebGL OR 3D OR world OR game OR FPS OR diorama OR shader OR procedural OR Blender OR Unreal OR Unity OR 场景 OR 浏览器 OR 游戏 OR 世界 OR 3Dシーン) -filter:retweets'
     # Claude Opus 5.5 / 5.6 (EN + ZH + JA)
     - '("Opus 5.5" OR "Opus 5.6") (threejs OR "three.js" OR "three js" OR WebGPU OR WebGL OR 3D OR world OR game OR FPS OR shader OR "pure code" OR procedural OR Blender OR Unreal OR Unity OR 场景 OR 游戏) -filter:retweets'
     # Broad video net for Opus 5.6 / Fable 5.2 posts omitting "3D"/"three.js"
     - '("Opus 5.6" OR "Fable 5.2" OR "GPT-6.2" OR "Astra 6.2") ("pure code" OR "single HTML" OR "one HTML" OR procedural OR shader OR anime) filter:videos min_faves:15 -filter:retweets'
     # Gemini 4 series (Neon / Hydrogen / Carbon / Argon + shorthand "Neon 4")
     - '("Gemini 4" OR "Gemini 4 Neon" OR "Neon 4" OR "Gemini 4 Hydrogen" OR "Gemini 4 Carbon") (threejs OR "three.js" OR "three js" OR WebGPU OR WebGL OR 3D OR world OR game OR shader OR Blender OR "path-traced" OR procedural OR 3D世界) -filter:retweets'
     # Generic frontier-era WebGPU / Single-HTML (catches posts naming "Claude"/"Gemini"/"GPT" without version)
     - '("single HTML" OR "one HTML file" OR WebGPU) (3D OR island OR world OR terrain OR diorama OR walk OR swim OR fly) (Claude OR Gemini OR GPT OR Codex) filter:videos -filter:retweets'
     # Extended live-demo hosting sweep
     - '(url:"threeui.com" OR url:"drop3.app" OR url:"playdrop.ai" OR url:"chatgpt.site" OR url:"claude.ai/artifact" OR url:"patch.gg" OR url:"ai.studio") (3D OR world OR threejs OR WebGPU OR game OR scene OR terrain) -filter:retweets'
   ```
4. Update `trusted_demo_hosts` to also include `threeui.com`, `drop3.app`, `playdrop.ai`.

### 4.2 Upgrade `src/apify_x.py`
1. **Concurrency Cap**: Change `ThreadPoolExecutor(max_workers=3)` to `max_workers=2` everywhere in `src/apify_x.py` (eliminates Apify concurrent-run `REFUSED` errors).
2. **Actor Failover**:
   - In `RunLedger.fetch()` / `search()`, if primary `ACTOR` (`scrape.badger~twitter-tweets-scraper`) fails with `Partial Apify run`, `TIMED-OUT`, or `REFUSED` (after slot wait), automatically retry the same query once on fallback actor `KAITO` (`kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest`), logging the failover in the ledger.
3. **New `--mode frontier` Backfill Command**:
   - CLI args: `--mode frontier`, `--since` (default `2026-11-01`), `--date` (anchor, default today), `--budget-usd` (allow up to `Decimal("10.00")` when `--mode frontier`, keeping `LIMIT = Decimal("1.50")` default for `incremental`).
   - Executes 4 layers with adaptive time-window bisection:
     1. **Layer 1 (`frontier_queries`)**: For each query in `config["frontier_queries"]`, run `search_adaptive(ledger, query, start, end, limit=120, min_days=1)`.
        - **Adaptive Bisection Algorithm**: Run `[start, end]` with `max_results=limit`. If `len(returned) >= int(limit * 0.9)` and `(end - start).days > min_days`, split at `mid = start + (end - start) // 2` and recursively fetch `[start, mid]` and `[mid, end]`. This guarantees high-volume launch days (e.g., Nov 18–24) are never silently truncated!
     2. **Layer 2 (`watch_accounts` frontier timelines)**: Batch `watch_accounts` (excluding `excluded_aggregator_accounts`) in groups of 5:
        - Query: `(from:a OR from:b OR ...) (filter:videos OR filter:links) since:<since> until:<until> -filter:retweets -filter:replies`
        - Use `search_adaptive(..., limit=100, min_days=2)` so prolific authors never crowd out quieter ones in the same batch.
     3. **Layer 3 (Official accounts & release threads)**:
        - Official timelines: `(from:Google OR from:GoogleAI OR from:GoogleDeepMind OR from:OpenAI OR from:OpenAIDevs OR from:claudeai OR from:AnthropicAI) (3D OR threejs OR "three.js" OR WebGPU OR world OR game OR physics OR path-traced OR arcade) since:<since> until:<until> -filter:retweets`
        - Official release threads from `config/catalogs.yaml` `official_threads` (excluding Kimi): `conversation_id:<id> filter:replies` and `quoted_tweet_id:<id> filter:quote` with fallback to `KAITO` if primary returns 0 rows or fails.
     4. **Layer 4 (`hydrate_thread_roots`)**: Expand link regex to also match `threeui\.com|drop3\.app|playdrop\.ai`.
4. **Update `incremental()`**:
   - Include `frontier_queries` in `discover_queries(config)` so daily scheduled syncs continuously use the upgraded frontier queries.

---

## 5. Workstream 4 — Blind Golden Benchmark Evaluator & Integrity Tests

### 5.1 Create `src/eval_golden.py`
CLI: `python -m src.eval_golden [--benchmark config/golden_benchmark.yaml] [--data-dir data] [--strict]`

Checks every item in `config/golden_benchmark.yaml` across 3 funnel stages:
1. **Stage 1 — Raw Capture**: `data/raw/x/<tweet_id>.json` exists (also reports whether `raw/x/signals/<tweet_id>.json` exists and its `likes`).
2. **Stage 2 — Post-Gate**: Either present in `data/processed/cases.jsonl` OR cached `true` in `data/processed/extraction/gate/`.
3. **Stage 3 — Published Frontier Export**: Present in `data/exports/ai_worlds.json` (matching `tweet_id` in `original_post_url` or `related_post_urls`) with `review_status != "rejected"` AND `model_era == "frontier"`.

Metrics printed & saved to `data/state/golden_eval.json` and `reports/golden_eval.md`:
- `core_raw_recall` & `core_final_recall` (`hits / len(positive_core)`)
- `long_tail_raw_recall` & `long_tail_final_recall` (`hits / len(positive_long_tail)`)
- `negative_leakage` (`false_positives / len(negative_controls)`) — **MUST be `0`**
- `secondary_lead_leakage` (count of `secondary_leads` published under aggregator handle) — **MUST be `0`**
- Per-item diagnostic table showing exact drop-off stage (`missed_at_crawl`, `dropped_at_gate`, `stuck_in_pending`, `wrong_model_era`, `hit`) so any miss is immediately actionable.
- When `--strict` is set: exit code `0` iff `core_final_recall >= 0.85` AND `negative_leakage == 0` AND `secondary_lead_leakage == 0`.

### 5.2 Create `tests/test_golden_benchmark.py`
Automated guardrails:
1. `config/golden_benchmark.yaml` parses cleanly and has no duplicate `tweet_id`s.
2. **Leakage guard**: ZERO `tweet_id`s from `config/golden_benchmark.yaml` appear in `config/seeds.yaml` `seed_urls`.
3. `src/eval_golden.py` runs cleanly on a fixture directory and accurately computes recall & leakage metrics.

---

## 6. Workstream 5 — Frontend Option A (Default Frontier + Archive Toggle)

### 6.1 `platform/` (Atlas — Pure-White Light Mode Workbench)
- `platform/lib/worlds.ts`:
  - Add `model_era?: "frontier" | "legacy";` and `work_type?: "interactive_world" | "coded_3d_scene";` to `World` interface.
  - Export helper `isFrontier(w: World): boolean` (`w.model_era === "frontier"`).
- `platform/components/world-catalog.tsx` (and `platform/lib/i18n.ts`):
  - Add state `eraFilter: "frontier" | "all"` defaulting to `"frontier"`.
  - Render a clean, compact light-mode segmented toggle in the filter bar:
    - ZH: `仅前沿模型` / `全部（含归档）`
    - EN: `Frontier Only` / `All (Incl. Archive)`
  - Update summary counter in the catalog header to reflect the active era scope.
  - Keep existing pure-white light mode styling and full ZH/EN bilingual parity (`enDetailHasChinese === false`).

### 6.2 `feed/` (WorldFeed — Light-Mode Desktop TikTok Feed)
- `feed/scripts/build-feed-data.mjs`:
  - Include `model_era: w.model_era || "legacy"` and `work_type: w.work_type || "interactive_world"` in each `feed.json` entry.
  - Keep ranking logic intact, with frontier items prioritized naturally.
- `feed/src/App.tsx`:
  - Default feed stream filter to `model_era === "frontier"`, with a subtle light-mode toggle (`Frontier` / `Archive`) in the top bar so users immediately land on fresh frontier worlds while keeping legacy accessible.

---

## 7. Execution Sequence & Acceptance Checklist

Run in this exact order:

```bash
# 1. Implement Workstreams 1–5 and run unit tests
pytest -q

# 2. Re-publish existing ledger to stamp model_era on all 1,081 existing cases (zero API cost)
python -m src.publish_catalog

# 3. Record BEFORE baseline on Golden Benchmark
python -m src.eval_golden

# 4. Run frontier X backfill (budget-capped at $5.00, concurrency=2, adaptive bisection)
python -m src.apify_x --mode frontier --since 2026-11-01 --budget-usd 5.00
python -m src.apify_x --mode report --audit-output research/expansion/apify_frontier_audit.json

# 5. Run qualification, extraction, cover generation, and publish (frontier-first)
ATLAS_FRONTIER_ONLY=true ATLAS_GATE_LIMIT=400 ATLAS_EXTRACT_LIMIT=120 AUTO_APPROVE_TRUSTED=true \
  X_ADAPTER=apify python -m src.sync_catalog

# 6. Run strict Golden Benchmark evaluation (target: Core Recall >= 85%, Negative Leakage = 0)
python -m src.eval_golden --strict

# 7. Rebuild & verify both frontends
cd platform && npm run lint && npm run build:static
cd ../feed && npm run build
```

### Final Acceptance Criteria
- [ ] `pytest -q` passes 100% (including `tests/test_model_era.py` and `tests/test_golden_benchmark.py`).
- [ ] Zero `golden_benchmark.yaml` URLs leaked into `config/seeds.yaml` `seed_urls`.
- [ ] `python -m src.eval_golden --strict` exits `0`:
  - `positive_core` final recall **≥ 85%** (at least 10 / 11).
  - `negative_controls` leakage **= 0 / 3** (no listicles, no `【PR】`, no Black Friday promo).
  - `secondary_leads` published under `@rewind02` **= 0 / 5**.
  - `positive_long_tail` recall reported transparently in `reports/golden_eval.md`.
- [ ] `data/exports/meta.json` reports balanced frontier coverage across GPT-6.2 Astra, Claude Fable 5.2 / Opus 5.5–5.6, and Gemini 4 series.
- [ ] Both `platform/` and `feed/` build cleanly, open strictly in light mode, default to `model_era === "frontier"`, and allow toggling to include legacy archive.
- [ ] Total Apify spend verified via `research/expansion/apify_frontier_audit.json` (<= `$5.00`).
