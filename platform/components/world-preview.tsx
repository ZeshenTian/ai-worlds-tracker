"use client";

import { CodeXml } from "lucide-react";
import { copy, useLang, type Lang } from "@/lib/i18n";
import { bestQuote, coverTint, sourceHost, themeLabel, type World } from "@/lib/worlds";

export function WorldPreview({
  world,
  variant = "card",
  lang: propLang,
}: {
  world: World;
  variant?: "card" | "detail";
  lang?: Lang;
}) {
  const [hookLang] = useLang();
  const lang = propLang ?? hookLang;
  const t = copy[lang];

  if (world.thumbnail_url) {
    const source = world.cover_source === "x_media"
      ? (lang === "en" ? "Original X media" : "X 原帖配图")
      : world.cover_source === "project_poster"
        ? (lang === "en" ? "Project page poster" : "作品页面海报")
      : world.cover_source === "project_media"
        ? (lang === "en" ? "Creator’s project image" : "作者项目配图")
        : (lang === "en" ? "Demo screenshot" : "试玩截图");
    return (
      <img
        src={world.thumbnail_url}
        alt={world.title + " · " + source}
        title={source}
        loading={variant === "detail" ? "eager" : "lazy"}
        width={960}
        height={540}
      />
    );
  }

  const tint = coverTint(world.theme_category);
  const quote = bestQuote(world);
  const host = sourceHost(world.original_post_url);
  const theme = themeLabel(world.theme_category, lang);

  return (
    <div className={`quote-cover tint-${tint} ${variant === "detail" ? "quote-cover-detail" : ""}`}>
      <div className="quote-cover-top">
        <span className="quote-kicker">{theme}</span>
        {world.is_open_source === true ? (
          <span className="quote-open-pill">
            <CodeXml size={11} aria-hidden="true" />
            {t.openSource}
          </span>
        ) : world.workflow_steps.length > 0 ? (
          <span className="quote-kicker">{t.workflowSteps(world.workflow_steps.length)}</span>
        ) : null}
      </div>
      <p className="quote-excerpt">“{quote}”</p>
      <div className="quote-cover-foot">
        {world.tech_stack.length > 0 ? (
          <span>{world.tech_stack.slice(0, 3).join(" · ")}</span>
        ) : host ? (
          <span>{host}</span>
        ) : null}
      </div>
    </div>
  );
}
