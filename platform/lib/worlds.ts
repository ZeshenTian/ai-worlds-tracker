import playableIds from "@/data/embeddable-ids.json";
import dataset from "@/data/worlds.json";
import enOverrides from "@/data/worlds-en.json";
import type { Lang } from "./i18n";

const enMap = enOverrides as Record<string, { wf?: string[]; sp?: string[]; title?: string; author?: string; summary?: string; tech_stack?: string[] }>;

const englishText = (value?: string | null) => value && !/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u.test(value) ? value : "";
const englishList = (list: string[]) => list.filter(s => Boolean(englishText(s)));

export function workflowStepsFor(world: World, lang: Lang): string[] {
  if (lang === "zh") return world.workflow_steps;
  return englishList(enMap[world.world_id]?.wf ?? (world.workflow_steps_en?.length ? world.workflow_steps_en : world.workflow_steps));
}

export function skillsFor(world: World, lang: Lang): string[] {
  if (lang === "zh") return world.skills_or_prompts_used;
  return englishList(enMap[world.world_id]?.sp ?? world.skills_or_prompts_used);
}

export function localizedWorld(w: World, lang: Lang): World {
  if (lang === "zh") return w;
  const tr = enMap[w.world_id] || {};
  const quotes = englishList(w.evidence_quotes);
  const summary = englishText(tr.summary) || englishText(w.summary_en) || englishText(w.summary) || quotes[0] || "";
  return {...w, title: englishText(tr.title) || englishText(w.title) || summary.split(/[.!?]\s/)[0] || "3D scene",
    author_name: englishText(tr.author) || englishText(w.author_name), author_handle: englishText(w.author_handle),
    summary, summary_en:summary, models_used:englishList(w.models_used),
    evidence_quotes:quotes, tech_stack:englishList(tr.tech_stack ?? w.tech_stack)};
}

export const themes: Record<string, string> = {
  nature_ecosystem: "自然生态",
  city_diorama: "城市微缩",
  fantasy_rpg: "奇幻世界",
  sci_fi: "科幻空间",
  physics_sim: "物理模拟",
  voxel_sandbox: "体素沙盒",
  historical: "历史重建",
  other: "其他",
};

export const themesEn: Record<string, string> = {
  nature_ecosystem: "Nature",
  city_diorama: "City",
  fantasy_rpg: "Fantasy",
  sci_fi: "Sci-Fi",
  physics_sim: "Physics",
  voxel_sandbox: "Voxel",
  historical: "Historical",
  other: "Other",
};

export const levels: Record<string, string> = {
  video_only: "仅视频",
  prompt_shared: "含提示词",
  live_demo: "在线试玩",
  full_repo: "完整仓库",
};

export const levelsEn: Record<string, string> = {
  video_only: "Video Only",
  prompt_shared: "Prompt Shared",
  live_demo: "Live Demo",
  full_repo: "Full Repo",
};

export function themeLabel(key: string, lang: Lang) {
  if (key === "other") return "";
  return (lang === "en" ? themesEn[key] : themes[key]) || "";
}

export function levelLabel(key: string, lang: Lang) {
  return (lang === "en" ? levelsEn[key] : levels[key]) || key;
}

export interface World {
  model_era?: "frontier" | "legacy";
  work_type?: "interactive_world" | "coded_3d_scene";
  world_id: string;
  title: string;
  summary: string;
  summary_en?: string | null;
  workflow_steps_en?: string[];
  cover_source?: string | null;
  cover_source_url?: string | null;
  theme_category: string;
  models_used: string[];
  tech_stack: string[];
  generation_mode: string;
  reproducibility_level: string;
  is_open_source: boolean | null;
  repo_url: string | null;
  live_demo_url: string | null;
  demo_health_status: string;
  thumbnail_url: string | null;
  original_post_url: string;
  author_handle: string | null;
  author_name: string | null;
  source_kind: string;
  first_seen_at: string | null;
  published_at: string | null;
  review_status: string;
  reported_cost_usd: number | null;
  reported_time_minutes: number | null;
  workflow_steps: string[];
  skills_or_prompts_used: string[];
  evidence_quotes: string[];
  evidence_source_urls: string[];
  related_post_urls: string[];
}

export const byline = (w: World, lang: Lang = "zh") =>
  w.author_name || (w.author_handle ? "@" + w.author_handle : lang === "en" ? "Unknown" : "匿名");

