import dataset from "@/data/worlds.json";

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

export const modes: Record<string, string> = {
  one_shot: "单次提示",
  iterative_chat: "对话迭代",
  agentic_loop: "智能体循环",
  hybrid_pipeline: "混合流程",
  unknown: "生成方式未披露",
};

export const levels: Record<string, string> = {
  video_only: "仅视频拆解",
  prompt_shared: "公开提示词",
  live_demo: "有试玩入口",
  full_repo: "完整仓库",
};

export const reviews: Record<string, string> = {
  pending: "待复核",
  approved: "已复核",
  rejected: "已拒绝",
};

export const submissionUrl =
  "https://github.com/ZeshenTian/ai-worlds-tracker/issues/new?template=new-world.yml";

export interface World {
  world_id: string;
  title: string;
  summary: string;
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

export const byline = (w: World) =>
  w.author_name || (w.author_handle ? "@" + w.author_handle : "作者未披露");

export const isPlayable = (w: World) => w.demo_health_status === "verified_playable";

export const healthLabels: Record<string, string> = {
  verified_playable: "已验活可试玩",
  login_required: "需登录",
  broken: "试玩不可用",
  no_demo: "未提供试玩",
  unverified: "试玩待验证",
};

export const worlds: World[] = dataset.filter((world) => world.review_status !== "rejected");
export function matchesWorldQuery(world: World, query: string) {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const searchable = [
    world.title,
    world.summary,
    world.author_name,
    world.author_handle,
    themes[world.theme_category],
    ...world.models_used,
    ...world.tech_stack,
    ...world.workflow_steps,
    ...world.skills_or_prompts_used,
    ...world.evidence_quotes,
  ].filter(Boolean).join(" ").toLocaleLowerCase();
  return terms.every((term) => searchable.includes(term));
}

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
  hasDemo: worlds.filter((w) => Boolean(webLink(w.live_demo_url)) && w.demo_health_status !== "broken").length,
  open: worlds.filter((world) => world.is_open_source === true).length,
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

export function bestQuote(world: World): string {
  const candidates = world.evidence_quotes
    .map((q) => q.replace(/\s+/g, " ").trim())
    .filter((q) => q.length >= 24 && !/^(GPT|Claude|Gemini)\b[^.!?,]{0,20}$/i.test(q));
  const picked = candidates[0] || world.summary;
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
