// Inspect actual standalone reports produced by reproduce.py, including from a wheel.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium, firefox } from "playwright";

const require = createRequire(import.meta.url);
const axe = await readFile(require.resolve("axe-core/axe.min.js"), "utf8");
const directory = resolve(process.argv[2]);
const destination = resolve(process.argv[3] ?? directory);
await mkdir(destination, { recursive: true });
const expected = {
  continuing_retries: { state: "ongoing", recovered: 15, final: 3, text: "18 runs with observed failures (15 passed on retry)" },
  actually_quiet: { state: "quiet", recovered: 3, final: 0, text: "Quiet: 3 runs with observed failures (3 passed on retry)" },
  new_retries: { state: "new", recovered: 3, final: 0, text: "the first failure came after 15 clean runs of 20" },
  ambiguous_tail: { state: null, recovered: 0, final: 3, text: "ambiguous outcomes interrupt the failure history" },
};
const results = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of [375, 1200]) {
      const colorScheme = width === 375 ? "light" : "dark";
      const context = await browser.newContext({ viewport: { width, height: 950 }, colorScheme, offline: true });
      try {
        const page = await context.newPage();
        for (const [name, want] of Object.entries(expected)) {
          const errors = [], network = [];
          const onError = error => errors.push(error.message);
          const onRequest = request => { if (/^https?:/.test(request.url())) network.push(request.url()); };
          page.on("pageerror", onError);
          page.on("request", onRequest);
          await page.goto(pathToFileURL(resolve(directory, `${name}.html`)).href);
          const row = page.locator("details.row");
          assert.equal(await row.count(), 1);
          assert.equal(await row.locator(".s-recovered").count(), want.recovered);
          assert.equal(await row.locator(".s-fail").count(), want.final);
          await row.locator("summary").focus();
          await page.keyboard.press("Enter");
          assert.equal(await row.getAttribute("open"), "");
          assert((await row.innerText()).includes(want.text));
          assert.equal(await row.locator(".stamp-quiet").count(), want.state === "quiet" ? 1 : 0);
          assert.equal(await row.locator(".stamp-new").count(), want.state === "new" ? 1 : 0);
          const data = JSON.parse(await readFile(resolve(directory, `${name}.json`), "utf8"));
          assert.equal(data.tests[0].activity?.state ?? null, want.state);
          assert.equal(data.tests[0].runs.fail, want.final);
          if (name === "continuing_retries") {
            assert.match((await row.locator(".evidence").allInnerTexts()).join("\n"), /run-19\/report.xml :: testcase 1/);
            assert(!(await row.innerText()).includes("The burst is over"));
          }
          if (name === "ambiguous_tail") {
            assert.equal(data.tests[0].activity_unavailable_reason, "ambiguous_outcomes");
            assert.equal(await row.locator(".s-unknown").count(), 1);
          }
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          await page.evaluate(axe);
          const violations = await page.evaluate(async () => (await window.axe.run(document, {
            runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "best-practice"] },
          })).violations.map(v => v.id));
          assert.deepEqual(violations, []);
          assert.deepEqual(errors, []);
          assert.deepEqual(network, []);
          let screenshot = null;
          if (name === "continuing_retries" || (name === "new_retries" && width === 1200)) {
            screenshot = `${engine}-${width}-${name}.png`;
            await page.screenshot({ path: resolve(destination, screenshot), fullPage: width !== 375 });
          }
          const bytes = await readFile(resolve(directory, `${name}.html`));
          results.push({ engine, browserVersion: browser.version(), width, colorScheme, scenario: name,
            offline: true, pageErrors: errors, networkRequests: network, accessibilityViolations: violations,
            htmlSha256: createHash("sha256").update(bytes).digest("hex"), screenshot,
            screenshotArea: screenshot ? (width === 375 ? "viewport" : "full page") : null });
          page.off("pageerror", onError);
          page.off("request", onRequest);
        }
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
await writeFile(resolve(destination, "browser.json"), JSON.stringify(results, null, 2) + "\n");
console.log(`Passed ${results.length} offline report scenarios, including keyboard evidence inspection.`);
