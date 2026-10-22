import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import AgentPanel from '../components/agent-panel';

afterEach(() => vi.unstubAllGlobals());

const stages = ['Data Ingest', 'Agent Planning', 'Tool Execution', 'Final Report Generation'].map(name => ({ name, status: 'complete' }));
const variance = { tool_name: 'analyze_station_variance', status: 'success', arguments: { station_id: 'HB106', current_period: '2026-02' }, values: [
  { entity_id: 'HB106', metric_type: 'contribution', dimension: 'member_casual', category: 'Casual', unit: 'percent', exact_tool_value: 30.36, eligible: true },
  { entity_id: 'HB106', metric_type: 'contribution', dimension: 'rideable_type', category: 'E-bike', unit: 'percent', exact_tool_value: 71.7, eligible: true },
] };
const complete = { run_id: 'run-1', status: 'complete', report_html: '<h1>Verified report</h1>', warning: null, candidate_id: 'HB106', stages, trace: [variance] };
function stream(events: object[]) {
  const encoder = new TextEncoder();
  return { ok: true, body: new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) controller.enqueue(encoder.encode(`${JSON.stringify(event)}\n`));
      controller.close();
    },
  }) };
}

test('streams stages, verified follow-up, and report', async () => {
  const fetchMock = vi.fn().mockResolvedValue(stream([
    { type: 'stage', name: 'Data Ingest', status: 'complete' },
    { type: 'candidate', candidate_id: 'HB106' },
    { type: 'tool', data: variance },
    { type: 'result', data: complete },
  ]));
  vi.stubGlobal('fetch', fetchMock);
  render(<AgentPanel period="2026-02" command="Investigate declining stations" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  await screen.findByText('Agent report ready for 2026-02.');
  expect(fetchMock.mock.calls[0][0]).toBe('/api/agent-runs/stream');
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ period: { year: 2026, month: 2 }, command: 'Investigate declining stations' });
  expect(screen.getByText(/analyze_station_variance/)).toBeInTheDocument();
  expect(screen.getByText('Mandatory investigation candidate: HB106')).toBeInTheDocument();
  expect(screen.getByText('member casual · Casual: 30.36%')).toBeInTheDocument();
  expect(screen.getByText('rideable type · E-bike: 71.7%')).toBeInTheDocument();
  expect(screen.getByTitle('Agent report for 2026-02')).toHaveAttribute('sandbox', '');
});

test('shows refusal without displaying a report', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{ type: 'result', data: {
    run_id: 'run-2', status: 'refused', report_html: '', warning: 'This request is outside the standard report scope. Try a standard monthly report.', stages: [], trace: [],
  } }])));
  render(<AgentPanel period="2026-02" command="Analyze" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Try a standard monthly report.');
  expect(screen.getByText('Request refused.')).toBeInTheDocument();
  expect(screen.queryByTitle('Agent report for 2026-02')).not.toBeInTheDocument();
});

test('requires month and command and reports API errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
  const { rerender } = render(<AgentPanel period="" command="" busy={false} />);
  expect(screen.getByRole('button', { name: 'Run agent analysis' })).toBeDisabled();
  rerender(<AgentPanel period="2026-02" command="Analyze" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Agent analysis failed. Retry.'));
});

test('hides a completed report after the selected request changes', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{ type: 'result', data: complete }])));
  const { rerender } = render(<AgentPanel period="2026-02" command="Standard report" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  expect(await screen.findByTitle('Agent report for 2026-02')).toBeInTheDocument();
  rerender(<AgentPanel period="2026-01" command="Standard report" busy={false} />);
  expect(screen.queryByTitle('Agent report for 2026-02')).not.toBeInTheDocument();
  rerender(<AgentPanel period="2026-02" command="Different request" busy={false} />);
  expect(screen.queryByTitle('Agent report for 2026-02')).not.toBeInTheDocument();
});

test('resubmits an ambiguous station with the explicit original request', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(stream([{type:'result',data:{...complete,status:'refused',report_html:'',station_choices:[{station_id:'A',station_name:'Park'}]}}])).mockResolvedValueOnce(stream([{type:'result',data:complete}]));
  vi.stubGlobal('fetch', fetcher);
  render(<AgentPanel period="2026-02" command="Park starts" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  fireEvent.click(await screen.findByRole('button',{name:'Analyze Park (A)'}));
  await screen.findByTitle('Agent report for 2026-02');
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({period:{year:2026,month:2},command:'Park starts',station_id:'A'});
});
