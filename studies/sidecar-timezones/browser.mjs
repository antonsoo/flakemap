// Inspect the generated before/installed-after reports offline in both engines.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox } from 'playwright';

const [before, after, screenshots] = process.argv.slice(2);
assert(before && after, 'Pass before and installed-after HTML directories.');
if (screenshots) await mkdir(screenshots, { recursive: true });
const profiles = ['aware-mixed', 'naive-mixed', 'naive-with-sequence', 'naive-with-report', 'naive-with-trx', 'real-conflict'];
const checks = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of [1200, 375]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, offline: true });
      try {
        const page = await context.newPage();
        const errors = [];
        const network = [];
        page.on('pageerror', e => errors.push(e.message));
        page.on('request', r => { if (/^https?:/.test(r.url())) network.push(r.url()); });
        for (const [phase, directory] of Object.entries({ before, after })) {
          for (const profile of profiles) {
            const file = resolve(directory, `${profile}.html`);
            const bytes = await readFile(file);
            const response = await page.goto(pathToFileURL(file).href);
            assert.deepEqual(await response.body(), bytes);
            const unavailable = profile === 'real-conflict' || (phase === 'before' ? profile === 'naive-with-sequence' : profile === 'naive-mixed');
            const state = unavailable ? null : profile === 'aware-mixed' || phase === 'after' ? 'QUIET' : 'NEW FLAKE';
            const row = page.locator('details.row');
            assert.equal(await row.count(), 1);
            assert.equal(await row.locator('.row-heatmap .s-pass').count(), 27);
            assert.equal(await row.locator('.row-heatmap .s-fail').count(), 3);
            assert.equal(await row.locator('.row-heatmap .s-unknown').count(), 0);
            assert.equal(await page.locator('.chronology-note').count(), Number(unavailable));
            assert.equal(await row.locator('.stamp').innerText(), state ?? 'INTERMITTENT');
            await row.locator('summary').focus();
            await page.keyboard.press('Enter');
            assert.equal(await row.getAttribute('open'), '');
            assert.match(await row.innerText(), /runs: 30; skipped: 0; excluded: 0/);
            assert.equal(await row.locator('table.failures tbody tr').count(), 3);
            assert.match(await row.innerText(), unavailable ? /Failures, display order only/ : /Failures, newest first/);
            if (state === 'QUIET') assert.match(await row.innerText(), /it has now been 25 runs/);
            const diagnostic = phase === 'after' && profile.startsWith('naive');
            if (diagnostic) {
              const warning = page.locator('details.warning');
              await warning.locator('summary').focus();
              await page.keyboard.press('Enter');
              assert.equal(await warning.getAttribute('open'), '');
              assert.match(await warning.innerText(), /explicit UTC offset \(for example Z or \+00:00\)/);
              await page.keyboard.press('Enter');
              assert.equal(await warning.getAttribute('open'), null);
            }
            const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
            assert(overflow <= 1, `${profile}: page overflow ${overflow}`);
            assert.deepEqual(errors, []);
            assert.deepEqual(network, []);
            let screenshot = null;
            if (screenshots && profile === 'naive-mixed') {
              screenshot = `${engine}-${width}-${phase}.png`;
              await page.screenshot({ path: resolve(screenshots, screenshot), fullPage: true });
            }
            checks.push({ engine, version: browser.version(), width, phase, profile, state, chronology_available: !unavailable,
              keyboard_evidence: true, offset_warning: diagnostic, remote_requests: 0, errors: 0, page_overflow: overflow,
              html_sha256: createHash('sha256').update(bytes).digest('hex'), screenshot });
          }
        }
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
console.log(JSON.stringify({ checks: checks.length, results: checks }, null, 2));
