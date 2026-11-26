"use client";
/* eslint-disable @next/next/no-html-link-for-pages */
import type { ReactNode } from "react";
import { copy, useLang } from "@/lib/i18n";
import { feedBase } from "@/lib/worlds";
import { CommandSearch } from "./command-search";
import meta from "@/data/meta.json";
import { useSyncExternalStore } from "react";
const subscribe = () => () => {};
export function useFeedBase() {
  return useSyncExternalStore(
    subscribe,
    feedBase,
    () =>
      process.env.NEXT_PUBLIC_WORLDFEED_URL ||
      "https://worldfeed.space",
  );
}
export function Shell({
  children,
  isHome = false,
}: {
  children: ReactNode;
  active: "catalog";
  isHome?: boolean;
  hideFooter?: boolean;
}) {
  const [lang, toggle] = useLang(),
    t = copy[lang],
    base = useFeedBase();
  return (
    <>
      <header>
        <a className="wordmark" href="/">
          {t.brand}
        </a>
        <CommandSearch isHome={isHome} />
        <nav>
          <a href={base}>{lang === "en" ? "WorldFeed ↗" : "刷世界 ↗"}</a>
          <button onClick={toggle}>{t.langSwitchLabel}</button>
        </nav>
      </header>
      <main>{children}</main>
      <footer>
        {t.brand} · © {meta.last_updated_at.slice(0, 4)} ·{" "}
        {meta.last_updated_at.slice(0, 10)}
      </footer>
    </>
  );
}
