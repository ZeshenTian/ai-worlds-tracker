"use client";
/* eslint-disable @next/next/no-html-link-for-pages */

import { Shell } from "@/components/atlas-shell";
import { copy, useLang } from "@/lib/i18n";

export default function NotFound() {
  const [lang] = useLang();
  const t = copy[lang];

  return (
    <Shell active="catalog">
      <div className="container subpage empty-state">
        <h1>{t.notFoundTitle}</h1>
        <p>{t.notFoundHint}</p>
        <a className="button button-primary" href="/">
          {t.backToCatalog}
        </a>
      </div>
    </Shell>
  );
}
