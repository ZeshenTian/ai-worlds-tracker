# Frontier 3D Worlds — Phase 2 Refinement & Reliability Spec (Codex-Executable)

> **Target Repo**: `/Users/zeshentian/Documents/ChatGPT/ai-worlds-tracker`
> **Builds On**: Phase 1 (`reports/frontier_acceptance.md`, 1,720 total / 1,175 frontier, Apify spend `$3.31`)
> **User-Approved Scope (2026-11-25)**: Plan **1A** — Unblock pending frontier backlog, repair failed Apify crawl gaps, canonicalize model taxonomy, merge all historical 3D creators, batch-verify live frontier demos, and pass BOTH V1 and V2 blind benchmarks.
> **Explicit Non-Goals for Phase 2**:
> - Do NOT chase 1–6 like random low-engagement accounts (`long_tail` is diagnostic only).
> - Do NOT add new non-English language expansion queries (English-first; keep existing working queries).
> - Do NOT build new non-X platform scrapers (Reddit/YouTube/itch.io) yet.

---

## 0. Root-Cause Diagnosis from Phase 1 Audit

Phase 1 achieved 100% raw crawl recall (11/11) on V1 Core and 7/9 (77.8%) on independent external V2 sampling, with 0 negative leakage and 0 aggregator leakage. However, four concrete bottlenecks prevented a clean strict pass and suppressed catalog quality:

1. **P0-1 — 1,390 Frontier Cases Stuck in `pending` (249 with >= 100 likes)**:
   - **Reverse-duplicate trap**: 10 of the top 15 viral pending frontier works (`@GoogleAI` 8,676 likes, `@kevin_t_ngo` 4,288 likes, `@flxrnc` 4,925 likes, `@chetaslua` 3,880 likes, `@GoogleDeepMind` 2,111 likes, plus V1 core `@RezAIT00/2125368341002924390`) have `possible_duplicate_urls` populated because **later reposts/copies** matched their media or links, and `publish_catalog.py:trusted()` blocks auto-approval whenever `possible_duplicate_urls` is non-empty.
   - **Over-paranoid attribution holds**: `src/recheck_creator_role.py` holds genuine creator showcases (e.g., `@scottstts/2124899361200931069` `"I love this one so much, Amber Hour in @threejs... made by fable 5.2"`) by misreading enthusiastic praise of the author's own model-generated output as `human_role: "reporting_on_others"`, and applies the same skepticism to official first-party AI lab accounts (`@GoogleAI`, `@GoogleDeepMind`, `@OpenAI`, `@claudeai`).
   - **Alibaba API Billing Rule Violation**: `src/recheck_creator_role.py:qwen_client()` currently uses `DASHSCOPE_API_KEY` + `https://dashscope.aliyuncs.com/compatible-mode/v1` (pay-as-you-go!). Per global user policy, **ALL Qwen/Alibaba calls MUST default to Token Plan**: `ALIBABA_TOKEN_PLAN_API_KEY` + `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` (loaded from env or `~/.config/ai-keys/keys.env`).
2. **P0-2 — 61 Failed / Timed-Out Apify Runs (21.7% failure rate on primary actor)**:
   - In `research/expansion/apify_frontier_audit.json`, primary actor `scrape.badger` (`pzMmk1t7AZ8OKJhfU`) had **41 `TIMED-OUT` + 20 `FAILED`** (32 author batches, 15 topical, 8 official quotes, 4 domain), whereas fallback actor `kaitoeasyapi` (`CJdippxWmn9uRfooo`) achieved **66/66 (100% success, 0 timeouts, 0 failures)**.
   - Additionally, 2 saturated 1-day windows still hit >= 90% of `max_results`, risking silent truncation on peak launch days.
3. **P1-1 — Polluted `models_used` & Fragmented `meta.json` Taxonomy**:
   - `data/exports/meta.json` currently lists non-models (`Tripo`, `UE 5.9`, `Rust + Vulkan`, `Two.js`, `gifenc`, `procedural Blender modeling`, `Higgsfield`, `Seedance`, `@fal`, `Rokoko`, `Suno`) inside `models_used` and `frontier_model_family_counts`, while fragmenting identical models into 10+ variants (`Fable 5.2`, `fable 5.2`, `FABLE 5.2`, `Fable5.2`, `Claude Fable 5.2`).
