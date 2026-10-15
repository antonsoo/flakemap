// Inspect the CLI's original and installed-wheel reports before any network use.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox } from 'playwright';

const [before, after, screenshots] = process.argv.slice(2);
assert(before && after, 'Pass before and installed-after HTML directories.');
if (screenshots) await mkdir(screenshots, { recursive: true });
const cases = [
  'junit-same-report-contradictory', 'trx-run-directory-contradictory',
  'junit-sibling-report-contradictory', 'junit-same-report-consistent',
];
const checks = [];
for (const [engine, launcher] of Object.entries({ chromium, firefox })) {
  const browser = await launcher.launch();
  try {
    for (const width of [1200, 375]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, offline: true });
      try {
        const page = await context.newPage();
        const errors = [];
        const network = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
        for (const [phase, directory] of Object.entries({ before, after })) {
          for (const name of cases) {
            const file = resolve(directory, `${name}.html`);
            const bytes = await readFile(file);
            const response = await page.goto(pathToFileURL(file).href);
            if (response) assert.deepEqual(await response.body(), bytes);
            const unavailable = name.includes('contradictory') && (phase === 'after' || name.includes('sibling'));
            const expectedState = unavailable ? 'INTERMITTENT' : name.includes('consistent') ? 'QUIET' : 'NEW FLAKE';
            const row = page.locator('details.row').filter({ has: page.locator('.name-text[title="Checkout.authorizes"]') });
            assert.equal(await page.locator('details.row').count(), 2);
            assert.equal(await row.count(), 1);
            assert.equal(await row.locator('.row-heatmap .s-pass').count(), 27);
            assert.equal(await row.locator('.row-heatmap .s-fail').count(), 3);
            assert.equal(await row.locator('.row-heatmap .s-unknown').count(), 0);
            assert.equal(await row.locator('.stamp').innerText(), expectedState);
            assert.equal(await page.locator('.chronology-note').count(), Number(unavailable));
            await row.locator('summary').focus();
            await page.keyboard.press('Enter');
            assert.equal(await row.getAttribute('open'), '');
            assert.match(await row.innerText(), /runs: 30; skipped: 0; excluded: 0/);
            assert.equal(await row.locator('table.failures tbody tr').count(), 3);
            assert.match(await row.innerText(), unavailable ? /Failures, display order only/ : /Failures, newest first/);
            const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
            assert(overflow <= 1, `page overflow: ${overflow}`);
            assert.deepEqual(errors, []);
            assert.deepEqual(network, []);
            let screenshot = null;
            if (screenshots && engine === 'chromium' && width === 1200 && name === cases[0]) {
              screenshot = `${phase}.png`;
              await page.screenshot({ path: resolve(screenshots, screenshot), fullPage: true });
            }
            checks.push({ engine, version: browser.version(), width, phase, case: name,
              state: expectedState, chronology_available: !unavailable, failures_retained: 3,
              passes_retained: 27, keyboard_evidence: true, remote_requests: 0, errors: 0,
              page_overflow: overflow, html_sha256: createHash('sha256').update(bytes).digest('hex'),
              response_body_checked: Boolean(response), screenshot });
          }
        }
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
console.log(JSON.stringify({ checks: checks.length, results: checks }, null, 2));
