import { expect, test } from '@playwright/test';

test('runs an agent request and exposes the adaptive aggregate follow-up', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { success: true, data: { status: 'ok' } } }));
  await page.route('**/api/agent-runs/stream', async route => {
    const payload = route.request().postDataJSON();
    expect(payload).toEqual({ period: { year: 2026, month: 2 }, command: 'Investigate declining stations' });
    const variance = { tool_name: 'analyze_station_variance', status: 'success', arguments: { station_id: 'HB106' }, values: [
      { metric_type: 'contribution', dimension: 'member_casual', category: 'Casual', exact_tool_value: 30.36, eligible: true },
      { metric_type: 'contribution', dimension: 'rideable_type', category: 'E-bike', exact_tool_value: 71.7, eligible: true },
    ] };
    const result = { run_id: 'test-run', status: 'complete', report_html: '<h1>Verified report</h1>', warning: null,
      candidate_id: 'HB106', stages: ['Data Ingest', 'Agent Planning', 'Tool Execution', 'Final Report Generation'].map(name => ({ name, status: 'complete' })), trace: [variance] };
    const body = [
      { type: 'stage', name: 'Data Ingest', status: 'complete' },
      { type: 'candidate', candidate_id: 'HB106' },
      { type: 'tool', data: variance },
      { type: 'result', data: result },
    ].map(event => JSON.stringify(event)).join('\n') + '\n';
    await route.fulfill({ contentType: 'application/x-ndjson', body });
  });
  await page.goto('/');
  await page.getByLabel('Reporting month').fill('2026-02');
  await page.getByLabel('Analysis request').fill('Investigate declining stations');
  await page.getByRole('button', { name: 'Run agent analysis' }).click();
  await expect(page.getByText('Agent report ready for 2026-02.')).toBeVisible();
  await expect(page.getByText(/analyze_station_variance/)).toBeVisible();
  await expect(page.getByText('Mandatory investigation candidate: HB106')).toBeVisible();
  await expect(page.getByText('member casual · Casual: 30.36%')).toBeVisible();
  await expect(page.frameLocator('iframe[title="Agent report for 2026-02"]').getByRole('heading', { name: 'Verified report' })).toBeVisible();
});
