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
import {
  byline,
  caseHref,
  count,
  family,
  familyTone,
  featured,
  healthLabels,
  isPlayable,
  matchesWorldQuery,
  levels,
  modelFamilies,
  modes,
  monthOf,
  reviews,
  themes,
  values,
  webLink,
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
  .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));

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
  if (!matchesWorldQuery(world, f.q)) return false;
  if (f.model && !world.models_used.some((m) => family(m) === f.model || m === f.model)) return false;
  if (f.theme && world.theme_category !== f.theme) return false;
  if (f.tech && !world.tech_stack.includes(f.tech)) return false;
  if (f.mode && world.generation_mode !== f.mode) return false;
  if (f.level) {
    if (f.level === "playable" && !isPlayable(world)) return false;
    else if (f.level === "source" && !world.repo_url) return false;
    else if (f.level === "has_demo" && !(webLink(world.live_demo_url) && world.demo_health_status !== "broken"))
      return false;
    else if (f.level !== "playable" && f.level !== "source" && f.level !== "has_demo" && world.reproducibility_level !== f.level)
      return false;
  }
  if (f.month && monthOf(world) !== f.month) return false;
  if (f.license) {
    if (f.license === "unknown" && world.is_open_source !== null) return false;
    if (f.license !== "unknown" && world.is_open_source !== (f.license === "open")) return false;
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

function WorldCard({
  world,
  selected,
  onInspect,
}: {
  world: World;
  selected: boolean;
  onInspect: (world: World) => void;
}) {
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
        aria-label={`在右侧快速预览 ${world.title}`}
      >
        <WorldPreview world={world} />
        {world.thumbnail_url && (
          <>
            {playable ? (
              <span className="cover-badge badge-ok">● 已验活可试玩</span>
            ) : world.is_open_source === true || repo ? (
              <span className="cover-badge badge-blue">⌘ 开源仓库</span>
            ) : null}
            <span className="cover-theme">{themes[world.theme_category] || "其他"}</span>
          </>
        )}
      </button>

      <div className="card-body">
        <div className="card-head">
          <h3>
            <a href={caseHref(world)}>{world.title}</a>
          </h3>
          <span className="card-author">{byline(world)}</span>
        </div>
        <p className="card-summary">{world.summary}</p>
        <div className="card-foot">
          <div className="tag-list">
            {world.models_used.slice(0, 1).map((m) => (
              <span key={m} className={`tag tag-model tone-${familyTone(m)}`}>
                {m}
              </span>
            ))}
            {world.tech_stack[0] ? (
              <span className="tag">{world.tech_stack[0]}</span>
            ) : (
              <span className="tag">{levels[world.reproducibility_level]}</span>
            )}
          </div>
          <div className="card-actions">
            {playable && demo ? (
              <a
                className="act-link act-play"
                href={demo}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`试玩 ${world.title}（新标签页）`}
              >
                <CirclePlay size={14} /> 试玩
              </a>
            ) : repo ? (
              <a
                className="act-link act-code"
                href={repo}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`查看 ${world.title} 源码（新标签页）`}
              >
                <CodeXml size={14} /> 源码
              </a>
            ) : hasDemo && demo ? (
              <a
                className="act-link act-code"
                href={demo}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`访问 ${world.title} 试玩（待验证，新标签页）`}
              >
                访问试玩 <ArrowUpRight size={13} />
              </a>
            ) : null}
            {repo && playable && (
              <a
                className="act-link act-code"
                href={repo}
                target="_blank"
                rel="noopener noreferrer"
              >
                源码
              </a>
            )}
            {original && (
              <a
                className="act-link act-muted"
                href={original}
                target="_blank"
                rel="noopener noreferrer"
              >
                {world.source_kind === "x_post" ? "原帖" : "原文"}
              </a>
            )}
            <button
              type="button"
              className={selected ? "act-inspect is-active" : "act-inspect"}
              onClick={() => onInspect(world)}
              aria-label={`快速预览 ${world.title}`}
              title="快速预览"
            >
              {selected ? "预览中" : "快览"}
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}

