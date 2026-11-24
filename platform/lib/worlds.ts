import dataset from "@/data/worlds.json";
import enOverrides from "@/data/worlds-en.json";
import type { Lang } from "./i18n";

const enMap = enOverrides as Record<string, { wf?: string[]; sp?: string[] }>;

export function workflowStepsFor(world: World, lang: Lang): string[] {
  if (lang === "en" && world.workflow_steps_en?.length) return world.workflow_steps_en;
  if (lang === "en" && enMap[world.world_id]?.wf) return enMap[world.world_id].wf!;
  return world.workflow_steps;
}

export function skillsFor(world: World, lang: Lang): string[] {
  if (lang === "en" && enMap[world.world_id]?.sp) return enMap[world.world_id].sp!;
  return world.skills_or_prompts_used;
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

export const modes: Record<string, string> = {
  one_shot: "单次提示",
  iterative_chat: "对话迭代",
  agentic_loop: "智能体循环",
  hybrid_pipeline: "混合流程",
  unknown: "未披露",
};

export const modesEn: Record<string, string> = {
  one_shot: "One-Shot",
  iterative_chat: "Iterative",
  agentic_loop: "Agentic Loop",
  hybrid_pipeline: "Hybrid",
  unknown: "Undisclosed",
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

export const healthLabels: Record<string, string> = {
  verified_playable: "可试玩",
  login_required: "需登录",
  broken: "不可用",
  no_demo: "无试玩",
  unverified: "待验证",
};

export const healthLabelsEn: Record<string, string> = {
  verified_playable: "Playable",
  login_required: "Login",
  broken: "Broken",
  no_demo: "No Demo",
  unverified: "Unverified",
};

export function themeLabel(key: string, lang: Lang) {
  return (lang === "en" ? themesEn[key] : themes[key]) || (lang === "en" ? "Other" : "其他");
}

export function modeLabel(key: string, lang: Lang) {
  return (lang === "en" ? modesEn[key] : modes[key]) || (lang === "en" ? "Undisclosed" : "未披露");
}

export function levelLabel(key: string, lang: Lang) {
  return (lang === "en" ? levelsEn[key] : levels[key]) || key;
}

export function healthLabel(key: string, lang: Lang) {
  return (lang === "en" ? healthLabelsEn[key] : healthLabels[key]) || key;
}

export const submissionUrl =
  "https://github.com/ZeshenTian/ai-worlds-tracker/issues/new?template=new-world.yml";

export interface World {
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

export const worlds: World[] = dataset.filter((world) => world.review_status !== "rejected");
export const featured = [
  "1 km² of Indiranagar",
  "Clockwork Observatory",
  "Francis Turbine Explorer",
  "Paris Atlas",
  "Torchlight Depths",
  "Pixel Village",
  "Papertrails",
  "Void Explorer",
  "Painted Valley",
];
export const modelFamilies = ["Claude", "GPT", "Gemini"];

export function family(name: string) {
  return /^codex/i.test(name)
    ? "GPT"
    : modelFamilies.find((prefix) => name.toLowerCase().startsWith(prefix.toLowerCase())) || name;
}

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

export const count = {
  all: worlds.length,
  playable: worlds.filter(isPlayable).length,
  open: worlds.filter((world) => world.is_open_source === true || Boolean(world.repo_url)).length,
  repos: worlds.filter((world) => Boolean(world.repo_url)).length,
  withThumb: worlds.filter((world) => Boolean(world.thumbnail_url)).length,
  withWorkflow: worlds.filter((world) => world.workflow_steps.length > 0).length,
};

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

export function caseHref(world: World) {
  return `/worlds/${world.world_id}`;
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
