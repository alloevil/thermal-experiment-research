async (page) => {
  const base = page.url().split('#')[0];
  const results = [];
  const require = (condition, message) => { if (!condition) throw new Error(message); };
  await page.goto(base);
  await page.emulateMedia({reducedMotion: 'reduce'});
  for (const [width, height] of [[1440, 900], [900, 900], [360, 900], [360, 800]]) {
    await page.setViewportSize({width, height});
    await page.getByRole('radio', {name: '前 100 秒'}).check();
    await page.evaluate(() => window.scrollTo(0, 0));
    const measurement = await page.evaluate(() => {
      const paragraphs = [...document.querySelectorAll('p')].filter(element => element.getClientRects().length);
      const labels = [...document.querySelectorAll('#case-100 .axis')].filter(element => element.getClientRects().length);
      return {
        width: innerWidth, viewportHeight: innerHeight, documentHeight: document.documentElement.scrollHeight,
        chartTop: document.querySelector('#case-100 .plots').getBoundingClientRect().top + scrollY,
        smallParagraphs: paragraphs.filter(element => parseFloat(getComputedStyle(element).fontSize) < 14).length,
        smallestAxisLabel: Math.min(...labels.map(element => parseFloat(getComputedStyle(element).fontSize) * element.getScreenCTM().a)),
        overflow: document.documentElement.scrollWidth > innerWidth
      };
    });
    require(!measurement.overflow, `Horizontal overflow at ${width}`);
    require(measurement.smallParagraphs === 0, `Small text at ${width}`);
    require(measurement.smallestAxisLabel >= 12, `Small chart labels at ${width}`);
    require(measurement.chartTop <= (width === 360 ? 650 : 680), `Chart too low at ${width}`);
    if (width === 1440) require(measurement.chartTop <= 600, 'Desktop first-screen goal not met');
    await page.screenshot({path: `output/playwright/redesign/final-${width}-${height}.png`, fullPage: true});
    await page.screenshot({path: `output/playwright/redesign/first-screen-${width}-${height}.png`});
    results.push(measurement);
  }
  await page.getByRole('radio', {name: '前 300 秒'}).check();
  await page.locator('#case-300 .plots').scrollIntoViewIfNeeded();
  await page.screenshot({path: 'output/playwright/redesign/mobile-300-detail.png'});
  return {status: 'PASS', measurements: results};
}
