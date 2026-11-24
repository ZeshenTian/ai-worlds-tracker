import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  Braces,
  Heart,
  Info,
  Link,
} from "lucide-react";
import { labels } from "../lib/i18n";
import { original, type FeedItem, type Language } from "../lib/types";
interface Props {
  item: FeedItem;
  lang: Language;
  index: number;
  length: number;
  saved: boolean;
  move: (by: number) => void;
  save: () => void;
  info: () => void;
  share: () => void;
}
export function ActionRail({
  item,
  lang,
  index,
  length,
  saved,
  move,
  save,
  info,
  share,
}: Props) {
  const t = labels[lang],
    url = original(item);
  return (
    <aside className="rail" aria-label={t.feed}>
      <div className="rail-group">
        <button
          data-action="previous"
          aria-label={t.prev}
          title={t.prev}
          disabled={!index}
          onClick={() => move(-1)}
        >
          <ArrowUp />
        </button>
        <button
          data-action="next"
          aria-label={t.next}
          title={t.next}
          disabled={length < 2}
          onClick={() => move(1)}
        >
          <ArrowDown />
        </button>
      </div>
      <div className="rail-divider" />
      <div className="rail-group">
        <button
          data-action="save"
          aria-pressed={saved}
          aria-label={saved ? t.unsave : t.save}
          title={saved ? t.unsave : t.save}
          className={saved ? "liked" : ""}
          onClick={save}
        >
          <Heart fill={saved ? "currentColor" : "none"} />
        </button>
        <button
          data-action="info"
          aria-label={t.info}
          title={t.info}
          onClick={info}
        >
          <Info />
        </button>
        {item.repo_url && (
          <a
            data-action="repo"
            aria-label={t.repo}
            title={t.repo}
            href={item.repo_url}
            target="_blank"
            rel="noreferrer"
          >
            <Braces />
          </a>
        )}
        {url && (
          <a
            data-action="external"
            aria-label={t.original}
            title={t.original}
            href={url}
            target="_blank"
            rel="noreferrer"
          >
            <ArrowUpRight />
          </a>
        )}
        <button
          data-action="share"
          aria-label={t.share}
          title={t.share}
          onClick={share}
        >
          <Link />
        </button>
      </div>
    </aside>
  );
}
