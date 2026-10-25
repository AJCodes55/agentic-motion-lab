import { expect, test } from '@playwright/test';

test('selects an ambiguous station and opens archived verified answer', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { success: true, data: { status: 'ok' } } }));
  await page.route('**/api/adhoc', async route => {
    const request = route.request().postDataJSON();
    expect(request).toMatchObject({ period: { year: 2026, month: 2 }, metric: 'station_starts', station_query: 'Park', comparison: true, chart: true });
    await route.fulfill({ json: { success: true, data: request.station_id
      ? { status: 'success', message: 'Verified answer ready.', html: '<h1>Park starts</h1>' }
      : { status: 'needs_station_selection', message: 'Choose a station.', station_choices: [{ station_id: 'A', station_name: 'Park' }, { station_id: 'B', station_name: 'Park' }] } } });
  });
  await page.route('**/api/reports/history', route => route.fulfill({ json: { success: true, data: { reports: [{ report_id: 'saved', report_kind: 'adhoc', status: 'complete', period: { year: 2026, month: 2 } }] } } }));
  await page.route('**/api/reports/history/saved?kind=adhoc', route => route.fulfill({ json: { success: true, data: { html: '<h1>Archived Park starts</h1>' } } }));
  await page.goto('/');
  await page.getByLabel('Reporting month').fill('2026-02');
  await page.getByLabel('Supported metric').selectOption('station_starts');
  await page.getByLabel('Station name or ID').fill('Park');
  await page.getByLabel('Compare with previous month').check();
  await page.getByLabel('Include chart').check();
  await page.getByRole('button', { name: 'Run supported query' }).click();
  await page.getByRole('button', { name: 'Park (A)' }).click();
  await expect(page.frameLocator('iframe[title="Supported query report for 2026-02"]').getByRole('heading', { name: 'Park starts' })).toBeVisible();
  // Synchronize the mouse after scrolling past the sandboxed report frame.
  await page.getByRole('button', { name: 'Refresh report history' }).scrollIntoViewIfNeeded();
  await page.getByRole('button', { name: 'Refresh report history' }).hover();
  await page.getByRole('button', { name: 'Refresh report history' }).click();
  await page.getByRole('button', { name: 'Open adhoc report for 2026-02 (saved)' }).click();
  await expect(page.frameLocator('iframe[title="Archived report saved"]').getByRole('heading', { name: 'Archived Park starts' })).toBeVisible();
});
