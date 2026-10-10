// Inspect CLI-generated standalone reports in both engines with networking disabled.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium, firefox } from "playwright";

const directory = resolve(process.argv[2] ?? "scratch/junit-counters/after");
const captures = resolve(directory, "browser");
await mkdir(captures, { recursive: true });
const evidence = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of [375, 1200]) {
      for (const colorScheme of ["light", "dark"]) {
        const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme, offline: true });
        try {
          for (const name of ["removed-failing-tests", "surefire-attempts", "kubernetes-pruned"]) {
            const page = await context.newPage();
            const errors = [], network = [];
            page.on("pageerror", error => errors.push(error.message));
            page.on("request", request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
            const file = resolve(directory, name, "report.html");
            const analysis = JSON.parse(await readFile(resolve(directory, name, "analysis.json"), "utf8"));
            await page.goto(pathToFileURL(file).href);
            assert.equal(await page.locator("details.row").count(), analysis.summary.total_tests);
            assert.equal(await page.locator(".row-heatmap .cell").count(), analysis.summary.total_tests);
            const warning = page.locator("details.warning");
            assert.equal(await warning.count(), analysis.summary.input_complete ? 0 : 1);
            if (!analysis.summary.input_complete) {
              await warning.locator("summary").focus();
              await page.keyboard.press("Enter");
              assert.equal(await warning.getAttribute("open"), "");
              assert.match(await warning.innerText(), /JUnit summary counters do not reconcile/);
              assert.match(await warning.innerText(), /report\.xml/);
              if (name === "removed-failing-tests") {
                assert.match(await warning.innerText(), /declares tests=4, failures=1, errors=1/);
                assert.match(await warning.innerText(), /testcase records \(tests=2, failures=0, errors=0/);
              }
            }
            assert.equal(await page.locator("script,iframe,object").count(), 0);
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
            assert.deepEqual(errors, []);
            assert.deepEqual(network, []);
            if (engine === "chromium" && name === "removed-failing-tests" &&
                ((width === 1200 && colorScheme === "light") || (width === 375 && colorScheme === "dark"))) {
              await page.screenshot({ path: resolve(captures, `${width}-${colorScheme}.png`), fullPage: true });
            }
            evidence.push({ engine, width, colorScheme, case: name,
              html_sha256: createHash("sha256").update(await readFile(file)).digest("hex"),
              input_complete: analysis.summary.input_complete, errors, network });
            await page.close();
          }
        } finally { await context.close(); }
      }
    }
  } finally { await browser.close(); }
}
await writeFile(resolve(captures, "results.json"), JSON.stringify(evidence, null, 2) + "\n");
console.log(`Verified ${evidence.length} offline report views.`);
