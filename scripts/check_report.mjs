// Optional browser check. Requires Playwright with Chromium already installed.
// Arguments: HTML generated from examples/retry_history, then the 222-run demo.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const { chromium } = createRequire(import.meta.url)("playwright");
const [retryPath, historyPath] = process.argv.slice(2);
if (!retryPath || !historyPath) throw new Error("Usage: node scripts/check_report.mjs retry.html history.html");

const browser = await chromium.launch();
try {
  for (const width of [375, 1200]) {
    for (const colorScheme of ["light", "dark"]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme, offline: true });
      const page = await context.newPage();
      const errors = [];
      const network = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("request", request => {
        if (/^https?:/.test(request.url())) network.push(request.url());
      });
      await page.goto(pathToFileURL(resolve(retryPath)).href);
      assert.equal(await page.locator("details.row").count(), 6);
      assert.equal(await page.locator('.row-heatmap .s-recovered').count(), 2);
      assert.equal(await page.locator('.row-heatmap .s-fail').count(), 1);
      assert.equal(await page.locator('.row-heatmap .s-error').count(), 1);
      assert.equal(await page.locator('.row-heatmap .s-skip').count(), 1);
      const row = page.locator("details.row").filter({ hasText: "recoversAfterTwoFailures" });
      await row.locator("summary").focus();
      await page.keyboard.press("Enter");
      assert.equal(await row.getAttribute("open"), "");
      assert.match(await row.locator(".evidence").innerText(), /3 recorded attempts; 2 failed/);
      assert.match(await row.locator(".evidence").innerText(), /report.xml :: testcase 5/);
      await page.keyboard.press("Space");
      assert.equal(await row.getAttribute("open"), null);
      // Exercise every detail panel, including long failure strings and source paths.
      await page.locator("details.row").evaluateAll(rows => rows.forEach(row => row.open = true));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const cells = await page.locator('.row-heatmap [role="img"]').all();
      for (const cell of cells) assert(await cell.getAttribute("aria-label"));
      await page.goto(pathToFileURL(resolve(historyPath)).href);
      assert.equal(await page.locator("details.row").count(), 12);
      assert.equal(await page.locator(".row-heatmap .cell").count(), 12 * 222);
      await page.locator("details.row").evaluateAll(rows => rows.forEach(row => row.open = true));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert.deepEqual(errors, []);
      assert.deepEqual(network, []);
      console.log(`PASS ${width}px ${colorScheme}: evidence, keyboard, layout, history, offline`);
      await context.close();
    }
  }
} finally {
  await browser.close();
}
