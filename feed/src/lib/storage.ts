import type { Language } from "./types";
export function readIDs(key: string): string[] {
  try {
    const ids: unknown = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(ids)
      ? ids.filter((id): id is string => typeof id === "string")
      : [];
  } catch {
    return [];
  }
}
export function readLang(): Language {
  try {
    return localStorage.getItem("atlas-lang") === "en" ? "en" : "zh";
  } catch {
    return "zh";
  }
}
export function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage is optional in private browsers */
  }
}
export const savedKey = "worldfeed-favorites",
  seenKey = "worldfeed-seen";
