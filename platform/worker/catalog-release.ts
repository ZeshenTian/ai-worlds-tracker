// The production Site reads the static branch written by the catalog workflow.
// Local builds render their own snapshot, including when exporting the next release.
import meta from "../data/meta.json";

const site = "generated-worlds-atlas.zeshentian1.chatgpt.site";
const origin = "https://raw.githubusercontent.com/ZeshenTian/ai-worlds-tracker/static-site/";
const types: Record<string, string> = {
  html: "text/html; charset=utf-8", js: "text/javascript; charset=utf-8",
  css: "text/css; charset=utf-8", json: "application/json",
  jpg: "image/jpeg", webp: "image/webp", svg: "image/svg+xml", png: "image/png", woff2: "font/woff2",
};

// A previous static export can outlive a Sites deployment. Only use an
// export compatible with this frontend and at least as recent as its catalog.
let nextCheck = 0;
let available: Promise<boolean> | undefined;
function hasCurrentRelease() {
  if (!available || Date.now() >= nextCheck) {
    nextCheck = Date.now() + 60_000;
    available = fetch(origin + "atlas-release.json", { signal: AbortSignal.timeout(2000) })
      .then(async response => {
        if (!response.ok) return false;
        const info = await response.json() as {format?: number; catalogUpdatedAt?: string};
        return info.format === 1 && Date.parse(info.catalogUpdatedAt || "") >= Date.parse(meta.last_updated_at);
      }).catch(() => false);
  }
  return available;
}

export async function catalogRelease(request: Request): Promise<Response | undefined> {
  const url = new URL(request.url);
  if (url.hostname !== site || !["GET", "HEAD"].includes(request.method)) return;
  const path = url.pathname.replace(/^\/|\/$/g, "");
  let file: string;
  if (path === "" || path === "trends" || /^worlds\/world-[a-z0-9_-]+$/.test(path)) {
    file = path ? path + "/index.html" : "index.html";
  } else if (/^(?:_next\/static|thumbnails|images|share)\/[a-zA-Z0-9_./-]+$/.test(path) && !path.includes("..")) {
    file = path;
  } else return;
  const type = types[file.split(".").pop() || ""];
  if (!type || !await hasCurrentRelease()) return;
  try {
    const response = await fetch(origin + file, {method: request.method, signal: AbortSignal.timeout(5000)});
    if (response.status === 404 && path.startsWith("worlds/")) {
      const missing = await fetch(origin + "404.html", {method: request.method, signal: AbortSignal.timeout(5000)});
      if (missing.ok) return new Response(missing.body, {status: 404, headers: {"Content-Type": types.html}});
    }
    if (!response.ok) return;
    return new Response(response.body, {headers: {"Content-Type": type, "X-Atlas-Release": "static-site",
      "Cache-Control": file.startsWith("_next/static/") ? "public,max-age=31536000,immutable" : "public,max-age=60"}});
  } catch { return; }
}
