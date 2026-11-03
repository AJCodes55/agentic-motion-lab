import { expect, test } from '@playwright/test';

test('inspects a completed station trace and replaces it with the next query', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { success: true, data: { status: 'ok' } } }));
  let count = 0;
  await page.route('**/api/agent-runs/stream', async route => {
    count += 1;
    const result = { run_id: `run-${count}`, status: 'refused', report_html: '', warning: 'No matching start station exists in the requested months.', stages: [], trace: [] };
    const events = [
      { type: 'trace', data: { sequence: 1, stage: 'routing', operation: 'station_resolution', status: 'success', source: 'application', summary: `Station lookup for query ${count}.`, inputs: route.request().postDataJSON(), output: { station_id: count === 1 ? 'OC8765' : 'UNKNOWN', matches: [] } } },
      { type: 'trace', data: { sequence: 2, stage: 'rendering', operation: 'final_response', status: 'success', source: 'application', summary: 'Request refused.', output: result } },
      { type: 'result', data: result },
    ];
    await route.fulfill({ contentType: 'application/x-ndjson', body: events.map(event => JSON.stringify(event)).join('\n') + '\n' });
  });
  await page.goto('/');
  await page.getByLabel('Reporting month').fill('2026-07');
  await page.getByLabel('Analysis request').fill('Total rides for station OC8765 in July 2026');
  await page.getByRole('button', { name: 'Run agent analysis' }).click();
  const trace = page.getByRole('region', { name: 'Trace' });
  await expect(trace.locator('details').first()).not.toHaveAttribute('open');
  await expect(page.locator('main > section').last()).toHaveAttribute('id', 'trace');
  await trace.getByText('Show more', { exact: true }).click();
  await expect(trace.getByText('Station lookup for query 1.')).toBeVisible();
  const lookup = trace.getByRole('listitem').first();
  await lookup.getByText('Inputs', { exact: true }).click();
  await expect(lookup.getByLabel('Inputs')).toContainText('OC8765');
  await lookup.getByText('Output', { exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(lookup.getByLabel('Output')).toContainText('"matches": []');
  await page.getByLabel('Analysis request').fill('Total rides for station UNKNOWN');
  await page.getByRole('button', { name: 'Run agent analysis' }).click();
  await expect(trace.locator('details').first()).not.toHaveAttribute('open');
  await trace.getByText('Show more', { exact: true }).click();
  await expect(trace.getByText('Station lookup for query 2.')).toBeVisible();
  await trace.getByText('Show less', { exact: true }).click();
  await expect(trace.getByText('Station lookup for query 2.')).not.toBeVisible();
  await expect(trace.getByText('Station lookup for query 1.')).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('region', { name: 'Trace' })).toHaveCount(0);
});
