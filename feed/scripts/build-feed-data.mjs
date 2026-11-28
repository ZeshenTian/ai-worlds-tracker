import { execFileSync } from "node:child_process";
import { basename, join } from "node:path";
import { mkdir, copyFile, access, readdir, unlink } from "node:fs/promises";
import {
  publicDir,
  root,
  state,
  feed,
  snapshot,
  web,
  saveJSON,
  readJSON,
} from "./paths.mjs";

const [rows, translations, overrides, probes, mirrors] = await Promise.all([
  readJSON(snapshot),
  readJSON(join(root, "platform/data/worlds-en.json"), {}),
  readJSON(join(feed, "content/english.json"), {}),
  readJSON(join(state, "embed_probe.json"), {}),
  readJSON(join(state, "mirrors.json"), {}),
]);
const thumbnails = join(publicDir, "thumbnails");
await mkdir(thumbnails, { recursive: true });
const used = new Set();
const eastAsian =
  /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;
const en = (value) =>
  typeof value === "string" && !eastAsian.test(value) ? value.trim() : "";
const strings = (values) =>
  Array.isArray(values)
    ? [
        ...new Set(
          values
            .map((x) => (typeof x === "string" ? x.trim() : ""))
            .filter(Boolean),
        ),
      ]
    : [];
const english = (values) => strings(values).map(en).filter(Boolean);
const bareModel =
  /^(?:(?:made|built|created)\s+(?:with|using)\s+)?(?:claude|gpt|gemini|codex|opus|fable|sonnet|astra|neon|marble)(?:[-\s.]*(?:\d+(?:\.\d+)*|opus|sonnet|fable|astra|neon|pro|flash|max|code))*[.!]?$/i;
