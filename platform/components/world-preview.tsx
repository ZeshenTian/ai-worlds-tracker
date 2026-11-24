import { CodeXml } from "lucide-react";
import {
  bestQuote,
  coverTint,
  sourceHost,
  themes,
  type World,
} from "@/lib/worlds";

export function WorldPreview({
  world,
  variant = "card",
}: {
  world: World;
  variant?: "card" | "detail";
}) {
  if (world.thumbnail_url) {
    return (
      <img
        src={world.thumbnail_url}
        alt={`${world.title} 的试玩画面`}
        loading={variant === "detail" ? "eager" : "lazy"}
        width={960}
        height={540}
      />
    );
  }

  const tint = coverTint(world.theme_category);
  const quote = bestQuote(world);
  const host = sourceHost(world.original_post_url);
  const kicker =
    world.workflow_steps.length > 0
      ? `含 ${world.workflow_steps.length} 步工作流 · 无实景图`
      : world.source_kind === "primary_page"
        ? "作品原文摘录 · 无实景图"
        : "作者原帖摘录 · 无实景图";

  return (
    <div className={`quote-cover tint-${tint} ${variant === "detail" ? "quote-cover-detail" : ""}`}>
      <div className="quote-cover-top">
        <span className="quote-kicker">{kicker}</span>
        {world.is_open_source === true && (
          <span className="quote-open-pill">
            <CodeXml size={11} aria-hidden="true" />
            开源
          </span>
        )}
      </div>
      <p className="quote-excerpt">“{quote}”</p>
      <div className="quote-cover-foot">
        <span>{themes[world.theme_category] || "其他"}</span>
        {world.tech_stack.length > 0 ? (
          <>
            <span aria-hidden="true">·</span>
            <span>{world.tech_stack.slice(0, 3).join(" · ")}</span>
          </>
        ) : host ? (
          <>
            <span aria-hidden="true">·</span>
            <span>{host}</span>
          </>
        ) : null}
      </div>
    </div>
  );
}
