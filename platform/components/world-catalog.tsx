"use client";

import { useEffect, useMemo, useState } from "react";
import { WorldPreview } from "./world-preview";
import { CirclePlay, CodeXml, Grid2X2, List, Search, SlidersHorizontal, X } from "lucide-react";
import {
  byline, caseHref, isPlayable, healthLabels, family, featured, levels, modelFamilies, modes, monthOf, themes,
  values, webLink, worlds, type World,
} from "@/lib/worlds";

const defaults = {
  q: "", model: "", theme: "", tech: "", mode: "", level: "", license: "", month: "",
  play: "", cost: "", sort: "",
};
type Filters = typeof defaults;
const initialAmount = 12;
const months = [...new Set(worlds.map(monthOf).filter(Boolean))].sort().reverse();

function fromLocation(): Filters {
  const url = new URLSearchParams(window.location.search);
  const result = { ...defaults };
  for (const key of Object.keys(defaults) as (keyof Filters)[]) result[key] = url.get(key) || "";
  return result;
}

function matches(world: World, filters: Filters): boolean {
  const searchable = [
    world.title, world.summary, world.author_handle, world.author_name, ...world.workflow_steps, ...world.skills_or_prompts_used, themes[world.theme_category],
    ...world.models_used, ...world.tech_stack,
  ].join(" ").toLocaleLowerCase();
  return filters.q.trim().toLocaleLowerCase().split(/\s+/).every(word => searchable.includes(word)) &&
    (!filters.model || world.models_used.some(model => family(model) === filters.model || model === filters.model)) &&
    (!filters.theme || world.theme_category === filters.theme) &&
    (!filters.tech || world.tech_stack.some(tech => tech === filters.tech)) &&
    (!filters.mode || world.generation_mode === filters.mode) &&
    (!filters.level || (filters.level === "playable" ? isPlayable(world) :
      filters.level === "source" ? Boolean(world.repo_url) : world.reproducibility_level === filters.level)) &&
    (!filters.month || monthOf(world) === filters.month) &&
    (!filters.license || (filters.license === "unknown" ? world.is_open_source === null : world.is_open_source === (filters.license === "open"))) &&
    (!filters.cost || world.reported_cost_usd !== null) && (!filters.play || isPlayable(world));
}

