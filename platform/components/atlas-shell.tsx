"use client";
/* eslint-disable @next/next/no-html-link-for-pages */

import { Aperture, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { copy, useLang } from "@/lib/i18n";
import { submissionUrl } from "@/lib/worlds";
import { CommandSearch } from "./command-search";

export function Header({
  active,
  isHome = false,
}: {
  active: "catalog" | "trends" | "submit";
  isHome?: boolean;
}) {
  const [lang, toggleLang] = useLang();
  const t = copy[lang];

  return (
    <header className="wb-topbar">
      <div className={isHome ? "wb-topbar-inner wb-topbar-full" : "wb-topbar-inner container"}>
        <div className="wb-brand-group">
          <a className="brand" href="/" aria-label={t.brand}>
            <span className="brand-icon" aria-hidden="true">
              <Aperture size={17} strokeWidth={1.9} />
            </span>
            <span className="brand-name">{t.brand}</span>
          </a>
        </div>

        <CommandSearch isHome={isHome} />

        <div className="wb-nav-group">
          <nav aria-label="Primary" className="primary-nav">
            <a href="/" aria-current={active === "catalog" ? "page" : undefined}>
              {t.navCatalog}
            </a>
            <a href="/trends" aria-current={active === "trends" ? "page" : undefined}>
              {t.navTrends}
            </a>
          </nav>

          <button
            type="button"
            className="lang-toggle"
            onClick={toggleLang}
            aria-label={t.langSwitchAria}
            title={t.langSwitchAria}
          >
            {t.langSwitchLabel}
          </button>

          <a
            className="button button-primary nav-submit"
            href={submissionUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-current={active === "submit" ? "page" : undefined}
          >
            <Plus size={15} strokeWidth={2.2} />
            <span>{t.submit}</span>
          </a>
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  const [lang] = useLang();
  const t = copy[lang];

  return (
    <footer className="site-footer">
      <div className="container footer-inner">
        <a className="brand" href="/">
          <Aperture size={16} />
          <span>{t.brand}</span>
        </a>
        <span>{t.footerNote}</span>
        <a href="/trends#method" className="text-link">
          {t.footerMethod}
        </a>
      </div>
    </footer>
  );
}

export function Shell({
  active,
  isHome = false,
  hideFooter = false,
  children,
}: {
  active: "catalog" | "trends" | "submit";
  isHome?: boolean;
  hideFooter?: boolean;
  children: ReactNode;
}) {
  const [lang] = useLang();
  const t = copy[lang];

  return (
    <>
      <a href="#main" className="skip-link">
        {t.skipLink}
      </a>
      <Header active={active} isHome={isHome} />
      <main id="main" className={isHome ? "wb-page-main" : undefined}>
        {children}
      </main>
      {!hideFooter && <Footer />}
    </>
  );
}