4. **P1-2 — Missing Historical Creators in `watch_accounts` & Unverified Frontier Playable Demos**:
   - Only frontier authors were promoted to `watch_accounts`, leaving historical 3D creators from the legacy catalog out of timeline monitoring.
   - Only **26 / 319 (8.1%)** of live frontier demos have completed `verified_playable` browser verification and updated `embed_probe.json` for WorldFeed.

---

## 1. Non-Negotiable Guardrails

1. **Strict Holdout Blindness (V1 + V2)**:
   - **NEVER** copy any URL, `tweet_id`, or author handle solely from `config/golden_benchmark.yaml` OR `config/golden_benchmark_v2.yaml` into `config/seeds.yaml` or hardcoded search queries.
   - Extend `tests/test_golden_benchmark.py` to enforce zero leakage for **BOTH** `config/golden_benchmark.yaml` and `config/golden_benchmark_v2.yaml`.
2. **Alibaba Qwen Token Plan Default (Mandatory)**:
   - In `src/recheck_creator_role.py` (and any other file calling Qwen/Alibaba models), switch default credentials & endpoint to:
     - Env key: `ALIBABA_TOKEN_PLAN_API_KEY` (read from `os.getenv` or `~/.config/ai-keys/keys.env`)
     - Base URL: `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
     - Do NOT mix `DASHSCOPE_API_KEY` with the Token Plan endpoint or vice versa. Never print plaintext keys.
3. **Budget & UI Guardrails**:
   - Apify Phase 2 retry/repair budget cap: **`$2.50`**.
   - Keep `platform/` and `feed/` strictly **light mode** (default `frontier`, archive toggle intact).

---

## 2. Workstream P0-1 — Fix Reverse-Duplicate Trap, Attribution False-Holds & Unblock Pending Backlog

### 2.1 Fix Earliest-Original Priority in Deduplication (`src/publish_catalog.py`, `src/recheck_duplicates.py`, `src/reconcile_sources.py`)
When multiple X cases are flagged as potential duplicates (via `possible_duplicate_urls`, identical media SHA/attachment, or identical `live_demo_url`/`repo_url`):
- Compare numeric X Snowflake `tweet_id`s (strictly chronological) and native media ownership:
  1. The **canonical earliest original post** (lowest numeric `tweet_id` among non-aggregator, non-rejected posts; or an official AI lab account if posting native media) MUST **clear** later-repost URLs from its `possible_duplicate_urls` and move them to `related_post_urls` (unless a verified earlier external creator exists with a strictly smaller `tweet_id` or proven earlier external upload!).
  2. Later reposts/copies keep `possible_duplicate_urls` pointing to the canonical original (and remain `rejected` or `pending`).
- Add unit tests in `tests/test_media_dedup.py` verifying that a viral original tweet (`@RezAIT00/2125368341002924390` pattern) is **never** blocked by later reposters linking/re-uploading the same video.

### 2.2 Fix Attribution False-Holds & Token Plan Endpoint (`src/recheck_creator_role.py`, `src/recheck_attribution.py`, `src/publish_catalog.py`)
1. **Switch `qwen_client()` to Alibaba Token Plan** (`ALIBABA_TOKEN_PLAN_API_KEY` + `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`).
2. **Official First-Party Fast Path**:
   - Posts from official AI lab accounts (`Google`, `GoogleAI`, `GoogleDeepMind`, `OpenAI`, `OpenAIDevs`, `claudeai`, `AnthropicAI`) that showcase a concrete 3D world/coded 3D scene with attached media or demo link are **first-party by definition** (still reject pure text model-launch announcements or pricing guides like `@ClaudeDevs/2119898687803621427` that show no concrete 3D scene!).
3. **Fix Creator-Praise vs Third-Party-Reporting Confusion in `RULES` (`src/recheck_creator_role.py` & `src/recheck_attribution.py`)**:
   - Explicitly instruct the classifier:
     - Enthusiastic admiration of the author's own output (`"I love this one so much"`, `"This is insane"`, `"Fable 5.2 is still the GOAT"`, `"It generated this FPS in 3 hours"`) where **NO other human creator or third-party account is named** AND the author uploaded original media/video is **`specific_creator_presentation` / `maker_or_team`**, NOT `reporting_on_others`!
     - Only classify as `reporting_on_others` / `other_human_or_team` when the post explicitly credits another human/team, quotes another user's work, uses third-party attribution (`"by @someone"`, `"dev: ..."`, `"check out what X built"`), or is a known aggregator/news account.
     - Relax `ground_resolution()` so that when `human_role in {"maker_or_team", "specific_creator_presentation"}` and `counterevidence == "none"` and `scope in {"interactive_spatial", "coded_scene"}`, a single strong `subject_quote` + `models` + `has_images` (or native video attachment) is sufficient even if the author omitted `"I built"` pronouns.
4. **Re-run attribution & publish over the existing 1,390 `frontier:pending` backlog**:
   - Prioritize `likes >= 15` (and all watched/known authors regardless of likes) in `data/processed/cases.jsonl` (`model_era == "frontier"` and `review_status == "pending"`).
   - Zero Apify cost! Record before/after counts (`pending_before` → `pending_after`, `newly_approved_frontier`, `newly_rejected_frontier`).

---

## 3. Workstream P0-2 — Repair Failed Apify Crawl Gaps & Saturated Windows (`src/apify_x.py`)

1. **Promote Reliable Actor (`kaitoeasyapi`) for Recovery & High-Failure Channels**:
   - Add CLI flag `--actor {auto,badger,kaito}` to `src/apify_x.py`, and add `--mode retry-gaps` which reads `research/expansion/apify_frontier_audit.json` (or `data/state/apify_x/ledger.json`) to find every frontier run that ended in `TIMED-OUT`, `FAILED`, or `incomplete=True` (all 61 failed runs from Phase 1) and replays ONLY those failed queries using `KAITO` (`kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest`, which had 66/66 = 100% success in Phase 1).
   - Also make `auto` failover immediately switch to `KAITO` on first `TIMED-OUT` or `FAILED` without wasting retries on a degraded actor.
2. **Fix 1-Day Saturated Window Truncation**:
   - In `search_adaptive()` (`src/apify_x.py`), when a window reaches `min_days == 1` and STILL returns `>= int(limit * 0.9)` rows, paginate backwards within that day using `max_id:<min_returned_id - 1>` (up to 3 extra pages per saturated day) so peak model-launch days are never truncated.
3. **Run targeted gap recovery (`--mode retry-gaps --budget-usd 2.50`)** + re-run extraction on newly captured active frontier tweets (`likes >= 15` or watched authors).
   - Save updated audit to `research/expansion/apify_frontier_phase2_audit.json`.

---

## 4. Workstream P1-1 — Canonicalize `models_used` & Purge Non-Model Tools (`src/model_era.py`, `src/models.py`, `src/publish_catalog.py`)

### 4.1 Add `canonicalize_models_and_stack(models_used, tech_stack)` in `src/model_era.py`
Clean up the taxonomy pollution observed in `data/exports/meta.json`:
1. **Non-model tool/engine/asset-gen demotion**: Move non-LLM tools & 3D/audio/video auxiliary tools out of `models_used` into `tech_stack` (never leave them in `models_used` or `frontier_model_family_counts`):
   - `Tripo`, `Tripo AI`, `Tripo HD 3.1`, `Tripo P2`, `Tripo Smart Mesh P2`, `Tripo Agentic Canvas`, `tripoai`, `Meshy`, `Hyper3D Rodin`, `Hunyuan3D`, `fal`, `@fal`, `fal TRELLIS-2`, `Higgsfield`, `HIGGSFIELD`, `UE 5.9`, `Unreal Engine`, `Two.js`, `Rust + Vulkan`, `gifenc`, `procedural Blender modeling`, `Rokoko`, `Mesh2Motion`, `Suno`, `Depth Anything V2 Large`, `VFX Studio`, `ClaudeAnimationBase`, `Antigravity` (when paired with an actual model like `Gemini 4 Neon`, move `Antigravity` to `tech_stack`; keep only if sole disclosed entry).
2. **Canonical LLM Name Normalization**: Collapse spelling/case/spacing/tier noise into clean canonical names (preserve version fidelity; never upgrade a version!):
   - `Claude Fable 5.2` ← `fable 5.2`, `FABLE 5.2`, `Fable  5.2`, `Fable5.2`, `fable5.2`, `Anthropic Fable 5.2`, `Claude(Fable 5.2)`, `Claude Fable 5.2 (Max)`, `Fable 5.2 High/Medium/xhigh`
   - `Claude Opus 5.5` ← `Opus 5.5`, `OPUS 5.5`, `opus 5.5`, `Opus5.5`, `Claude (Opus 5.5)`, `Claude Code（Opus 5.5）`, `Claude code opus 5.5`, `Opus 5.5 Extra/Medium/Xhigh`
   - `Claude Opus 5.6` ← `Opus 5.6`, `opus model (5.6)`
   - `GPT-6.2 Astra` ← `GPT 6.2 Astra`, `GPT-6.2-Astra`, `GPT-6.2 ASTRA`, `Astra 6.2`, `astra 6.2`, `6.2 Astra`, `ChatGPT-6.2 Astra`, `GPT Astra 6.2`, `GPT Astra-6.2`, `GPT-6.2 Atra High`, `GPT 6.2 Astra (High)`, `GPT-6.2 Astra Ultra`, `Astra 6.2 High/Ultra`
   - `GPT-6.2 Sol` ← `GPT 6.2 Sol`, `GPT 6.2 sol`, `GPT 6.2 SOL MAX`, `Sol 6.2`, `sol 6.2`, `Sol 6.2 High`, `GPT-6.2 Sol(高)`
   - `Gemini 4 Neon` ← `gemini 4 neon`, `Gemini4 Neon`, `Gemini 4 Neon (High)`, `Gemini 4 Neon Extra High`, `Gemini 4 Neon Low`, `Neon 4`, `gemini neon`
   - `Gemini 4 Hydrogen` ← `GEMINI 4 HYDROGEN`, `Gemini 4 Hydrogen (XHigh)`, `Gemini 4 Hydrogen Flash`, `Gemini 4 Hydrogen xhigh`, `Google Gemini 4 Hydrogen (Extra)`
   - `Gemini 4 Carbon` ← `GEMINI 4 CARBON`, `Gemini 4 Carbon (High)`, `Gemini 4 Carbon High`, `Gemini 4 Carbon-H`, `Gemini Carbon 4`
   - `Gemini 4 Argon` ← `gemini 4 argon`, `Gemini 4 Argon (High)`, `Google's Gemini 4 Argon`, `Gemini Argon`
   - Also normalize legacy names cleanly (`GPT-6 Astra`, `Claude Fable 5`, `Claude Fable 5.1`, `Marble`, `Kimi K3.1 Pro`).
