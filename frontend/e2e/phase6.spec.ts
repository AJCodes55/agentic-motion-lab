import { expect, test } from '@playwright/test';

test('keyboard skip link reaches reporting controls on a narrow screen', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/');
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: 'Skip to reporting controls' });
  await expect(skip).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#request-heading')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Reporting month')).toBeFocused();
  await expect(page.getByLabel('Reporting month')).toHaveValue('');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('new report tables and charts support keyboard scrolling on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/');
  const header = 'ride_id,rideable_type,started_at,ended_at,start_station_name,start_station_id,end_station_name,end_station_id,start_lat,start_lng,end_lat,end_lng,member_casual\n';
  const row = 'phase6,classic_bike,2026-04-01 10:00:00,2026-04-01 10:02:00,Start,001,End,002,40,-74,40,-74,member\n';
  await page.getByLabel('Choose data files').setInputFiles({ name: 'JC-202604-citibike-tripdata.csv', mimeType: 'text/csv', buffer: Buffer.from(header + row) });
  await page.getByRole('button', { name: 'Upload selected files' }).click();
  await expect(page.getByText('2026-04: accepted')).toBeVisible();
  await page.getByLabel('Reporting month').fill('2026-04');
  await page.getByRole('button', { name: 'Generate baseline report' }).click();
  const report = page.frameLocator('iframe[title="Baseline report for 2026-04"]');
  await expect(report.getByRole('heading', { name: 'Monthly mobility baseline: 2026-04' })).toBeVisible();
  const table = report.getByRole('region', { name: 'Scrollable data table' }).first();
  await table.focus();
  await expect(table).toBeFocused();
  await table.press('ArrowRight');
  await expect.poll(() => table.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
  const chart = report.getByRole('region', { name: 'Scrollable chart' }).first();
  await chart.focus();
  await expect(chart).toBeFocused();
  await chart.press('ArrowRight');
  await expect.poll(() => chart.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
