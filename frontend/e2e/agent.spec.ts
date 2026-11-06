import { expect, test } from '@playwright/test';

test('runs an agent request and presents the report without completed tool activity', async ({ page }) => {
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
  await expect(page.getByRole('region', { name: 'Agent tool activity' })).toHaveCount(0);
  await expect(page.getByText('Exact tool identity and inputs')).toHaveCount(0);
  await expect(page.getByText('Mandatory investigation candidate: HB106')).toBeVisible();
  await expect(page.getByRole('list', { name: 'Variance breakdowns' })).toHaveCount(0);
  await expect(page.frameLocator('iframe[title="Agent report for 2026-02"]').getByRole('heading', { name: 'Verified report' })).toBeVisible();
});

for (const answer of ['choice', 'station ID'] as const) {
  test(`answers station clarification with a ${answer} while preserving the request`, async ({ page }) => {
    const command = 'Show starts at Central for July 2026';
    const period = { year: 2026, month: 7 };
    let requests = 0;
    await page.route('**/api/health', route => route.fulfill({ json: { success: true, data: { status: 'ok' } } }));
    await page.route('**/api/agent-runs/stream', async route => {
      const payload = route.request().postDataJSON();
      requests += 1;
      const result = requests === 1 ? {
        run_id: 'clarify-station', status: 'refused', report_html: '', error_code: 'ERR_STATION_SELECTION',
        warning: 'Select an explicit station and submit the reporting month again.', stages: [], trace: [],
        station_choices: answer === 'choice' ? [
          { station_id: 'CENTRAL-EAST', station_name: 'Central East' },
          { station_id: 'CENTRAL-WEST', station_name: 'Central West' },
        ] : [],
      } : {
        run_id: 'selected-station', status: 'complete', report_html: '<h1>Central West station starts</h1>',
        warning: null, stages: ['Data Ingest', 'Agent Planning', 'Tool Execution', 'Final Report Generation']
          .map(name => ({ name, status: 'complete' })), trace: [],
      };
      expect(payload).toEqual({ period, command, ...(requests === 1 ? {} : { station_id: 'CENTRAL-WEST' }) });
      await route.fulfill({ contentType: 'application/x-ndjson', body: `${JSON.stringify({ type: 'result', data: result })}\n` });
    });
    await page.goto('/');
    await page.getByLabel('Reporting month').fill('2026-07');
    await page.getByLabel('Analysis request').fill(command);
    await page.getByRole('button', { name: 'Run agent analysis' }).click();
    const clarification = page.getByRole('region', { name: 'Choose a station' });
    await expect(clarification).toBeVisible();
    if (answer === 'choice') {
      await clarification.getByRole('combobox', { name: 'Matching station' }).selectOption('CENTRAL-WEST');
      await clarification.getByRole('button', { name: 'Analyze selected station' }).click();
    } else {
      await expect(clarification.getByRole('button', { name: 'Use station ID' })).toBeDisabled();
      await clarification.getByLabel('Station ID').fill('CENTRAL-WEST');
      await clarification.getByRole('button', { name: 'Use station ID' }).click();
    }
    await expect(page.getByText('Agent report ready for 2026-07.')).toBeVisible();
    await expect(clarification).toHaveCount(0);
    await expect(page.getByLabel('Reporting month')).toHaveValue('2026-07');
    await expect(page.getByLabel('Analysis request')).toHaveValue(command);
    await expect(page.frameLocator('iframe[title="Agent report for 2026-07"]').getByRole('heading', { name: 'Central West station starts' })).toBeVisible();
    expect(requests).toBe(2);
  });
}
