"use client";
/* eslint-disable @next/next/no-html-link-for-pages */

import { useEffect } from "react";
import { ArrowUpRight, ChevronLeft, CirclePlay, CodeXml, Globe2 } from "lucide-react";
import { copy, useLang } from "@/lib/i18n";
import {
  bestQuote,
  byline,
  caseHref,
  cleanQuotes,
  familyTone,
  healthLabel,
  isPlayable,
  levelLabel,
  modeLabel,
  skillsFor,
  themeLabel,
  webLink,
  workflowStepsFor,
  type World,
} from "@/lib/worlds";
import { WorldPreview } from "./world-preview";

export function WorldDetailView({
  world,
  similar,
}: {
  world: World;
  similar: World[];
}) {
  const [lang] = useLang();
  const t = copy[lang];

  useEffect(() => {
    document.title = `${world.title} · ${t.brand}`;
  }, [world.title, t.brand]);

  const demo = webLink(world.live_demo_url);
  const repo = webLink(world.repo_url);
  const original = webLink(world.original_post_url);
  const playable = isPlayable(world) && Boolean(demo);
  const hasDemo = Boolean(demo) && world.demo_health_status !== "broken";
  const date = world.published_at?.slice(0, 10);
  const quotes = cleanQuotes(world);
  const steps = workflowStepsFor(world, lang);
  const skills = skillsFor(world, lang);
  const extraSources = [...new Set([...world.related_post_urls, ...world.evidence_source_urls])]
    .map((u) => webLink(u))
    .filter((u): u is string => Boolean(u));

  const facts: { label: string; value: string }[] = [
    { label: t.model, value: world.models_used.join(" · ") || "—" },
    ...(world.tech_stack.length
      ? [{ label: t.techStack, value: world.tech_stack.join(" · ") }]
      : []),
    ...(world.generation_mode !== "unknown"
      ? [{ label: t.mode, value: modeLabel(world.generation_mode, lang) }]
      : []),
    { label: t.reproducibility, value: levelLabel(world.reproducibility_level, lang) },
    ...(world.is_open_source !== null
      ? [{ label: t.license, value: world.is_open_source ? t.openYes : t.openNo }]
      : []),
    ...(world.reported_time_minutes !== null
      ? [{ label: t.timeLabel, value: t.minutes(world.reported_time_minutes) }]
      : []),
    ...(world.reported_cost_usd !== null
      ? [{ label: t.costLabel, value: `US$ ${world.reported_cost_usd}` }]
      : []),
  ];

  const lead = lang === "zh" ? world.summary : world.summary_en || bestQuote(world);

  return (
    <div className="container subpage">
      <a className="back-link" href="/">
        <ChevronLeft size={16} /> {t.backToCatalog}
      </a>

      <section className="detail-intro">
        <div className="detail-intro-copy">
          <div className="tag-list">
            {world.demo_health_status === "verified_playable" ? (
              <span className="pill-ok">● {t.playable}</span>
            ) : (
              <span className="pill-neutral">{healthLabel(world.demo_health_status, lang)}</span>
            )}
            <span className="pill-neutral">{themeLabel(world.theme_category, lang)}</span>
            {(world.is_open_source === true) && (
              <span className="pill-blue">{t.openSource}</span>
            )}
          </div>

          <h1>{world.title}</h1>
          <p className="detail-summary">{lead}</p>

          <div className="byline">
            <span>
              {t.author}: {byline(world, lang)}
            </span>
            {date && (
              <>
                <span aria-hidden="true">·</span>
                <time dateTime={date}>{date}</time>
              </>
            )}
          </div>

          <div className="detail-actions">
            {hasDemo && demo && (
              <a
                className={playable ? "button button-primary" : "button button-subtle"}
                href={demo}
                target="_blank"
                rel="noopener noreferrer"
              >
                <CirclePlay size={16} />
                {playable ? t.openDemo : t.visitDemo}
                <ArrowUpRight size={15} />
              </a>
            )}
            {repo && (
              <a
                className="button button-subtle"
                href={repo}
                target="_blank"
                rel="noopener noreferrer"
              >
                <CodeXml size={16} /> {t.viewCode}
              </a>
            )}
            {original && (
              <a
                className="button button-ghost"
                href={original}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Globe2 size={16} />{" "}
                {world.source_kind === "primary_page" ? t.originalPage : t.originalPost}
              </a>
            )}
          </div>
        </div>

        <figure className="detail-cover">
          <WorldPreview world={world} variant="detail" lang={lang} />
        </figure>
      </section>

      <div className="detail-grid">
        <div className="detail-content">
          {steps.length > 0 && (
            <section className="panel">
              <h2>{t.workflow}</h2>
              <ol className="steps">
                {steps.map((step, index) => (
                  <li key={step}>
                    <span className="step-badge">{index + 1}</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
              {skills.length > 0 && (
                <div className="detail-subblock">
                  <h3>{t.toolsAndPrompts}</h3>
                  <div className="tag-list">
                    {skills.map((tool) => (
                      <span className="tag" key={tool}>
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {quotes.length > 0 && (
            <section className="panel">
              <h2>{t.evidence}</h2>
              <div className="quotes">
                {quotes.map((quote) => (
                  <blockquote key={quote}>
                    <p>{quote}</p>
                  </blockquote>
                ))}
              </div>
              {original && (
                <div className="evidence-links">
                  <a
                    className="text-link"
                    href={original}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t.viewSource} <ArrowUpRight size={13} />
                  </a>
                </div>
              )}
              {extraSources.length > 0 && (
                <ul className="source-list">
                  {extraSources.map((link) => (
                    <li key={link}>
                      <a href={link} target="_blank" rel="noopener noreferrer" className="text-link">
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>

        <aside className="panel facts">
          <h2>{t.facts}</h2>
          <div className="tag-list" style={{ marginBottom: 12 }}>
            {world.models_used.map((m) => (
              <span key={m} className={`tag tag-model tone-${familyTone(m)}`}>
                {m}
              </span>
            ))}
          </div>
          <dl>
            {facts.map((fact) => (
              <div className="fact-row" key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </aside>
      </div>

      {similar.length > 0 && (
        <section className="similar">
          <h2>{t.similarTitle}</h2>
          <div className="similar-grid">
            {similar.map((item) => (
              <a href={caseHref(item)} className="panel related-card" key={item.world_id}>
                <div className="related-top">
                  <strong>{item.title}</strong>
                  {item.models_used[0] && (
                    <span className={`tag tag-model tone-${familyTone(item.models_used[0])}`}>
                      {item.models_used[0]}
                    </span>
                  )}
                </div>
                <span>{lang === "zh" ? item.summary : item.summary_en || bestQuote(item)}</span>
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