3. **Apply in `publish_catalog.py`**:
   - Run `canonicalize_models_and_stack()` before `classify_model_era()` and before computing `meta.json` (`model_counts`, `model_family_counts`, `frontier_model_family_counts`).
   - Verify `frontier_model_family_counts` contains ONLY genuine AI model families (`Claude`, `GPT`, `Gemini`, plus rare secondary LLMs if co-used with a frontier model — ZERO `Tripo`, `UE 5.9`, `gifenc`, `Two.js`, `Higgsfield`, etc.!).
4. Add comprehensive unit tests in `tests/test_model_era.py`.

---

## 5. Workstream P1-2 — Expand Creator Watchlist & Batch-Verify Live Frontier Demos

1. **Merge ALL Historical 3D Creators into `config/seeds.yaml` `watch_accounts`**:
   - Extract every unique `author_handle` from `data/exports/ai_worlds.json` (both `frontier` and `legacy` — NOT just frontier, since legacy 3D creators frequently publish new frontier builds!), minus `excluded_aggregator_accounts`, and merge into `watch_accounts`.
   - Confirm via `tests/test_golden_benchmark.py` that ZERO handles were added solely from V1 or V2 holdout files.
   - Run one quick targeted author-timeline sweep ONLY for newly added historical creators (`since:2026-11-01`, `KAITO`, within the `$2.50` cap) so missed works from prior creators are captured.
