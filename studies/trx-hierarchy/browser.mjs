// Inspect real CLI output files offline; no report server or injected product script.
// node studies/trx-hierarchy/browser.mjs REPLAY_DIR SCREENSHOT_DIR
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium, firefox } from "playwright";

const [directory, output] = process.argv.slice(2);
assert(directory && output, "REPLAY_DIR SCREENSHOT_DIR");
await mkdir(output, { recursive: true });
const require = createRequire(import.meta.url);
const axe = await readFile(require.resolve("axe-core/axe.min.js"), "utf8");
const replay = JSON.parse(await readFile(resolve(directory, "results.json"), "utf8"));
const views = [];
for (const [engine, launcher] of Object.entries({ chromium, firefox })) {
  const browser = await launcher.launch();
  try {
    for (const width of [1200, 375]) {
      for (const theme of ["light", "dark"]) {
        const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme, offline: true });
        try {
          for (const item of replay.observations) {
            const page = await context.newPage(), errors = [], network = [];
            page.on("pageerror", error => errors.push(error.message));
            page.on("request", request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
            await page.addInitScript(() => {
              window.nativeCsp = [];
              document.addEventListener("securitypolicyviolation", event => window.nativeCsp.push(event.violatedDirective));
            });
            await page.goto(pathToFileURL(resolve(directory, item.case, "report.html")).href);
            assert.equal(await page.locator("details.row").count(), item.analysis.summary.total_tests);
            assert.equal(await page.locator("script, iframe, object").count(), 0);
            const parent = page.locator("details.row").filter({ has: page.locator('.name-text[title="Capture.Example.Data"]') });
            assert.equal(await parent.count(), 1);
            await parent.locator("summary").focus(); await page.keyboard.press("Enter");
            assert.equal(await parent.getAttribute("open"), "");
            const data = item.analysis.tests.find(test => test.test === "Capture.Example.Data");
            const unknown = data.runs.unknown > 0;
            assert.equal(await parent.locator(".s-unknown").count(), Number(unknown));
            const warning = page.locator("details.warning");
            assert.equal(await warning.count(), Number(!item.analysis.summary.input_complete));
            if (!item.analysis.summary.input_complete) {
              await warning.locator("summary").focus(); await page.keyboard.press("Enter");
              assert.match(await warning.innerText(), /conflicts with recorded failing inner results/);
              assert.match(await parent.innerText(), /reported (Passed|NotExecuted); normalized unknown/);
              assert.match(await parent.innerText(), /Controlled nested row failure/);
              assert.equal((await parent.locator(".row-rate").innerText()).trim(), "n/a");
            }
            await page.evaluate(() => document.fonts.ready);
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
            await page.evaluate(axe);
            const violations = await page.evaluate(async () => (await window.axe.run()).violations.map(item => item.id));
            assert.deepEqual(violations, []);
            assert.deepEqual(errors, []); assert.deepEqual(network, []);
            assert.deepEqual(await page.evaluate(() => window.nativeCsp), []);
            if (item.case === "passed-parent-failed-row" && theme === (width === 1200 ? "light" : "dark")) {
              await page.screenshot({ path: resolve(output, `${engine}-${width}.png`), fullPage: true });
            }
            views.push({ engine, width, theme, case: item.case, inputComplete: item.analysis.summary.input_complete,
              parent: data.runs, noOverflow: true, axeViolations: [], pageErrors: errors, networkRequests: network, cspViolations: [] });
            await page.close();
          }
        } finally { await context.close(); }
      }
    }
  } finally { await browser.close(); }
}
await writeFile(resolve(output, "browser.json"), JSON.stringify({ scope: "Actual CLI-generated standalone HTML files, offline in both engines; keyboard disclosure, JSON/DOM agreement, native evidence labels and accessibility.", views }, null, 2) + "\n");
console.log(JSON.stringify({ views: views.length, errors: 0 }));
