import { readFile, writeFile, mkdir, rename } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const feed = fileURLToPath(new URL("../", import.meta.url));
export const root = resolve(feed, "..");
export const snapshot = resolve(root, "data/exports/ai_worlds.json");
export const state = resolve(root, "data/state");
export const publicDir = resolve(feed, "public");
export async function readJSON(path, fallback) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT" && fallback !== undefined) return fallback;
    throw error;
  }
}
export async function saveJSON(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const tmp = path + "." + process.pid + ".tmp";
  await writeFile(tmp, JSON.stringify(value, null, 2) + "\n");
  await rename(tmp, path);
}
export function web(value) {
  try {
    const u = new URL(value);
    if (
      ["http:", "https:"].includes(u.protocol) &&
      !u.username &&
      !u.password &&
      !/^(?:localhost|127\.|10\.|192\.168\.|169\.254\.|0\.|\[)/i.test(
        u.hostname,
      )
    )
      return u.href;
  } catch {
    /* empty or invalid optional URL */
  }
  return null;
}
