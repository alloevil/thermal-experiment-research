async (page) => {
  const base = 'http://127.0.0.1:18766/';
  const checks = [];
  const requests = [];
  const errors = [];
  const failedResponses = [];
  const require = (condition, message) => { if (!condition) throw new Error(message); };
  page.on('request', request => requests.push(request.url()));
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => { if (response.status() >= 400) failedResponses.push(response.url()); });
  await page.goto(base);
  await page.emulateMedia({reducedMotion: 'reduce'});
  require(await page.locator('h1').count() === 1, 'Expected one h1');
  require(await page.locator('#case-100').isVisible(), 'Initial 100s case missing');
  require(await page.locator('#case-300').isHidden(), 'Both enhanced cases visible');
  require(await page.locator('meta[name="robots"]').getAttribute('content') === 'noindex, nofollow', 'Preview must not be indexed');
  checks.push('PASS semantic entrypoint and noindex preview');

  await page.getByRole('radio', {name: '前 100 秒'}).focus();
  await page.keyboard.press('ArrowRight');
  require(await page.getByRole('radio', {name: '前 300 秒'}).isChecked(), 'Radio keyboard navigation failed');
  require(await page.locator('#case-300').isVisible(), '300s case not shown');
  require((await page.locator('#case-300 [data-metric="validation"]').textContent()).includes('2.169'), '300s metric mismatch');
  require((await page.locator('#run-command').textContent()).includes('--before-seconds 300'), 'Command did not follow case');
  await page.keyboard.press('ArrowLeft');
  require(await page.locator('#case-100').isVisible(), 'Keyboard return to 100s failed');
  checks.push('PASS native keyboard window switching; metrics and command synchronized');

  await page.locator('#point-100').focus();
  await page.keyboard.press('End');
  await page.keyboard.press('ArrowLeft');
  const reading = await page.evaluate(() => {
    const rows = JSON.parse(document.getElementById('case-data').textContent)['100'];
    const slider = document.getElementById('point-100');
    const output = document.getElementById('reading-100').textContent;
    const row = rows[597];
    return {index: slider.value, time: output.includes(row[0].toFixed(3)),
      values: row.slice(2).every(value => output.includes(value.toFixed(2))),
      cursor: [...document.querySelectorAll('#case-100 [data-cursor]')].every(cursor =>
        Math.abs(Number(cursor.getAttribute('x1')) - Number(cursor.dataset.left) - row[0] / 600 * Number(cursor.dataset.width)) < 1e-7)};
  });
  require(reading.index === '597' && reading.time && reading.values && reading.cursor, 'Point inspector differs from source data');
  checks.push('PASS keyboard point inspector and both SVG cursors match saved row 597');

  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  const expectedCommand = await page.locator('#run-command').textContent();
  require(expectedCommand.includes('\\\n'), 'Command lost shell continuations');
  await page.getByRole('button', {name: '复制命令'}).click();
  await page.locator('#copy-status').filter({hasText: '命令已复制'}).waitFor();
  require(await page.evaluate(() => navigator.clipboard.readText()) === expectedCommand, 'Clipboard content mismatch');
  checks.push('PASS actual clipboard content matches displayed command');
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
      writeText: async () => { throw new Error('Clipboard denied for negative-path test'); }
    }});
  });
  await page.getByRole('button', {name: '复制命令'}).click();
  await page.locator('#copy-status').filter({hasText: '未能自动复制'}).waitFor();
  require(await page.evaluate(() => window.getSelection().toString()) === expectedCommand, 'Manual selection fallback missing');
  checks.push('PASS clipboard denial reports failure and selects text, without false success');

  await page.reload();
  const summary = page.locator('.faq-list summary').first();
  await summary.focus();
  await page.keyboard.press('Enter');
  require(await page.locator('.faq-list details').first().getAttribute('open') !== null, 'FAQ keyboard disclosure failed');
  await page.keyboard.press('Enter');
  await page.getByRole('radio', {name: '前 300 秒'}).check();
  for (const width of [1440, 900, 360]) {
    await page.setViewportSize({width, height: 900});
    require(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Horizontal overflow at ${width}px`);
    await page.screenshot({path: `output/playwright/verified-${width}.png`, fullPage: true});
    checks.push(`PASS ${width}px viewport without horizontal overflow; screenshot saved`);
  }
  require(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior) === 'auto', 'Reduced motion not respected');
  const downloadEvent = page.waitForEvent('download');
  await page.locator('a[download][href="evidence/before-300/prediction.csv"]').click();
  const download = await downloadEvent;
  require(await download.failure() === null, 'Evidence download failed');
  await download.saveAs('output/playwright/download-before-300.csv');
  checks.push('PASS CSV download and reduced-motion setting');

  const noScript = await page.context().browser().newContext({javaScriptEnabled: false, viewport: {width: 360, height: 800}});
  const staticPage = await noScript.newPage();
  staticPage.on('request', request => requests.push(request.url()));
  await staticPage.goto(base);
  require(await staticPage.locator('#case-100').isVisible() && await staticPage.locator('#case-300').isVisible(), 'No-JS evidence missing');
  require(await staticPage.locator('.window-switch').isHidden(), 'No-JS controls should not look operable');
  require(await staticPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No-JS mobile overflow');
  await staticPage.screenshot({path: 'output/playwright/verified-no-js-360.png', fullPage: true});
  await noScript.close();
  checks.push('PASS no-JavaScript mobile page keeps both complete cases readable');
  require(errors.length === 0, 'Browser errors: ' + errors.join('; '));
  require(failedResponses.length === 0, 'HTTP errors: ' + failedResponses.join('; '));
  require(requests.every(url => url.startsWith(base)), 'Unexpected external runtime request');
  checks.push(`PASS ${requests.length} same-origin runtime requests; zero external requests, page errors or HTTP errors`);
  return {status: 'PASS', checks};
}
