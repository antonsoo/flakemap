// Check the actual installed-package report offline, including its absent/skip evidence.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium, firefox } from "playwright";

const directory = resolve(process.argv[2]);
const destination = resolve(process.argv[3]);
await mkdir(destination, { recursive: true });
const require = createRequire(import.meta.url);
const axe = await readFile(require.resolve("axe-core/axe.min.js"), "utf8");
const results = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of [375, 1200]) {
      for (const colorScheme of ["light", "dark"]) {
        const context = await browser.newContext({ viewport: { width, height: 950 }, colorScheme, offline: true });
        try {
          const page = await context.newPage();
          for (const scenario of ["retired", "recent"]) {
            const errors = [], network = [];
            const onError = error => errors.push(error.message);
            const onRequest = request => { if (/^https?:/.test(request.url())) network.push(request.url()); };
            page.on("pageerror", onError);
            page.on("request", onRequest);
            await page.goto(pathToFileURL(resolve(directory, scenario, "report.html")).href);
            assert.equal(await page.locator("details.row").count(), 3);
            for (const [name, tail] of [["test_removed_after_build_35", "s-missing"], ["test_skipped_after_build_35", "s-skip"]]) {
              const row = page.locator("details.row").filter({ hasText: name });
              assert.equal(await row.locator(".s-fail").count(), 3);
              assert.equal(await row.locator(`.${tail}`).count(), scenario === "retired" ? 20 : 0);
              await row.locator("summary").focus();
              await page.keyboard.press("Enter");
              assert.equal(await row.getAttribute("open"), "");
              assert.match(await row.innerText(), /controlled old failure/);
              assert.match(await row.innerText(), /run-30/);
            }
            const data = JSON.parse(await readFile(resolve(directory, scenario, "report.json"), "utf8"));
            assert.equal(data.summary.input_complete, true);
            for (const test of data.tests.filter(test => test.runs.fail)) {
              assert.equal(test.history_runs_since_first_failure, scenario === "retired" ? 26 : 6);
              assert.equal(test.activity.runs_since_first_failure, 6);
            }
            assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
            await page.evaluate(axe);
            const violations = await page.evaluate(async () => (await window.axe.run(document, {
              runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "best-practice"] },
            })).violations.map(violation => violation.id));
            assert.deepEqual(violations, []);
            assert.deepEqual(errors, []);
            assert.deepEqual(network, []);
            let screenshot = null;
            if (scenario === "retired" && colorScheme === (width === 375 ? "light" : "dark")) {
              screenshot = `${engine}-${width}.png`;
              await page.screenshot({ path: resolve(destination, screenshot), fullPage: true });
            }
            results.push({ engine, browserVersion: browser.version(), width, colorScheme, scenario,
              offline: true, errors, network, accessibilityViolations: violations,
              htmlSha256: createHash("sha256").update(await readFile(resolve(directory, scenario, "report.html"))).digest("hex"),
              screenshot });
            page.off("pageerror", onError);
            page.off("request", onRequest);
          }
        } finally { await context.close(); }
      }
    }
  } finally { await browser.close(); }
}
await writeFile(resolve(destination, "browser.json"), JSON.stringify(results, null, 2) + "\n");
console.log(`Passed ${results.length} offline browser scenarios.`);
