"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, CirclePlay, CodeXml, Search, X } from "lucide-react";
import { copy, useLang } from "@/lib/i18n";
import { byline, caseHref, isPlayable, themeLabel, themes, themesEn, worlds } from "@/lib/worlds";

export function CommandSearch({ isHome = false }: { isHome?: boolean }) {
  const [lang] = useLang();
  const t = copy[lang];
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

  const matches = useMemo(() => {
    const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const list = worlds.filter((w) => {
      if (!terms.length) return true;
      const hay = [
        w.title,
        w.summary,
        w.author_name,
        w.author_handle,
        themes[w.theme_category],
        themesEn[w.theme_category],
        ...w.models_used,
        ...w.tech_stack,
        ...w.evidence_quotes,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase();
      return terms.every((term) => hay.includes(term));
    });
    return list.slice(0, 8);
  }, [query]);

  function applyToCatalog(value: string) {
    if (isHome) {
      inlineQueryRef.current = value;
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
            aria-label={t.searchPlaceholder}
            placeholder={t.searchPlaceholder}
            value={inlineQuery}
            onChange={(e) => handleInlineChange(e.target.value)}
          />
          {inlineQuery ? (
            <button
              type="button"
              className="wb-search-clear"
              aria-label={t.searchClear}
              onClick={() => handleInlineChange("")}
            >
              <X size={13} />
            </button>
          ) : (
            <button
              type="button"
              className="wb-kbd-btn"
              title={`${t.searchOpen} (⌘K)`}
              aria-label={t.searchOpen}
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
          aria-label={t.searchOpen}
        >
          <Search size={15} className="wb-search-ico" aria-hidden="true" />
          <span className="wb-search-placeholder">{t.searchPlaceholder}</span>
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
            {t.searchOpen}
          </h1>
          <Search size={17} className="wb-search-ico" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            className="cmd-input"
            placeholder={t.searchModalPlaceholder}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIndex((i) => Math.min(matches.length - 1, i + 1));
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
            <button type="submit" className="icon-btn" aria-label={t.searchClose}>
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
              <span>{t.searchFilterCta(query.trim())}</span>
              <ArrowUpRight size={14} />
            </button>
          )}
          {matches.length > 0 ? (
            <ul className="cmd-list" role="listbox" aria-label={t.searchOpen}>
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
                        {byline(world, lang)} · {themeLabel(world.theme_category, lang)}
                      </span>
                    </div>
                    <div className="cmd-item-meta">
                      {world.models_used[0] && <span className="pill-neutral">{world.models_used[0]}</span>}
                      {isPlayable(world) && (
                        <span className="pill-ok">
                          <CirclePlay size={12} /> {t.play}
                        </span>
                      )}
                      {world.repo_url && (
                        <span className="pill-blue">
                          <CodeXml size={12} /> {t.sourceCode}
                        </span>
                      )}
                    </div>
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="cmd-empty">{t.searchEmpty(query)}</p>
          )}
        </div>

        {open && (
          <div className="cmd-foot">
            <span>{t.searchHints}</span>
            <span>{t.totalCount(worlds.length)}</span>
          </div>
        )}
      </dialog>
    </>
  );
}
