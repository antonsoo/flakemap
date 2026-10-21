// Exercise the actual standalone gallery, including offline native downloads.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium, firefox } from "playwright";

const [baseURL, output, expectedSite = "site"] = process.argv.slice(2);
assert(baseURL && output, "Usage: node browser.mjs BASE_URL OUTPUT_DIR [EXPECTED_SITE_DIR]");
const directory = resolve(output);
await mkdir(directory, { recursive: true });
const expectedJSON = JSON.parse(await readFile(resolve(expectedSite, "pytest.json"), "utf8"));
const expectedZIP = await readFile(resolve(expectedSite, "pytest-inputs.zip"));
const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");
const results = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of [375, 1440]) {
      for (const colorScheme of ["light", "dark"]) {
        const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme, reducedMotion: "reduce", deviceScaleFactor: 1 });
        try {
          const page = await context.newPage();
          const errors = [], requests = [];
          page.on("pageerror", error => errors.push(error.message));
          const response = await page.goto(new URL("index.html", baseURL).href);
          assert(response && response.status() === 200);
          const target = new URL("pytest.html", baseURL).href;
          await page.getByRole("navigation", { name: "Report examples" }).getByRole("link", { name: "Pytest retries", exact: true }).focus();
          const navigation = page.waitForURL(target);
          const destination = page.waitForResponse(reply => reply.url() === target);
          await page.keyboard.press("Enter");
          await navigation;
          assert.equal((await destination).status(), 200);
          await page.evaluate(() => document.fonts.ready);
          assert.equal(await page.getByRole("navigation", { name: "Report examples" }).getByRole("link").count(), 8);
          assert.equal(await page.locator("details.row").count(), 15);
          for (const [kind, count] of Object.entries({ recovered: 4, fail: 2, error: 3, skip: 2, pass: 4 })) {
            assert.equal(await page.locator(`.row-heatmap .s-${kind}`).count(), count);
          }
          const row = page.locator("details.row").filter({ hasText: "test_recovered_call_and_teardown" });
          await row.locator("summary").focus();
          await page.keyboard.press("Enter");
          const evidence = await row.locator(".evidence").innerText();
          assert.match(evidence, /2 recorded attempts; 1 failed/);
          assert.match(evidence, /call failed first.*teardown failed too/s);
          assert.match(evidence, /report\.xml :: testcase 9/);
          await context.setOffline(true);
          page.on("request", request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
          const downloadBytes = async name => {
            const pending = page.waitForEvent("download");
            await page.getByRole("link", { name, exact: true }).click();
            return readFile(await (await pending).path());
          };
          const json = await downloadBytes("Download this analysis as JSON");
          assert.deepEqual(JSON.parse(json.toString()), expectedJSON);
          const zip = await downloadBytes("Download captured pytest XML");
          assert.equal(sha256(zip), sha256(expectedZIP));
          const bounds = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
          assert.equal(bounds.width, width);
          assert(bounds.scrollWidth <= bounds.clientWidth, JSON.stringify(bounds));
          assert.deepEqual(errors, []);
          assert.deepEqual(requests, []);
          const screenshot = `${engine}-${width}-${colorScheme}.png`;
          await page.screenshot({ path: resolve(directory, screenshot), fullPage: true });
          const evidenceScreenshot = `${engine}-${width}-${colorScheme}-evidence.png`;
          await row.screenshot({ path: resolve(directory, evidenceScreenshot) });
          results.push({ engine, viewport: page.viewportSize(), colorScheme, tests: 15, recovered: 4, exhausted: 5, keyboardEntry: true, keyboardEvidence: true, jsonMatches: true, inputZipSha256: sha256(zip), offlineDownloads: true, networkAfterOffline: requests, pageErrors: errors, bounds, screenshot, evidenceScreenshot });
        } finally { await context.close(); }
      }
    }
  } finally { await browser.close(); }
}
await writeFile(resolve(directory, "browser.json"), `${JSON.stringify({ baseURL, results }, null, 2)}\n`);
console.log(JSON.stringify({ cases: results.length, actualOfflineDownloads: results.length * 2, errors: 0 }));
