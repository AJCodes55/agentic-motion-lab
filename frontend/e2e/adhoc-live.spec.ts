import { expect, test } from '@playwright/test';
const header = 'ride_id,rideable_type,started_at,ended_at,start_station_name,start_station_id,end_station_name,end_station_id,start_lat,start_lng,end_lat,end_lng,member_casual\n';
const row = (id: string, station: string) => `${id},classic_bike,2026-03-01 10:00:00,2026-03-01 10:02:00,Park,${station},End,002,40,-74,40,-74,member\n`;
test('real query selects station, renders chart, and reads immutable history', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Choose data files').setInputFiles({ name: 'JC-202603-citibike-tripdata.csv', mimeType: 'text/csv', buffer: Buffer.from(header + row('one', 'P1') + row('two', 'P2')) });
  await page.getByRole('button', { name: 'Upload selected files' }).click();
  await expect(page.getByText('2026-03: accepted')).toBeVisible();
  await page.getByLabel('Reporting month').fill('2026-03');
  await page.getByLabel('Supported metric').selectOption('station_starts');
  await page.getByLabel('Station name or ID (optional)').fill('Park');
  await page.getByLabel('Include chart').check();
  await page.getByRole('button', { name: 'Run supported query' }).click();
  const answerResponse = page.waitForResponse(response => response.url().endsWith('/api/adhoc') && response.request().method() === 'POST' && response.request().postDataJSON().station_id === 'P1');
  await page.getByRole('button', { name: 'Park (P1)' }).click();
  const answer = await (await answerResponse).json();
  const report = page.frameLocator('iframe[title="Supported query report for 2026-03"]');
  await expect(report.getByRole('heading', { name: 'Station starts: Park (P1)' })).toBeVisible();
  await expect(report.locator('svg')).toBeVisible();
  // Synchronize the mouse after scrolling past the sandboxed report frame.
  await page.getByRole('button', { name: 'Refresh report history' }).scrollIntoViewIfNeeded();
  await page.getByRole('button', { name: 'Refresh report history' }).hover();
  await page.getByRole('button', { name: 'Refresh report history' }).click();
  await page.getByRole('button', { name: `Open adhoc report for 2026-03 (${answer.data.report_id})`, exact: true }).click();
  await expect(page.frameLocator('iframe[title^="Archived report"]').getByRole('heading', { name: 'Station starts: Park (P1)' })).toBeVisible();
});
