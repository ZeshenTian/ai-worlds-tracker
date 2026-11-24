import dataset from "@/data/worlds.json";

export const themes: Record<string, string> = {
  nature_ecosystem: "自然生态", city_diorama: "城市微缩", fantasy_rpg: "奇幻世界",
  sci_fi: "科幻空间", physics_sim: "物理模拟", voxel_sandbox: "体素沙盒",
  historical: "历史重建", other: "其他",
};

export const modes: Record<string, string> = {
  one_shot: "单次提示", iterative_chat: "对话迭代", agentic_loop: "智能体循环",
  hybrid_pipeline: "混合流程", unknown: "生成方式未披露",
};

export const levels: Record<string, string> = {
  video_only: "仅视频拆解", prompt_shared: "公开提示词", live_demo: "有试玩入口", full_repo: "完整仓库",
};

export const reviews: Record<string, string> = {
  pending: "待复核", approved: "已复核", rejected: "已拒绝",
};

export const submissionUrl = "https://github.com/ZeshenTian/ai-worlds-tracker/issues/new?template=new-world.yml";

export interface World {
  world_id: string; title: string; summary: string; theme_category: string;
  models_used: string[]; tech_stack: string[]; generation_mode: string; reproducibility_level: string;
  is_open_source: boolean | null; repo_url: string | null; live_demo_url: string | null;
  demo_health_status: string; thumbnail_url: string | null; original_post_url: string;
  author_handle: string | null; author_name: string | null; source_kind: string;
  first_seen_at: string | null; published_at: string | null; review_status: string;
  reported_cost_usd: number | null; reported_time_minutes: number | null;
  workflow_steps: string[]; skills_or_prompts_used: string[]; evidence_quotes: string[]; evidence_source_urls: string[]; related_post_urls: string[];
}
export const byline = (w: World) => w.author_name || (w.author_handle ? "@" + w.author_handle : "作者未披露");
export const isPlayable = (w: World) => w.demo_health_status === "verified_playable";
export const healthLabels: Record<string,string> = {
  verified_playable: "已验证可试玩", login_required: "需登录", broken: "试玩不可用",
  no_demo: "未提供试玩", unverified: "试玩待验证",
};

export const worlds: World[] = dataset.filter(world => world.review_status !== "rejected");
export const featured = ["Papertrails", "Void Explorer", "Painted Valley"];
export const modelFamilies = ["Claude", "GPT", "Gemini"];

export function family(name: string) {
  return /^codex/i.test(name) ? "GPT" : modelFamilies.find(prefix => name.toLowerCase().startsWith(prefix.toLowerCase())) || name;
}

export function values(key: "tech_stack" | "models_used") {
  return [...new Set(worlds.flatMap(world => world[key]))].sort();
}

export const count = {
  all: worlds.length,
  playable: worlds.filter(isPlayable).length,
  open: worlds.filter(world => world.is_open_source === true).length,
  repos: worlds.filter(world => world.repo_url).length,
};

export function monthOf(world: World) {
  return world.published_at?.slice(0, 7) ?? "";
}

export function webLink(value: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (["http:", "https:"].includes(url.protocol) && !url.username && !url.password) return url.href;
  } catch { /* incomplete source URL */ }
  return undefined;
}

export function caseHref(world: World) {
  return `/worlds/${world.world_id}`;
}
