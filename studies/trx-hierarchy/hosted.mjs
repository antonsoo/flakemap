// Inspect the actual published gallery against one verified local build.
// node studies/trx-hierarchy/hosted.mjs BASE_URL SITE_DIR OUTPUT_DIR
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium, firefox } from "playwright";

const [baseURL, directory, output] = process.argv.slice(2);
assert(baseURL && directory && output, "BASE_URL SITE_DIR OUTPUT_DIR");
assert(baseURL.endsWith("/"));
await mkdir(output, { recursive: true });
const require = createRequire(import.meta.url);
const axe = await readFile(require.resolve("axe-core/axe.min.js"), "utf8");
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const views = [];
const slugs = (await readdir(directory)).filter(name => name.endsWith('.html')).map(name => name.slice(0, -5)).sort();
for (const [engine, launcher] of Object.entries({ chromium, firefox })) {
  const browser = await launcher.launch();
  try {
    for (const [width, theme] of [[1200, "light"], [375, "dark"]]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
      try {
        for (const slug of slugs) {
          const page = await context.newPage(), errors = [], offOrigin = [], failedRequests = [];
          page.on("pageerror", error => errors.push(error.message));
          page.on("request", request => {
            if (/^https?:/.test(request.url()) && !request.url().startsWith(baseURL)) offOrigin.push(request.url());
          });
          page.on("requestfailed", request => failedRequests.push(request.url()));
          await page.addInitScript(() => {
            window.hostedCsp = [];
            document.addEventListener("securitypolicyviolation", event => window.hostedCsp.push(event.violatedDirective));
          });
          await context.setOffline(false);
          const response = await page.goto(new URL(`${slug}.html`, baseURL).href);
          assert.equal(response.status(), 200);
          const local = await readFile(resolve(directory, `${slug}.html`));
          assert.equal(sha(await response.body()), sha(local));
          await page.evaluate(() => document.fonts.ready);
          await context.setOffline(true);
          const nav = page.getByRole("navigation", { name: "Report examples" });
          assert.equal(await nav.getByRole("link").count(), slugs.length);
          assert.equal(await nav.locator('[aria-current="page"]').getAttribute("href"), `${slug}.html`);
          assert.equal(await page.locator("script, iframe, object").count(), 0);
          if (slug !== "kubernetes") {
            const companion = await readFile(resolve(directory, `${slug}.json`));
            const expected = JSON.parse(companion);
            assert.equal(await page.locator("details.row").count(), expected.summary.total_tests);
            const pending = page.waitForEvent("download");
            await page.getByRole("link", { name: "Download this analysis as JSON" }).click();
            const download = await pending;
            assert.equal(download.suggestedFilename(), `${slug}.json`);
            assert.equal(sha(await readFile(await download.path())), sha(companion));
          } else {
            assert.equal(await page.locator(".row-heatmap svg.strip").count(), 28);
            assert.equal(await page.locator(".healthy-list li").count(), 1496);
          }
          if (slug === "cofailure") {
            const healthy = page.locator("details.row").filter({ has: page.locator('.name-text[title="tests.test_service.test_healthy_control"]') });
            await healthy.locator("summary").focus(); await page.keyboard.press("Enter");
            assert.equal(await healthy.getAttribute("open"), "");
            assert.match(await healthy.innerText(), /0%\s+\[0%[\u2013-]24%\]/);
            assert.match(await healthy.innerText(), /0 of 12 runs/);
          }
          if (slug === "incomplete") {
            const warning = page.locator("details.warning");
            await warning.locator("summary").focus(); await page.keyboard.press("Enter");
            assert.match(await warning.innerText(), /3 input \/ ordering warnings/);
            const unknown = page.locator("details.row").filter({ has: page.locator('.name-text[title="C.qualitativeUnknown"]') });
            await unknown.locator("summary").focus(); await page.keyboard.press("Enter");
            assert.equal(await unknown.locator(".s-unknown").count(), 1);
            assert.match(await unknown.innerText(), /unknown: no usable outcomes/);
          }
          let nativeArchive = null;
          if (slug === "generic") {
            const failing = page.locator('details.row').filter({ has: page.locator('.name-text[title="NativePairs.Pair<Int32,Double>.Check"]') });
            await failing.locator('summary').focus(); await page.keyboard.press('Enter');
            assert.equal(await failing.locator('.s-fail').count(), 6);
            assert.equal(await failing.locator('.s-pass, .s-unknown').count(), 0);
            const passing = page.locator('details.row').filter({ has: page.locator('.name-text[title="NativePairs.Pair<Int32,String>.Check"]') });
            await passing.locator('summary').focus(); await page.keyboard.press('Enter');
            assert.equal(await passing.locator('.s-pass').count(), 6);
            assert.equal(await passing.locator('.s-fail, .s-unknown').count(), 0);
            const pending = page.waitForEvent('download');
            await page.getByRole('link', { name: 'Download native TRX inputs', exact: true }).click();
            const archive = await pending;
            const file = `${engine}-${width}-generic-inputs.zip`;
            await archive.saveAs(resolve(output, file));
            const bytes = await readFile(resolve(output, file));
            assert.equal(sha(bytes), sha(await readFile(resolve(directory, 'generic-inputs.zip'))));
            nativeArchive = { file, bytes: bytes.length, sha256: sha(bytes) };
          }
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
          await page.evaluate(axe);
          assert.deepEqual(await page.evaluate(async () => (await window.axe.run()).violations.map(item => item.id)), []);
          assert.deepEqual(errors, []); assert.deepEqual(offOrigin, []); assert.deepEqual(failedRequests, []);
          assert.deepEqual(await page.evaluate(() => window.hostedCsp), []);
          if (["cofailure", "incomplete", "generic"].includes(slug)) {
            await page.screenshot({ path: resolve(output, `${engine}-${width}-${slug}.png`), fullPage: true });
          }
          views.push({ engine, browserVersion: browser.version(), width, theme, page: `${slug}.html`,
            responseMatchesBuild: true, offlineDisclosureAndDownload: true,
            ...(nativeArchive ? { nativeArchive } : {}),
            pageErrors: [], offOriginRequests: [], failedRequests: [], cspViolations: [], accessibilityViolations: [] });
          await page.close();
        }
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
await writeFile(resolve(output, "browser.json"), JSON.stringify({ checkedAtUtc: new Date().toISOString(), baseURL,
  scope: "Actual hosted precomputed gallery; byte agreement, offline disclosures and JSON downloads, two engines and widths. This does not deploy or exercise a native TRX processor.", views }, null, 2) + "\n");
console.log(JSON.stringify({ views: views.length, errors: 0 }));
