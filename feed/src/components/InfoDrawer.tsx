import { useEffect, useRef } from "react";
import { ArrowUpRight, X } from "lucide-react";
import { labels } from "../lib/i18n";
import { titleOf, type FeedItem, type Language } from "../lib/types";
interface Props {
  item: FeedItem;
  lang: Language;
  close: () => void;
}
export function InfoDrawer({ item, lang, close }: Props) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    panel.current?.querySelector("button")?.focus();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, []);
  const t = labels[lang],
    en = lang === "en",
    steps = en ? item.workflow_steps_en : item.workflow_steps_zh,
    skills = en ? item.skills_en : item.skills_zh;
  const quotes = item.evidence_quotes.filter(
    (q) =>
      !en ||
      !/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u.test(
        q,
      ),
  );
  const groups: [string, string[]][] = [
    [t.model, en ? item.models_used_en : item.models_used],
    [t.tech, en ? item.tech_stack_en : item.tech_stack],
    [t.skills, skills],
  ];
  return (
    <div
      className="drawer-layer"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <section
        ref={panel}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onKeyDown={(e) => {
          if (e.key !== "Tab") return;
          const nodes =
            panel.current?.querySelectorAll<HTMLElement>("button,a[href]");
          if (!nodes?.length) return;
          const first = nodes[0],
            last = nodes[nodes.length - 1];
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
          if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }}
      >
        <header>
          <span>{t.info}</span>
          <button aria-label={t.close} onClick={close}>
            <X size={19} />
          </button>
        </header>
        <div className="drawer-scroll">
          <div className="detail-badges">
            <span className={item.tier === "external" ? "neutral" : "green"}>
              {t[item.tier]}
            </span>
            {item.is_open_source && <span>{t.openSource}</span>}
          </div>
          <h2 id="drawer-title">{titleOf(item, lang)}</h2>
          <p className="summary">{en ? item.summary_en : item.summary_zh}</p>
          {groups.map(
            ([name, values]) =>
              values.length > 0 && (
                <section key={name}>
                  <h3>{name}</h3>
                  <div className="chips">
                    {values.map((v) => (
                      <span key={v}>{v}</span>
                    ))}
                  </div>
                </section>
              ),
          )}
          {steps.length > 0 && (
            <section>
              <h3>{t.workflow}</h3>
              <ol>
                {steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            </section>
          )}
          {(quotes.length > 0 || item.original_post_url) && (
            <section>
              <h3>{t.evidence}</h3>
              {quotes.map((q) => (
                <blockquote key={q}>{q}</blockquote>
              ))}
              {item.original_post_url && (
                <a
                  href={item.original_post_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {t.reference}
                  <ArrowUpRight size={14} />
                </a>
              )}
            </section>
          )}
        </div>
      </section>
    </div>
  );
}
