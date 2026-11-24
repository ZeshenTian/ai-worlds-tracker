"use client";

import { useEffect } from "react";
import { Boxes, CodeXml, Layers3, Play } from "lucide-react";
import { copy, useLang } from "@/lib/i18n";
import {
  caseHref,
  count,
  family,
  levelLabel,
  monthOf,
  skillsFor,
  themeLabel,
  worlds,
} from "@/lib/worlds";

type Entry = { key: string; label: string; count: number; tone?: string };

function frequencies(
  extract: (world: (typeof worlds)[number]) => string[],
  labelFor: (key: string) => string = (k) => k
) {
  const totals = new Map<string, number>();
  for (const world of worlds) {
    for (const value of new Set(extract(world))) {
      if (value) totals.set(value, (totals.get(value) || 0) + 1);
    }
  }
  return [...totals]
    .map(([key, c]) => ({ key, label: labelFor(key), count: c }))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key, "en"));
}

function chartLink(filter: string, key: string) {
  return `/?${new URLSearchParams({ [filter]: key })}`;
}

function Bars({
  title,
  rows,
  filter,
  percent = false,
  accent = "",
}: {
  title: string;
  rows: Entry[];
  filter?: string;
  percent?: boolean;
  accent?: string;
}) {
  const scale = percent ? Math.max(1, worlds.length) : Math.max(1, ...rows.map((r) => r.count));
  return (
    <section className={`panel chart-panel ${accent}`}>
      <h2>{title}</h2>
      <ul className="chart-list">
        {rows.map((row) => {
          const width = `${(row.count / scale) * 100}%`;
          const inner = (
            <>
              <span className="bar-label">{row.label}</span>
              <span className="bar-track">
                <span className={row.tone ? `bar-fill-${row.tone}` : undefined} style={{ width }} />
              </span>
              <strong>
                {percent ? Math.round((100 * row.count) / Math.max(1, worlds.length)) + "%" : row.count}
              </strong>
            </>
          );
          return (
            <li key={row.key}>
              {filter && row.count ? (
                <a href={chartLink(filter, row.key)} className="bar-row">
                  {inner}
                </a>
              ) : (
                <div className="bar-row">{inner}</div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function TrendsView() {
  const [lang] = useLang();
  const t = copy[lang];

  useEffect(() => {
    document.title = `${t.trendsTitle} · ${t.brand}`;
  }, [t.trendsTitle, t.brand]);

  const models: Entry[] = frequencies((world) => world.models_used.map(family)).map((row) => ({
    ...row,
    tone:
      row.key === "Claude"
        ? "claude"
        : row.key === "GPT"
          ? "gpt"
          : row.key === "Gemini"
            ? "gemini"
            : undefined,
  }));

  const posted = frequencies((world) => [monthOf(world)]).sort((a, b) => a.key.localeCompare(b.key));
  const periods = posted.length ? [posted[0].key, posted[posted.length - 1].key] : [];
  const dates: Entry[] = [];
  if (periods.length) {
    const current = new Date(periods[0] + "-01T00:00:00Z");
    while (current.toISOString().slice(0, 7) <= periods[1]) {
      const month = current.toISOString().slice(0, 7);
      dates.push(posted.find((item) => item.key === month) || { key: month, label: month, count: 0 });
      current.setUTCMonth(current.getUTCMonth() + 1);
    }
  }

  const workflowGroups = [
    {
      label: lang === "en" ? "Map & Reference Driven" : "参考图与地图驱动",
      matches: (w: (typeof worlds)[number]) =>
        /参考图|地图|图纸|reference image/i.test(w.workflow_steps.join(" ")),
    },
    {
      label: lang === "en" ? "Iterative Debugging" : "迭代调试与测试",
      matches: (w: (typeof worlds)[number]) =>
        /迭代|调试|测试|调参|playwright/i.test(
          [...w.workflow_steps, ...w.skills_or_prompts_used].join(" ")
        ),
    },
  ]
    .map((group) => ({ label: group.label, samples: worlds.filter(group.matches) }))
    .filter((g) => g.samples.length)
    .sort((a, b) => b.samples.length - a.samples.length);

  const disclosed = worlds.filter(
    (world) => world.reported_cost_usd !== null || world.reported_time_minutes !== null
  );
  const costCount = worlds.filter((w) => w.reported_cost_usd !== null).length;
  const timeCount = worlds.filter((w) => w.reported_time_minutes !== null).length;

  return (
    <div className="container subpage">
      <header className="page-heading">
        <h1>{t.trendsTitle}</h1>
        <p>{t.trendsSubtitle}</p>
      </header>

      <div className="metric-grid">
        {(
          [
            [Boxes, count.all, t.statTotal, "neutral"],
            [Play, count.playable, t.statPlayable, "ok"],
            [CodeXml, count.repos, t.statRepos, "blue"],
            [Layers3, models.length, t.statModels, "neutral"],
          ] as const
        ).map(([Icon, value, label, tone]) => (
          <div className={`panel metric metric-${tone}`} key={label}>
            <span className="metric-ico" aria-hidden="true">
              <Icon size={19} />
            </span>
            <div>
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="chart-grid">
        <Bars title={t.chartModels} rows={models} filter="model" />
        <Bars
          title={t.chartThemes}
          rows={frequencies(
            (world) => world.theme_category === "other" ? [] : [world.theme_category],
            (k) => themeLabel(k, lang)
          )}
          filter="theme"
          accent="emerald-bars"
        />
        <Bars
          title={t.chartTech}
          percent
          rows={frequencies((world) => world.tech_stack).slice(0, 8)}
          filter="tech"
        />
        <Bars title={t.chartTimeline} rows={dates} filter="month" />
        <Bars
          title={t.chartLevels}
          rows={frequencies(
            (world) => [world.reproducibility_level],
            (k) => levelLabel(k, lang)
          )}
          filter="level"
          accent="emerald-bars"
        />
        <Bars
          title={t.chartSkills}
          rows={frequencies((world) => skillsFor(world, lang)).slice(0, 8)}
          filter="q"
        />
        <section className="panel chart-panel">
          <h2>{t.chartHandbook}</h2>
          <ul className="workflow-list">
            {workflowGroups.map((group) => (
              <li key={group.label}>
                <strong>
                  {group.label} · {group.samples.length}
                </strong>
                <div>
                  {group.samples.slice(0, 3).map((w) => (
                    <a className="text-link" href={caseHref(w)} key={w.world_id}>
                      {w.title}
                    </a>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {disclosed.length > 0 && (
        <section className="panel trend-table">
          <h2>{t.costSectionTitle}</h2>
          <p className="muted">{t.costSectionSummary(costCount, timeCount)}</p>
          <div
            tabIndex={0}
            role="region"
            aria-labelledby="cost-table-caption"
            className="table-wrapper"
            style={{ marginTop: 12 }}
          >
            <table
              className="research-table cost-table"
              style={
                {
                  "--label-2": `"${t.colCost}"`,
                  "--label-3": `"${t.colTime}"`,
                } as React.CSSProperties
              }
            >
              <caption id="cost-table-caption" className="sr-only">
                {t.costSectionTitle}
              </caption>
              <thead>
                <tr>
                  <th scope="col">{t.colWorld}</th>
                  <th scope="col">{t.colCost}</th>
                  <th scope="col">{t.colTime}</th>
                </tr>
              </thead>
              <tbody>
                {disclosed.map((world) => (
                  <tr key={world.world_id}>
                    <th scope="row">
                      <a className="text-link" href={caseHref(world)}>
                        {world.title}
                      </a>
                    </th>
                    <td>{world.reported_cost_usd ?? t.undisclosed}</td>
                    <td>{world.reported_time_minutes ?? t.undisclosed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="panel methodology" id="method">
        <h2>{t.methodTitle}</h2>
        {t.methodBullets.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </section>
    </div>
  );
}