2. **Batch Demo Verification & Embed Probing for Frontier Live Links**:
   - Run `src/verify_demos.py` (increase batch cap to cover unverified `model_era == "frontier"` cases with `live_demo_url`, targeting at least 150+ checked frontier demos, prioritizing highest-engagement / newest demos first).
   - Re-run `cd feed && node scripts/probe-embeds.mjs && node scripts/build-feed-data.mjs` so WorldFeed immediately reflects all newly unblocked frontier worlds, cleaned model tags, and newly verified playable/embeddable demos!
3. **Rebuild & Verify Both Frontends**:
   - `cd platform && npm run lint && npm run build:static`
   - `cd feed && npm run build`
   - Re-run headless Chrome checks confirming light mode, zero console errors, default frontier count matching `meta.json` `frontier_total`, and clean model filter chips (no `Tripo`/`gifenc` junk).

---

## 6. Dual-Benchmark Verification & Final Acceptance Criteria

Run in order:
```bash
# 1. Unit tests (including V1 + V2 zero-leakage & model canonicalization & dedup tests)
pytest -q

# 2. P0-1: Unblock pending frontier backlog & canonicalize models (zero Apify spend)
python -m src.recheck_attribution --frontier-pending
python -m src.publish_catalog

# 3. P0-2 & P1-2: Retry 61 failed Apify runs + newly merged historical creators (KAITO, <= $2.50)
python -m src.apify_x --mode retry-gaps --actor kaito --budget-usd 2.50
python -m src.apify_x --mode report --audit-output research/expansion/apify_frontier_phase2_audit.json

# 4. Sync newly captured active frontier items (likes >= 15 or watched author), verify demos, publish
ATLAS_FRONTIER_ONLY=true ATLAS_MIN_LIKES=15 ATLAS_GATE_LIMIT=400 ATLAS_EXTRACT_LIMIT=150 \
  ATLAS_VERIFY_LIMIT=150 AUTO_APPROVE_TRUSTED=true X_ADAPTER=apify python -m src.sync_catalog

# 5. Dual Blind Benchmark Evaluation (BOTH V1 and V2 MUST pass strict!)
python -m src.eval_golden --benchmark config/golden_benchmark.yaml --report reports/golden_eval_v1.md --strict
python -m src.eval_golden --benchmark config/golden_benchmark_v2.yaml --report reports/golden_eval_v2.md --strict

# 6. Rebuild WorldFeed embed probes & both frontends
cd feed && node scripts/probe-embeds.mjs && npm run build
cd ../platform && npm run lint && npm run build:static
```

