"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  CirclePlay,
  CodeXml,
  ExternalLink,
  Eye,
  Globe2,
  Grid2X2,
  List,
  PanelRightClose,
  Search,
  SlidersHorizontal,
  Table2,
  X,
} from "lucide-react";
import { copy, useLang, type Lang } from "@/lib/i18n";
import {
  bestQuote,
  byline,
  caseHref,
  cleanQuotes,
  count,
  family,
  familyTone,
  featured,
  healthLabel,
  isPlayable,
  levelLabel,
  modeLabel,
  modelFamilies,
  modes,
  monthOf,
  skillsFor,
  themeLabel,
  themes,
  themesEn,
  values,
  webLink,
  workflowStepsFor,
  worlds,
  type World,
} from "@/lib/worlds";
import { UpdateTime } from "./update-time";
import { WorldPreview } from "./world-preview";

const defaults = {
  q: "",
  model: "",
  theme: "",
  tech: "",
  mode: "",
  level: "",
  license: "",
  month: "",
  play: "",
  cost: "",
  thumb: "",
  wf: "",
  sort: "",
};
type Filters = typeof defaults;
type ViewMode = "grid" | "list" | "table";

const initialAmount = 18;
const months = [...new Set(worlds.map(monthOf).filter(Boolean))].sort().reverse();
const allTechStacks = values("tech_stack")
  .map((tech) => ({
    key: tech,
    count: worlds.filter((w) => w.tech_stack.includes(tech)).length,
  }))
  .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key, "en"));

function fromLocation(): Filters {
  const url = new URLSearchParams(window.location.search);
  const result = { ...defaults };
  for (const key of Object.keys(defaults) as (keyof Filters)[]) {
    result[key] = url.get(key) || "";
  }
  return result;
}

function syncUrl(next: Filters) {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(next)) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  window.history.replaceState(window.history.state, "", url);
}

function matches(world: World, filters: Filters, omit?: keyof Filters): boolean {
  const f = omit ? { ...filters, [omit]: "" } : filters;
  const terms = f.q.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length) {
    const searchable = [
      world.title,
      world.summary, world.summary_en, ...(world.workflow_steps_en || []),
      world.author_handle,
      world.author_name,
      ...world.workflow_steps,
      ...world.skills_or_prompts_used,
      ...world.evidence_quotes,
      themes[world.theme_category],
      themesEn[world.theme_category],
      ...world.models_used,
      ...world.tech_stack,
    ]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase();
    if (!terms.every((word) => searchable.includes(word))) return false;
  }
  if (f.model && !world.models_used.some((m) => family(m) === f.model || m === f.model)) return false;
  if (f.theme && world.theme_category !== f.theme) return false;
  if (f.tech && !world.tech_stack.includes(f.tech)) return false;
  if (f.mode && world.generation_mode !== f.mode) return false;
  if (f.level) {
    if (f.level === "playable" && !isPlayable(world)) return false;
    else if (f.level === "source" && !world.repo_url) return false;
    else if (f.level !== "playable" && f.level !== "source" && world.reproducibility_level !== f.level)
      return false;
  }
  if (f.month && monthOf(world) !== f.month) return false;
  if (f.license) {
    if (f.license === "open" && !(world.is_open_source === true || Boolean(world.repo_url))) return false;
    if (f.license === "closed" && world.is_open_source !== false) return false;
    if (f.license === "unknown" && world.is_open_source !== null) return false;
  }
  if (f.cost && world.reported_cost_usd === null) return false;
  if (f.play && !isPlayable(world)) return false;
  if (f.thumb && !world.thumbnail_url) return false;
  if (f.wf && world.workflow_steps.length === 0) return false;
  return true;
}

function compare(a: World, b: World, sort: string) {
  if (sort === "ingested")
    return (b.first_seen_at || "").localeCompare(a.first_seen_at || "") || a.title.localeCompare(b.title);
  if (sort === "title") return a.title.localeCompare(b.title, "zh-CN");
  if (sort !== "recent") {
    const playableOrder = Number(isPlayable(b)) - Number(isPlayable(a));
    if (playableOrder) return playableOrder;
    const screenshotOrder = Number(Boolean(b.thumbnail_url)) - Number(Boolean(a.thumbnail_url));
    if (screenshotOrder) return screenshotOrder;
    const score = (world: World) => {
      const index = featured.indexOf(world.title);
      return index === -1 ? featured.length : index;
    };
    const difference = score(a) - score(b);
    if (difference) return difference;
  }
  return (b.published_at || "").localeCompare(a.published_at || "");
}

