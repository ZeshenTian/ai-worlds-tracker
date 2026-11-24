"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, CirclePlay, CodeXml, Search, X } from "lucide-react";
import { byline, caseHref, isPlayable, matchesWorldQuery, themes, worlds } from "@/lib/worlds";

export function CommandSearch({ isHome = false }: { isHome?: boolean }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const inlineQueryRef = useRef("");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [inlineQuery, setInlineQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const openModal = useCallback(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!dialog.open) {
      setQuery(isHome ? inlineQueryRef.current : "");
      setActiveIndex(0);
      setOpen(true);
      dialog.showModal();
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [isHome]);

  // Sync topbar inline search with URL on Home page
  useEffect(() => {
    if (!isHome) return;
    const syncFromUrl = () => {
      const q = new URLSearchParams(window.location.search).get("q") || "";
      inlineQueryRef.current = q;
      setInlineQuery(q);
    };
    const syncFromCatalog = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (typeof detail === "string") {
        inlineQueryRef.current = detail;
        setInlineQuery(detail);
      }
    };
    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);
    window.addEventListener("wb:query-sync", syncFromCatalog);
    return () => {
      window.removeEventListener("popstate", syncFromUrl);
      window.removeEventListener("wb:query-sync", syncFromCatalog);
    };
  }, [isHome]);

  // Global Cmd/Ctrl+K shortcut (opens modal dialog) and "/" shortcut
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openModal();
        return;
      }
      if (
        event.key === "/" &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        !(event.target instanceof HTMLInputElement) &&
        !(event.target instanceof HTMLTextAreaElement) &&
        !(event.target instanceof HTMLSelectElement)
      ) {
        event.preventDefault();
        if (isHome) {
          const topInput = document.getElementById("wb-global-search") as HTMLInputElement | null;
          if (topInput) {
            topInput.focus();
            topInput.select();
            return;
          }
        }
        openModal();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isHome, openModal]);

  // Light-dismiss fallback for browsers without native dialog closedby="any"
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const onClose = () => {
      setOpen(false);
      dialog.returnValue = "";
    };
    dialog.addEventListener("close", onClose);

    if ("closedBy" in HTMLDialogElement.prototype) {
      return () => dialog.removeEventListener("close", onClose);
    }
    const outside = (e: PointerEvent) => {
      const r = dialog.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    let pressedOutside = false;
    const onDown = (e: PointerEvent) => {
      pressedOutside = outside(e);
    };
    const onUp = (e: PointerEvent) => {
      if (pressedOutside && outside(e)) dialog.close();
      pressedOutside = false;
    };
    dialog.addEventListener("pointerdown", onDown);
    dialog.addEventListener("pointerup", onUp);
    return () => {
      dialog.removeEventListener("close", onClose);
      dialog.removeEventListener("pointerdown", onDown);
      dialog.removeEventListener("pointerup", onUp);
    };
  }, []);

  function closeModal() {
    const dialog = dialogRef.current;
    if (dialog?.open) dialog.close();
  }

  const matches = useMemo(
    () => worlds.filter((world) => matchesWorldQuery(world, query)).slice(0, 8),
    [query],
  );

  function applyToCatalog(value: string) {
    if (isHome) {
      setInlineQuery(value);
      window.dispatchEvent(new CustomEvent("wb:query-set", { detail: value }));
      closeModal();
    } else {
      const target = value.trim() ? `/?q=${encodeURIComponent(value.trim())}` : "/";
      window.location.href = target;
    }
  }

  function handleInlineChange(value: string) {
    inlineQueryRef.current = value;
    setInlineQuery(value);
    window.dispatchEvent(new CustomEvent("wb:query-set", { detail: value }));
  }

  return (
    <>
      {isHome ? (
        <div className="wb-search-bar">
          <Search size={15} className="wb-search-ico" aria-hidden="true" />
          <input
            id="wb-global-search"
            type="search"
            aria-label="搜索案例、作者、模型、技术栈或原文摘录"
            placeholder="搜索案例、作者、模型、技术栈或原文摘录…"
            value={inlineQuery}
            onChange={(e) => handleInlineChange(e.target.value)}
          />
          {inlineQuery ? (
            <button
              type="button"
              className="wb-search-clear"
              aria-label="清空搜索"
              onClick={() => handleInlineChange("")}
            >
              <X size={13} />
            </button>
          ) : (
            <button
              type="button"
              className="wb-kbd-btn"
              title="打开快捷搜索面板 (⌘K)"
              aria-label="打开快捷搜索面板"
              onClick={openModal}
            >
              ⌘K
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          className="wb-search-bar wb-search-trigger"
          onClick={openModal}
          aria-label="打开快捷搜索面板"
        >
          <Search size={15} className="wb-search-ico" aria-hidden="true" />
          <span className="wb-search-placeholder">搜索 {worlds.length} 个交互世界、模型或工作流…</span>
          <span className="wb-kbd">⌘K</span>
        </button>
      )}

      <dialog
        ref={dialogRef}
        className="cmd-dialog"
        aria-labelledby="cmd-dialog-title"
        {...({ closedby: "any" } as Record<string, string>)}
      >
        <div className="cmd-head">
          <h1 id="cmd-dialog-title" className="sr-only">
            快捷搜索世界案例
          </h1>
          <Search size={17} className="wb-search-ico" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            className="cmd-input"
            aria-label="搜索世界案例"
            placeholder="输入案例名、模型（Claude / GPT / Gemini）、技术栈或关键词…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIndex((i) => Math.min(Math.max(0, matches.length - 1), i + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => Math.max(0, i - 1));
              } else if (e.key === "Enter" && matches[activeIndex]) {
                e.preventDefault();
                window.location.href = caseHref(matches[activeIndex]);
              }
            }}
          />
          <form method="dialog">
            <button type="submit" className="icon-btn" aria-label="关闭快捷搜索">
              <X size={16} />
            </button>
          </form>
        </div>

        <div className="cmd-body">
          {query.trim() && (
            <button
              type="button"
              className="cmd-filter-cta"
              onClick={() => applyToCatalog(query)}
            >
              <Search size={14} />
              <span>在工作台目录中筛选 “{query.trim()}”</span>
              <ArrowUpRight size={14} />
            </button>
          )}
          {matches.length > 0 ? (
            <ul className="cmd-list" role="listbox" aria-label="匹配的案例">
              {matches.map((world, idx) => (
                <li key={world.world_id}>
                  <a
                    href={caseHref(world)}
                    className={idx === activeIndex ? "cmd-item active" : "cmd-item"}
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => closeModal()}
                  >
                    <div className="cmd-item-main">
                      <strong>{world.title}</strong>
                      <span>
                        {byline(world)} · {themes[world.theme_category] || "其他"}
                      </span>
                    </div>
                    <div className="cmd-item-meta">
                      {world.models_used[0] && <span className="pill-neutral">{world.models_used[0]}</span>}
                      {isPlayable(world) && (
                        <span className="pill-ok">
                          <CirclePlay size={12} /> 验活
                        </span>
                      )}
                      {world.repo_url && (
                        <span className="pill-blue">
                          <CodeXml size={12} /> 源码
                        </span>
                      )}
                    </div>
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="cmd-empty">没有找到与 “{query}” 匹配的案例。</p>
          )}
        </div>

        {open && (
          <div className="cmd-foot">
            <span>↑↓ 选择 · Enter 打开详情 · Esc 关闭</span>
            <span>共收录 {worlds.length} 个交互世界</span>
          </div>
        )}
      </dialog>
    </>
  );
}
