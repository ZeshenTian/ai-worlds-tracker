import "./sites-env.mjs";
import { cp, mkdir, mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { unstable_dev } from "wrangler";


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
  await render("/missing", "404.html", 404);
  const { last_updated_at } = JSON.parse(await readFile("data/meta.json", "utf8"));
  await writeFile(path.join(stage, "atlas-release.json"), JSON.stringify({ format: 1, catalogUpdatedAt: last_updated_at }));
  await rm("out", { recursive: true, force: true });
  await rename(stage, "out");
  console.log("Static frontier catalog built.");
} finally {
  if (worker) await worker.stop();
  await rm(stage, { recursive: true, force: true });
}
