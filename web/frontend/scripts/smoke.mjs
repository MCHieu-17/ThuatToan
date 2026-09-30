import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const browser = await chromium.launch({
  executablePath: process.env.BROWSER_EXECUTABLE || '/usr/bin/brave-browser',
  headless: true,
  args: ['--no-sandbox'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));

try {
  await page.goto(process.env.WEB_URL || 'http://127.0.0.1:3000/', { waitUntil: 'networkidle' });
  await page.locator('.network-map').waitFor();
  assert.match(await page.locator('.stat-strip').innerText(), /10/);
  await page.getByRole('button', { name: /Chạy mô phỏng/ }).click();
  await page.locator('.vehicle-row').first().waitFor({ timeout: 30000 });
  assert.equal(await page.locator('.timeline-tick').count(), 6);
  await page.locator('.timeline-tick').nth(1).click({ force: true });
  assert.match(await page.locator('.decision-panel').innerText(), /Lập lại tuyến/);
  await page.getByRole('button', { name: /So sánh/ }).click();
  assert.match(await page.locator('.comparison-head').innerText(), /Ba phương pháp/);
  await page.getByRole('button', { name: /Chạy cả 3/ }).click();
  await page.locator('.route-card').first().waitFor({ timeout: 30000 });
  assert.equal(await page.locator('.route-card').count(), 3);
  await page.getByRole('button', { name: /Giải thích thuật toán/ }).click();
  assert.match(await page.locator('.proof-copy').innerText(), /ALG ≤ 2 × MST ≤ 2 × OPT/);
  assert.equal(errors.length, 0, errors.join('\n'));
  console.log('Browser smoke passed: run, playback, comparison, proof.');
} finally {
  await browser.close();
}
