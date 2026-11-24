"use client";

import { useEffect, useState } from "react";
import { copy, useLang } from "@/lib/i18n";

export function UpdateTime({ iso }: { iso: string }) {
  const [lang] = useLang();
  const t = copy[lang];
  const date = new Date(iso);
  const [hours, setHours] = useState<number | null>(null);

  useEffect(() => {
    function update() {
      setHours(Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 3600000)));
    }
    update();
    const timer = window.setInterval(update, 60000);
    return () => window.clearInterval(timer);
  }, [iso]);

  const label =
    hours === null
      ? iso.slice(0, 10)
      : hours < 1
        ? t.justNow
        : hours < 24
          ? t.hoursAgo(hours)
          : t.daysAgo(Math.floor(hours / 24));

  return (
    <time dateTime={iso} title={date.toISOString()}>
      {label}
    </time>
  );
}