export const isPlayable = (w: World) => w.demo_health_status === "verified_playable";

export const worlds: World[] = dataset
  .filter((world) => world.review_status !== "rejected" && world.model_era === "frontier")
  .map((world) => ({
    ...world,
    model_era: world.model_era === "frontier" ? "frontier" : "legacy",
    work_type: world.work_type === "coded_3d_scene" ? "coded_3d_scene" : "interactive_world",
  }));
export function family(name: string) {
  const label = name.trim();
  if (/^(?:(?:openai(?:['’]s)?\s+)?(?:gpt|chatgpt|codex|astra|sol)(?=\b|\d)|\d+(?:\.\d+)?\s+astra\b)/i.test(label)) return "GPT";
  if (/^(?:(?:anthropic(?:['’]s)?|routed)\s+)?(?:claude|opus|fable|haiku|sonnet)(?=\b|\d)/i.test(label)) return "Claude";
  if (/^(?:google(?:['’]s)?\s+)?(?:gemini|neon|argon|hydrogen|carbon|antigravity)(?=\b|\d)/i.test(label)) return "Gemini";
  return "Other";
}
export const modelFamilies = [...new Set(["Claude", "GPT", "Gemini", ...worlds.flatMap(w => w.models_used.map(family))])];

export function familyTone(name: string): "claude" | "gpt" | "gemini" | "other" {
  const f = family(name);
  if (f === "Claude") return "claude";
  if (f === "GPT") return "gpt";
  if (f === "Gemini") return "gemini";
  return "other";
}

export function values(key: "tech_stack" | "models_used") {
  return [...new Set(worlds.flatMap((world) => world[key]))].sort();
}

export const isFrontier = (w: World) => w.model_era === "frontier";

export const countWorlds = (worlds: World[]) => ({
  all: worlds.length,
  playable: worlds.filter(isPlayable).length,
  open: worlds.filter((world) => world.is_open_source === true).length,
  repos: worlds.filter((world) => Boolean(world.repo_url)).length,
  withThumb: worlds.filter((world) => Boolean(world.thumbnail_url)).length,
  withWorkflow: worlds.filter((world) => world.workflow_steps.length > 0).length,
});
export const count = countWorlds(worlds);

export function monthOf(world: World) {
  return world.published_at?.slice(0, 7) ?? "";
}

export function webLink(value: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (["http:", "https:"].includes(url.protocol) && !url.username && !url.password) return url.href;
  } catch {
    /* incomplete source URL */
  }
  return undefined;
}

export const playable = new Set(playableIds);
export function feedBase() {
  return process.env.NEXT_PUBLIC_WORLDFEED_URL || (typeof location !== "undefined" && ["localhost","127.0.0.1"].includes(location.hostname) ? "http://127.0.0.1:8871" : "https://worldfeed.zeshentian1.chatgpt.site");
}
export const hasLiveDemo = (world: World) => Boolean(world.live_demo_url) && world.demo_health_status !== "broken";

export function caseHref(world: World, base = feedBase()) {
  if (!hasLiveDemo(world)) return world.original_post_url;
  return playable.has(world.world_id) ? base.replace(/\/$/, "") + "/?w=" + world.world_id : world.live_demo_url || world.original_post_url;
}

const BARE_MODEL_QUOTE = /^(made\s+with\s+)?(claude|gpt|gemini|codex)[\w\s.\-()]{0,24}$/i;

export function cleanQuotes(world: World): string[] {
  const normalized = world.evidence_quotes
    .map((q) => q.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  const meaningful = normalized.filter((q) => !BARE_MODEL_QUOTE.test(q));
  return meaningful.length > 0 ? meaningful : normalized;
}

export function bestQuote(world: World): string {
  const quotes = cleanQuotes(world);
  const picked = quotes.find((q) => q.length >= 20) || quotes[0] || world.summary;
  return picked.length > 136 ? picked.slice(0, 134).trimEnd() + "…" : picked;
}

export function sourceHost(url: string | null): string {
  const valid = webLink(url);
  if (!valid) return "";
  try {
    const parsed = new URL(valid);
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export function coverTint(theme: string): "sage" | "sky" | "sand" | "slate" {
  if (theme === "nature_ecosystem" || theme === "voxel_sandbox") return "sage";
  if (theme === "sci_fi" || theme === "physics_sim") return "sky";
  if (theme === "historical" || theme === "fantasy_rpg") return "sand";
  return "slate";
}
