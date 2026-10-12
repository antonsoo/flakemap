// Actual cmark-gfm output, offline; this is not a hosted GitHub-page test.
// node browser.mjs BEFORE_DIRECTORY AFTER_DIRECTORY OUTPUT_DIRECTORY
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { chromium, firefox } from 'playwright';

const [before, after, output] = process.argv.slice(2).map(path => resolve(path));
await mkdir(output, { recursive: true });
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const visible = text => text.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/g,
  ch => `\\x${ch.charCodeAt(0).toString(16).padStart(2, '0')}`).replaceAll('\n', ' ').replaceAll('\r', ' ');
const css = `body{font:16px/1.5 system-ui,sans-serif;color:#172033;background:white;margin:24px auto;padding:0 20px;max-width:1240px;overflow-wrap:anywhere}
table{font-size:14px;border-collapse:collapse;display:block;overflow:auto;margin:20px 0}td,th{border:1px solid #cbd2dc;padding:8px 10px;text-align:left;min-width:60px}td:first-child{min-width:260px}th{background:#eff2f6;white-space:nowrap}code{font:13px/1.5 ui-monospace,monospace;white-space:pre-wrap;background:#eff2f6}h1{font-size:28px}h2{font-size:23px}blockquote{border-left:4px solid #cbd2dc;margin-left:0;padding-left:12px}`;
const results = [];
for (const [engine, type] of Object.entries({ chromium, firefox })) {
  const browser = await type.launch();
  try {
    for (const width of [1440, 375]) {
      const context = await browser.newContext({ viewport: { width, height: 950 }, offline: true });
      await context.route('**/*', route => route.abort());
      const page = await context.newPage();
      let requests = [], errors = [];
      page.on('request', request => requests.push(request.url()));
      page.on('pageerror', error => errors.push(error.message));
      for (const [phase, path] of [['before', before], ['after', after]]) {
        const receipt = JSON.parse(await readFile(join(path, 'receipt.json'), 'utf8'));
        for (const item of receipt.workflows) {
          const bytes = await readFile(join(path, item.name, 'rendered.html'));
          assert.equal(hash(bytes), item.files['rendered.html'].sha256);
          requests = []; errors = [];
          await page.setContent(`<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Actual Flakemap Markdown report</title><style>${css}</style></head><body><main>${bytes.toString('utf8')}</main></body></html>`);
          const observed = await page.evaluate(() => ({
            images: document.querySelectorAll('img').length,
            importedLinks: [...document.querySelectorAll('a')].map(a => a.getAttribute('href')).filter(href => href !== 'https://github.com/antonsoo/flakemap'),
            codeChildren: document.querySelectorAll('code *').length,
            codeTexts: [...document.querySelectorAll('code')].map(el => el.textContent),
            text: document.body.textContent,
            overflow: document.documentElement.scrollWidth > innerWidth + 1,
          }));
          assert.equal(observed.images, item.images);
          assert.deepEqual(observed.importedLinks, item.importedLinks);
          assert.equal(observed.codeChildren, item.codeChildren);
          assert.deepEqual(observed.codeTexts, item.codeTexts);
          const literalFields = item.fields.filter(row => observed.text.includes(visible(row.value))).length;
          assert.equal(literalFields, item.fields.filter(row => row.literal).length);
          assert.equal(errors.length, 0);
          if (phase === 'after') {
            assert.equal(literalFields, item.fields.length);
            assert.equal(requests.length, 0);
            assert.equal(observed.overflow, false);
          }
          if ((engine === 'chromium' && width === 1440 && item.name === 'pytest') ||
              (engine === 'firefox' && width === 375 && item.name === 'warning')) {
            await page.screenshot({ path: join(output, `${phase}-${item.name}-${engine}-${width}.png`), fullPage: width > 375 });
          }
          results.push({ engine, version: browser.version(), width, phase, workflow: item.name,
            literalFields, fields: item.fields.length, images: observed.images,
            importedLinks: observed.importedLinks.length, codeChildren: observed.codeChildren,
            attemptedRequests: [...requests], pageErrors: [...errors], overflow: observed.overflow,
            offline: true, htmlSha256: hash(bytes) });
        }
      }
      await context.close();
    }
  } finally { await browser.close(); }
}
await writeFile(join(output, 'receipt.json'), JSON.stringify({ scope: 'Reference-rendered CLI Markdown in local presentation wrapper; no hosted GitHub or platform sanitization claim.', results }, null, 2) + '\n');
console.log(JSON.stringify({ loads: results.length, beforeRequests: results.filter(r => r.phase === 'before').reduce((n,r) => n + r.attemptedRequests.length,0), afterRequests: results.filter(r => r.phase === 'after').reduce((n,r) => n + r.attemptedRequests.length,0) }));
