import assert from "node:assert/strict";
import { createServer } from "node:http";
import { createReadStream } from "node:fs";
import { mkdir, stat, readFile, writeFile } from "node:fs/promises";
import { join, extname, resolve, sep } from "node:path";
import { chromium } from "playwright-core";
import { feed, readJSON } from "./paths.mjs";

const dist = join(feed, "dist"),
  output = join(feed, "acceptance");
await mkdir(output, { recursive: true });
const data = await readJSON(join(dist, "data/feed.json"));
const mirrors = data.filter((w) => w.tier === "mirror");
assert.ok(mirrors.length >= 2);
const recommend = data.filter(
  (w) => w.tier !== "external" || w.thumbnail_url || w.preview_video_url,
);
const external = data.find(
  (w) => w.tier === "external" && w.thumbnail_url && w.external_demo_url,
);
const embed = data.find(
  (w) =>
    w.tier === "embed" &&
    w.title === (process.env.FEED_VERIFY_EMBED || "Francis Turbine Explorer"),
);
assert.ok(
  external && embed,
  "Expected an actual external and an embeddable world in this snapshot",
);
const mime = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".wasm": "application/wasm",
};
const server = createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(
      new URL(req.url, "http://localhost").pathname,
    );
    const path = resolve(
      dist,
      "." + (pathname === "/" ? "/index.html" : pathname),
    );
    if (!path.startsWith(dist + sep) || !(await stat(path)).isFile())
      throw Error();
    res.writeHead(200, {
      "Content-Type": mime[extname(path)] || "application/octet-stream",
    });
    createReadStream(path).pipe(res);
  } catch {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = "http://127.0.0.1:" + server.address().port;
const errors = [],
  httpFailures = [],
  checks = [],
  results = {};
const zh = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u;
const live = "iframe[data-world-embed]";
let browser;
function pass(label) {
  checks.push(label);
  console.log("PASS", label);
}
function diagnostics(page) {
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text() + " " + m.location().url);
  });
  page.on("response", (r) => {
    if (r.status() >= 400) httpFailures.push(r.status() + " " + r.url());
  });
}
async function launch() {
  // Each run opens its own real Chrome process, window and disposable profile.
  const proxy = process.env.FEED_CHROME_PROXY;
  return chromium.launch({
    channel: "chrome",
    headless: false,
    args: ["--new-window"],
    ...(proxy
      ? { proxy: { server: proxy, bypass: "localhost,127.0.0.1" } }
      : {}),
  });
}
async function waitWorld(p, w) {
  await p.waitForFunction(
    (id) =>
      document.querySelector(".theatre")?.getAttribute("data-world") === id,
    w.world_id,
  );
  await p.waitForFunction(
    (id) => new URL(location.href).searchParams.get("w") === id,
    w.world_id,
  );
}
async function go(p, w) {
  await p.goto(origin + "/?w=" + w.world_id, { waitUntil: "domcontentloaded" });
  await waitWorld(p, w);
}
async function assertEnglish(p) {
  assert.equal(await p.locator("html").getAttribute("lang"), "en");
  assert.ok(
    !zh.test(await p.locator("body").innerText()),
    "CJK text in English interface",
  );
}
async function layout(p, width, height) {
  const dimensions = await p.evaluate(() => ({
    width: innerWidth,
    height: innerHeight,
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  assert.equal(dimensions.width, width);
  assert.equal(dimensions.height, height);
  assert.ok(dimensions.scroll <= dimensions.client, JSON.stringify(dimensions));
  return dimensions;
}
async function loadedImage(p) {
  await p.waitForFunction(() => {
    const el = document.querySelector(".visual img");
    return el?.complete && el.naturalWidth > 0;
  });
}
async function assertPlay(p) {
  await p.locator('.theatre[data-mode="playing"]').waitFor({ timeout: 60000 });
  assert.equal(await p.locator(live).count(), 1);
}
const action = (p, key) => p.locator('[data-action="' + key + '"]');
try {
  browser = await launch();
  results.chrome = browser.version();
  const c = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    permissions: ["clipboard-read", "clipboard-write"],
  });
  const p = await c.newPage();
  diagnostics(p);
  // Record transient two-frame regressions as well as the states at each assertion.
  await p.addInitScript(() => {
    window.__maxEmbeds = 0;
    new MutationObserver(() => {
      window.__maxEmbeds = Math.max(
        window.__maxEmbeds,
        document.querySelectorAll("iframe[data-world-embed]").length,
      );
    }).observe(document, { subtree: true, childList: true });
  });
  await p.goto(origin);
  await waitWorld(p, recommend[0]);
  await loadedImage(p);
  results.desktop = await layout(p, 1440, 900);
  await p.screenshot({ path: join(output, "desktop-1440x900.png") });
  assert.equal(await p.locator(live).count(), 0);
  assert.equal(await action(p, "previous").isDisabled(), true);
  const rail = await p.locator(".rail").boundingBox(),
    stage = await p.locator(".frame").boundingBox();
  assert.ok(rail.x >= stage.x + stage.width);
  await p.mouse.move(450, 330);
  // An accelerated scroll followed by a decaying trackpad tail lasting longer than 420 ms.
  for (const d of [
    16, 23, 39, 69, 105, 71, 60, 46, 34, 25, 18, 12, 8, 5, 3, 2, 1,
  ]) {
    await p.mouse.wheel(0, d);
    await p.waitForTimeout(32);
  }
  await waitWorld(p, recommend[1]);
  await p.keyboard.press("k");
  await waitWorld(p, recommend[0]);
  await p.keyboard.press("j");
  await waitWorld(p, recommend[1]);
  await p.keyboard.press("ArrowUp");
  await waitWorld(p, recommend[0]);
  pass("Wheel inertia advances one world; J/K and arrow navigation");
  for (const w of mirrors) {
    await go(p, w);
    await p.keyboard.press("Space");
    await assertPlay(p);
    const frame = p.frameLocator(live);
    await frame.locator("canvas").first().waitFor();
    assert.ok(
      await frame
        .locator("canvas")
        .first()
        .evaluate((el) => el.width > 0 && el.height > 0),
    );
    const f = p.locator(live);
    assert.equal(await f.getAttribute("referrerpolicy"), "no-referrer");
    assert.equal(
      await f.getAttribute("sandbox"),
      "allow-scripts allow-same-origin allow-pointer-lock allow-popups allow-forms",
    );
    const inner = await (await f.elementHandle()).contentFrame();
    assert.equal(new URL(inner.url()).origin, origin);
    await f.focus();
    await action(p, "exit").click();
    await p.locator('.theatre[data-mode="browse"]').waitFor();
    assert.equal(await p.locator(live).count(), 0);
    await action(p, "start").click();
    await assertPlay(p);
    await f.focus();
    await action(p, "next").click();
    await p.locator('.theatre[data-mode="browse"]').waitFor();
    assert.notEqual(
      await p.locator(".theatre").getAttribute("data-world"),
      w.world_id,
    );
    assert.equal(await p.locator(live).count(), 0);
    assert.equal(await p.evaluate(() => window.__maxEmbeds), 1);
  }
  pass(
    "All pinned mirrors render same-origin canvases; a single iframe unmounts on exit and next",
  );
  await go(p, embed);
  // Delay the real navigation to exercise the four-second control. Never substitute an iframe response.
  await p.route(embed.embed_url, async (route) => {
    await new Promise((r) => setTimeout(r, 4800));
    await route.continue();
  });
  await action(p, "start").click();
  await p.locator('.theatre[data-mode="loading"]').waitFor();
  assert.equal(await action(p, "recovery").count(), 0);
  await action(p, "recovery").waitFor({ timeout: 4700 });
  assert.equal(
    await p.locator(".theatre").getAttribute("data-mode"),
    "loading",
  );
  await assertPlay(p);
  await p
    .frameLocator(live)
    .locator("canvas")
    .first()
    .waitFor({ timeout: 65000 });
  const foreign = await (await p.locator(live).elementHandle()).contentFrame();
  assert.notEqual(new URL(foreign.url()).origin, origin);
  await p.locator(live).focus();
  await action(p, "next").click();
  await p.locator('.theatre[data-mode="browse"]').waitFor();
  assert.equal(await p.locator(live).count(), 0);
  pass(
    "Actual cross-origin embed renders a canvas; delayed load reveals recovery and frame-external next works",
  );
  await go(p, external);
  await loadedImage(p);
  assert.equal(await action(p, "start").getAttribute("target"), "_blank");
  const popupPromise = p.waitForEvent("popup");
  await action(p, "start").click();
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded");
  assert.equal(
    new URL(popup.url()).hostname,
    new URL(external.external_demo_url).hostname,
  );
  await popup.close();
  assert.equal(await p.locator(live).count(), 0);
  pass("External preview opens its original demo in a new tab");
  await go(p, mirrors[0]);
  await p.getByRole("button", { name: "Switch to English" }).click();
  await assertEnglish(p);
  const multilingual = data.find((w) => zh.test(w.title));
  await go(p, multilingual);
  await assertEnglish(p);
  await p.keyboard.press("i");
  await p.getByRole("dialog").waitFor();
  await assertEnglish(p);
  await p.keyboard.press("Escape");
  await p.reload();
  await waitWorld(p, multilingual);
  await assertEnglish(p);
  await p.keyboard.press("l");
  await p.locator('[data-tab="favorites"]').click();
  await waitWorld(p, multilingual);
  await p.reload();
  await waitWorld(p, multilingual);
  assert.equal(await action(p, "save").getAttribute("aria-pressed"), "true");
  await action(p, "share").click();
  await p.getByRole("status").waitFor();
  assert.equal(
    await p.evaluate(() => navigator.clipboard.readText()),
    origin + "/?w=" + multilingual.world_id,
  );
  await action(p, "save").click();
  await p.getByText("No saved worlds yet").waitFor();
  assert.equal(new URL(p.url()).searchParams.get("w"), null);
  for (const tab of [
    "playable",
    "opensource",
    "Claude",
    "GPT",
    "Gemini",
    "for-you",
  ]) {
    await p.locator('[data-tab="' + tab + '"]').click();
    await p.waitForFunction(
      (t) => new URL(location.href).searchParams.get("tab") === t,
      tab,
    );
    const row = data.find(
      (w) => w.world_id === new URL(p.url()).searchParams.get("w"),
    );
    assert.ok(row);
    if (tab === "playable") assert.notEqual(row.tier, "external");
    if (tab === "opensource") assert.ok(row.is_open_source);
    if (["Claude", "GPT", "Gemini"].includes(tab))
      assert.ok(row.model_families.includes(tab));
  }
  await p.goto(origin + "/?w=" + external.world_id + "&tab=playable");
  await waitWorld(p, external);
  assert.equal(new URL(p.url()).searchParams.get("tab"), "for-you");
  const hidden = data.find((w) => !recommend.includes(w));
  if (hidden) {
    await go(p, hidden);
    await waitWorld(p, hidden);
  }
  assert.ok(
    (await p.evaluate(() => JSON.parse(localStorage.getItem("worldfeed-seen"))))
      .length >= 2,
  );
  for (const w of data)
    assert.ok(
      !zh.test(
        [
          w.title_en,
          w.author_en,
          w.summary_en,
          ...w.workflow_steps_en,
          ...w.skills_en,
          ...w.tech_stack_en,
          ...w.models_used_en,
        ].join(" "),
      ),
      w.world_id,
    );
  pass(
    "English UI and drawer, all localized fields, language persistence, channels, favorites, shared and text-only deep links",
  );
  await browser.close();
  browser = await launch();
  const m = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 1,
  });
  const mp = await m.newPage();
  diagnostics(mp);
  await go(mp, recommend[0]);
  await loadedImage(mp);
  results.mobile = await layout(mp, 390, 844);
  await mp.screenshot({ path: join(output, "mobile-390x844.png") });
  const bar = await mp.locator(".rail").boundingBox(),
    box = await mp.locator(".frame").boundingBox();
  assert.ok(bar.y >= box.y + box.height - 1);
  const cdp = await m.newCDPSession(mp);
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [{ x: 160, y: 420 }],
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [{ x: 161, y: 290 }],
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  await waitWorld(mp, recommend[1]);
  await mp.reload();
  await waitWorld(mp, recommend[1]);
  await action(mp, "info").tap();
  const dialog = await mp.getByRole("dialog").boundingBox();
  assert.ok(dialog && dialog.y > 300 && dialog.height < 520);
  await layout(mp, 390, 844);
  pass(
    "Desktop and mobile fit the viewport; actual touch gesture, bottom drawer and deep-link refresh",
  );
  assert.deepEqual(httpFailures, [], "HTTP failures during acceptance");
  assert.deepEqual(errors, [], "Chrome console/page errors");
  pass(
    "Zero console and page errors or HTTP 4xx/5xx in the tested views and frames",
  );
  await writeFile(
    join(output, "results.json"),
    JSON.stringify(
      {
        tested_at: new Date().toISOString(),
        ...results,
        worlds: data.length,
        recommended: recommend.length,
        tiers: Object.fromEntries(
          ["mirror", "embed", "external"].map((t) => [
            t,
            data.filter((w) => w.tier === t).length,
          ]),
        ),
        tested_world_ids: {
          mirrors: mirrors.map((w) => w.world_id),
          embed: embed.world_id,
          external: external.world_id,
        },
        checks,
        errors,
        httpFailures,
      },
      null,
      2,
    ) + "\n",
  );
} catch (err) {
  console.error("Observed errors:", errors, "HTTP failures:", httpFailures);
  throw err;
} finally {
  await browser?.close();
  server.closeAllConnections();
  await new Promise((r) => server.close(r));
}
