"use client";
import { useState, useEffect, useMemo } from "react";
import { copy, useLang } from "@/lib/i18n";
import {
  worlds,
  themes,
  themeLabel,
  family,
  localizedWorld,
  byline,
  playable,
  hasLiveDemo,
  caseHref,
  type World,
} from "@/lib/worlds";
import { useFeedBase } from "./atlas-shell";
import { WorldPreview } from "./world-preview";
const ordered = [...worlds].sort(
  (a, b) =>
    (b.published_at || "").localeCompare(a.published_at || "") ||
    a.world_id.localeCompare(b.world_id),
);
const modes = ["all", "playable", "video"] as const;
type Mode = (typeof modes)[number];
const playableCount = ordered.filter(hasLiveDemo).length;
const totals = {
  playable: playableCount,
  video: ordered.length - playableCount,
  all: ordered.length,
};
const formatCount = (n: number) => n.toLocaleString("en-US");
function tally(rows: World[], values: (world: World) => string[]) {
  const counts = new Map<string, number>();
  counts.set("", rows.length);
  for (const world of rows) {
    for (const value of new Set(values(world)))
      counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return counts;
}
export function WorldCatalog() {
  const [lang] = useLang(),
    en = lang === "en",
    base = useFeedBase();
  const [mode, setMode] = useState<Mode>("all");
  const [query, Q] = useState(""),
    [model, M] = useState(""),
    [theme, T] = useState(""),
    [stack, K] = useState(""),
    [page, P] = useState(1);
  function url(n: number, q: string, push = false, nextMode?: Mode) {
    const u = new URL(location.href);
    u.searchParams.delete("archive");
    if (nextMode === "all") u.searchParams.delete("tab");
    else if (nextMode) u.searchParams.set("tab", nextMode);
    if (n > 1) u.searchParams.set("page", String(n));
    else u.searchParams.delete("page");
    if (q) u.searchParams.set("q", q);
    else u.searchParams.delete("q");
    history[push ? "pushState" : "replaceState"](null, "", u);
  }
  useEffect(() => {
    function sync() {
      const s = new URLSearchParams(location.search);
      const value = s.get("tab");
      setMode(value === "video" || value === "playable" ? value : "all");
      M("");
      T("");
      K("");
      P(Math.max(1, Number.parseInt(s.get("page") || "1") || 1));
      Q(s.get("q") || "");
    }
    function search(e: Event) {
      const q = (e as CustomEvent<string>).detail;
      Q(q);
      P(1);
      url(1, q);
    }
    sync();
    window.addEventListener("popstate", sync);
    window.addEventListener("wb:query-set", search);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("wb:query-set", search);
    };
  }, []);
  const localized = useMemo(
    () => ordered.map((w) => localizedWorld(w, lang)),
    [lang],
  );
  const scoped = localized.filter(
    (w) => mode === "all" || hasLiveDemo(w) === (mode === "playable"),
  );
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const matches = scoped.filter(
    (w) =>
      !terms.length ||
      terms.every((term) =>
        [w.title, w.summary, byline(w, lang), ...w.tech_stack, ...w.models_used]
          .join(" ")
          .toLowerCase()
          .includes(term),
      ),
  );
  const matchModel = (w: World) =>
    !model || w.models_used.some((m) => family(m) === model);
  const matchTheme = (w: World) => !theme || w.theme_category === theme;
  const matchStack = (w: World) => !stack || w.tech_stack.includes(stack);
  const filtered = matches.filter(
    (w) => matchModel(w) && matchTheme(w) && matchStack(w),
  );
  // Lead the mixed catalog with one desktop row of directly playable worlds.
  const lead =
    mode === "all"
      ? filtered
          .filter((w) => hasLiveDemo(w) && playable.has(w.world_id))
          .slice(0, 4)
      : [];
  const rows = lead.length
    ? [...lead, ...filtered.filter((w) => !lead.includes(w))]
    : filtered;
  const modelCounts = tally(
    matches.filter((w) => matchTheme(w) && matchStack(w)),
    (w) => w.models_used.map(family),
  );
  const themeCounts = tally(
    matches.filter((w) => matchModel(w) && matchStack(w)),
    (w) => [w.theme_category],
  );
  const stackCounts = tally(
    matches.filter((w) => matchModel(w) && matchTheme(w)),
    (w) => w.tech_stack,
  );
  const stacks = [...stackCounts.keys()]
    .filter(Boolean)
    .sort(
      (a, b) => stackCounts.get(b)! - stackCounts.get(a)! || a.localeCompare(b),
    )
    .slice(0, 9);
  if (stack && !stacks.includes(stack)) stacks.push(stack);
  const pages = Math.max(1, Math.ceil(rows.length / 24)),
    cur = Math.min(page, pages);
  function turn(n: number) {
    P(n);
    url(n, query, true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function group(
    label: string,
    opts: string[],
    selected: string,
    set: (s: string) => void,
    name: (k: string) => string,
    counts: Map<string, number>,
  ) {
    return (
      <div className="group" aria-label={label}>
        <b>{label}</b>
        {opts.map((k) => (
          <button
            key={k}
            disabled={!!k && !counts.get(k) && k !== selected}
            aria-pressed={k === selected}
            onClick={() => {
              set(k);
              P(1);
              url(1, query);
            }}
          >
            {name(k)}{" "}
            <span className="facet-count">
              {formatCount(counts.get(k) ?? 0)}
            </span>
          </button>
        ))}
      </div>
    );
  }
  return (
    <section className="catalog">
      <h1>{en ? "Explore worlds" : "探索世界"}</h1>
      <section className="toolbar">
        <div
          className="group"
          role="group"
          aria-label={en ? "Content type" : "内容类型"}
        >
          <b>{en ? "Type" : "类型"}</b>
          {modes.map((value) => (
            <button
              key={value}
              data-tab={value}
              aria-pressed={value === mode}
              onClick={() => {
                if (value === mode) return;
                setMode(value);
                M("");
                T("");
                K("");
                P(1);
                url(1, query, true, value);
              }}
            >
              {copy[lang].modes[value]}{" "}
              <span className="facet-count">{formatCount(totals[value])}</span>
            </button>
          ))}
        </div>
        {group(
          en ? "Model" : "模型",
          ["", "Claude", "GPT", "Gemini", "Other"],
          model,
          M,
          (k) => (k === "Other" && !en ? "其他" : k || (en ? "All" : "全部")),
          modelCounts,
        )}
        {group(
          en ? "Theme" : "主题",
          ["", ...Object.keys(themes).filter((k) => k !== "other")],
          theme,
          T,
          (k) => (k ? themeLabel(k, lang) : en ? "All" : "全部"),
          themeCounts,
        )}
        {group(
          en ? "Stack" : "技术栈",
          ["", ...stacks],
          stack,
          K,
          (k) => k || (en ? "All" : "全部"),
          stackCounts,
        )}
      </section>
      <div className="results">
        <strong>
          {rows.length.toLocaleString("en-US")} {en ? "worlds" : "个世界"}
        </strong>
        {(model || theme || stack || query) && (
          <button
            onClick={() => {
              M("");
              T("");
              K("");
              Q("");
              P(1);
              url(1, "");
              window.dispatchEvent(
                new CustomEvent("wb:query-sync", { detail: "" }),
              );
            }}
          >
            {en ? "Reset" : "重置"}
          </button>
        )}
      </div>
      <div className="world-grid">
        {rows.slice((cur - 1) * 24, cur * 24).map((w) => {
          const live = hasLiveDemo(w);
          const play = live && playable.has(w.world_id);
          const href = caseHref(w, base);
          const action = play
            ? en
              ? "Play"
              : "试玩"
            : live
              ? en
                ? "Visit ↗"
                : "访问 ↗"
              : en
                ? "Post"
                : "原帖";
          return (
            <article key={w.world_id} data-id={w.world_id}>
              <a
                className="preview"
                href={href}
                target="_blank"
                rel="noopener noreferrer"
              >
                <WorldPreview world={w} lang={lang} />
              </a>
              <div className="cardbody">
                <small>
                  {w.models_used.slice(0, 2).join(" · ")} ·{" "}
                  {w.published_at?.slice(0, 10)}
                </small>
                <h2>
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {w.title}
                  </a>
                </h2>
                <p>{byline(w, lang)}</p>
                <div className="actions">
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {action}
                  </a>
                  {play && w.live_demo_url && (
                    <a
                      href={w.live_demo_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {en ? "Official ↗" : "官方入口 ↗"}
                    </a>
                  )}
                  {live && (
                    <a
                      href={w.original_post_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {en ? "Post" : "原帖"}
                    </a>
                  )}
                  {w.repo_url && (
                    <a
                      href={w.repo_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {en ? "Code" : "源码"}
                    </a>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>
      <div className="pagination">
        <button disabled={cur === 1} onClick={() => turn(cur - 1)}>
          ← {en ? "Prev" : "上一页"}
        </button>
        {Array.from({ length: pages }, (_, i) => i + 1)
          .filter((n) => n === 1 || n === pages || Math.abs(n - cur) <= 1)
          .map((n, i, arr) => (
            <span key={n}>
              {i > 0 && n - arr[i - 1] > 1 ? " … " : ""}
              <button
                aria-current={n === cur ? "page" : undefined}
                onClick={() => turn(n)}
              >
                {n}
              </button>
            </span>
          ))}
        <button disabled={cur === pages} onClick={() => turn(cur + 1)}>
          {en ? "Next" : "下一页"} →
        </button>
        <small>
          {cur} / {pages} · {rows.length}
        </small>
      </div>
    </section>
  );
}
