import { labels } from "../lib/i18n";
import type { Language } from "../lib/types";
export function ShortcutsHint({ lang }: { lang: Language }) {
  const t = labels[lang];
  return (
    <footer className="hints" aria-hidden="true">
      <span>
        <kbd>↑</kbd>
        <kbd>↓</kbd>
        {t.browse}
      </span>
      <span>
        <kbd>Space</kbd>
        {t.keysPlay}
      </span>
      <span>
        <kbd>I</kbd>
        {t.keysInfo}
      </span>
      <span>
        <kbd>L</kbd>
        {t.keysSave}
      </span>
    </footer>
  );
}
