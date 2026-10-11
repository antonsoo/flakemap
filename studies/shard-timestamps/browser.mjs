// Inspect generated standalone reports offline, including keyboard-opened evidence.
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox } from 'playwright';

const [before, after, screenshots] = process.argv.slice(2);
assert(before && after, 'Pass the before and installed-after HTML artifact directories.');
if (screenshots) await mkdir(screenshots, { recursive: true });
const checks = [];
for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1200, height: 850 }, offline: true });
    const errors = [];
    const remote = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', request => { if (/^https?:/.test(request.url())) remote.push(request.url()); });
    for (const [phase, directory] of Object.entries({ before, after })) {
      for (const profile of ['sidecar-over-report', 'real-conflict']) {
        await page.goto(pathToFileURL(resolve(directory, `${profile}.html`)).href);
        const excluded = phase === 'before' || profile === 'real-conflict';
        assert.equal(await page.locator('details.row').count(), 3);
        assert.equal(await page.locator('.row-heatmap .s-unknown').count(), excluded ? 3 : 0);
        assert.equal(await page.locator('.row-heatmap .s-pass').count(), excluded ? 0 : 3);
        const tally = page.locator('.tally-item').filter({ hasText: 'test-runs excluded' });
        assert.equal(await tally.locator('b').innerText(), excluded ? '3' : '0');
        const first = page.locator('details.row').first();
        await first.locator('summary').focus();
        await page.keyboard.press('Enter');
        assert.equal(await first.getAttribute('open'), '');
        assert.match(await first.innerText(), excluded ? /excluded: 1/ : /runs: 1; skipped: 0; excluded: 0/);
        assert.equal(errors.length, 0);
        assert.equal(remote.length, 0);
        if (screenshots && name === 'chromium' && profile === 'sidecar-over-report') {
          await page.screenshot({ path: resolve(screenshots, `${phase}.png`), fullPage: true });
        }
        checks.push({ engine: name, phase, profile, excluded: excluded ? 3 : 0, keyboard_details: true });
      }
    }
  } finally { await browser.close(); }
}
console.log(JSON.stringify({ checks }, null, 2));
