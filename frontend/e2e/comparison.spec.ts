import { expect, test, type Page } from '@playwright/test';

const datasets = [1, 2].map(month => ({
  period: { year: 2026, month }, version_id: `month-${month}`, sha256: String(month).repeat(64),
}));
const baseline = {
  monthly_totals: { '2026-01': 100, '2026-02': 80 },
  top_stations: [{ station_id: '001', station_name: 'Shared station', ride_count: 75 }],
  inputs: datasets.map(dataset => ({ dataset })),
};
const evidence = {
  run_id: 'comparison-browser', tool_call_id: 'compare-1', stage: 'execution',
  tool_name: 'compare_periods', status: 'success', datasets,
  arguments: { current_period: { year: 2026, month: 2 }, comparison_period: { year: 2026, month: 1 } },
  values: [{ entity_id: 'system', metric_type: 'trip_count', period: { year: 2026, month: 1 },
    comparison_period: { year: 2026, month: 2 }, dimension: null, category: null, unit: 'trips',
    exact_tool_value: 100, eligible: true, eligibility_reason: null }], validation_reason: null,
};

const result = {
  report_id: 'comparison-browser', period: { year: 2026, month: 2 }, datasets, baseline,
  agent: {
    run_id: 'comparison-browser', status: 'partial', period: { year: 2026, month: 2 }, datasets,
    report_html: '<h1>Standard baseline fallback</h1>',
    warning: 'Reasoning budget exhausted. Displaying standard baseline metrics only.',
    error_code: 'ERR_BUDGET_EXCEEDED', stages: [], trace: [evidence],
    counters: { llm_calls: 6, tool_calls: 2, input_tokens: 120, output_tokens: 30 },
    candidate_id: null,
  },
  rows: [
    { month: '2026-01', python_total: 100, agent_total: 100, difference: 0, status: 'match' },
    { month: '2026-02', python_total: 80, agent_total: null, difference: null, status: 'unavailable' },
  ],
  timing_seconds: { shared_preparation: 0.1, python_calculation: 0.02, agent_workflow: 0.4 },
  dollar_cost: null,
};

async function prepare(page: Page, months = [1, 2]) {
  await page.route('**/api/health', route => route.fulfill({ json: { success: true, data: { status: 'ok' } } }));
  await page.route('**/api/periods', route => route.fulfill({ json: { success: true, data: {
    periods: months.map(month => ({ period: { year: 2026, month }, version_id: `month-${month}` })),
  } } }));
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    const state = window as typeof window & {
      comparisonRequests: unknown[];
      comparisonEmit: (event: unknown, close?: boolean) => void;
    };
    state.comparisonRequests = [];
    window.fetch = async (input, init) => {
      if (String(input) !== '/api/comparisons/stream') return original(input, init);
      state.comparisonRequests.push(JSON.parse(String(init?.body)));
      const stream = new ReadableStream({ start(controller) {
        state.comparisonEmit = (event, close = false) => {
          controller.enqueue(new TextEncoder().encode(JSON.stringify(event) + '\n'));
          if (close) controller.close();
        };
      } });
      return new Response(stream, { headers: { 'Content-Type': 'application/x-ndjson' } });
    };
  });
  await page.goto('/');
  await page.getByLabel('Reporting month').fill('2026-02');
}

async function emit(page: Page, event: unknown, close = false) {
  await page.evaluate(({ event, close }) => {
    (window as typeof window & { comparisonEmit: (event: unknown, close: boolean) => void }).comparisonEmit(event, close);
  }, { event, close });
}

test('comparison requires both accepted demo months before submission', async ({ page }) => {
  await prepare(page, [2]);
  const panel = page.getByRole('region', { name: 'Baseline vs Agent', exact: true });
  await expect(panel.getByRole('button', { name: 'Run demo comparison' })).toBeDisabled();
  expect(await page.evaluate(() => (window as typeof window & { comparisonRequests: unknown[] }).comparisonRequests)).toEqual([]);
});

