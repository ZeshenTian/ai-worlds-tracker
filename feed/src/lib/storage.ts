import type { Language } from "./types";
export const likesKey = "worldfeed-liked-ids";
export function readLikes(): string[] {
  try {
    const ids: unknown = JSON.parse(localStorage.getItem(likesKey) || "[]");
    return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}
export function readLang(): Language {
  try {
    return localStorage.getItem("atlas-lang") === "zh" ? "zh" : "en";
  } catch {
    return "en";
  }
}
export function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage is optional in private browsers */
  }
}
