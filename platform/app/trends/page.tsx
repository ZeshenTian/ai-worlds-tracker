import type { Metadata } from "next";
import { Boxes, CodeXml, Layers3, Play } from "lucide-react";
import { Shell } from "@/components/atlas-shell";
import { caseHref, count, family, levels, modes, monthOf, themes, worlds } from "@/lib/worlds";

export const metadata: Metadata = { title: "趋势与工作流" };

type Entry = { key: string; label: string; count: number; tone?: string };

function frequencies(
  extract: (world: (typeof worlds)[number]) => string[],
  labels: Record<string, string> = {}
) {
  const totals = new Map<string, number>();
  for (const world of worlds) {
    for (const value of new Set(extract(world))) {
      if (value) totals.set(value, (totals.get(value) || 0) + 1);
    }
  }
  return [...totals]
    .map(([key, c]) => ({ key, label: labels[key] || key, count: c }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

function chartLink(filter: string, key: string) {
  return `/?${new URLSearchParams({ [filter]: key })}`;
}

function Bars({
  title,
  note,
  rows,
  filter,
  percent = false,
  accent = "",
}: {
  title: string;
  note: string;
  rows: Entry[];
  filter?: string;
  percent?: boolean;
  accent?: string;
}) {
  const scale = percent ? Math.max(1, worlds.length) : Math.max(1, ...rows.map((r) => r.count));
  return (
    <section className={`panel chart-panel ${accent}`}>
      <h2>{title}</h2>
      <p className="muted">{note}</p>
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
                <a
                  href={chartLink(filter, row.key)}
                  className="bar-row"
                  aria-label={`查看 ${row.label} 的 ${row.count} 个案例`}
                >
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

export default function Trends() {
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

  const known = worlds.filter((world) => world.is_open_source !== null);
  const open = known.filter((world) => world.is_open_source);
  const workflowGroups = [
    { label: "单轮提示生成", matches: (w: (typeof worlds)[number]) => w.generation_mode === "one_shot" },
    { label: "智能体循环", matches: (w: (typeof worlds)[number]) => w.generation_mode === "agentic_loop" },
    {
      label: "参考图、地图与设计稿",
      matches: (w: (typeof worlds)[number]) =>
        /参考图|地图|图纸|reference image/i.test(w.workflow_steps.join(" ")),
    },
    {
      label: "迭代调试与测试",
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

  return (
    <Shell active="trends">
      <div className="container subpage">
        <header className="page-heading">
          <h1>趋势与工作流</h1>
          <p>
            对比当前 {count.all} 条样本里的模型家族、世界主题、技术栈与制作方式。点击图表中的任意条目，可直接回到工作台查看对应案例。
          </p>
        </header>

        <div className="metric-grid">
          {(
            [
              [Boxes, count.all, "收录案例", "neutral"],
              [Play, count.playable, "已验活可试玩", "ok"],
              [CodeXml, count.repos, "公开源码仓库", "blue"],
              [Layers3, models.length, "覆盖模型家族", "neutral"],
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
          <Bars title="模型家族" note="同一案例可计入多个家族；点击直接筛选" rows={models} filter="model" />
          <Bars
            title="世界主题"
            note="每个案例归属一个主主题"
            rows={frequencies((world) => [world.theme_category], themes)}
            filter="theme"
            accent="emerald-bars"
          />
          <Bars
            title="常用技术栈"
            percent
            note="出现于全部案例的比例，展示前 8 项；同一案例可使用多项技术"
            rows={frequencies((world) => world.tech_stack).slice(0, 8)}
            filter="tech"
          />
          <Bars title="案例发布时间" note="按已知的作品发布月份统计" rows={dates} filter="month" />
          <Bars
            title="生成方式"
            note="缺少作者说明的案例保留未知分类"
            rows={frequencies((world) => [world.generation_mode], modes)}
            filter="mode"
          />
          <Bars
            title="复现程度"
            note="按资料中最完整的公开入口归类"
            rows={frequencies((world) => [world.reproducibility_level], levels)}
            filter="level"
            accent="emerald-bars"
          />
          <Bars
            title="常用 Skill 与提示"
            note="按原资料中的工具名或提示记录归并，每个案例计一次"
            rows={frequencies((world) => world.skills_or_prompts_used).slice(0, 8)}
            filter="q"
          />
          <section className="panel chart-panel">
            <h2>工作流手册</h2>
            <p className="muted">从代表案例详情查看每类制作流程的具体步骤与原文。</p>
            <ul className="workflow-list">
              {workflowGroups.map((group) => (
                <li key={group.label}>
                  <strong>
                    {group.label} · {group.samples.length} 例
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

        <section className="panel trend-table">
          <h2>费用与耗时披露</h2>
          <p className="muted">
            {worlds.filter((w) => w.reported_cost_usd !== null).length} 条披露了可核实的美元费用，
            {worlds.filter((w) => w.reported_time_minutes !== null).length} 条披露了精确制作耗时。
          </p>
          {disclosed.length > 0 && (
            <div
              tabIndex={0}
              role="region"
              aria-labelledby="cost-table-caption"
              className="table-wrapper"
              style={{ marginTop: 12 }}
            >
              <table className="research-table cost-table">
                <caption id="cost-table-caption" className="sr-only">
                  披露费用与耗时的案例列表
                </caption>
                <thead>
                  <tr>
                    <th scope="col">案例</th>
                    <th scope="col">费用（USD）</th>
                    <th scope="col">耗时（分钟）</th>
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
                      <td>{world.reported_cost_usd ?? "未披露"}</td>
                      <td>{world.reported_time_minutes ?? "未披露"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel methodology" id="method">
          <h2>统计口径</h2>
          <p>
            数据来自公开原帖和项目页面，同一作品可使用多个模型。发布时间分布只反映收录样本，部分月份可能仍在补录。
          </p>
          <p>
            开源状态明确的案例中，{known.length} 条里有 {open.length} 条确认开源，其余{" "}
            {worlds.length - known.length} 条状态未知。成本和耗时仅采纳作者可核实的明确披露。
          </p>
          <p>
            已验活可试玩数取自浏览器实测验活结果；需要登录、暂待人工复核或失效的入口均单独标注，不混入已验活统计。
          </p>
        </section>
      </div>
    </Shell>
  );
}
