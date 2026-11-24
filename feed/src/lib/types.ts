export type PlayTier = "mirror" | "embed" | "external";
export type Language = "zh" | "en";
export type ModelFamily = "Claude" | "GPT" | "Gemini" | "Other";
export type Tab =
  | "for-you"
  | "playable"
  | "opensource"
  | "Claude"
  | "GPT"
  | "Gemini"
  | "favorites";
export type PlayState = "browse" | "loading" | "playing";
export interface FeedItem {
  world_id: string;
  title: string;
  title_en: string;
  author: string;
  author_en: string;
  theme_category: string;
  models_used: string[];
  models_used_en: string[];
  model_family: ModelFamily;
  model_families: ModelFamily[];
  tech_stack: string[];
  tech_stack_en: string[];
  generation_mode: string;
  is_open_source: boolean;
  verified_playable: boolean;
  tier: PlayTier;
  embed_url: string | null;
  external_demo_url: string | null;
  repo_url: string | null;
  original_post_url: string | null;
  preview_video_url: string | null;
  thumbnail_url: string | null;
  summary_zh: string;
  summary_en: string;
  workflow_steps_zh: string[];
  workflow_steps_en: string[];
  skills_zh: string[];
  skills_en: string[];
  evidence_quotes: string[];
  published_at: string | null;
}
export const tabs: Tab[] = [
  "for-you",
  "playable",
  "opensource",
  "Claude",
  "GPT",
  "Gemini",
  "favorites",
];
export function inChannel(item: FeedItem, tab: Tab, favorites: string[]) {
  switch (tab) {
    case "for-you":
      return Boolean(
        item.tier !== "external" ||
        item.thumbnail_url ||
        item.preview_video_url,
      );
    case "playable":
      return item.tier !== "external";
    case "opensource":
      return item.is_open_source;
    case "favorites":
      return favorites.includes(item.world_id);
    default:
      return item.model_families.includes(tab);
  }
}
export function original(item: FeedItem) {
  return item.external_demo_url || item.original_post_url || item.repo_url;
}
export const titleOf = (item: FeedItem, lang: Language) =>
  lang === "en" ? item.title_en : item.title;