function family(model) {
  const label = model.trim();
  if (/^(?:(?:openai(?:['’]s)?\s+)?(?:gpt|chatgpt|codex|astra|sol)(?=\b|\d)|\d+(?:\.\d+)?\s+astra\b)/i.test(label)) return "GPT";
  if (/^(?:(?:anthropic(?:['’]s)?|routed)\s+)?(?:claude|opus|fable|haiku|sonnet)(?=\b|\d)/i.test(label)) return "Claude";
  if (/^(?:google(?:['’]s)?\s+)?(?:gemini|neon|argon|hydrogen|carbon|antigravity)(?=\b|\d)/i.test(label)) return "Gemini";
  return "Other";
}
async function thumbnail(w) {
  const mirrorCover = mirrors[w.world_id]?.cover;
  const value = mirrorCover
    ? "/thumbnails/" + mirrorCover
    : w.thumbnail_url || "";
  const custom = join(feed, "content/covers", w.world_id + ".webp");
  let src, name;
  if (/^\/thumbnails\/[\w.-]+\.(webp|jpe?g|png|avif)$/i.test(value)) {
    name = basename(value);
    src = join(root, "platform/public/thumbnails", name);
  } else {
    try {
      await access(custom);
    } catch {
      return null;
    }
    name = w.world_id + ".webp";
    src = custom;
  }
  try {
    await copyFile(src, join(thumbnails, name));
  } catch (err) {
    if (err.code === "ENOENT") return null;
    throw err;
  }
  used.add(name);
  return "/thumbnails/" + name;
}
const stars = await readJSON(join(state, "github_stars.json"), {});
const previousFeed = await readJSON(join(publicDir, "data/feed.json"), null);
const previousItems = new Map(previousFeed?.map((w) => [w.world_id, w]));
const buildDay = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" });
const frontier = rows.filter(w => w.model_era === "frontier" && w.review_status !== "rejected");
// Use the catalog's version cutoffs and disclosure-date rules for each label.
const primaryModels = JSON.parse(execFileSync("python3", ["-m", "src.feed_models"], {
  cwd: root,
  input: JSON.stringify(frontier.map(({models_used, published_at}) => ({models_used, published_at}))),
  encoding: "utf8",
}));
const items = [];
for (const [index, w] of frontier.entries()) {
  if (!/^[a-zA-Z0-9_-]+$/.test(w.world_id)) throw Error("Invalid world ID");
  const m = mirrors[w.world_id];
  if (m) await access(join(publicDir, "mirrors", w.world_id, "index.html"));
  const demo = w.demo_health_status === "broken" ? null : web(w.live_demo_url);
  const probe = demo && probes[w.live_demo_url];
  const embedded =
    probe?.embeddable && w.demo_health_status !== "login_required"
      ? web(probe.final_url || demo)
      : null;
  const tier = m ? "mirror" : embedded ? "embed" : "external";
  if (tier === "external") continue;
  const tweet = w.original_post_url?.match(/\/status\/(\d+)/)?.[1];
  const signals = tweet ? await readJSON(join(root,"data/raw/x/signals",tweet+".json"), {}) : {};
  const repo = w.repo_url?.match(/^https:\/\/github\.com\/([\w.-]+\/[\w.-]+)/i)?.[1]?.replace(/\.git$/i,"").toLowerCase();
  const tr = translations[w.world_id] || {};
  const extra = overrides[w.world_id] || {};
  const author =
    w.author_name || (w.author_handle && "@" + w.author_handle) || "";
  const models = strings(w.models_used);
  const families = [...new Set(models.map(family))];
  const quotes = strings(w.evidence_quotes).filter(
    (q) =>
      !bareModel.test(q) &&
      !models.some((m) => m.toLowerCase() === q.toLowerCase()),
  );
  const summaryEn =
    en(extra.summary) ||
    en(w.summary_en) ||
    en(w.summary) ||
    english(quotes)[0] ||
    "";
  const videoURL = web(w.preview_video_url);
  const previous = previousItems.get(w.world_id);
  const feedAddedOn = previous ? previous.feed_added_on : previousFeed && buildDay;
  items.push({
    world_id: w.world_id,
    x_likes: Number(signals.likes ?? previous?.x_likes) || 0,
    github_stars: stars[repo]?.stars ?? null,
    model_era: w.model_era || "legacy",
    work_type: w.work_type || "interactive_world",
    title: w.title,
    title_en:
      en(extra.title) ||
      en(w.title) ||
      summaryEn.split(/[.!?]\s/)[0] ||
      "Interactive world",
    author,
    author_en:
      en(extra.author) ||
      en(author) ||
      (en(w.author_handle) ? "@" + w.author_handle : ""),
    theme_category: w.theme_category,
    models_used: models,
    models_used_en: english(models),
    primary_model: primaryModels[index],
    model_family: primaryModels[index] ? family(primaryModels[index]) : "Other",
    model_families: families,
    tech_stack: strings(w.tech_stack),
    tech_stack_en: english(extra.tech_stack || w.tech_stack),
    generation_mode: w.generation_mode,
    is_open_source: w.is_open_source === true,
    verified_playable: w.demo_health_status === "verified_playable",
    tier,
    embed_url: m ? "/mirrors/" + w.world_id + "/index.html" : embedded,
    external_demo_url: demo,
    repo_url: web(w.repo_url),
    original_post_url: web(w.original_post_url),
    preview_video_url: videoURL,
    thumbnail_url: await thumbnail(w),
    summary_zh: w.summary || "",
    summary_en: summaryEn,
    workflow_steps_zh: strings(w.workflow_steps),
    workflow_steps_en: english(
      extra.workflow ||
        (w.workflow_steps_en?.length
          ? w.workflow_steps_en
          : tr.wf || w.workflow_steps),
    ),
    skills_zh: strings(w.skills_or_prompts_used),
    skills_en: english(extra.skills || tr.sp || w.skills_or_prompts_used),
    evidence_quotes: quotes,
    published_at: w.published_at || null,
    ...(feedAddedOn && { feed_added_on: feedAddedOn }),
  });
}
const ids = new Set(items.map((w) => w.world_id));
if (ids.size !== items.length) throw Error("Duplicate world IDs in snapshot");
function rank(w) {
  return w.tier === "mirror" ? 0 : w.verified_playable ? 1 : 2;
}
items.sort(
  (a, b) =>
    rank(a) - rank(b) ||
    (b.published_at || "").localeCompare(a.published_at || "") ||
    a.world_id.localeCompare(b.world_id),
);
await saveJSON(join(publicDir, "data/feed.json"), items);
for (const name of await readdir(thumbnails)) {
  if (
    /^world-[\w.-]+\.(?:webp|png|avif|jpg|jpeg)$/i.test(name) &&
    !used.has(name)
  )
    await unlink(join(thumbnails, name));
}
console.log(
  "Feed:",
  items.length,
  "worlds;",
  used.size,
  "local previews.",
  JSON.stringify(
    items.reduce((acc, w) => ((acc[w.tier] = (acc[w.tier] || 0) + 1), acc), {}),
  ),
);
