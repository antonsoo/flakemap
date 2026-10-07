// Open actual standalone reports from disk in both browser engines, offline.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium, firefox } from "playwright";

const require = createRequire(import.meta.url);
const axeSource = await readFile(require.resolve("axe-core/axe.min.js"), "utf8");
const directory = resolve(process.argv[2] ?? "scratch/browser");
const fixtures = JSON.parse(await readFile(resolve(directory, "manifest.json"), "utf8"));
const screenshots = resolve(directory, "screenshots");
await mkdir(screenshots, { recursive: true });
const results = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of [320, 1200]) {
      for (const colorScheme of ["light", "dark"]) {
        const context = await browser.newContext({
          viewport: { width, height: 900 }, colorScheme, offline: true,
          reducedMotion: "reduce",
        });
        try {
          const page = await context.newPage();
          await page.addInitScript(() => {
            window.reportCspViolations = [];
            document.addEventListener("securitypolicyviolation", event => {
              window.reportCspViolations.push(`${event.violatedDirective}: ${event.blockedURI}`);
            });
          });
          for (const fixture of fixtures) {
            const errors = [];
            const network = [];
            const errorListener = error => errors.push(error.message);
            const requestListener = request => {
              if (/^https?:/.test(request.url())) network.push(request.url());
            };
            page.on("pageerror", errorListener);
            page.on("request", requestListener);
            try {
              await page.goto(pathToFileURL(resolve(directory, `${fixture.name}.html`)).href);
              assert.equal(await page.locator("details.row").count(), fixture.tests);
              assert.equal(await page.locator(".row-heatmap .cell").count(), fixture.runs * fixture.tests);
              assert.equal(await page.locator("script, iframe, object").count(), 0);
              assert.match(await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute("content"), /default-src 'none'/);
              if (fixture.name.startsWith("gallery/")) {
                const nav = page.getByRole("navigation", { name: "Report examples" });
                assert.equal(await nav.getByRole("link").count(), 4);
                assert.equal(await nav.locator('[aria-current="page"]').count(), 1);
                assert.equal(await nav.locator('[aria-current="page"]').getAttribute("href"), `${fixture.name.split("/")[1]}.html`);
                const destination = fixture.name === "gallery/cofailure" ? "retry.html" : "cofailure.html";
                const link = nav.locator(`a[href="${destination}"]`);
                await link.focus();
                await page.keyboard.press("Enter");
                await page.waitForURL(`**/${destination}`);
                assert.equal(await page.locator(".cofailure").count(), 1);
                await page.goBack();
                await page.waitForURL(`**/${fixture.name}.html`);
                const pending = page.waitForEvent("download");
                await page.getByRole("link", { name: "Download this analysis as JSON" }).click();
                const download = await pending;
                assert.deepEqual(JSON.parse(await readFile(await download.path(), "utf8")),
                  JSON.parse(await readFile(resolve(directory, `${fixture.name}.json`), "utf8")));
              }
              if (fixture.name === "retry") {
                assert.equal(await page.locator(".row-heatmap .s-recovered").count(), 2);
                assert.equal(await page.locator(".row-heatmap .s-fail").count(), 1);
                assert.equal(await page.locator(".row-heatmap .s-error").count(), 1);
                assert.equal(await page.locator(".row-heatmap .s-skip").count(), 1);
                const row = page.locator("details.row").filter({ hasText: "recoversAfterTwoFailures" });
                await row.locator("summary").focus();
                await page.keyboard.press("Enter");
                assert.equal(await row.getAttribute("open"), "");
                assert.match(await row.locator(".evidence").innerText(), /3 recorded attempts; 2 failed/);
                assert.match(await row.locator(".evidence").innerText(), /report.xml :: testcase 5/);
                assert.notEqual(await row.locator("summary").evaluate(el => getComputedStyle(el).outlineStyle), "none");
                await page.keyboard.press("Space");
                assert.equal(await row.getAttribute("open"), null);
              }
              if (fixture.name === "incomplete") {
                const warning = page.locator("details.warning");
                await warning.locator("summary").focus();
                await page.keyboard.press("Enter");
                assert.match(await warning.innerText(), /salvaged 2 completed/);
                assert.match(await warning.innerText(), /Completed/);
                assert.match(await warning.innerText(), /invalid TRX duration/);
                const names = await page.locator(".test-identity").allTextContents();
                assert(!names.some(name => /imaginary|unfinished/.test(name)));
                const timing = page.locator("details.row").filter({ hasText: "C.sparseTiming" });
                await timing.locator("summary").click();
                assert.match(await timing.innerText(), /\+2000\.0 ms\/history run/);
                assert.match(await timing.innerText(), /Timing observations \(without retries\)\s+2/);
                const unknown = page.locator("details.row").filter({ hasText: "C.qualitativeUnknown" });
                await unknown.locator("summary").click();
                assert.match(await unknown.innerText(), /unknown: no usable outcomes/);
                assert.match(await unknown.innerText(), /02\/report.trx :: testcase 2/);
                assert.equal(await unknown.locator(".row-heatmap .s-unknown").count(), 1);
                const failure = page.locator("details.row").filter({ hasText: "C.closedFailure" });
                await failure.locator("summary").click();
                assert.match(await failure.innerText(), /<img src=x onerror=alert\(1\)>/);
                assert.equal(await page.locator("img").count(), 0);
              }
              const companion = JSON.parse(await readFile(resolve(directory, `${fixture.name}.json`), "utf8"));
              if (companion.cofailure.groups.length) {
                const groups = page.locator("details.cohort");
                assert.equal(await groups.count(), Math.min(20, companion.cofailure.groups.length));
                const first = groups.first();
                await first.locator("summary").focus();
                // A download click can leave Firefox in pointer modality after history
                // navigation. Enter alone on a programmatically focused element does not
                // establish keyboard focus. Exercise real tab navigation before checking it.
                await page.keyboard.press("Tab");
                await page.keyboard.press("Shift+Tab");
                assert(await first.locator("summary").evaluate(el => el === document.activeElement));
                await page.keyboard.press("Enter");
                assert.equal(await first.getAttribute("open"), "");
                assert.notEqual(await first.locator("summary").evaluate(el => getComputedStyle(el).outlineStyle), "none");
                assert.equal(await first.locator("tbody tr").count(), Math.min(40, companion.cofailure.groups[0].evidence.length));
                const pending = page.waitForEvent("download");
                await page.locator(".cofailure-download").click();
                const download = await pending;
                assert.equal(download.suggestedFilename(), "flakemap-cofailure.json");
                const exported = JSON.parse(await readFile(await download.path(), "utf8"));
                assert.deepEqual(exported, {
                  schema_version: 1, input_complete: companion.summary.input_complete,
                  warnings: companion.warnings, cofailure: companion.cofailure,
                });
                // A member link moves keyboard focus to the actual per-test disclosure.
                const link = first.locator(".cohort-members a").first();
                const target = await link.getAttribute("href");
                await link.focus();
                await page.keyboard.press("Enter");
                assert.equal(await page.evaluate(() => document.activeElement.id), target.slice(1));
                await page.keyboard.press("Enter");
                assert.equal(await page.locator(target).evaluate(el => el.parentElement.open), true);
                if (width === 320) {
                  const scroller = first.locator(".cohort-scroll");
                  await scroller.focus();
                  await page.keyboard.press("ArrowRight");
                  await page.waitForFunction(() => document.querySelector(".cohort-scroll").scrollLeft > 0);
                }
                await first.locator("summary").focus();
                await page.keyboard.press("Space");
                assert.equal(await first.getAttribute("open"), null);
                if (fixture.name === "cofailure") {
                  assert.match(await page.locator(".cofailure").innerText(), /3 tests in 1 exact outcome cohort/);
                  assert.equal(companion.cofailure.groups[0].evidence.length, 9);
                }
                if (fixture.name === "cofailure-bounds") {
                  assert.equal(companion.cofailure.groups.length, 22);
                  assert.equal(companion.cofailure.ambiguous_tests_excluded.length, 2);
                  assert.equal(companion.cofailure.groups[0].evidence.length, 625);
                  assert.equal(await first.locator(".cohort-members li").count(), 20);
                  await first.locator("summary").click();
                  assert.match(await first.innerText(), /Showing 40 of 625/);
                  assert.match(await first.innerText(), /5 more members/);
                  assert.match(await first.innerText(), /5 more in JSON/);
                  assert.match(await first.innerText(), /full text in JSON/);
                  assert.equal(await page.locator("img").count(), 0);
                }
              }
              await page.locator("details").evaluateAll(rows => rows.forEach(row => row.open = true));
              assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
              assert.equal(await page.locator('.row-heatmap [role="img"]:not([aria-label])').count(), 0);
              // Truncated row labels remain available in the opened panel, including on phones.
              for (const row of await page.locator("details.row").all()) {
                assert.equal(await row.locator(".test-identity").innerText(), await row.locator(".name-text").getAttribute("title"));
              }
              await page.evaluate(axeSource);
              const violations = await page.evaluate(async () => (await window.axe.run(document, {
                runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "best-practice"] },
              })).violations.map(item => ({ id: item.id, impact: item.impact, nodes: item.nodes.map(node => node.target) })));
              assert.deepEqual(violations, [], `${engine}/${width}/${colorScheme}/${fixture.name} accessibility`);
              assert.deepEqual(errors, []);
              assert.deepEqual(network, []);
              assert.deepEqual(await page.evaluate(() => window.reportCspViolations), []);
              if (["retry", "incomplete", "cofailure"].includes(fixture.name)) {
                await page.evaluate(() => {
                  document.querySelectorAll(".cohort-scroll").forEach(el => { el.scrollLeft = 0; });
                  window.scrollTo(0, 0);
                });
                await page.waitForTimeout(200);
                await page.screenshot({ path: resolve(screenshots, `${engine}-${width}-${colorScheme}-${fixture.name}.png`), fullPage: true });
              }
              results.push({ engine, browserVersion: browser.version(), width, colorScheme,
                fixture: fixture.name, runs: fixture.runs, tests: fixture.tests,
                accessibilityViolations: 0, pageErrors: 0, cspViolations: 0, networkRequests: 0 });
              console.log(`PASS ${engine} ${width}px ${colorScheme} ${fixture.name}`);
            } finally {
              page.off("pageerror", errorListener);
              page.off("request", requestListener);
            }
          }
        } finally {
          await context.close();
        }
      }
    }
  } finally {
    await browser.close();
  }
}
const artifacts = [];
for (const fixture of fixtures) {
  const bytes = await readFile(resolve(directory, `${fixture.name}.html`));
  artifacts.push({ fixture: fixture.name, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") });
}
await writeFile(resolve(directory, "browser-results.json"), JSON.stringify({
  generatedAt: new Date().toISOString(), node: process.version,
  playwright: require("playwright/package.json").version,
  axe: require("axe-core/package.json").version,
  scenarios: results, artifacts,
}, null, 2) + "\n");
console.log(`PASS ${results.length} offline report scenarios; evidence in ${directory}`);
