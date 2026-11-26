import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  Heart,
  Library,
} from "lucide-react";
import { titleOf, type FeedItem, type Language } from "../lib/types";

interface TopBarProps {
  lang: Language;
  item?: FeedItem;
  position: number;
  total: number;
  liked: boolean;
  toggleLike: () => void;
  move: (direction: number) => void;
  reset: () => void;
  toggle: () => void;
}

function ShortcutHelp({ en }: { en: boolean }) {
  const [open, setOpen] = useState(false);
  const control = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent | FocusEvent) => {
      if (!control.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", dismiss);
    window.addEventListener("focusin", dismiss);
    const blur = () => setOpen(false);
    window.addEventListener("blur", blur);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", dismiss);
      window.removeEventListener("focusin", dismiss);
      window.removeEventListener("blur", blur);
      window.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <div
      className="help"
      ref={control}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        className="help-trigger"
        aria-expanded={open}
        aria-controls="shortcuts"
        aria-label={en ? "Keyboard shortcuts" : "快捷键"}
        onClick={() => setOpen(true)}
      >
        ?
      </button>
      {open && (
        <div id="shortcuts" role="note">
          {en
            ? "WASD Play · ↑↓ / Top bar wheel Switch · L Like · G Original link · O Post"
            : "WASD 游玩 · ↑↓ / 顶栏滚轮 切世界 · L 点赞 · G 原始链接 · O 原帖"}
        </div>
      )}
    </div>
  );
}

export function TopBar({
  lang,
  item,
  position,
  total,
  liked,
  toggleLike,
  move,
  reset,
  toggle,
}: TopBarProps) {
  const en = lang === "en";
  const atlas =
    import.meta.env.VITE_ATLAS_URL ||
    (["localhost", "127.0.0.1"].includes(location.hostname)
      ? "http://127.0.0.1:8870"
      : "https://generated-worlds-atlas.zeshentian1.chatgpt.site/");
  const title = item && titleOf(item, lang);
  const author = item && (en ? item.author_en : item.author);
  return (
    <header className="topbar">
      <div className="identity">
        <button className="brand" onClick={reset}>
          WorldFeed
        </button>
        {item && (
          <>
            <i className="divider" aria-hidden="true" />
            <strong className="world-name" title={title}>
              {title}
            </strong>
            <span className="author" title={author}>
              {author}
            </span>
            {item.primary_model && (
              <span
                className="model"
                data-family={item.model_family}
                aria-label={item.primary_model}
                title={item.primary_model}
              >
                <span className="full-model">{item.primary_model}</span>
                <span className="short-model">
                  {item.primary_model.replace(
                    /^(Claude |GPT-|Gemini )(?=.)/,
                    "",
                  )}
                </span>
              </span>
            )}
          </>
        )}
      </div>
      {item && (
        <div className="controls">
          <div className="switcher pill">
            <button
              aria-label={en ? "Previous world" : "上一个世界"}
              data-action="prev"
              onClick={() => move(-1)}
            >
              <ArrowUp />
            </button>
            <span>
              {position} / {total}
            </span>
            <button
              aria-label={en ? "Next world" : "下一个世界"}
              data-action="next"
              onClick={() => move(1)}
            >
              <ArrowDown />
            </button>
          </div>
          <button className="pill like" data-action="like" aria-pressed={liked}
            aria-label={en ? "Like" : "点赞"} onClick={toggleLike}>
            <Heart aria-hidden="true" />
            <small>{item.x_likes + Number(liked)}</small>
          </button>
          {item.external_demo_url && (
            <a
              className="pill official"
              data-action="official"
              aria-label={en ? "Original link" : "原始链接"}
              title={en ? "Original link" : "原始链接"}
              href={item.external_demo_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span>{en ? "Original link" : "原始链接"}</span>
              <ArrowUpRight />
            </a>
          )}
          {item.repo_url && (
            <a
              className="pill repo"
              data-action="repo"
              href={item.repo_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {en ? "Code" : "源码"}
            </a>
          )}
          <ShortcutHelp en={en} />
        </div>
      )}
      <nav className="destinations">
        <i className="divider" aria-hidden="true" />
        <button className="lang" onClick={toggle}>
          {en ? "中文" : "EN"}
        </button>
        <a className="atlas" href={atlas} aria-label={en ? "Atlas" : "图鉴"}>
          <Library className="atlas-icon" />
          <span>{en ? "Atlas" : "图鉴"}</span>
          <ArrowUpRight className="external-icon" />
        </a>
      </nav>
    </header>
  );
}
