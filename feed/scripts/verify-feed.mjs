// Run against the built Atlas and WorldFeed served at the specified local URLs.
import assert from "node:assert/strict";
import { readFile, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { root } from "./paths.mjs";

const helper =
  process.env.TEST_BROWSER_HELPER ||
  join(homedir(), "Projects/ciw-sdk/scripts/test-browser.mjs");
const headless = process.argv.includes("--headless");
const browser = headless
  ? await (
      await import("playwright-core")
    ).chromium.launch({ channel: "chrome", headless: true })
  : null;
const context = browser ? await browser.newContext() : null;
const openTestTab = context
  ? async () => {
      const page = await context.newPage();
      return { page, windowId: "headless", close: () => page.close() };
    }
  : (await import(pathToFileURL(helper))).openTestTab;
const atlas = process.env.TEST_ATLAS_URL || "http://127.0.0.1:8870";
const feed = process.env.TEST_FEED_URL || "http://127.0.0.1:8871";
const json = async (p) => JSON.parse(await readFile(join(root, p), "utf8"));
const pool = await json("feed/dist/data/feed.json");
const frontier = (await json("data/exports/ai_worlds.json")).filter(
  (x) => x.model_era === "frontier",
);
const ids = pool.map((x) => x.world_id);
assert.deepEqual(
  [...ids].sort(),
  await json("platform/data/embeddable-ids.json"),
);
assert.ok(
  pool.every(
    (x) =>
      x.model_era === "frontier" &&
      ["embed", "mirror"].includes(x.tier) &&
      x.embed_url &&
      Number.isFinite(x.x_likes),
  ),
);
const first = pool[0];
const sorted = [...frontier].sort(
  (a, b) =>
    (b.published_at || "").localeCompare(a.published_at || "") ||
    a.world_id.localeCompare(b.world_id),
);
const live = (w) =>
  Boolean(w.live_demo_url) && w.demo_health_status !== "broken";
const firstRow = sorted
  .filter((w) => live(w) && ids.includes(w.world_id))
  .slice(0, 4);
const buckets = {
  playable: sorted.filter(live),
  video: sorted.filter((w) => !live(w)),
  all: [...firstRow, ...sorted.filter((w) => !firstRow.includes(w))],
};
const rank = (w) => (w.tier === "mirror" ? 0 : w.verified_playable ? 1 : 2);
assert.deepEqual(
  pool,
  [...pool].sort(
    (a, b) =>
      rank(a) - rank(b) ||
      (b.published_at || "").localeCompare(a.published_at || "") ||
      a.world_id.localeCompare(b.world_id),
  ),
);
let shared;
try {
  for (const [width, height] of [
    [1440, 900],
    [390, 844],
  ]) {
    const tab = await openTestTab();
    const p = tab.page;
    const errors = [];
    const notices = [];
    const onConsole = (m) => {
      if (m.type() !== "error") return;
      const u = m.location().url;
      if (!u || u.startsWith(atlas) || u.startsWith(feed))
        errors.push(m.text());
      else notices.push(m.text());
    };
    p.on("console", onConsole);
    p.on("pageerror", (e) => errors.push(e.message));
    p.setDefaultTimeout(15000);
    const storageKeys = ["atlas-lang", "worldfeed-liked-ids"];
    const saved = new Map();
    async function snapshot(origin) {
      await p.goto(origin, { waitUntil: "domcontentloaded" });
      saved.set(
        origin,
        await p.evaluate(
          (keys) => keys.map((k) => localStorage.getItem(k)),
          storageKeys,
        ),
      );
    }
    async function layout() {
      const info = await p.evaluate(() => [
        getComputedStyle(document.documentElement).colorScheme,
        document.documentElement.scrollWidth,
        innerWidth,
      ]);
      assert.equal(info[0], "light");
      assert.ok(info[1] <= info[2] + 1, JSON.stringify(info));
    }
    try {
      shared ??= tab.windowId;
      assert.equal(tab.windowId, shared);
      await p.setViewportSize({ width, height });
      await p.emulateMedia({ colorScheme: "dark" });
      await snapshot(atlas);
      await p.evaluate(() => localStorage.setItem("atlas-lang", "zh"));
      await p.reload();
      const cards = p.locator("article");
      await cards.first().waitFor();
      // Wait for the static catalog to hydrate before exercising its controls.
      await p.waitForFunction(
        (url) =>
          document.querySelector("header nav a")?.href.replace(/\/$/, "") ===
          url,
        feed,
      );
      await layout();
      assert.equal(await cards.count(), 24);
      if (process.argv.includes("--capture") && width === 1440) {
        await mkdir(join(root, "reports/live"), {recursive:true});
        await p.screenshot({path: join(root, "reports/live/atlas-grid-desktop.png")});
      }
      assert.deepEqual(
        await cards.evaluateAll((els) => els.map((e) => e.dataset.id)),
        buckets.all.slice(0, 24).map((w) => w.world_id),
      );
      assert.equal(
        await p
          .locator(
            "select,.brand-icon,aside,.era-segments,.wb-inspector,a[href*='/trends'],a[href*='/submit'],a[href*='/worlds/']",
          )
          .count(),
        0,
      );
      assert.equal(
        await p
          .locator(".world-grid")
          .evaluate(
            (e) => getComputedStyle(e).gridTemplateColumns.split(" ").length,
          ),
        width === 1440 ? 4 : 1,
      );
      assert.equal(await p.locator(".group").count(), 4);
      assert.deepEqual(
        await p
          .locator("[data-tab]")
          .evaluateAll((es) => es.map((e) => e.dataset.tab)),
        ["all", "playable", "video"],
      );
      assert.equal(
        await p.locator("[data-tab=all]").getAttribute("aria-pressed"),
        "true",
      );
      assert.ok(
        await p
          .locator(".group")
          .evaluateAll((es) =>
            es.every((e) =>
              e.querySelector("button").textContent.trim().startsWith("全部 "),
            ),
          ),
      );
      assert.doesNotMatch(
        await p.locator(".toolbar").innerText(),
        /全部技术栈|全部主题|Antigravity/i,
      );
      await p.getByRole("button", { name: "下一页 →" }).click();
      await p.waitForURL((url) => url.searchParams.get("page") === "2");
      assert.equal(
        await cards.first().getAttribute("data-id"),
        buckets.all[24].world_id,
      );
      const modelGroup = p.locator('.group[aria-label="模型"]');
      for (const key of ["video", "all", "playable"]) {
        await p.locator('[data-tab="' + key + '"]').click();
        assert.equal(
          new URL(p.url()).searchParams.get("tab"),
          key === "all" ? null : key,
        );
        assert.equal(new URL(p.url()).searchParams.has("page"), false);
        assert.equal(
          await cards.first().getAttribute("data-id"),
          buckets[key][0].world_id,
        );
        assert.equal(
          await p.locator(".results strong").innerText(),
          buckets[key].length.toLocaleString("en-US") + " 个世界",
        );
        assert.equal(
          await modelGroup
            .locator("button")
            .first()
            .locator("span")
            .innerText(),
          buckets[key].length.toLocaleString("en-US"),
        );
        const modelCount = buckets[key].filter((w) =>
          w.models_used.some((m) => /^claude/i.test(m)),
        ).length;
        assert.equal(
          await modelGroup
            .getByRole("button", { name: /^Claude/ })
            .locator("span")
            .innerText(),
          modelCount.toLocaleString("en-US"),
        );
        if (key === "video") {
          const broken = buckets.video.find(
            (w) => w.demo_health_status === "broken" && w.live_demo_url,
          );
          if (broken) {
            const n = Math.floor(buckets.video.indexOf(broken) / 24) + 1;
            await p.goto(atlas + "/?tab=video&page=" + n);
            const primary = p
              .locator('article[data-id="' + broken.world_id + '"] .actions a')
              .first();
            await primary.waitFor();
            assert.equal(
              await primary.getAttribute("href"),
              broken.original_post_url,
            );
          }
        }
      }
      await modelGroup.getByRole("button", { name: /^Claude/ }).click();
      assert.ok((await cards.count()) > 0);
      await p.getByRole("button", { name: "重置" }).click();
      await p
        .locator('.group[aria-label="主题"]')
        .locator("button")
        .nth(1)
        .click();
      await p.getByRole("button", { name: "重置" }).click();
      await p
        .locator('.group[aria-label="技术栈"]')
        .locator("button")
        .nth(1)
        .click();
      await p.getByRole("button", { name: "重置" }).click();
      await p.locator("header nav button").click();
      await p.waitForFunction(() => document.documentElement.lang === "en");
      assert.doesNotMatch(
        (await p.locator("body").innerText()).replace("中文", ""),
        /[\u3400-\u9fff]/u,
      );
      await p.locator("#wb-global-search").fill(first.title_en);
      const card = p.locator('article[data-id="' + first.world_id + '"]');
      await card.waitFor();
      assert.equal(
        await p.getByRole("button", { name: /^(List|Grid|Table)$/ }).count(),
        0,
      );
      assert.equal(
        new URL(
          await card.getByText("Play", { exact: true }).getAttribute("href"),
          atlas,
        ).searchParams.get("w"),
        first.world_id,
      );
      assert.equal(
        await card
          .getByText("Official ↗", { exact: true })
          .getAttribute("href"),
        first.external_demo_url,
      );
      assert.equal(
        await card.getByText("Post", { exact: true }).getAttribute("href"),
        first.original_post_url,
      );
      const playURL = await card
        .getByText("Play", { exact: true })
        .getAttribute("href");
      assert.equal(new URL(playURL).origin, feed);
      await snapshot(feed);
      await p.goto(playURL, { waitUntil: "domcontentloaded" });
      const frame = p.locator("iframe[data-world-embed]"),
        stage = p.locator(".stage");
      await frame.waitFor();
      await layout();
      assert.equal(await stage.getAttribute("data-world"), first.world_id);
      assert.ok((await frame.boundingBox()).height >= height * 0.88);
      assert.equal(await p.locator("iframe").count(), 1);
      assert.equal(
        await p
          .locator(
            ".brand-icon,.playbar,.drawer,.rail,.caption,.hint,.spinner,[data-action=start],[data-action=share]",
          )
          .count(),
        0,
      );
      const header = p.locator(".topbar");
      const model = header.locator(".model");
      assert.equal(await model.count(), 1);
      assert.equal(await model.getAttribute("title"), first.primary_model);
      assert.deepEqual(await frame.boundingBox(), {
        x: 0,
        y: 48,
        width,
        height: height - 48,
      });
      assert.deepEqual(await header.boundingBox(), {
        x: 0,
        y: 0,
        width,
        height: 48,
      });
      const fits = await header.evaluate((h) =>
        [...h.querySelectorAll("button, a, strong, .model")].every((el) => {
          const r = el.getBoundingClientRect();
          return (
            !r.width ||
            (r.left >= 0 &&
              r.right <= innerWidth + 1 &&
              r.top >= 0 &&
              r.bottom <= 48)
          );
        }),
      );
      assert.ok(fits, "Top-bar controls fit one row");
      assert.equal(
        await p.getByRole("button", { name: /分享|share/i }).count(),
        0,
      );
      if (width >= 960) {
        const help = header.locator(".help-trigger");
        await help.hover();
        await p.locator("#shortcuts").waitFor();
        await help.click();
        await p.keyboard.press("Escape");
        assert.equal(await p.locator("#shortcuts").count(), 0);
      } else {
        assert.equal(await header.locator(".help").isVisible(), false);
      }
      assert.ok(
        await p.evaluate(() =>
          [
            [2, 50],
            [innerWidth - 2, 50],
            [2, innerHeight - 2],
            [innerWidth - 2, innerHeight - 2],
            [innerWidth / 2, innerHeight / 2],
          ].every(([x, y]) =>
            document
              .elementFromPoint(x, y)
              ?.matches("iframe[data-world-embed]"),
          ),
        ),
      );

      const originalFrame = await frame.elementHandle();
      await p.locator("main").focus();
      await p.keyboard.press("ArrowDown");
      await p.waitForFunction(
        (id) => document.querySelector(".stage")?.dataset.world === id,
        pool[1].world_id,
      );
      assert.equal(await originalFrame.evaluate((e) => e.isConnected), false);
      assert.equal(await model.getAttribute("title"), pool[1].primary_model);
      if (
        pool[1].models_used.includes("GPT-6 Astra") &&
        pool[1].models_used.includes("Gemini 4 Carbon")
      )
        assert.equal(await model.getAttribute("title"), "Gemini 4 Carbon");

      await p.keyboard.press("ArrowUp");
      await p.waitForFunction(
        (id) => document.querySelector(".stage")?.dataset.world === id,
        first.world_id,
      );
      await p
        .frameLocator("iframe")
        .locator("canvas")
        .first()
        .waitFor({ timeout: 45000 });
      if ((headless || process.argv.includes("--capture")) && width === 1440) {
        // Enter the local mirror through the author's own game menus.
        const game = p.frameLocator("iframe");
        if (first.world_id === "world-3bc9b04773e624981797759d") {
          await game.locator("#press").waitFor();
          await frame.evaluate((f) => f.contentWindow.focus());
          await p.keyboard.press("Enter", { delay: 100 });
          await game.locator("[data-act=story]").click();
          await game.locator("[data-act=new]").click();
          for (let step = 0; step < 5; step++) {
            const next = game
              .locator(
                "[data-act=sortie]:visible,#st-skip:visible,#tk-skip:visible,#br-skip:visible",
              )
              .first();
            await next.waitFor();
            const launch = (await next.getAttribute("data-act")) === "sortie";
            await next.click();
            if (launch) break;
          }
          await game.locator("#briefing").waitFor({ state: "hidden" });
          await p.waitForTimeout(2000);
        }
        await p.mouse.move(0, 0);
        await mkdir(join(root, "reports/live"), { recursive: true });
        await p.screenshot({
          path: join(root, "reports/live/worldfeed-topbar-desktop.png"),
        });
      }
      await frame.evaluate((f) => f.contentWindow.focus());
      await p.keyboard.press("w");
      await p.keyboard.press("ArrowDown");
      await p.waitForFunction(
        (id) => document.querySelector(".stage")?.dataset.world === id,
        pool[1].world_id,
      );
      await p.locator("[data-action=prev]").click();
      await p.waitForFunction(
        (id) => document.querySelector(".stage")?.dataset.world === id,
        first.world_id,
      );
      const heart = header.locator("[data-action=like]");
      const prior = await heart.getAttribute("aria-pressed") === "true";
      await heart.click();
      assert.equal(await heart.getAttribute("aria-pressed"), String(!prior));
      assert.equal(await heart.locator("small").innerText(), String(first.x_likes + Number(!prior)));
      await p.reload({waitUntil:"domcontentloaded"});
      await heart.waitFor();
      assert.equal(await heart.getAttribute("aria-pressed"), String(!prior));
      await p.locator("main").focus();
      await p.keyboard.press("l");
      assert.equal(await heart.getAttribute("aria-pressed"), String(prior));
      assert.equal(await heart.locator("small").innerText(), String(first.x_likes + Number(prior)));
      assert.equal(await header.locator(".lucide-star").count(), 0);
      assert.equal(
        await header.locator("[data-action=official]").getAttribute("href"),
        first.external_demo_url,
      );
      assert.match(
        await header.locator("[data-action=official]").innerText(),
        /原始链接|Original link/,
      );
      assert.equal(
        await p.locator("[data-action=repo]").getAttribute("href"),
        first.repo_url,
      );
      for (const [key, url] of [
        ["g", first.external_demo_url],
        ["o", first.original_post_url],
      ]) {
        await p.locator("main").focus();
        const wait = p.waitForEvent("popup");
        await p.keyboard.press(key);
        const popup = await wait;
        try {
          assert.equal(popup.url().split("?")[0], url.split("?")[0]);
        } finally {
          await popup.close();
        }
      }
      await p.locator(".brand").hover();
      await p.mouse.wheel(0, 450);
      await p.waitForFunction(
        (id) => document.querySelector(".stage")?.dataset.world !== id,
        first.world_id,
      );
      const external = pool.find((w) => w.tier === "embed");
      await p.goto(feed + "/?w=" + external.world_id, {
        waitUntil: "domcontentloaded",
      });
      await frame.waitFor();
      assert.equal(await frame.getAttribute("src"), external.embed_url);
      await frame.evaluate((el) => el.focus());
      await p.locator("[data-action=next]").click();
      await p.waitForFunction(
        (id) => document.querySelector(".stage")?.dataset.world !== id,
        external.world_id,
      );
      await p.keyboard.press("ArrowUp");
      await p.waitForFunction(
        (id) => document.querySelector(".stage")?.dataset.world === id,
        external.world_id,
      );
      await p.keyboard.press("j");
      await p.waitForFunction(
        (id) => document.querySelector(".stage")?.dataset.world !== id,
        external.world_id,
      );
      await p.keyboard.press("k");
      await p.waitForFunction(
        (id) => document.querySelector(".stage")?.dataset.world === id,
        external.world_id,
      );
      console.log(
        JSON.stringify({
          width,
          height,
          window: shared,
          atlas: frontier.length,
          feed: pool.length,
          errors,
          externalConsole: notices.length,
        }),
      );
      assert.deepEqual(errors, []);
      assert.deepEqual(notices, []);
    } finally {
      p.off("console", onConsole);
      try {
        for (const [origin, vals] of saved) {
          await p.goto(origin, { waitUntil: "domcontentloaded" });
          await p.evaluate(
            ([keys, values]) =>
              keys.forEach((k, i) =>
                values[i] === null
                  ? localStorage.removeItem(k)
                  : localStorage.setItem(k, values[i]),
              ),
            [storageKeys, vals],
          );
        }
      } finally {
        await tab.close();
      }
    }
  }
} finally {
  await browser?.close();
}
