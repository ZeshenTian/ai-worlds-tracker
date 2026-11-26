import { useEffect, useState, useRef } from "react";
import { type FeedItem, type Language, titleOf } from "../lib/types";
export function StageCard({
  item,
  lang,
  bridge,
}: {
  item: FeedItem;
  lang: Language;
  bridge: (e: KeyboardEvent) => void;
}) {
  const [loaded, load] = useState(false),
    [slow, delay] = useState(false),
    frame = useRef<HTMLIFrameElement>(null),
    remove = useRef<() => void>(() => {});
  useEffect(() => {
    const t = setTimeout(() => delay(true), 4000);
    return () => {
      clearTimeout(t);
      remove.current();
    };
  }, []);
  const en = lang === "en";
  return (
    <section className="stage" data-world={item.world_id}>
      <iframe
        ref={frame}
        data-world-embed
        title={titleOf(item, lang)}
        src={item.embed_url!}
        sandbox="allow-scripts allow-same-origin allow-pointer-lock allow-popups allow-forms"
        allow="fullscreen; autoplay; xr-spatial-tracking; accelerometer; gyroscope"
        allowFullScreen
        referrerPolicy="no-referrer"
        onLoad={() => {
          load(true);
          remove.current();
          if (item.tier === "mirror") {
            try {
              const doc = frame.current!.contentDocument;
              if (doc) {
                doc.addEventListener("keydown", bridge, true);
                remove.current = () =>
                  doc.removeEventListener("keydown", bridge, true);
              }
            } catch {
              /* redirected away from the mirror */
            }
          }
        }}
      />
      {!loaded && slow && item.tier === "embed" && item.external_demo_url && (
        <a
          className="slow"
          href={item.external_demo_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {en
            ? "Slow to load? Press G for Original Link ↗"
            : "加载较慢？按 G 打开原始链接 ↗"}
        </a>
      )}
    </section>
  );
}
