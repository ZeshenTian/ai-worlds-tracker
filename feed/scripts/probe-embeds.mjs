import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { join } from "node:path";
import { snapshot, state, readJSON, saveJSON, web } from "./paths.mjs";

const run = promisify(execFile);
const loginHost =
  /(^|\.)(claude\.ai|ai\.studio|aistudio\.google\.com|accounts\.google\.com|auth\.openai\.com|login\.microsoftonline\.com)$/i;
const origin = process.env.FEED_ORIGIN
  ? new URL(process.env.FEED_ORIGIN).origin
  : null;
const cacheFile = join(state, "embed_probe.json");
const old = await readJSON(cacheFile, {});
const rows = await readJSON(snapshot);
const urls = [
  ...new Set(
    rows
      .filter((w) => w.live_demo_url && w.demo_health_status !== "broken")
      .map((w) => w.live_demo_url),
  ),
].sort();
const loginURLs = new Set(
  rows
    .filter((w) => w.demo_health_status === "login_required")
    .map((w) => w.live_demo_url),
);
const results = {};
function ancestorAllowed(list, target) {
  return list.some((source) => {
    if (source === "*") return true;
    if (!origin) return false;
    if (source === "'self'") return origin === new URL(target).origin;
    if (/^https?:$/.test(source)) return new URL(origin).protocol === source;
    try {
      const entry = new URL(source.replace("://*.", "://wildcard."));
      const host = new URL(origin);
      return (
        origin === entry.origin ||
        (entry.hostname.startsWith("wildcard.") &&
          host.protocol === entry.protocol &&
          host.port === entry.port &&
          host.hostname.endsWith(entry.hostname.slice(8)))
      );
    } catch {
      return false;
    }
  });
}
async function request(url, head) {
  const args = [
    "-sS",
    "-L",
    "--max-redirs",
    "5",
    "--proto",
    "=http,https",
    "--proto-redir",
    "=http,https",
    "--connect-timeout",
    "5",
    "--max-time",
    "14",
    "-A",
    "Mozilla/5.0 (compatible; WorldFeed/1.0)",
    "-D",
    "-",
    "-o",
    "/dev/null",
    "-w",
    "\\nWF_RESULT %{http_code} %{url_effective}",
    ...(head ? ["-I"] : ["--range", "0-8191", "--max-filesize", "1048576"]),
    "--",
    url,
  ];
  let output;
  try {
    output = (await run("curl", args, { maxBuffer: 512 * 1024 })).stdout;
  } catch (error) {
    if (error.code === 63 && error.stdout) output = error.stdout;
    else throw error;
  }
  const [raw, final] = output.split("\nWF_RESULT ");
  const [code, target] = (final || "").trim().split(" ");
  const block =
    raw
      .trim()
      .split(/\r?\n\r?\n/)
      .at(-1) || "";
  const headers = (name) =>
    block
      .split(/\r?\n/)
      .filter((line) => line.toLowerCase().startsWith(name + ":"))
      .map((line) => line.slice(name.length + 1).trim());
  return { code: Number(code), target, headers };
}
async function probe(input) {
  const url = web(input);
  if (!url) return { embeddable: false, reason: "invalid_url" };
  if (loginHost.test(new URL(url).hostname) || loginURLs.has(input))
    return { embeddable: false, reason: "login_wall" };
  try {
    // Prefer encrypted navigation even for older HTTP-only catalog links.
    const target = url.replace(/^http:/, "https:");
    let res = await request(target, true);
    if (
      [400, 403, 405, 501].includes(res.code) ||
      !res.headers("content-type").length
    )
      res = await request(target, false);
    const { code, target: final, headers } = res;
    let reason = "allowed";
    if (!(code >= 200 && code < 300) || !web(final)) reason = "http_error";
    else if (
      loginHost.test(new URL(final).hostname) ||
      /\/(?:log-?in|sign-?in|oauth\/authorize)(?:\/|$)/i.test(
        new URL(final).pathname,
      )
    )
      reason = "login_wall";
    else if (
      headers("x-frame-options").some((x) => /(?:deny|sameorigin)/i.test(x))
    )
      reason = "x_frame_options";
    else if (
      headers("content-security-policy")
        .flatMap((x) => x.split(","))
        .some((policy) => {
          const directive = policy
            .split(";")
            .map((d) => d.trim().split(/\s+/))
            .find((d) => d[0]?.toLowerCase() === "frame-ancestors");
          return directive && !ancestorAllowed(directive.slice(1), final);
        })
    )
      reason = "frame_ancestors";
    else if (
      headers("content-type").length &&
      !headers("content-type").some((x) =>
        /text\/html|application\/xhtml\+xml/i.test(x),
      )
    )
      reason = "not_html";
    else if (!final.startsWith("https:")) reason = "mixed_content";
    return {
      embeddable: reason === "allowed",
      reason,
      status: code,
      final_url: final,
    };
  } catch (error) {
    return {
      embeddable: false,
      reason: "network_error",
      curl_code: error.code ?? null,
    };
  }
}
let cursor = 0;
const refresh = process.argv.includes("--refresh");
async function worker() {
  while (cursor < urls.length) {
    const url = urls[cursor++];
    const cached = old[url];
    results[url] =
      !refresh &&
      cached &&
      cached.origin === origin &&
      cached.login_required === loginURLs.has(url) &&
      cached.reason !== "network_error"
        ? cached
        : {
            ...(await probe(url)),
            checked_at: new Date().toISOString(),
            origin,
            login_required: loginURLs.has(url),
          };
  }
}
await Promise.all(Array.from({ length: 18 }, worker));
await saveJSON(cacheFile, Object.fromEntries(urls.map((u) => [u, results[u]])));
console.log(
  "Probed",
  urls.length,
  "demo URLs;",
  Object.values(results).filter((r) => r.embeddable).length,
  "permit embedding.",
);
