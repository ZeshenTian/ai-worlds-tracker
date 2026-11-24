import "./sites-env.mjs";
import { cp, mkdir, mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { unstable_dev } from "wrangler";

const worlds = JSON.parse(await readFile("data/worlds.json", "utf8"));
const stage = await mkdtemp(path.resolve(".static-export-"));
let worker;
try {
  await cp("dist/client", stage, { recursive: true });
  worker = await unstable_dev("dist/server/index.js", {
    config: "dist/server/wrangler.json", ip: "127.0.0.1", port: 0, local: true,
    logLevel: "error", experimental: { disableExperimentalWarning: true, disableDevRegistry: true },
  });
  async function render(route, file, status = 200) {
    const response = await worker.fetch(route);
    const html = await response.text();
    if (response.status !== status || !html.includes("</html>")) {
      throw new Error("Unable to render " + route + " (HTTP " + response.status + ")");
    }
    const dest = path.join(stage, file);
    await mkdir(path.dirname(dest), { recursive: true });
    await writeFile(dest, html);
  }
  await render("/", "index.html");
  await render("/trends", "trends/index.html");
  for (const world of worlds) {
    const route = "/worlds/" + world.world_id;
    await render(route, route.slice(1) + "/index.html");
  }
  await render("/worlds/missing", "404.html", 404);
  await mkdir(path.join(stage, "submit"));
  const issue = "https://github.com/ZeshenTian/ai-worlds-tracker/issues/new?template=new-world.yml";
  await writeFile(path.join(stage, "submit/index.html"), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=' + issue + '"><title>提交新世界</title><a href="' + issue + '">打开投稿表单</a></html>');
  await rm("out", { recursive: true, force: true });
  await rename(stage, "out");
  console.log("Static catalog built with " + worlds.length + " detail pages.");
} finally {
  if (worker) await worker.stop();
  await rm(stage, { recursive: true, force: true });
}
