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
              if (["retry", "incomplete"].includes(fixture.name)) {
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
