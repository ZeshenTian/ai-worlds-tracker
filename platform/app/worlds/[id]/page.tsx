import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ChevronLeft, CodeXml, Globe2, Play } from "lucide-react";
import { Shell } from "@/components/atlas-shell";
import { WorldPreview } from "@/components/world-preview";
import { byline, caseHref, healthLabels, isPlayable, modes, levels, reviews, themes, webLink, worlds } from "@/lib/worlds";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const world = worlds.find(item => item.world_id === id);
  return world ? { title: world.title, description: world.summary } : { title: "案例未找到" };
}

export default async function WorldPage({ params }: Props) {
  const { id } = await params;
  const world = worlds.find(item => item.world_id === id);
  if (!world) notFound();
  const demo = webLink(world.live_demo_url);
  const repo = webLink(world.repo_url);
  const original = webLink(world.original_post_url);
  const similar = worlds.filter(item => item.world_id !== id && item.theme_category === world.theme_category).slice(0, 3);
  const date = world.published_at?.slice(0, 10);
  return (
    <Shell active="catalog">
      <div className="container subpage">
        <a className="back-link" href="/#catalog"><ChevronLeft size={17} />世界目录</a>
        <section className="detail-intro">
          <div>
            <div className="tag-list"><span className="tag amber-tag">{themes[world.theme_category]}</span><span className="tag">{reviews[world.review_status]}</span></div>
            <h1>{world.title}</h1><p>{world.summary}</p>
            <div className="byline">{byline(world)}{date && <time dateTime={date}>{date}</time>}</div>
            <div className="detail-actions">
              {demo && world.demo_health_status !== "broken" && <a className={isPlayable(world) ? "button button-primary" : "button"} href={demo} target="_blank" rel="noopener noreferrer"><Play size={17} fill="currentColor" />{isPlayable(world) ? "打开试玩" : "访问项目"}</a>}
              {repo && <a className="button" href={repo} target="_blank" rel="noopener noreferrer"><CodeXml size={19} />查看源码</a>}
              {original && <a className="button" href={original} target="_blank" rel="noopener noreferrer"><Globe2 size={17} />{world.source_kind === "primary_page" ? "查看作品原文" : "查看原帖"}</a>}
            </div>
            <p className="hint">{healthLabels[world.demo_health_status]}</p>
          </div>
          <figure className="detail-cover"><WorldPreview world={world} />{world.thumbnail_url && <figcaption>试玩页面截图</figcaption>}</figure>
        </section>
        <div className="detail-grid">
          <div className="detail-content">
            <section className="panel"><h2>创作工作流</h2>
              {world.workflow_steps.length ? <ol className="steps">{world.workflow_steps.map((step, index) => <li key={step}><span>{index + 1}</span>{step}</li>)}</ol>
                : <p className="muted">已收集的资料中没有可核实的创作步骤。</p>}
              {world.skills_or_prompts_used.length > 0 && <><h3>工具与提示</h3><div className="tag-list">{world.skills_or_prompts_used.map(tool => <span className="tag" key={tool}>{tool}</span>)}</div></>}
            </section>
            <section className="panel"><h2>原文证据</h2>
              {world.evidence_quotes.length ? <div className="quotes">{world.evidence_quotes.map(quote => <blockquote key={quote}><p>{quote}</p></blockquote>)}</div> : <p className="muted">暂无原文摘录。</p>}
              {original && <a className="text-link" href={original} target="_blank" rel="noopener noreferrer">查看原始来源</a>}
              {(world.related_post_urls.length + world.evidence_source_urls.length > 0) && <ul className="source-list">{[...new Set([...world.related_post_urls, ...world.evidence_source_urls])].map(link => webLink(link) && <li key={link}><a href={webLink(link)} target="_blank" rel="noopener noreferrer">{link}</a></li>)}</ul>}
            </section>
          </div>
          <aside className="panel facts"><h2>案例信息</h2><dl>
            <dt>使用模型</dt><dd>{world.models_used.join("、") || "未披露"}</dd>
            <dt>技术栈</dt><dd>{world.tech_stack.join("、") || "未披露"}</dd>
            <dt>生成方式</dt><dd>{modes[world.generation_mode]}</dd>
            <dt>复现程度</dt><dd>{levels[world.reproducibility_level]}</dd>
            <dt>开源状态</dt><dd>{world.is_open_source === null ? "未知" : world.is_open_source ? "开源" : "闭源"}</dd>
            <dt>费用（USD）</dt><dd>{world.reported_cost_usd === null ? "作者未披露" : `US$ ${world.reported_cost_usd}`}</dd>
            <dt>耗时</dt><dd>{world.reported_time_minutes === null ? "作者未披露" : `${world.reported_time_minutes} 分钟`}</dd>
          </dl></aside>
        </div>
        {similar.length > 0 && <section className="similar"><h2>同主题案例</h2><div className="similar-grid">
          {similar.map(item => <a href={caseHref(item)} className="panel related-card" key={item.world_id}><strong>{item.title}</strong><span>{item.summary}</span></a>)}
        </div></section>}
      </div>
    </Shell>
  );
}
