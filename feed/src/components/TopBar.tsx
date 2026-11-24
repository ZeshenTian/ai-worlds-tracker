import { ArrowUpRight, BookOpen, Layers3 } from "lucide-react";
import { channels, labels } from "../lib/i18n";
import { tabs, type Tab, type Language } from "../lib/types";

export function TopBar({
  lang,
  tab,
  select,
  toggle,
}: {
  lang: Language;
  tab: Tab;
  select: (t: Tab) => void;
  toggle: () => void;
}) {
  const t = labels[lang];
  return (
    <header className="topbar">
      <button
        className="wordmark"
        onClick={() => select("for-you")}
        aria-label="WorldFeed"
      >
        <span className="brand-icon">
          <Layers3 size={20} />
        </span>
        WorldFeed
      </button>
      <nav aria-label={t.channel}>
        {tabs.map((key) => (
          <button
            key={key}
            data-tab={key}
            aria-current={tab === key ? "page" : undefined}
            onClick={() => select(key)}
          >
            {channels[lang][key]}
          </button>
        ))}
      </nav>
      <div className="top-actions">
        <button className="lang" aria-label={t.language} onClick={toggle}>
          {t.languageButton}
        </button>
        <a
          className="atlas"
          href="https://generated-worlds-atlas.zeshentian1.chatgpt.site/"
          target="_blank"
          rel="noreferrer"
          aria-label={t.atlas}
        >
          <BookOpen size={14} />
          <span>{t.atlas}</span>
          <ArrowUpRight size={13} />
        </a>
      </div>
    </header>
  );
}