function compare(a: World, b: World, sort: string) {
  if (sort === "ingested") return (b.first_seen_at || "").localeCompare(a.first_seen_at || "") || a.title.localeCompare(b.title);
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

function FilterSelect({ label, value, onChange, options }: {
  label: string; value: string; onChange: (value: string) => void; options: [string, string][];
}) {
  return (
    <label className="filter-select">
      <span className="sr-only">{label}</span>
      <select aria-label={label} value={value} onChange={event => onChange(event.target.value)}>
        <option value="">{label}</option>
        {options.map(([key, name]) => <option key={key} value={key}>{name}</option>)}
      </select>
    </label>
  );
}

export function WorldCard({ world }: { world: World }) {
  const demo = webLink(world.live_demo_url);
  const repo = webLink(world.repo_url);
  const action = (isPlayable(world) && demo) || repo;
  const play = isPlayable(world) && Boolean(demo);
  return (
    <article className="world-card">
      <a className="card-image" href={caseHref(world)} aria-label={`查看 ${world.title} 详情`}>
        <WorldPreview world={world} />
        <span className="image-chip">{themes[world.theme_category] || "其他"}</span>
      </a>
      <div className="card-body">
        <div className="card-title"><h3><a href={caseHref(world)}>{world.title}</a></h3><span>{byline(world)}</span></div>
        <p>{world.summary}</p>
        <div className="card-meta">
          <div className="tag-list">
            {world.models_used.slice(0,2).map(model => <span key={model} className="tag">{model}</span>)}
            <span className="tag">{levels[world.reproducibility_level]}</span>
          </div>
          {action && <a className="card-action" href={action} target="_blank" rel="noopener noreferrer"
                        aria-label={`${play ? "试玩" : "查看源码"} ${world.title}（新标签页）`}>
            {play ? <CirclePlay size={17} /> : <CodeXml size={17} />}{play ? "试玩" : "源码"}
          </a>}
        </div>
        <div className="source-line"><span>{healthLabels[world.demo_health_status]}</span><a href={world.original_post_url} target="_blank" rel="noopener noreferrer">{world.source_kind === "x_post" ? "作者原帖" : "作品原文"}</a></div>
      </div>
    </article>
  );
}

export function WorldCatalog() {
  const [filters, setFilters] = useState<Filters>(defaults);
  const [advanced, setAdvanced] = useState(false);
  const [list, setList] = useState(false);
  const [limit, setLimit] = useState(initialAmount);

  useEffect(() => {
    function restore() {
      const next = fromLocation();
      setFilters(next);
      setAdvanced(Boolean(next.tech || next.mode || next.level || next.license || next.month || next.play || next.cost));
      setLimit(initialAmount);
    }
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  const results = useMemo(() => worlds.filter(world => matches(world, filters))
    .sort((a, b) => compare(a, b, filters.sort)), [filters]);

  function update(next: Filters) {
    setFilters(next);
    setLimit(initialAmount);
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries(next)) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    window.history.replaceState(window.history.state, "", url);
  }
  const select = (key: keyof Filters) => (value: string) => update({ ...filters, [key]: value });
  const hasFilters = Object.entries(filters).some(([key, value]) => key !== "sort" && value);
  const toggleLayout = () => setList(current => !current);

  return (
    <section id="catalog" className="container catalog" aria-labelledby="catalog-heading">
      <div className="section-heading">
        <div><h2 id="catalog-heading">探索世界</h2><p>查找案例、试玩原作，查看背后的模型与工作流。</p></div>
        <div className="layout-switch" aria-label="目录布局">
          <button type="button" aria-label="卡片布局" title="卡片布局" aria-pressed={!list} onClick={list ? toggleLayout : undefined}><Grid2X2 size={17} /></button>
          <button type="button" aria-label="列表布局" title="列表布局" aria-pressed={list} onClick={!list ? toggleLayout : undefined}><List size={19} /></button>
        </div>
      </div>
      <div className="filters">
        <div className="filters-primary">
          <label className="search-field">
            <Search size={19} />
            <input type="search" aria-label="搜索案例" placeholder="搜索案例、作者、工具或工作流…" value={filters.q} onChange={event => select("q")(event.target.value)} />
          </label>
          <FilterSelect label="全部模型" value={filters.model} onChange={select("model")} options={[
            ...modelFamilies.map((name): [string,string] => [name, name]),
            ...values("models_used").filter(name => !modelFamilies.includes(name)).map((name): [string,string] => [name, name]),
          ]} />
          <FilterSelect label="全部主题" value={filters.theme} onChange={select("theme")} options={Object.entries(themes)} />
          <button className="button filter-more" type="button" aria-expanded={advanced} aria-controls="advanced-filters" onClick={() => setAdvanced(!advanced)}>
            <SlidersHorizontal size={17} />更多筛选
          </button>
        </div>
        {advanced && <div className="filters-extra" id="advanced-filters">
          <FilterSelect label="全部技术栈" value={filters.tech} onChange={select("tech")} options={values("tech_stack").map(value => [value, value])} />
          <FilterSelect label="全部生成方式" value={filters.mode} onChange={select("mode")} options={Object.entries(modes)} />
          <FilterSelect label="全部复现程度" value={filters.level} onChange={select("level")} options={[["playable","已验活在线试玩"],["source","有公开源码"],["video_only","仅视频拆解"],["prompt_shared","公开提示词"],["live_demo","有试玩入口"],["full_repo","完整仓库"]]} />
          <FilterSelect label="全部开源状态" value={filters.license} onChange={select("license")} options={[["open","开源"],["closed","闭源"],["unknown","未知"]]} />
          <FilterSelect label="全部月份" value={filters.month} onChange={select("month")} options={months.map(value => [value, value])} />
          <label className="checkbox-label"><input type="checkbox" checked={Boolean(filters.cost)} onChange={event => select("cost")(event.target.checked ? "1" : "")} />成本已披露</label>
          <label className="checkbox-label"><input type="checkbox" checked={Boolean(filters.play)} onChange={event => select("play")(event.target.checked ? "1" : "")} />仅可试玩</label>
        </div>}
      </div>
      <div className="results-bar">
        <div><span role="status"><strong>{results.length}</strong> 个案例</span>{hasFilters && <button className="reset-button" onClick={() => update({ ...defaults, sort: filters.sort })}><X size={13} />清除筛选</button>}</div>
        <FilterSelect label="精选排序" value={filters.sort} onChange={select("sort")} options={[["recent","最新发布"],["ingested","最近收录"],["title","案例名称"]]} />
      </div>
      {results.length > 0 ?
        <div className={list ? "world-grid list-view" : "world-grid"}>
          {results.slice(0, limit).map(world => <WorldCard key={world.world_id} world={world} />)}
        </div> :
        <div className="empty-state"><Search size={26} /><h3>没有匹配的案例</h3><p>试试更短的关键词，或清除筛选条件。</p><button className="button" onClick={() => update({ ...defaults })}>清除筛选</button></div>}
      {limit < results.length && <div className="load-more"><button className="button" onClick={() => setLimit(limit + initialAmount)}>查看更多案例 <span>{Math.min(limit,results.length)} / {results.length}</span></button></div>}
    </section>
  );
}