function QuickInspector({
  world,
  mode,
  onClose,
}: {
  world: World | null;
  mode: "auto" | "open" | "closed";
  onClose: () => void;
}) {
  if (mode === "closed" || !world) return null;
  const demo = webLink(world.live_demo_url);
  const repo = webLink(world.repo_url);
  const original = webLink(world.original_post_url);
  const playable = isPlayable(world) && Boolean(demo);
  const hasDemo = Boolean(demo) && world.demo_health_status !== "broken";
  const date = world.published_at?.slice(0, 10);

  const kvItems: { label: string; value: string }[] = [
    { label: "使用模型", value: world.models_used.join(" · ") || "未披露" },
    { label: "生成方式", value: modes[world.generation_mode] || "未披露" },
    ...(world.tech_stack.length
      ? [{ label: "技术栈", value: world.tech_stack.slice(0, 4).join(" · ") }]
      : []),
    {
      label: "开放与复现",
      value:
        world.is_open_source === true
          ? `开源 · ${levels[world.reproducibility_level]}`
          : levels[world.reproducibility_level],
    },
    ...(world.reported_time_minutes !== null
      ? [{ label: "制作耗时", value: `${world.reported_time_minutes} 分钟` }]
      : []),
    ...(world.reported_cost_usd !== null
      ? [{ label: "披露费用", value: `US$ ${world.reported_cost_usd}` }]
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
        aria-label={`快速预览：${world.title}`}
      >
        <div className="insp-head">
          <span className="insp-label">快速预览 · 案例档案</span>
          <div className="insp-head-actions">
            <a href={caseHref(world)} className="insp-full-link">
              打开完整页面 <ArrowUpRight size={13} />
            </a>
            <button
              type="button"
              className="icon-btn"
              onClick={onClose}
              aria-label="关闭快速预览"
              title="收起预览栏"
            >
              <PanelRightClose size={16} />
            </button>
          </div>
        </div>

        <div className="insp-body scroller">
          <div className="insp-media">
            <WorldPreview world={world} variant="detail" />
          </div>

          <div className="insp-header">
            <div className="tag-list">
              <span className={statusPillTone(world.demo_health_status)}>
                {world.demo_health_status === "verified_playable" ? "● " : ""}
                {healthLabels[world.demo_health_status]}
              </span>
              <span className="pill-neutral">{themes[world.theme_category] || "其他"}</span>
              {world.is_open_source === true && <span className="pill-blue">⌘ 开源</span>}
              <span className="pill-neutral">{reviews[world.review_status]}</span>
            </div>
            <h2>
              <a href={caseHref(world)}>{world.title}</a>
            </h2>
            <p className="insp-byline">
              {byline(world)}
              {date && (
                <>
                  {" · "}
                  <time dateTime={date}>{date}</time>
                </>
              )}
              {" · "}
              {world.source_kind === "primary_page" ? "官方/作品原文" : "X 原帖"}
            </p>
            <p className="insp-summary">{world.summary}</p>
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
                {playable ? "打开在线试玩" : "访问试玩（待验）"}
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
                <CodeXml size={15} /> 查看源码
              </a>
            )}
            {original && (
              <a
                className="button button-ghost"
                href={original}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Globe2 size={15} /> {world.source_kind === "primary_page" ? "作品原文" : "作者原帖"}
              </a>
            )}
          </div>

          <div className="kv-grid">
            {kvItems.slice(0, 4).map((item) => (
              <div className="kv" key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>

          <section className="insp-card">
            <div className="insp-card-head">
              <h3>创作工作流</h3>
              <span>{world.workflow_steps.length ? `${world.workflow_steps.length} 步` : "暂无披露"}</span>
            </div>
            {world.workflow_steps.length > 0 ? (
              <ol className="insp-steps">
                {world.workflow_steps.map((step, i) => (
                  <li key={step}>
                    <span className="step-badge">{i + 1}</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="insp-empty">原帖未拆解详细步骤，可参考下方原文证据或原帖上下文。</p>
            )}
            {world.skills_or_prompts_used.length > 0 && (
              <div className="insp-subblock">
                <span className="insp-sublabel">工具与提示</span>
                <div className="tag-list">
                  {world.skills_or_prompts_used.map((skill) => (
                    <span className="tag" key={skill}>
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="insp-card">
            <div className="insp-card-head">
              <h3>原文证据摘录</h3>
              {original && (
                <a href={original} target="_blank" rel="noopener noreferrer" className="text-link">
                  溯源 <ExternalLink size={12} />
                </a>
              )}
            </div>
            {world.evidence_quotes.length > 0 ? (
              <div className="insp-quotes">
                {world.evidence_quotes.slice(0, 3).map((q) => (
                  <blockquote key={q}>{q}</blockquote>
                ))}
              </div>
            ) : (
              <p className="insp-empty">暂无原文摘录。</p>
            )}
          </section>
        </div>
      </aside>
    </>
  );
}

export function WorldCatalog({ lastUpdatedAt }: { lastUpdatedAt: string }) {
  const [filters, setFilters] = useState<Filters>(defaults);
  const [view, setView] = useState<ViewMode>("grid");
  const [limit, setLimit] = useState(initialAmount);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inspectorMode, setInspectorMode] = useState<"auto" | "open" | "closed">("auto");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Restore filters from URL and listen for topbar search & Escape
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

  // Cross-filtered facet counts for intuitive exploration
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
        allTechStacks.map((t) => [t.key, techBase.filter((w) => w.tech_stack.includes(t.key)).length])
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
    if (filters.q.trim()) chips.push({ key: "q", label: `关键词：${filters.q.trim()}` });
    if (filters.model) chips.push({ key: "model", label: `模型：${filters.model}` });
    if (filters.theme) chips.push({ key: "theme", label: `主题：${themes[filters.theme] || filters.theme}` });
    if (filters.tech) chips.push({ key: "tech", label: `技术栈：${filters.tech}` });
    if (filters.mode) chips.push({ key: "mode", label: `方式：${modes[filters.mode] || filters.mode}` });
    if (filters.play) chips.push({ key: "play", label: "已验活可试玩" });
    if (filters.license) {
      const map: Record<string, string> = { open: "确认开源", closed: "闭源", unknown: "开源状态未知" };
      chips.push({ key: "license", label: map[filters.license] || filters.license });
    }
    if (filters.level) {
      const map: Record<string, string> = {
        playable: "已验活可试玩",
        source: "有公开源码",
        has_demo: "有试玩入口",
        ...levels,
      };
      chips.push({ key: "level", label: `复现：${map[filters.level] || filters.level}` });
    }
    if (filters.thumb) chips.push({ key: "thumb", label: "含实景封面" });
    if (filters.wf) chips.push({ key: "wf", label: "含创作工作流" });
    if (filters.month) chips.push({ key: "month", label: `月份：${filters.month}` });
    if (filters.cost) chips.push({ key: "cost", label: "成本已披露" });
    return chips;
  }, [filters]);

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
        aria-label="分面筛选栏"
      >
        <div className="wb-sidebar-mobile-head">
          <strong>筛选条件</strong>
          <button
            type="button"
            className="icon-btn"
            aria-label="关闭筛选栏"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={16} />
          </button>
        </div>

        <div className="facet-group">
          <div className="facet-title">模型家族</div>
          <button
            type="button"
            className={!filters.model ? "facet-item active" : "facet-item"}
            onClick={() => replaceField("model", "")}
          >
            <span className="facet-left">
              <span className="dot dot-all" aria-hidden="true" />
              全部模型
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
          <div className="facet-title">可用性与开放度</div>
          <button
            type="button"
            className={filters.play ? "facet-item active" : "facet-item"}
            onClick={() => setField("play", "1")}
          >
            <span className="facet-left">
              <span className="dot dot-ok" aria-hidden="true" />
              已验活可试玩
            </span>
            <span className="facet-count count-ok">{count.playable}</span>
          </button>
          <button
            type="button"
            className={filters.level === "has_demo" ? "facet-item active" : "facet-item"}
            onClick={() => setField("level", "has_demo")}
          >
            <span className="facet-left">有试玩入口</span>
            <span className="facet-count">{count.hasDemo}</span>
          </button>
          <button
            type="button"
            className={filters.license === "open" ? "facet-item active" : "facet-item"}
            onClick={() => setField("license", "open")}
          >
            <span className="facet-left">确认开源</span>
            <span className="facet-count count-blue">{count.open}</span>
          </button>
          <button
            type="button"
            className={filters.level === "source" ? "facet-item active" : "facet-item"}
            onClick={() => setField("level", "source")}
          >
            <span className="facet-left">公开源码仓库</span>
            <span className="facet-count">{count.repos}</span>
          </button>
          <button
            type="button"
            className={filters.wf ? "facet-item active" : "facet-item"}
            onClick={() => setField("wf", "1")}
          >
            <span className="facet-left">含创作工作流</span>
            <span className="facet-count">{count.withWorkflow}</span>
          </button>
        </div>

        <div className="facet-group">
          <div className="facet-title">世界主题</div>
          {Object.entries(themes).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={filters.theme === key ? "facet-item active" : "facet-item"}
              onClick={() => setField("theme", key)}
            >
              <span className="facet-left">{label}</span>
              <span className="facet-count">{facetCounts.themes[key] ?? 0}</span>
            </button>
          ))}
        </div>

        <div className="facet-group">
          <div className="facet-title">生成方式</div>
          {(["hybrid_pipeline", "iterative_chat", "one_shot", "agentic_loop"] as const).map((key) => (
            <button
              key={key}
              type="button"
              className={filters.mode === key ? "facet-item active" : "facet-item"}
              onClick={() => setField("mode", key)}
            >
              <span className="facet-left">{modes[key]}</span>
              <span className="facet-count">{facetCounts.modes[key] ?? 0}</span>
            </button>
          ))}
        </div>

        <details className="facet-disclosure" open={Boolean(filters.tech || filters.month)}>
          <summary>技术栈与发布月份</summary>
          <div className="facet-disclosure-body">
            <div className="facet-sublabel">常用技术栈</div>
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

            <div className="facet-sublabel">发布月份</div>
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
            同步于 <UpdateTime iso={lastUpdatedAt} /> · 纯静态
          </span>
        </div>
      </aside>

      {/* Center Catalog Workspace */}
      <section className="wb-main scroller" aria-labelledby="catalog-heading">
        <h1 id="catalog-heading" className="sr-only">
          生成世界图鉴 · 开源交互世界检索工作台
        </h1>

        <div className="wb-kpi-row">
          <div className="wb-kpi-chips">
            <button
              type="button"
              className="button button-subtle wb-mobile-filter-btn"
              onClick={() => setSidebarOpen(true)}
              aria-expanded={sidebarOpen}
            >
              <SlidersHorizontal size={14} /> 筛选
              {hasFilters && <span className="filter-badge">{activeChips.length}</span>}
            </button>

            <button
              type="button"
              className={!hasFilters ? "kpi-chip active" : "kpi-chip"}
              onClick={() => update({ ...defaults, sort: filters.sort })}
            >
              全部案例 <strong>{count.all}</strong>
            </button>
            <button
              type="button"
              className={filters.play ? "kpi-chip ok active-ring" : "kpi-chip ok"}
              onClick={() => setField("play", "1")}
            >
              ● 已验活可试玩 <strong>{count.playable}</strong>
            </button>
            <button
              type="button"
              className={filters.license === "open" ? "kpi-chip blue active-ring" : "kpi-chip blue"}
              onClick={() => setField("license", "open")}
            >
              ⌘ 开源 <strong>{count.open}</strong>
            </button>
            <button
              type="button"
              className={filters.thumb ? "kpi-chip active" : "kpi-chip"}
              onClick={() => setField("thumb", "1")}
            >
              含实景封面 <strong>{count.withThumb}</strong>
            </button>
          </div>

          <div className="wb-controls">
            <label className="sort-wrap">
              <span className="sr-only">排序方式</span>
              <select
                aria-label="排序方式"
                value={filters.sort}
                onChange={(e) => replaceField("sort", e.target.value)}
              >
                <option value="">排序：精选优先</option>
                <option value="recent">排序：最新发布</option>
                <option value="ingested">排序：最近收录</option>
                <option value="title">排序：案例名称</option>
              </select>
            </label>

            <div className="view-switch" role="group" aria-label="目录视图">
              <button
                type="button"
                aria-pressed={view === "grid"}
                onClick={() => setView("grid")}
                title="卡片视图"
              >
                <Grid2X2 size={14} /> <span>卡片</span>
              </button>
              <button
                type="button"
                aria-pressed={view === "list"}
                onClick={() => setView("list")}
                title="列表视图"
              >
                <List size={14} /> <span>列表</span>
              </button>
              <button
                type="button"
                aria-pressed={view === "table"}
                onClick={() => setView("table")}
                title="研究表格视图"
              >
                <Table2 size={14} /> <span>表格</span>
              </button>
            </div>
          </div>
        </div>

        <div className="wb-status-bar">
          <div className="wb-status-left">
            <span role="status" className="wb-result-count">
              显示 <strong>{results.length}</strong> 个世界
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
                清除全部
              </button>
            )}
          </div>
          {inspectorMode === "closed" && activeWorld && (
            <button
              type="button"
              className="open-inspector-btn"
              onClick={() => setInspectorMode("open")}
            >
              <Eye size={14} /> 展开右侧快览
            </button>
          )}
        </div>

        {results.length === 0 ? (
          <div className="empty-state">
            <Search size={24} />
            <h2>没有匹配的案例</h2>
            <p>可以尝试缩短关键词，或清除部分筛选条件。</p>
            <button
              type="button"
              className="button button-primary"
              onClick={() => update({ ...defaults })}
            >
              清除全部筛选
            </button>
          </div>
        ) : view === "grid" ? (
          <div className="world-grid">
            {visible.map((world) => (
              <WorldCard
                key={world.world_id}
                world={world}
                selected={inspectorActive && activeWorld?.world_id === world.world_id}
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
                    aria-label={`快速预览 ${world.title}`}
                  >
                    {world.thumbnail_url ? (
                      <img src={world.thumbnail_url} alt="" loading="lazy" width={192} height={108} />
                    ) : (
                      <span className="list-thumb-text">
                        {world.is_open_source === true ? "⌘ 开源" : "❝ 引文"}
                      </span>
                    )}
                  </button>
                  <div className="list-main">
                    <div className="list-title-row">
                      <h3>
                        <a href={caseHref(world)}>{world.title}</a>
                      </h3>
                      <span className="card-author">{byline(world)}</span>
                      <span className={statusPillTone(world.demo_health_status)}>
                        {healthLabels[world.demo_health_status]}
                      </span>
                    </div>
                    <p className="list-summary">{world.summary}</p>
                    <div className="tag-list">
                      {world.models_used.map((m) => (
                        <span key={m} className={`tag tag-model tone-${familyTone(m)}`}>
                          {m}
                        </span>
                      ))}
                      <span className="tag">{themes[world.theme_category] || "其他"}</span>
                      {world.tech_stack.slice(0, 3).map((t) => (
                        <span key={t} className="tag">
                          {t}
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
                        <CirclePlay size={14} /> 试玩
                      </a>
                    ) : hasDemo && demo ? (
                      <a
                        className="button button-subtle button-sm"
                        href={demo}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        访问试玩 <ArrowUpRight size={13} />
                      </a>
                    ) : null}
                    {repo && (
                      <a
                        className="button button-subtle button-sm"
                        href={repo}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <CodeXml size={14} /> 源码
                      </a>
                    )}
                    <button
                      type="button"
                      className="button button-ghost button-sm"
                      onClick={() => handleInspect(world)}
                    >
                      快览
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div
            tabIndex={0}
            role="region"
            aria-label="交互世界研究表格"
            className="table-wrapper"
          >
            <table className="research-table">
              <caption className="sr-only">AI 生成交互世界案例目录表格</caption>
              <thead>
                <tr>
                  <th scope="col">案例</th>
                  <th scope="col">模型</th>
                  <th scope="col">主题</th>
                  <th scope="col">技术栈</th>
                  <th scope="col">验活与开放</th>
                  <th scope="col">操作</th>
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
                            {byline(world)} · {world.summary}
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
                      <td>{themes[world.theme_category] || "其他"}</td>
                      <td>
                        {world.tech_stack.length ? (
                          <div className="tag-list">
                            {world.tech_stack.slice(0, 2).map((t) => (
                              <span key={t} className="tag">
                                {t}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>
                        <span className={statusPillTone(world.demo_health_status)}>
                          {healthLabels[world.demo_health_status]}
                        </span>
                        {world.is_open_source === true && (
                          <span className="pill-blue" style={{ marginInlineStart: 4 }}>
                            开源
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
                              试玩 ↗
                            </a>
                          ) : hasDemo && demo ? (
                            <a
                              className="act-link act-code"
                              href={demo}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              试玩 ↗
                            </a>
                          ) : null}
                          {repo && (
                            <a
                              className="act-link act-code"
                              href={repo}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              源码
                            </a>
                          )}
                          <button
                            type="button"
                            className="act-inspect"
                            onClick={() => handleInspect(world)}
                          >
                            快览
                          </button>
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
              查看更多案例
              <span className="load-more-count">
                {Math.min(limit, results.length)} / {results.length}
              </span>
            </button>
            <button
              type="button"
              className="button button-ghost"
              onClick={() => setLimit(results.length)}
            >
              全部展开 ({results.length})
            </button>
          </div>
        )}

        <footer className="wb-inline-footer">
          <span>基于公开原帖与作者发布的项目 · 收录 {count.all} 例</span>
          <a href="/trends#method" className="text-link">
            查看统计口径与趋势分析 →
          </a>
        </footer>
      </section>

      {/* Right Quick Inspector Drawer */}
      <QuickInspector
        world={activeWorld}
        mode={inspectorMode}
        onClose={() => setInspectorMode("closed")}
      />
    </div>
  );
}
