import { useState, useEffect, useRef, useCallback } from "react";
import { type FeedItem } from "./lib/types";
import { readLang, readLikes, likesKey, store } from "./lib/storage";
import { TopBar } from "./components/TopBar";
import { StageCard } from "./components/StageCard";
export function App() {
  const [rows, setRows] = useState<FeedItem[]>([]),
    [i, index] = useState(0),
    [lang, setLang] = useState(readLang),
    [likes, setLikes] = useState(readLikes),
    [failed, fail] = useState(false);
  const touchY = useRef<number | null>(null);
  const main = useRef<HTMLElement>(null),
    item = rows[i],
    en = lang === "en";
  useEffect(() => {
    fetch("/data/feed.json")
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((list: FeedItem[]) => {
        const clean = list.filter(
          (w) =>
            w.model_era === "frontier" &&
            ["mirror", "embed"].includes(w.tier) &&
            w.embed_url,
        );
        index(
          Math.max(
            0,
            clean.findIndex(
              (w) =>
                w.world_id === new URLSearchParams(location.search).get("w"),
            ),
          ),
        );
        setRows(clean);
      })
      .catch(() => fail(true));
  }, []);
  const move = useCallback(
    (n: number) => {
      if (rows.length) {
        index((v) => (v + n + rows.length) % rows.length);
        window.focus();
        main.current?.focus({ preventScroll: true });
      }
    },
    [rows.length],
  );
  useEffect(() => {
    if (item) history.replaceState(null, "", "/?w=" + item.world_id);
  }, [item]);
  useEffect(() => {
    document.documentElement.lang = en ? "en" : "zh-CN";
  }, [en]);
  const toggleLike = useCallback(() => {
    if (!item) return;
    const id = item.world_id;
    const next = likes.includes(id) ? likes.filter(value => value !== id) : [...likes, id];
    setLikes(next);
    store(likesKey, JSON.stringify(next));
  }, [item, likes]);
  const handle = useCallback(
    (e: KeyboardEvent) => {
      if (!item || e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
      const k = e.key.toLowerCase();
      if (["arrowup", "k", "arrowdown", "j"].includes(k)) {
        e.preventDefault();
        e.stopPropagation();
        move(k === "arrowup" || k === "k" ? -1 : 1);
      } else if (k === "l") {
        toggleLike();
      } else if (k === "g" || k === "o") {
        const url = k === "g" ? item.external_demo_url : item.original_post_url;
        if (url) window.open(url, "_blank", "noopener,noreferrer");
      }
    },
    [item, move, toggleLike],
  );
  useEffect(() => {
    let last = 0;
    function wheel(e: WheelEvent) {
      if (Math.abs(e.deltaY) > 8 && Date.now() - last > 450) {
        last = Date.now();
        move(Math.sign(e.deltaY));
      }
    }
    function unlock() {
      if (!document.pointerLockElement) main.current?.focus();
    }
    window.addEventListener("keydown", handle);
    window.addEventListener("wheel", wheel, { passive: true });
    document.addEventListener("pointerlockchange", unlock);
    return () => {
      window.removeEventListener("keydown", handle);
      window.removeEventListener("wheel", wheel);
      document.removeEventListener("pointerlockchange", unlock);
    };
  }, [handle, move]);
  return (
    <main
      ref={main}
      tabIndex={-1}
      onTouchStart={(e) => {
        touchY.current = e.touches[0]?.clientY ?? null;
      }}
      onTouchEnd={(e) => {
        const start = touchY.current;
        touchY.current = null;
        if (start !== null) {
          const delta = start - e.changedTouches[0].clientY;
          if (Math.abs(delta) > 55) move(Math.sign(delta));
        }
      }}
      onPointerDown={(e) => {
        if (!(e.target as HTMLElement).closest("iframe,input"))
          main.current?.focus({ preventScroll: true });
      }}
    >
      <TopBar
        lang={lang}
        item={item}
        position={i + 1}
        total={rows.length}
        move={move}
        liked={!!item && likes.includes(item.world_id)}
        toggleLike={toggleLike}
        reset={() => {
          index(0);
          main.current?.focus();
        }}
        toggle={() => {
          const l = en ? "zh" : "en";
          setLang(l);
          store("atlas-lang", l);
        }}
      />
      {item ? (
        <>
          <StageCard
            key={item.world_id}
            item={item}
            lang={lang}
            bridge={(e) => {
              if (e.key.startsWith("Arrow")) handle(e);
            }}
          />
        </>
      ) : (
        <p>
          {failed
            ? en
              ? "Feed unavailable"
              : "加载失败"
            : en
              ? "Loading…"
              : "加载中…"}
        </p>
      )}
    </main>
  );
}