function statusPillTone(status: string) {
  if (status === "verified_playable") return "pill-ok";
  if (status === "login_required" || status === "broken") return "pill-warn";
  return "pill-neutral";
}

function cardLead(world: World, lang: Lang) {
  if (lang === "zh") return world.summary;
  return world.summary_en || bestQuote(world);
}

function WorldCard({
  world,
  selected,
  lang,
  onInspect,
}: {
  world: World;
  selected: boolean;
  lang: Lang;
  onInspect: (world: World) => void;
}) {
  const t = copy[lang];
  const demo = webLink(world.live_demo_url);
  const repo = webLink(world.repo_url);
  const original = webLink(world.original_post_url);
  const playable = isPlayable(world) && Boolean(demo);
  const hasDemo = Boolean(demo) && world.demo_health_status !== "broken";

  return (
    <article
      className={selected ? "world-card is-selected" : "world-card"}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("a, button")) return;
        onInspect(world);
      }}
    >
      <button
        type="button"
        className="card-cover-btn"
        onClick={() => onInspect(world)}
        aria-label={world.title}
      >
        <WorldPreview world={world} lang={lang} />
        {world.thumbnail_url && (
          <>
            {playable ? (
              <span className="cover-badge badge-ok">● {t.playable}</span>
            ) : world.is_open_source === true || repo ? (
              <span className="cover-badge badge-blue">{t.openSource}</span>
            ) : null}
            <span className="cover-theme">{themeLabel(world.theme_category, lang)}</span>
          </>
        )}
      </button>

      <div className="card-body">
        <div className="card-head">
          <h3>
            <a href={caseHref(world)}>{world.title}</a>
          </h3>
          <span className="card-author">{byline(world, lang)}</span>
        </div>
        <p className="card-summary">{cardLead(world, lang)}</p>
        <div className="card-foot">
          <div className="tag-list">
            {world.models_used.slice(0, 1).map((m) => (
              <span key={m} className={`tag tag-model tone-${familyTone(m)}`}>
                {m}
              </span>
            ))}
            {world.tech_stack[0] && <span className="tag">{world.tech_stack[0]}</span>}
          </div>
          <div className="card-actions">
            {playable && demo ? (
              <a
                className="act-link act-play"
                href={demo}
                target="_blank"
                rel="noopener noreferrer"
              >
                <CirclePlay size={14} /> {t.play}
              </a>
            ) : repo ? (
              <a
                className="act-link act-code"
                href={repo}
                target="_blank"
                rel="noopener noreferrer"
              >
                <CodeXml size={14} /> {t.sourceCode}
              </a>
            ) : hasDemo && demo ? (
              <a
                className="act-link act-code"
                href={demo}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t.visit} <ArrowUpRight size={13} />
              </a>
            ) : null}
            {repo && playable && (
              <a
                className="act-link act-code"
                href={repo}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t.sourceCode}
              </a>
            )}
            {original && (
              <a
                className="act-link act-muted"
                href={original}
                target="_blank"
                rel="noopener noreferrer"
              >
                {world.source_kind === "x_post" ? t.originalPost : t.originalPage}
              </a>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

function QuickInspector({
  world,
  mode,
  lang,
  onClose,
}: {
  world: World | null;
  mode: "auto" | "open" | "closed";
  lang: Lang;
  onClose: () => void;
}) {
  if (mode === "closed" || !world) return null;
  const t = copy[lang];
  const demo = webLink(world.live_demo_url);
  const repo = webLink(world.repo_url);
  const original = webLink(world.original_post_url);
  const playable = isPlayable(world) && Boolean(demo);
  const hasDemo = Boolean(demo) && world.demo_health_status !== "broken";
  const date = world.published_at?.slice(0, 10);
  const quotes = cleanQuotes(world);
  const steps = workflowStepsFor(world, lang);
  const skills = skillsFor(world, lang);

  const kvItems: { label: string; value: string }[] = [
    { label: t.model, value: world.models_used.join(" · ") || "—" },
    ...(world.generation_mode !== "unknown"
      ? [{ label: t.mode, value: modeLabel(world.generation_mode, lang) }]
      : []),
    ...(world.tech_stack.length
      ? [{ label: t.techStack, value: world.tech_stack.slice(0, 4).join(" · ") }]
      : []),
    ...(world.reported_time_minutes !== null
      ? [{ label: t.timeLabel, value: t.minutes(world.reported_time_minutes) }]
      : []),
    ...(world.reported_cost_usd !== null
      ? [{ label: t.costLabel, value: `US$ ${world.reported_cost_usd}` }]
      : []),
  ];

  return (
    <>
      <div
        className={mode === "auto" ? "wb-inspector-scrim is-auto" : "wb-inspector-scrim"}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={mode === "auto" ? "wb-inspector is-auto" : "wb-inspector"}
        aria-label={world.title}
      >
        <div className="insp-head">
          <span className="insp-label">{t.inspectorTitle}</span>
          <div className="insp-head-actions">
            <a href={caseHref(world)} className="insp-full-link">
              {t.fullPage} <ArrowUpRight size={13} />
            </a>
            <button
              type="button"
              className="icon-btn"
              onClick={onClose}
              aria-label={t.closeInspector}
              title={t.closeInspector}
            >
              <PanelRightClose size={16} />
            </button>
          </div>
        </div>

        <div className="insp-body scroller">
          <div className="insp-media">
            <WorldPreview world={world} variant="detail" lang={lang} />
          </div>

          <div className="insp-header">
            <div className="tag-list">
              {world.demo_health_status === "verified_playable" && (
                <span className="pill-ok">● {t.playable}</span>
              )}
              <span className="pill-neutral">{themeLabel(world.theme_category, lang)}</span>
              {(world.is_open_source === true || repo) && (
                <span className="pill-blue">{t.openSource}</span>
              )}
            </div>
            <h2>
              <a href={caseHref(world)}>{world.title}</a>
            </h2>
            <p className="insp-byline">
              {byline(world, lang)}
              {date && (
                <>
                  {" · "}
                  <time dateTime={date}>{date}</time>
                </>
              )}
            </p>
            <p className="insp-summary">{cardLead(world, lang)}</p>
          </div>

          <div className="insp-cta">
            {hasDemo && demo && (
              <a
                className={playable ? "button button-primary" : "button button-subtle"}
                href={demo}
                target="_blank"
                rel="noopener noreferrer"
              >
                <CirclePlay size={15} />
                {playable ? t.openDemo : t.visitDemo}
                <ArrowUpRight size={14} />
              </a>
            )}
            {repo && (
              <a
                className="button button-subtle"
                href={repo}
                target="_blank"
                rel="noopener noreferrer"
              >
                <CodeXml size={15} /> {t.sourceCode}
              </a>
            )}
            {original && (
              <a
                className="button button-ghost"
                href={original}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Globe2 size={15} /> {world.source_kind === "primary_page" ? t.originalPage : t.originalPost}
              </a>
            )}
          </div>

          {kvItems.length > 0 && (
            <div className="kv-grid">
              {kvItems.slice(0, 4).map((item) => (
                <div className="kv" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          )}

          {steps.length > 0 && (
            <section className="insp-card">
              <div className="insp-card-head">
                <h3>{t.workflow}</h3>
                <span>{t.workflowSteps(steps.length)}</span>
              </div>
              <ol className="insp-steps">
                {steps.map((step, i) => (
                  <li key={step}>
                    <span className="step-badge">{i + 1}</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
              {skills.length > 0 && (
                <div className="insp-subblock">
                  <span className="insp-sublabel">{t.toolsAndPrompts}</span>
                  <div className="tag-list">
                    {skills.map((skill) => (
                      <span className="tag" key={skill}>
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {quotes.length > 0 && (
            <section className="insp-card">
              <div className="insp-card-head">
                <h3>{t.evidence}</h3>
                {original && (
                  <a href={original} target="_blank" rel="noopener noreferrer" className="text-link">
                    {t.viewSource} <ExternalLink size={12} />
                  </a>
                )}
              </div>
              <div className="insp-quotes">
                {quotes.slice(0, 3).map((q) => (
                  <blockquote key={q}>{q}</blockquote>
                ))}
              </div>
            </section>
          )}
        </div>
      </aside>
    </>
  );
}

export function WorldCatalog({ lastUpdatedAt }: { lastUpdatedAt: string }) {
  const [lang] = useLang();
  const t = copy[lang];
  const [filters, setFilters] = useState<Filters>(defaults);
  const [view, setView] = useState<ViewMode>("grid");
  const [limit, setLimit] = useState(initialAmount);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inspectorMode, setInspectorMode] = useState<"auto" | "open" | "closed">("auto");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    document.title = lang === "en" ? "World Atlas" : "生成世界图鉴";
  }, [lang]);

  useEffect(() => {
    const restore = () => {
      const next = fromLocation();
      setFilters(next);
      setLimit(initialAmount);
      window.dispatchEvent(new CustomEvent("wb:query-sync", { detail: next.q }));
    };
    restore();

    const onQuerySet = (event: Event) => {
      const nextQ = (event as CustomEvent<string>).detail ?? "";
      setFilters((prev) => {
        const next = { ...prev, q: nextQ };
        syncUrl(next);
        return next;
      });
      setLimit(initialAmount);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSidebarOpen(false);
        if (!window.matchMedia("(min-width: 1260px)").matches) {
          setInspectorMode("closed");
        }
      }
    };

    window.addEventListener("popstate", restore);
    window.addEventListener("wb:query-set", onQuerySet);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("popstate", restore);
      window.removeEventListener("wb:query-set", onQuerySet);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  function update(next: Filters) {
    setFilters(next);
    setLimit(initialAmount);
    syncUrl(next);
    window.dispatchEvent(new CustomEvent("wb:query-sync", { detail: next.q }));
  }

  const setField = (key: keyof Filters, value: string) =>
    update({ ...filters, [key]: filters[key] === value ? "" : value });
  const replaceField = (key: keyof Filters, value: string) =>
    update({ ...filters, [key]: value });

  const results = useMemo(
    () => worlds.filter((w) => matches(w, filters)).sort((a, b) => compare(a, b, filters.sort)),
    [filters]
  );

  const facetCounts = useMemo(() => {
    const modelBase = worlds.filter((w) => matches(w, filters, "model"));
    const themeBase = worlds.filter((w) => matches(w, filters, "theme"));
    const modeBase = worlds.filter((w) => matches(w, filters, "mode"));
    const techBase = worlds.filter((w) => matches(w, filters, "tech"));

    return {
      allModels: modelBase.length,
      models: Object.fromEntries(
        modelFamilies.map((fam) => [
          fam,
          modelBase.filter((w) => w.models_used.some((m) => family(m) === fam)).length,
        ])
      ),
      themes: Object.fromEntries(
        Object.keys(themes).map((k) => [k, themeBase.filter((w) => w.theme_category === k).length])
      ),
      modes: Object.fromEntries(
        Object.keys(modes).map((k) => [k, modeBase.filter((w) => w.generation_mode === k).length])
      ),
      tech: Object.fromEntries(
        allTechStacks.map((item) => [item.key, techBase.filter((w) => w.tech_stack.includes(item.key)).length])
      ),
    };
  }, [filters]);

  const activeWorld = useMemo(() => {
    if (!results.length) return null;
    if (selectedId) {
      const found = results.find((w) => w.world_id === selectedId);
      if (found) return found;
    }
    return results[0];
  }, [results, selectedId]);

  const activeChips = useMemo(() => {
    const chips: { key: keyof Filters; label: string }[] = [];
    if (filters.q.trim()) chips.push({ key: "q", label: t.chipKeyword(filters.q.trim()) });
    if (filters.model) chips.push({ key: "model", label: filters.model });
    if (filters.theme) chips.push({ key: "theme", label: themeLabel(filters.theme, lang) });
    if (filters.tech) chips.push({ key: "tech", label: filters.tech });
    if (filters.mode) chips.push({ key: "mode", label: modeLabel(filters.mode, lang) });
    if (filters.play) chips.push({ key: "play", label: t.playable });
    if (filters.license === "open") chips.push({ key: "license", label: t.openSource });
    if (filters.level) {
      const label =
        filters.level === "playable"
          ? t.playable
          : filters.level === "source"
            ? t.openSource
            : levelLabel(filters.level, lang);
      chips.push({ key: "level", label });
    }
    if (filters.thumb) chips.push({ key: "thumb", label: t.withPreview });
    if (filters.wf) chips.push({ key: "wf", label: t.hasWorkflow });
    if (filters.month) chips.push({ key: "month", label: filters.month });
    return chips;
  }, [filters, lang, t]);

  const hasFilters = activeChips.length > 0;
  const visible = results.slice(0, limit);
  const inspectorActive = inspectorMode !== "closed" && Boolean(activeWorld);

  function handleInspect(world: World) {
    setSelectedId(world.world_id);
    setInspectorMode("open");
  }

  return (
    <div
      id="catalog"
      className={
        inspectorMode === "open" && activeWorld
          ? "wb-shell has-inspector"
          : inspectorMode === "auto" && activeWorld
            ? "wb-shell has-inspector-auto"
            : "wb-shell"
      }
    >
      {sidebarOpen && (
        <div
          className="wb-sidebar-scrim"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Left Faceted Sidebar */}
      <aside
        className={sidebarOpen ? "wb-sidebar is-open scroller" : "wb-sidebar scroller"}
        aria-label={t.filter}
      >
        <div className="wb-sidebar-mobile-head">
          <strong>{t.filter}</strong>
          <button
            type="button"
            className="icon-btn"
            aria-label={t.filterClose}
            onClick={() => setSidebarOpen(false)}
          >
            <X size={16} />
          </button>
        </div>

        <div className="facet-group">
          <div className="facet-title">{t.facetModels}</div>
          <button
            type="button"
            className={!filters.model ? "facet-item active" : "facet-item"}
            onClick={() => replaceField("model", "")}
          >
            <span className="facet-left">
              <span className="dot dot-all" aria-hidden="true" />
              {t.allModels}
            </span>
            <span className="facet-count">{facetCounts.allModels}</span>
          </button>
          {modelFamilies.map((fam) => (
            <button
              key={fam}
              type="button"
              className={filters.model === fam ? "facet-item active" : "facet-item"}
              onClick={() => setField("model", fam)}
            >
              <span className="facet-left">
                <span className={`dot dot-${familyTone(fam)}`} aria-hidden="true" />
                {fam}
              </span>
              <span className="facet-count">{facetCounts.models[fam] ?? 0}</span>
            </button>
          ))}
        </div>

        <div className="facet-group">
          <div className="facet-title">{t.facetStatus}</div>
          <button
            type="button"
            className={filters.play ? "facet-item active" : "facet-item"}
            onClick={() => setField("play", "1")}
          >
            <span className="facet-left">
              <span className="dot dot-ok" aria-hidden="true" />
              {t.playable}
            </span>
            <span className="facet-count count-ok">{count.playable}</span>
          </button>
          <button
            type="button"
            className={filters.license === "open" ? "facet-item active" : "facet-item"}
            onClick={() => setField("license", "open")}
          >
            <span className="facet-left">{t.openSource}</span>
            <span className="facet-count count-blue">{count.open}</span>
          </button>
          <button
            type="button"
            className={filters.wf ? "facet-item active" : "facet-item"}
            onClick={() => setField("wf", "1")}
          >
            <span className="facet-left">{t.hasWorkflow}</span>
            <span className="facet-count">{count.withWorkflow}</span>
          </button>
        </div>

        <div className="facet-group">
          <div className="facet-title">{t.facetThemes}</div>
          {Object.keys(themes).map((key) => (
            <button
              key={key}
              type="button"
              className={filters.theme === key ? "facet-item active" : "facet-item"}
              onClick={() => setField("theme", key)}
            >
              <span className="facet-left">{themeLabel(key, lang)}</span>
              <span className="facet-count">{facetCounts.themes[key] ?? 0}</span>
            </button>
          ))}
        </div>

        <div className="facet-group">
          <div className="facet-title">{t.facetModes}</div>
          {(["hybrid_pipeline", "iterative_chat", "one_shot", "agentic_loop"] as const).map((key) => (
            <button
              key={key}
              type="button"
              className={filters.mode === key ? "facet-item active" : "facet-item"}
              onClick={() => setField("mode", key)}
            >
              <span className="facet-left">{modeLabel(key, lang)}</span>
              <span className="facet-count">{facetCounts.modes[key] ?? 0}</span>
            </button>
          ))}
        </div>

        <details className="facet-disclosure" open={Boolean(filters.tech || filters.month)}>
          <summary>{t.facetMore}</summary>
          <div className="facet-disclosure-body">
            <div className="facet-sublabel">{t.techStack}</div>
            <div className="facet-chip-wrap">
              {allTechStacks.slice(0, 10).map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={filters.tech === item.key ? "mini-facet active" : "mini-facet"}
                  onClick={() => setField("tech", item.key)}
                >
                  {item.key} <span>{facetCounts.tech[item.key] ?? 0}</span>
                </button>
              ))}
            </div>

            <div className="facet-sublabel">{t.publishMonth}</div>
            <div className="facet-chip-wrap">
              {months.map((m) => (
                <button
                  key={m}
                  type="button"
                  className={filters.month === m ? "mini-facet active" : "mini-facet"}
                  onClick={() => setField("month", m)}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
        </details>

        <div className="wb-sidebar-foot">
          <span className="dot dot-ok" aria-hidden="true" />
          <span>
            {t.updatedPrefix} <UpdateTime iso={lastUpdatedAt} />
          </span>
        </div>
      </aside>

      {/* Center Catalog Workspace */}
      <section className="wb-main scroller" aria-labelledby="catalog-heading">
        <h1 id="catalog-heading" className="sr-only">
          {t.brand}
        </h1>

        <div className="wb-kpi-row">
          <div className="wb-kpi-chips">
            <button
              type="button"
              className="button button-subtle wb-mobile-filter-btn"
              onClick={() => setSidebarOpen(true)}
              aria-expanded={sidebarOpen}
            >
              <SlidersHorizontal size={14} /> {t.filter}
              {hasFilters && <span className="filter-badge">{activeChips.length}</span>}
            </button>

            <button
              type="button"
              className={!hasFilters ? "kpi-chip active" : "kpi-chip"}
              onClick={() => update({ ...defaults, sort: filters.sort })}
            >
              {t.all} <strong>{count.all}</strong>
            </button>
            <button
              type="button"
              className={filters.play ? "kpi-chip ok active-ring" : "kpi-chip ok"}
              onClick={() => setField("play", "1")}
            >
              ● {t.playable} <strong>{count.playable}</strong>
            </button>
            <button
              type="button"
              className={filters.license === "open" ? "kpi-chip blue active-ring" : "kpi-chip blue"}
              onClick={() => setField("license", "open")}
            >
              {t.openSource} <strong>{count.open}</strong>
            </button>
            <button
              type="button"
              className={filters.thumb ? "kpi-chip active" : "kpi-chip"}
              onClick={() => setField("thumb", "1")}
            >
              {t.withPreview} <strong>{count.withThumb}</strong>
            </button>
          </div>

          <div className="wb-controls">
            <label className="sort-wrap">
              <span className="sr-only">{t.sortFeatured}</span>
              <select
                aria-label={t.sortFeatured}
                value={filters.sort}
                onChange={(e) => replaceField("sort", e.target.value)}
              >
                <option value="">{t.sortFeatured}</option>
                <option value="recent">{t.sortRecent}</option>
                <option value="ingested">{t.sortIngested}</option>
                <option value="title">{t.sortTitle}</option>
              </select>
            </label>

            <div className="view-switch" role="group" aria-label="View">
              <button
                type="button"
                aria-pressed={view === "grid"}
                onClick={() => setView("grid")}
                title={t.viewGrid}
              >
                <Grid2X2 size={14} /> <span>{t.viewGrid}</span>
              </button>
              <button
                type="button"
                aria-pressed={view === "list"}
                onClick={() => setView("list")}
                title={t.viewList}
              >
                <List size={14} /> <span>{t.viewList}</span>
              </button>
              <button
                type="button"
                aria-pressed={view === "table"}
                onClick={() => setView("table")}
                title={t.viewTable}
              >
                <Table2 size={14} /> <span>{t.viewTable}</span>
              </button>
            </div>
          </div>
        </div>

        {(hasFilters || inspectorMode === "closed") && (
          <div className="wb-status-bar">
            <div className="wb-status-left">
              <span role="status" className="wb-result-count">
                <strong>{results.length}</strong> / {count.all}
              </span>
              {activeChips.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className="active-chip"
                  onClick={() => replaceField(chip.key, "")}
                >
                  <span>{chip.label}</span>
                  <X size={12} aria-hidden="true" />
                </button>
              ))}
              {hasFilters && (
                <button
                  type="button"
                  className="reset-link"
                  onClick={() => update({ ...defaults, sort: filters.sort })}
                >
                  {t.clearAll}
                </button>
              )}
            </div>
            {inspectorMode === "closed" && activeWorld && (
              <button
                type="button"
                className="open-inspector-btn"
                onClick={() => setInspectorMode("open")}
              >
                <Eye size={14} /> {t.openInspector}
              </button>
            )}
          </div>
        )}

        {results.length === 0 ? (
          <div className="empty-state">
            <Search size={24} />
            <h2>{t.emptyTitle}</h2>
            <p>{t.emptyHint}</p>
            <button
              type="button"
              className="button button-primary"
              onClick={() => update({ ...defaults })}
            >
              {t.clearAll}
            </button>
          </div>
        ) : view === "grid" ? (
          <div className="world-grid">
            {visible.map((world) => (
              <WorldCard
                key={world.world_id}
                world={world}
                selected={inspectorActive && activeWorld?.world_id === world.world_id}
                lang={lang}
                onInspect={handleInspect}
              />
            ))}
          </div>
        ) : view === "list" ? (
          <div className="world-list">
            {visible.map((world) => {
              const demo = webLink(world.live_demo_url);
              const repo = webLink(world.repo_url);
              const playable = isPlayable(world) && Boolean(demo);
              const hasDemo = Boolean(demo) && world.demo_health_status !== "broken";
              const isSelected = inspectorActive && activeWorld?.world_id === world.world_id;
              return (
                <article
                  key={world.world_id}
                  className={isSelected ? "list-row is-selected" : "list-row"}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest("a, button")) return;
                    handleInspect(world);
                  }}
                >
                  <button
                    type="button"
                    className="list-thumb"
                    onClick={() => handleInspect(world)}
                    aria-label={world.title}
                  >
                    {world.thumbnail_url ? (
                      <img src={world.thumbnail_url} alt="" loading="lazy" width={192} height={108} />
                    ) : (
                      <span className="list-thumb-text">
                        {themeLabel(world.theme_category, lang)}
                      </span>
                    )}
                  </button>
                  <div className="list-main">
                    <div className="list-title-row">
                      <h3>
                        <a href={caseHref(world)}>{world.title}</a>
                      </h3>
                      <span className="card-author">{byline(world, lang)}</span>
                      {world.demo_health_status === "verified_playable" && (
                        <span className="pill-ok">● {t.playable}</span>
                      )}
                    </div>
                    <p className="list-summary">{cardLead(world, lang)}</p>
                    <div className="tag-list">
                      {world.models_used.map((m) => (
                        <span key={m} className={`tag tag-model tone-${familyTone(m)}`}>
                          {m}
                        </span>
                      ))}
                      <span className="tag">{themeLabel(world.theme_category, lang)}</span>
                      {world.tech_stack.slice(0, 3).map((tech) => (
                        <span key={tech} className="tag">
                          {tech}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="list-actions">
                    {playable && demo ? (
                      <a
                        className="button button-primary button-sm"
                        href={demo}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <CirclePlay size={14} /> {t.play}
                      </a>
                    ) : hasDemo && demo ? (
                      <a
                        className="button button-subtle button-sm"
                        href={demo}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {t.visit} <ArrowUpRight size={13} />
                      </a>
                    ) : null}
                    {repo && (
                      <a
                        className="button button-subtle button-sm"
                        href={repo}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <CodeXml size={14} /> {t.sourceCode}
                      </a>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div
            tabIndex={0}
            role="region"
            aria-label={t.viewTable}
            className="table-wrapper"
          >
            <table
              className="research-table"
              style={
                {
                  "--label-2": `"${t.colModel}"`,
                  "--label-3": `"${t.colTheme}"`,
                  "--label-4": `"${t.colStack}"`,
                  "--label-5": `"${t.colStatus}"`,
                  "--label-6": `"${t.colActions}"`,
                } as React.CSSProperties
              }
            >
              <caption className="sr-only">{t.brand}</caption>
              <thead>
                <tr>
                  <th scope="col">{t.colWorld}</th>
                  <th scope="col">{t.colModel}</th>
                  <th scope="col">{t.colTheme}</th>
                  <th scope="col">{t.colStack}</th>
                  <th scope="col">{t.colStatus}</th>
                  <th scope="col">{t.colActions}</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((world) => {
                  const demo = webLink(world.live_demo_url);
                  const repo = webLink(world.repo_url);
                  const playable = isPlayable(world) && Boolean(demo);
                  const hasDemo = Boolean(demo) && world.demo_health_status !== "broken";
                  const isSelected = inspectorActive && activeWorld?.world_id === world.world_id;
                  return (
                    <tr
                      key={world.world_id}
                      className={isSelected ? "is-selected" : undefined}
                      onClick={(e) => {
                        if ((e.target as HTMLElement).closest("a, button")) return;
                        handleInspect(world);
                      }}
                    >
                      <th scope="row">
                        <div className="tbl-world">
                          <a href={caseHref(world)} className="tbl-title">
                            {world.title}
                          </a>
                          <span className="tbl-sub">
                            {byline(world, lang)} · {cardLead(world, lang)}
                          </span>
                        </div>
                      </th>
                      <td>
                        <div className="tag-list">
                          {world.models_used.slice(0, 2).map((m) => (
                            <span key={m} className={`tag tag-model tone-${familyTone(m)}`}>
                              {m}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td>{themeLabel(world.theme_category, lang)}</td>
                      <td>
                        {world.tech_stack.length ? (
                          <div className="tag-list">
                            {world.tech_stack.slice(0, 2).map((tech) => (
                              <span key={tech} className="tag">
                                {tech}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>
                        <span className={statusPillTone(world.demo_health_status)}>
                          {healthLabel(world.demo_health_status, lang)}
                        </span>
                        {(world.is_open_source === true || repo) && (
                          <span className="pill-blue" style={{ marginInlineStart: 4 }}>
                            {t.openSource}
                          </span>
                        )}
                      </td>
                      <td>
                        <div className="card-actions">
                          {playable && demo ? (
                            <a
                              className="act-link act-play"
                              href={demo}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {t.play} ↗
                            </a>
                          ) : hasDemo && demo ? (
                            <a
                              className="act-link act-code"
                              href={demo}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {t.visit} ↗
                            </a>
                          ) : null}
                          {repo && (
                            <a
                              className="act-link act-code"
                              href={repo}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {t.sourceCode}
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {limit < results.length && (
          <div className="load-more">
            <button
              type="button"
              className="button button-subtle"
              onClick={() => setLimit((n) => n + initialAmount)}
            >
              {t.loadMore}
              <span className="load-more-count">
                {Math.min(limit, results.length)} / {results.length}
              </span>
            </button>
            <button
              type="button"
              className="button button-ghost"
              onClick={() => setLimit(results.length)}
            >
              {t.showAll(results.length)}
            </button>
          </div>
        )}
      </section>

      {/* Right Quick Inspector Drawer */}
      <QuickInspector
        world={activeWorld}
        mode={inspectorMode}
        lang={lang}
        onClose={() => setInspectorMode("closed")}
      />
    </div>
  );
}
