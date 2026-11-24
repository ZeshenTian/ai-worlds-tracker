/* eslint-disable @next/next/no-html-link-for-pages */
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArrowUpRight, ChevronLeft, CirclePlay, CodeXml, Globe2 } from "lucide-react";
import { Shell } from "@/components/atlas-shell";
import { WorldPreview } from "@/components/world-preview";
import {
  byline,
  caseHref,
  familyTone,
  healthLabels,
  isPlayable,
  levels,
  modes,
  reviews,
  themes,
  webLink,
  worlds,
} from "@/lib/worlds";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const world = worlds.find((item) => item.world_id === id);
  return world ? { title: world.title, description: world.summary } : { title: "案例未找到" };
}

export default async function WorldPage({ params }: Props) {
  const { id } = await params;
  const world = worlds.find((item) => item.world_id === id);
  if (!world) notFound();

  const demo = webLink(world.live_demo_url);
  const repo = webLink(world.repo_url);
  const original = webLink(world.original_post_url);
  const playable = isPlayable(world) && Boolean(demo);
  const hasDemo = Boolean(demo) && world.demo_health_status !== "broken";
  const similar = worlds
    .filter((item) => item.world_id !== id && item.theme_category === world.theme_category)
    .slice(0, 3);
  const date = world.published_at?.slice(0, 10);
  const extraSources = [...new Set([...world.related_post_urls, ...world.evidence_source_urls])]
    .map((u) => webLink(u))
    .filter((u): u is string => Boolean(u));

  const disclosedFacts: { label: string; value: string }[] = [
    { label: "使用模型", value: world.models_used.join("、") || "未披露" },
    ...(world.tech_stack.length
      ? [{ label: "技术栈", value: world.tech_stack.join("、") }]
      : []),
    ...(world.generation_mode !== "unknown"
      ? [{ label: "生成方式", value: modes[world.generation_mode] }]
      : []),
    { label: "复现程度", value: levels[world.reproducibility_level] },
    ...(world.is_open_source !== null
      ? [{ label: "开源状态", value: world.is_open_source ? "确认开源" : "闭源" }]
      : []),
    ...(world.reported_time_minutes !== null
      ? [{ label: "制作耗时", value: `${world.reported_time_minutes} 分钟` }]
      : []),
    ...(world.reported_cost_usd !== null
      ? [{ label: "费用（USD）", value: `US$ ${world.reported_cost_usd}` }]
      : []),
  ];

  const undisclosedLabels: string[] = [];
  if (!world.tech_stack.length) undisclosedLabels.push("技术栈");
  if (world.generation_mode === "unknown") undisclosedLabels.push("生成方式");
  if (world.is_open_source === null) undisclosedLabels.push("开源许可");
  if (world.reported_cost_usd === null) undisclosedLabels.push("费用");
  if (world.reported_time_minutes === null) undisclosedLabels.push("精确耗时");

  return (
    <Shell active="catalog">
      <div className="container subpage">
        <a className="back-link" href="/">
          <ChevronLeft size={16} /> 返回工作台目录
        </a>

        <section className="detail-intro">
          <div className="detail-intro-copy">
            <div className="tag-list">
              <span
                className={
                  world.demo_health_status === "verified_playable"
                    ? "pill-ok"
                    : world.demo_health_status === "login_required" ||
                        world.demo_health_status === "broken"
                      ? "pill-warn"
                      : "pill-neutral"
                }
              >
                {world.demo_health_status === "verified_playable" ? "● " : ""}
                {healthLabels[world.demo_health_status]}
              </span>
              <span className="pill-neutral">{themes[world.theme_category] || "其他"}</span>
              {world.is_open_source === true && <span className="pill-blue">⌘ 开源</span>}
              <span className="pill-neutral">{reviews[world.review_status]}</span>
            </div>

            <h1>{world.title}</h1>
            <p className="detail-summary">{world.summary}</p>

            <div className="byline">
              <span>作者：{byline(world)}</span>
              {date && (
                <>
                  <span aria-hidden="true">·</span>
                  <time dateTime={date}>{date}</time>
                </>
              )}
              <span aria-hidden="true">·</span>
              <span>{world.source_kind === "primary_page" ? "官方/作品原文" : "X 原帖收录"}</span>
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
                  {playable ? "打开在线试玩" : "访问试玩（待验证）"}
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
                  <CodeXml size={16} /> 查看源码仓库
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
                  {world.source_kind === "primary_page" ? "查看作品原文" : "查看作者原帖"}
                </a>
              )}
            </div>
          </div>

          <figure className="detail-cover">
            <WorldPreview world={world} variant="detail" />
            {world.thumbnail_url && <figcaption>试玩页面实景截图</figcaption>}
          </figure>
        </section>

        <div className="detail-grid">
          <div className="detail-content">
            {world.workflow_steps.length > 0 && (
              <section className="panel">
                <h2>创作工作流</h2>
                <ol className="steps">
                  {world.workflow_steps.map((step, index) => (
                    <li key={step}>
                      <span className="step-badge">{index + 1}</span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
                {world.skills_or_prompts_used.length > 0 && (
                  <div className="detail-subblock">
                    <h3>工具与提示线索</h3>
                    <div className="tag-list">
                      {world.skills_or_prompts_used.map((tool) => (
                        <span className="tag" key={tool}>
                          {tool}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </section>
            )}

            <section className="panel">
              <h2>原文证据</h2>
              {world.evidence_quotes.length > 0 ? (
                <div className="quotes">
                  {world.evidence_quotes.map((quote) => (
                    <blockquote key={quote}>
                      <p>{quote}</p>
                    </blockquote>
                  ))}
                </div>
              ) : (
                <p className="muted">暂无原文摘录。</p>
              )}
              <div className="evidence-links">
                {original && (
                  <a
                    className="text-link"
                    href={original}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    查看原始来源 <ArrowUpRight size={13} />
                  </a>
                )}
              </div>
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

            {world.workflow_steps.length === 0 && (
              <section className="panel panel-muted">
                <h2>创作工作流</h2>
                <p className="muted">
                  已收集的公开资料中暂无可核实的拆解步骤，可通过上方原文证据与原帖查看作者分享的上下文。
                </p>
                {world.skills_or_prompts_used.length > 0 && (
                  <div className="detail-subblock">
                    <h3>提及工具</h3>
                    <div className="tag-list">
                      {world.skills_or_prompts_used.map((tool) => (
                        <span className="tag" key={tool}>
                          {tool}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </section>
            )}
          </div>

          <aside className="panel facts">
            <h2>案例档案</h2>
            <div className="tag-list" style={{ marginBottom: 12 }}>
              {world.models_used.map((m) => (
                <span key={m} className={`tag tag-model tone-${familyTone(m)}`}>
                  {m}
                </span>
              ))}
            </div>
            <dl>
              {disclosedFacts.map((fact) => (
                <div className="fact-row" key={fact.label}>
                  <dt>{fact.label}</dt>
                  <dd>{fact.value}</dd>
                </div>
              ))}
            </dl>
            {undisclosedLabels.length > 0 && (
              <p className="facts-footnote">
                作者未公开披露：{undisclosedLabels.join("、")}。
              </p>
            )}
          </aside>
        </div>

        {similar.length > 0 && (
          <section className="similar">
            <h2>同主题案例</h2>
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
                  <span>{item.summary}</span>
                </a>
              ))}
            </div>
          </section>
        )}
      </div>
    </Shell>
  );
}
