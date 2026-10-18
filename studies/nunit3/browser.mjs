// BASE_URL EXPECTED_SITE OUTPUT: actual served report and offline downloads.
// A file: URL can check a local build; HTTPS checks never substitute app bytes.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium, firefox } from 'playwright';

const [base, site, output] = process.argv.slice(2);
assert(base && site && output, 'BASE_URL EXPECTED_SITE OUTPUT');
await mkdir(output, { recursive: true });
const require = createRequire(import.meta.url);
const axe = await readFile(require.resolve('axe-core/axe.min.js'), 'utf8');
const expected = JSON.parse(await readFile(resolve(site, 'nunit.json'), 'utf8'));
const archiveSha = createHash('sha256').update(await readFile(resolve(site, 'nunit-inputs.zip'))).digest('hex');
const records = [];
for (const [engine, launcher] of Object.entries({ chromium, firefox })) {
  const browser = await launcher.launch();
  try {
    for (const [width, theme] of [[1200, 'light'], [375, 'dark']]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
      try {
        const page = await context.newPage(), errors = [], network = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(() => {
          window.reportCsp = [];
          document.addEventListener('securitypolicyviolation', event => window.reportCsp.push(event.violatedDirective));
        });
        const response = await page.goto(new URL('nunit.html', base).href);
        assert.equal(response.status(), 200);
        await context.setOffline(true);
        page.on('request', request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
        assert.equal(await page.locator('details.row').count(), 18);
        assert.equal(await page.locator('.demo-context h2').innerText(), 'Native NUnit results');
        assert.equal(await page.locator('.row-heatmap .s-unknown').count(), 2);
        assert.equal(await page.locator('.row-heatmap .s-pass').count(), 6);
        assert.equal(await page.locator('.row-heatmap .s-fail').count(), 3);
        assert.equal(await page.locator('.row-heatmap .s-error').count(), 4);
        assert.equal(await page.locator('.row-heatmap .s-skip').count(), 3);
        assert.equal(await page.getByRole('navigation', { name: 'Report examples' }).getByRole('link').count(), 7);
        const warnings = page.locator('details.warning');
        await warnings.locator('summary').focus();
        await page.keyboard.press('Enter');
        assert.match(await warnings.innerText(), /BrokenTeardown.*TearDown.*Controlled one-time teardown failure/s);
        const pair = page.locator('details.row').filter({ hasText: 'Pair<Int32,Double>.Check' });
        await pair.locator('summary').focus();
        await page.keyboard.press('Enter');
        assert.equal(await pair.locator('.test-identity').innerText(), 'NativeNUnit.Pair<Int32,Double>.Check');
        assert.match(await pair.innerText(), /Controlled generic fixture outcome/);
        const setup = page.locator('details.row').filter({ hasText: 'BrokenSetup.NeverReachedA' });
        await setup.locator('summary').click();
        assert.match(await setup.innerText(), /site=Parent.*OneTimeSetUp/);
        const downloads = [];
        for (const [label, kind] of [['Download this analysis as JSON', 'json'], ['Download native NUnit XML', 'zip']]) {
          const pending = page.waitForEvent('download');
          await page.getByRole('link', { name: label, exact: true }).click();
          const download = await pending;
          const bytes = await readFile(await download.path());
          const sha256 = createHash('sha256').update(bytes).digest('hex');
          if (kind === 'json') assert.deepEqual(JSON.parse(bytes), expected);
          else assert.equal(sha256, archiveSha);
          if (!records.length) await writeFile(resolve(output, `download.${kind}`), bytes);
          downloads.push({ kind, filename: download.suggestedFilename(), bytes: bytes.length, sha256 });
        }
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        assert.equal(await page.locator('script,iframe,object').count(), 0);
        await page.evaluate(axe);
        const violations = await page.evaluate(async () => (await window.axe.run()).violations.map(item => item.id));
        assert.deepEqual(violations, []);
        assert.deepEqual(errors, []);
        assert.deepEqual(network, []);
        assert.deepEqual(await page.evaluate(() => window.reportCsp), []);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: resolve(output, `${engine}-${width}.png`), fullPage: true });
        records.push({ engine, browserVersion: browser.version(), width, theme, offline: true,
          rows: 18, downloads, errors, network, axeViolations: violations, overflow: false, csp: [] });
        await page.close();
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
await writeFile(resolve(output, 'browser.json'), JSON.stringify({ checkedAtUtc: new Date().toISOString(), base,
  scope: 'Actual served native NUnit report, original identities, suite failure and parent/setup evidence, keyboard disclosures, actual JSON/native-input archive downloads after disconnection. No application assets intercepted.', records }, null, 2) + '\n');
console.log(`${records.length} served native NUnit workflows passed`);