test('comparison streams Python first, blocks duplicates, and distinguishes partial evidence', async ({ page }) => {
  await prepare(page);
  const panel = page.getByRole('region', { name: 'Baseline vs Agent', exact: true });
  await panel.getByRole('button', { name: 'Run demo comparison' }).click();
  await expect(panel.getByRole('button', { name: 'Running demo comparison…' })).toBeDisabled();
  await expect.poll(() => page.evaluate(() => (window as typeof window & { comparisonRequests: unknown[] }).comparisonRequests.length)).toBe(1);
  await emit(page, { type: 'baseline', data: baseline });
  await expect(panel.getByText('Python baseline ready. Agent workflow in progress.')).toBeVisible();
  await expect(panel.getByText('Shared station')).toBeVisible();
  await expect(panel.locator('iframe')).toHaveCount(0);
  await emit(page, { type: 'stage', name: 'Agent Planning', status: 'complete' });
  await expect(panel).toContainText('Agent Planning');
  await emit(page, { type: 'tool', data: evidence });
  await expect(panel.getByText('Verified evidence and tool activity')).toBeVisible();
  await emit(page, { type: 'result', data: result }, true);
  await expect(panel.getByText('Agent analysis partial. Verified totals do not establish agent completion.')).toBeVisible();
  const january = panel.getByRole('row').filter({ hasText: '2026-01' });
  await expect(january).toContainText('Match');
  const february = panel.getByRole('row').filter({ hasText: '2026-02' });
  await expect(february).toContainText('Unavailable');
  await expect(panel.locator('iframe')).toHaveAttribute('sandbox', '');
  await expect(page.frameLocator('iframe[title="Comparison agent report for 2026-02"]').getByRole('heading', { name: 'Standard baseline fallback' })).toBeVisible();
  await expect(panel).toContainText('120');
  await expect(panel).toContainText('30');
  const pythonBox = await panel.getByRole('region', { name: 'Independent Python baseline', exact: true }).boundingBox();
  const agentBox = await panel.getByRole('region', { name: 'Additional agent analysis', exact: true }).boundingBox();
  expect(pythonBox).not.toBeNull();
  expect(agentBox).not.toBeNull();
  expect(agentBox!.x).toBeGreaterThan(pythonBox!.x + pythonBox!.width);
  expect(Math.abs(agentBox!.y - pythonBox!.y)).toBeLessThan(2);
});

test('interrupted comparison retains Python results and reports incomplete agent work', async ({ page }) => {
  await prepare(page);
  const panel = page.getByRole('region', { name: 'Baseline vs Agent', exact: true });
  await panel.getByRole('button', { name: 'Run demo comparison' }).click();
  await emit(page, { type: 'baseline', data: baseline }, true);
  await expect(panel.getByRole('alert')).toContainText(/interrupt|incomplete|before|without/i);
  await expect(panel.getByText('Shared station')).toBeVisible();
  await expect(panel.locator('iframe')).toHaveCount(0);
});

test('comparison hides stale streamed results after reporting month changes', async ({ page }) => {
  await prepare(page);
  const panel = page.getByRole('region', { name: 'Baseline vs Agent', exact: true });
  await panel.getByRole('button', { name: 'Run demo comparison' }).click();
  await emit(page, { type: 'baseline', data: baseline });
  await expect(panel.getByText('Shared station')).toBeVisible();
  await page.getByLabel('Reporting month').fill('2026-03');
  await emit(page, { type: 'result', data: result }, true);
  await expect(panel.getByText('Shared station')).toHaveCount(0);
  await expect(panel.locator('iframe')).toHaveCount(0);
  await expect(panel.getByRole('button', { name: 'Run demo comparison' })).toBeDisabled();
});

test('comparison supports keyboard submission and stacked mobile results without page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await prepare(page);
  const panel = page.getByRole('region', { name: 'Baseline vs Agent', exact: true });
  const button = panel.getByRole('button', { name: 'Run demo comparison' });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press('Enter');
  await emit(page, { type: 'baseline', data: baseline });
  await emit(page, { type: 'result', data: result }, true);
  await expect(panel.getByText('Baseline-only analysis', { exact: true })).toBeVisible();
  await expect(panel.getByText('Additional agent analysis', { exact: true })).toBeVisible();
  const pythonBox = await panel.getByRole('region', { name: 'Independent Python baseline', exact: true }).boundingBox();
  const agentBox = await panel.getByRole('region', { name: 'Additional agent analysis', exact: true }).boundingBox();
  expect(agentBox!.y).toBeGreaterThan(pythonBox!.y + pythonBox!.height);
  const table = panel.getByRole('region', { name: 'Monthly totals comparison' });
  await table.focus();
  await expect(table).toBeFocused();
  await table.press('ArrowRight');
  const overflows = await table.evaluate(element => element.scrollWidth > element.clientWidth);
  if (overflows) await expect.poll(() => table.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/comparison-mobile.png', fullPage: true });
});
