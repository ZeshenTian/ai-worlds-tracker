import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  CircleUserRound,
  Globe2,
  LoaderCircle,
  Play,
  X,
} from "lucide-react";
import { labels } from "../lib/i18n";
import {
  original,
  titleOf,
  type FeedItem,
  type Language,
  type PlayState,
} from "../lib/types";

interface Props {
  item: FeedItem;
  lang: Language;
  mode: PlayState;
  start: () => void;
  exit: () => void;
  loaded: () => void;
  move: (n: number) => void;
}
export function StageCard({
  item,
  lang,
  mode,
  start,
  exit,
  loaded,
  move,
}: Props) {
  const t = labels[lang],
    title = titleOf(item, lang),
    author = lang === "en" ? item.author_en : item.author;
  const [slow, setSlow] = useState(false);
  const point = useRef<{ x: number; y: number } | null>(null),
    swiped = useRef(0);
  const url = original(item);
  useEffect(() => {
    setSlow(false);
    if (mode !== "loading") return;
    const timer = window.setTimeout(() => setSlow(true), 4000);
    return () => window.clearTimeout(timer);
  }, [mode, item.world_id]);
  return (
    <section
      className={"theatre " + (mode === "browse" ? "browsing" : "active")}
      data-world={item.world_id}
      data-mode={mode}
      data-tier={item.tier}
      aria-label={title}
    >
      {mode !== "browse" && (
        <div className="playbar" data-playbar>
          <span className="live-state">
            {mode === "loading" ? (
              <LoaderCircle size={14} className="spin" />
            ) : (
              <i />
            )}
            {mode === "loading" ? t.loading : t.playing}
          </span>
          <span className="switch-hint">{t.switchHint}</span>
          {(slow || mode === "playing") && url && (
            <a
              data-action="recovery"
              href={url}
              target="_blank"
              rel="noreferrer"
            >
              {t.recovery}
              <ArrowUpRight size={13} />
            </a>
          )}
          <button data-action="exit" onClick={exit}>
            <X size={14} />
            {t.exit}
          </button>
        </div>
      )}
      <div
        className="frame"
        data-world-frame
        onTouchStart={(e) => {
          const p = e.touches[0];
          point.current =
            mode === "browse" && e.touches.length === 1
              ? { x: p.clientX, y: p.clientY }
              : null;
        }}
        onTouchCancel={() => {
          point.current = null;
        }}
        onTouchEnd={(e) => {
          if (!point.current || mode !== "browse") return;
          const p = e.changedTouches[0],
            dy = p.clientY - point.current.y,
            dx = p.clientX - point.current.x;
          point.current = null;
          if (Math.abs(dy) > 50 && Math.abs(dy) > Math.abs(dx)) {
            swiped.current = performance.now();
            move(dy < 0 ? 1 : -1);
          }
        }}
      >
        {mode === "browse" ? (
          <>
            <div
              className="visual"
              onClick={() => {
                if (!swiped.current || performance.now() - swiped.current > 400)
                  start();
              }}
            >
              {item.preview_video_url ? (
                <video
                  src={item.preview_video_url}
                  poster={item.thumbnail_url || undefined}
                  autoPlay
                  muted
                  loop
                  playsInline
                />
              ) : item.thumbnail_url ? (
                <img
                  src={item.thumbnail_url}
                  alt={title}
                  loading="eager"
                  fetchPriority="high"
                  draggable={false}
                />
              ) : (
                <div className="no-preview">
                  <Globe2 strokeWidth={0.75} aria-hidden="true" />
                </div>
              )}
            </div>
            <div className="caption">
              <h1>{title}</h1>
              <div className="credits">
                {author && (
                  <span className="author">
                    <CircleUserRound size={15} />
                    {author}
                  </span>
                )}
                {(lang === "en" ? item.models_used_en : item.models_used).map(
                  (model) => (
                    <span key={model} className="model-badge">
                      {model}
                    </span>
                  ),
                )}
              </div>
            </div>
            {item.tier === "external" && url ? (
              <a
                className="primary"
                data-action="start"
                href={url}
                target="_blank"
                rel="noreferrer"
              >
                <ArrowUpRight size={17} />
                {item.external_demo_url ? t.visit : t.source}
              </a>
            ) : (
              item.embed_url && (
                <button className="primary" data-action="start" onClick={start}>
                  <Play size={15} fill="currentColor" />
                  {t.play}
                </button>
              )
            )}
          </>
        ) : (
          <iframe
            data-world-embed
            title={title}
            src={item.embed_url!}
            onLoad={loaded}
            sandbox="allow-scripts allow-same-origin allow-pointer-lock allow-popups allow-forms"
            allow="fullscreen; autoplay; xr-spatial-tracking; accelerometer; gyroscope"
            allowFullScreen
            referrerPolicy="no-referrer"
          />
        )}
      </div>
    </section>
  );
}