### Hard Acceptance Checklist (Write final report to `reports/frontier_phase2_acceptance.md`)
- [ ] `pytest -q` 100% green, including V1 + V2 zero-leakage tests and `canonicalize_models_and_stack()` tests.
- [ ] `src/recheck_creator_role.py` defaults to Alibaba **Token Plan** (`ALIBABA_TOKEN_PLAN_API_KEY` + `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`).
- [ ] **V1 Strict Pass (`reports/golden_eval_v1.md`)**: `positive_core >= 85%` (>= 10/11), `negative_controls == 0/3`, `secondary_leads == 0/5`.
- [ ] **V2 Strict Pass (`reports/golden_eval_v2.md`)**: `positive_core >= 85%` (>= 8/9), `negative_controls == 0/5`.
- [ ] **Pending Backlog Reduced**: Report exact `frontier:pending` count before (1,390) vs after, plus how many `likes >= 100` viral frontier worlds were unblocked.
- [ ] **Apify Recovery**: Report how many of the 61 failed Phase 1 runs succeeded on `kaitoeasyapi`, total Phase 2 Apify spend (`<= $2.50`).
- [ ] **Clean Taxonomy**: `meta.json` `frontier_model_family_counts` contains ZERO tool/engine names (`Tripo`, `UE 5.9`, `Two.js`, `gifenc`, `Higgsfield`, etc.) and normalized canonical model names.
- [ ] **Playable Coverage**: Report exact frontier `verified_playable` count (before: 26) and WorldFeed embeddable count after `probe-embeds.mjs`.
- [ ] Both `platform/` and `feed/` pass build + light-mode Chrome verification.
