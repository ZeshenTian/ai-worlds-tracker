"use client";
import { useEffect, useState } from "react";

export function UpdateTime({ iso }: {iso: string}) {
  const date = new Date(iso);
  const [label, setLabel] = useState(iso.slice(0, 10));
  useEffect(() => {
    function update() {
      const hours = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 3600000));
      setLabel(hours < 1 ? "刚刚" : hours < 24 ? hours + " 小时前" : Math.floor(hours / 24) + " 天前");
    }
    update();
    const timer = window.setInterval(update, 60000);
    return () => window.clearInterval(timer);
  }, [iso]);
  return <time dateTime={iso} title={date.toISOString()}>{label}</time>;
}
