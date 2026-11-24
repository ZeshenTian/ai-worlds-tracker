import { useEffect, useRef, useState } from "react";
import { Heart, LoaderCircle, Check } from "lucide-react";
import { TopBar } from "./components/TopBar";
import { StageCard } from "./components/StageCard";
import { ActionRail } from "./components/ActionRail";
import { InfoDrawer } from "./components/InfoDrawer";
import { ShortcutsHint } from "./components/ShortcutsHint";
import { labels } from "./lib/i18n";
import { readIDs, readLang, store, savedKey, seenKey } from "./lib/storage";
import {
  inChannel,
  original,
  tabs,
  type FeedItem,
  type Tab,
  type PlayState,
} from "./lib/types";

function locationState() {
  const params = new URLSearchParams(location.search),
    raw = params.get("tab") as Tab;
  return {
    tab: tabs.includes(raw) ? raw : ("for-you" as Tab),
    id: params.get("w") || "",
  };
}
function preload(w: FeedItem | undefined) {
  if (w?.thumbnail_url) {
    const img = new Image();
    img.src = w.thumbnail_url;
  }
  if (w?.preview_video_url) {
    const video = document.createElement("video");
    video.preload = "metadata";
    video.src = w.preview_video_url;
    return () => {
      video.removeAttribute("src");
      video.load();
    };
  }
}
export function App() {
  const [worlds, setWorlds] = useState<FeedItem[]>([]),
    [failed, setFailed] = useState(false);
  const [lang, setLang] = useState(readLang),
    [favorites, setFavorites] = useState(() => readIDs(savedKey));
  const [selection, setSelection] = useState(locationState),
    [linked, setLinked] = useState(() => locationState().id);
  const [mode, setMode] = useState<PlayState>("browse"),
    [drawer, setDrawer] = useState(false),
    [notice, setNotice] = useState("");
  const [manualLink, setManualLink] = useState("");
  const seen = useRef(new Set(readIDs(seenKey)));
  const wheel = useRef({ sum: 0, last: 0, locked: false });
  const t = labels[lang],
    { id } = selection;
  const direct = linked && worlds.find((w) => w.world_id === linked);
  // A shared URL can name a channel the recipient cannot use (especially Saved).
  const tab =
    direct && !inChannel(direct, selection.tab, favorites)
      ? "for-you"
      : selection.tab;
  const filtered = worlds.filter((w) => inChannel(w, tab, favorites));
  if (direct && !filtered.some((w) => w.world_id === direct.world_id))
    filtered.unshift(direct);
  const index = Math.max(
      0,
      filtered.findIndex((w) => w.world_id === id),
    ),
    item = filtered[index];
  const activeId = item?.world_id,
    previous = filtered[index - 1],
    next =
      filtered.length > 1 ? filtered[(index + 1) % filtered.length] : undefined;
  useEffect(() => {
    const controller = new AbortController();
    fetch("/data/feed.json", { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((data) => {
        if (!Array.isArray(data) || !data.length) throw Error();
        setWorlds(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const onPop = () => {
      const s = locationState();
      setLinked(s.id);
      setSelection(s);
      resetPlay();
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    if (!worlds.length) return;
    const url = new URL(location.href);
    if (activeId) url.searchParams.set("w", activeId);
    else url.searchParams.delete("w");
    url.searchParams.set("tab", tab);
    history.replaceState(null, "", url);
    if (activeId && !seen.current.has(activeId)) {
      seen.current.add(activeId);
      store(seenKey, JSON.stringify([...seen.current]));
    }
  }, [activeId, tab, worlds]);
  useEffect(() => {
    document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
    store("atlas-lang", lang);
  }, [lang]);
  useEffect(() => {
    const cleanups = [preload(previous), preload(next)];
    return () => cleanups.forEach((fn) => fn?.());
  }, [previous, next]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 1800);
    return () => clearTimeout(timer);
  }, [notice]);
  function resetPlay() {
    setMode("browse");
    setDrawer(false);
    setManualLink("");
    setNotice("");
  }
  function move(by: number) {
    if (!filtered.length || (by < 0 && index === 0) || filtered.length < 2)
      return;
    const target = filtered[(index + by + filtered.length) % filtered.length];
    resetPlay();
    setLinked("");
    setSelection({ tab, id: target.world_id });
  }
  function select(target: Tab) {
    resetPlay();
    setLinked("");
    setSelection({ tab: target, id: "" });
  }
  function save() {
    if (!item) return;
    const updated = favorites.includes(item.world_id)
      ? favorites.filter((id) => id !== item.world_id)
      : [...favorites, item.world_id];
    if (tab === "favorites" && !updated.includes(item.world_id)) {
      resetPlay();
      setLinked("");
      setSelection({ tab, id: next?.world_id || "" });
    }
    setFavorites(updated);
    store(savedKey, JSON.stringify(updated));
  }
  function start() {
    if (!item || mode !== "browse") return;
    if (item.tier !== "external" && item.embed_url) {
      setMode("loading");
      return;
    }
    const url = original(item);
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  }
  function info() {
    setMode("browse");
    setDrawer((v) => !v);
  }
  async function share() {
    if (!item) return;
    const url = new URL("/", location.origin);
    url.searchParams.set("w", item.world_id);
    try {
      await navigator.clipboard.writeText(url.href);
      setNotice(t.copied);
    } catch {
      setManualLink(url.href);
    }
  }
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (
        e.ctrlKey ||
        e.metaKey ||
        e.altKey ||
        e.repeat ||
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;
      if (e.key === "Escape") {
        resetPlay();
        return;
      }
      if (drawer) {
        if (e.key.toLowerCase() === "i") {
          e.preventDefault();
          setDrawer(false);
        }
        return;
      }
      if (mode !== "browse" || manualLink || !item) return;
      const key = e.key.toLowerCase();
      if (
        (key === " " || key === "enter") &&
        e.target instanceof Element &&
        e.target.closest("button,a")
      )
        return;
      switch (key) {
        case "arrowdown":
        case "j":
          e.preventDefault();
          move(1);
          break;
        case "arrowup":
        case "k":
          e.preventDefault();
          move(-1);
          break;
        case " ":
        case "enter":
          e.preventDefault();
          start();
          break;
        case "i":
          e.preventDefault();
          info();
          break;
        case "l":
          e.preventDefault();
          save();
          break;
      }
    }
    function onWheel(e: WheelEvent) {
      if (
        mode !== "browse" ||
        drawer ||
        !item ||
        e.ctrlKey ||
        Math.abs(e.deltaX) > Math.abs(e.deltaY) ||
        (e.target instanceof Element && e.target.closest("nav,.drawer"))
      )
        return;
      e.preventDefault();
      const s = wheel.current,
        now = performance.now();
      // Keep the lock through the inertial tail. A fresh gesture after a quiet interval can navigate again.
      if (now - s.last > 420) {
        s.sum = 0;
        s.locked = false;
      }
      s.last = now;
      if (s.locked) return;
      const dy =
        e.deltaY *
        (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? innerHeight : 1);
      if (Math.sign(s.sum) !== Math.sign(dy)) s.sum = 0;
      s.sum += dy;
      if (Math.abs(s.sum) >= 60) {
        s.locked = true;
        move(s.sum > 0 ? 1 : -1);
        s.sum = 0;
      }
    }
    function outside(e: PointerEvent) {
      if (
        mode !== "browse" &&
        e.target instanceof Element &&
        !e.target.closest("[data-world-frame],[data-playbar],.rail")
      )
        setMode("browse");
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("pointerdown", outside);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("pointerdown", outside);
    };
  });
  return (
    <>
      <TopBar
        lang={lang}
        tab={tab}
        select={select}
        toggle={() => setLang(lang === "en" ? "zh" : "en")}
      />
      {item ? (
        <main className="view">
          <div className="theatre-layout">
            <StageCard
              key={item.world_id}
              item={item}
              lang={lang}
              mode={mode}
              start={start}
              exit={() => setMode("browse")}
              loaded={() =>
                setMode((current) =>
                  current === "loading" ? "playing" : current,
                )
              }
              move={move}
            />
            <ActionRail
              item={item}
              lang={lang}
              index={index}
              length={filtered.length}
              saved={favorites.includes(item.world_id)}
              move={move}
              save={save}
              info={info}
              share={share}
            />
          </div>
          <ShortcutsHint lang={lang} />
        </main>
      ) : (
        <main className="empty">
          {!worlds.length && !failed ? (
            <LoaderCircle className="spin" aria-label={t.loading} />
          ) : (
            <>
              <Heart size={30} />
              <h1>
                {failed ? t.error : tab === "favorites" ? t.empty : t.noItems}
              </h1>
              {tab === "favorites" && <p>{t.collect}</p>}
              <button
                className="empty-action"
                onClick={() => (failed ? location.reload() : select("for-you"))}
              >
                {failed ? t.retry : t.discover}
              </button>
            </>
          )}
        </main>
      )}
      {drawer && item && (
        <InfoDrawer item={item} lang={lang} close={() => setDrawer(false)} />
      )}
      {notice && (
        <div className="toast" role="status">
          <Check size={16} />
          {notice}
        </div>
      )}
      {manualLink && (
        <div className="manual">
          <label>
            {t.copyFailed}
            <input
              readOnly
              autoFocus
              value={manualLink}
              onFocus={(e) => e.currentTarget.select()}
            />
          </label>
          <button onClick={() => setManualLink("")}>{t.close}</button>
        </div>
      )}
    </>
  );
}
