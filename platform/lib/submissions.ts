import { z } from "zod";
import { themes, webLink } from "@/lib/worlds";

const url = z.string().trim().max(800).refine(value => Boolean(webLink(value)), "请输入完整的 HTTP 或 HTTPS 链接");
const optionalUrl = z.union([z.literal(""), url]).optional();
export const submissionSchema = z.object({
  title: z.string().trim().min(2, "请输入至少 2 个字符").max(120),
  source: url,
  demo: optionalUrl,
  repo: optionalUrl,
  theme: z.string().refine(value => Object.hasOwn(themes, value), "请选择一个主题"),
  notes: z.string().trim().max(1500).optional(),
  website: z.string().max(100).optional(),
}).strict();

export function referenceKey(value: string) {
  const url = new URL(value);
  const host = url.hostname.replace(/^www\./, "").toLowerCase();
  const post = url.pathname.match(/\/status\/(\d+)(?:\/|$)/);
  if (post && /^(?:(?:mobile|m)\.)?(?:x|twitter)\.com$/.test(host)) return `x:${post[1]}`;
  const path = url.pathname.replace(/\/+$/, "");
  for (const key of [...url.searchParams.keys()]) {
    if (/^utm_|^(fbclid|gclid|ref_src)$/i.test(key)) url.searchParams.delete(key);
  }
  url.searchParams.sort();
  return host + (url.port ? ":" + url.port : "") + path + url.search;
}
