import { expect, test } from '@playwright/test';

for (const outcome of ['partial', 'stream error'] as const) {
  test(`keeps terminal progress for an August standard report: ${outcome}`, async ({ page }) => {
    await page.route('**/api/health', route => route.fulfill({ json: { success: true, data: { status: 'ok' } } }));
    await page.route('**/api/agent-runs/stream', async route => {
      expect(route.request().postDataJSON()).toEqual({ period: { year: 2026, month: 8 }, command: 'Generate a standard report for August 2026' });
      const events = [
        { type: 'stage', name: 'Data Ingest', status: 'complete' },
        outcome === 'partial' ? { type: 'result', data: {
          run_id: 'failed-plan', status: 'partial', report_html: '', trace: [],
          warning: 'No report was added.', validation_reason: 'invalid_plan',
          stages: [{name:'Data Ingest',status:'complete'},{name:'Agent Planning',status:'failed'},{name:'Tool Execution',status:'skipped'},{name:'Final Report Generation',status:'skipped'}],
        } } : { type: 'error', message: 'Service interrupted.' },
      ];
      await route.fulfill({ contentType: 'application/x-ndjson', body: events.map(event => JSON.stringify(event)).join('\n') + '\n' });
    });
    await page.goto('/');
    await page.getByLabel('Reporting month').fill('2026-08');
    await page.getByLabel('Analysis request').fill('Generate a standard report for August 2026');
    await page.getByRole('button', { name: 'Run agent analysis' }).click();
    const agent = page.getByRole('region', { name: 'Agent analysis' });
    await expect(agent.getByRole('alert')).toContainText(outcome === 'partial' ? 'The model did not choose the allowed tools.' : 'Service interrupted.');
    const stages = agent.getByRole('list', { name: 'Agent stages' });
    await expect(stages).toContainText('Data Ingest: complete');
    await expect(stages).toContainText('Agent Planning: failed');
    await expect(stages).toContainText('Tool Execution: skipped');
    await expect(stages).toContainText('Final Report Generation: skipped');
    await expect(stages).not.toContainText('idle');
    await expect(agent.getByText('Agent service returned an invalid report. Retry.')).toHaveCount(0);
  });
}
