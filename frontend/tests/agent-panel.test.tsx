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
    run_id: 'run-2', status: 'refused', report_html: '', warning: 'This request is outside the standard report scope. Try a standard monthly report.',
    stages: [{name:'Data Ingest',status:'complete'},{name:'Agent Planning',status:'failed'},{name:'Tool Execution',status:'skipped'},{name:'Final Report Generation',status:'skipped'}], trace: [],
  } }])));
  render(<AgentPanel period="2026-02" command="Analyze" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Try a standard monthly report.');
  expect(screen.getByText(/Agent Planning: failed. This request is outside the standard report scope/)).toBeInTheDocument();
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
  const fetcher = vi.fn().mockResolvedValueOnce(stream([{type:'result',data:{...complete,status:'refused',error_code:'ERR_STATION_SELECTION',report_html:'',station_choices:[{station_id:'A',station_name:'Park'}]}}])).mockResolvedValueOnce(stream([{type:'result',data:complete}]));
  vi.stubGlobal('fetch', fetcher);
  render(<AgentPanel period="2026-02" command="Park starts" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  const select = await screen.findByRole('combobox', {name:'Matching station'});
  const submit = screen.getByRole('button', {name:'Analyze selected station'});
  expect(submit).toBeDisabled();
  expect(screen.queryByRole('list', {name:'Agent matching stations'})).not.toBeInTheDocument();
  fireEvent.change(select, {target:{value:'A'}});
  expect(fetcher).toHaveBeenCalledTimes(1);
  fireEvent.click(submit);
  await screen.findByTitle('Agent report for 2026-02');
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({period:{year:2026,month:2},command:'Park starts',station_id:'A'});
});
test('renders the station leaderboard above the chained variance breakdown', async () => {
  const ranking = (rank: number, station_name: string, tied = false) => ({ ranked_by: 'ebike_share_pct', order: 'top', rank, tied, station_name, filter_by: null });
  const rank = { tool_name: 'rank_stations', status: 'success', arguments: { current_period: { year: 2026, month: 2 }, metric: 'ebike_share_pct', order: 'top', top_n: 2 }, values: [
    { entity_id: 'HB106', metric_type: 'share', dimension: 'rideable_type', category: 'E-bike', unit: 'percent', exact_tool_value: 71.256, eligible: true, ranking: ranking(1, 'Grove St PATH', true) },
    { entity_id: 'HB106', metric_type: 'current_volume', unit: 'trips', exact_tool_value: 1204, eligible: true, ranking: ranking(1, 'Grove St PATH', true) },
    { entity_id: 'JC009', metric_type: 'share', dimension: 'rideable_type', category: 'E-bike', unit: 'percent', exact_tool_value: 71.256, eligible: true, ranking: ranking(2, 'Hamilton Park', true) },
    { entity_id: 'JC009', metric_type: 'current_volume', unit: 'trips', exact_tool_value: 300, eligible: true, ranking: ranking(2, 'Hamilton Park', true) },
  ] };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{ type: 'result', data: { ...complete, candidate_id: null, trace: [rank, variance] } }])));
  render(<AgentPanel period="2026-02" command="Top 2 stations by e-bike share and compare the leader" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  const table = await screen.findByRole('table', { name: 'Station leaderboard' });
  const rows = table.querySelectorAll('tbody tr');
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent('1HB106Grove St PATH71.26%1,204Tied100+ starts');
  expect(rows[1]).toHaveTextContent('2JC009Hamilton Park71.26%300');
  expect(screen.getByText('E-bike share')).toBeInTheDocument();
  expect(screen.getByText('ebike_share_pct')).toBeInTheDocument();
  const breakdown = screen.getByRole('list', { name: 'Variance breakdowns' });
  expect(table.compareDocumentPosition(breakdown) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByText(/Station change breakdown/).parentElement).toHaveTextContent('adaptive follow-up');
});

test('counts-based leaderboard reads starts from the ranked value', async () => {
  const rank = { tool_name: 'rank_stations', status: 'success', values: [
    { entity_id: 'JC001', metric_type: 'current_volume', unit: 'trips', exact_tool_value: 3, eligible: true, ranking: { ranked_by: 'total_starts', order: 'bottom', rank: 1, tied: false, station_name: 'Quiet Corner' } },
  ] };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{ type: 'result', data: { ...complete, candidate_id: null, trace: [rank] } }])));
  render(<AgentPanel period="2026-02" command="Least-used station" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  const table = await screen.findByRole('table', { name: 'Station leaderboard' });
  expect(table.querySelector('tbody tr')).toHaveTextContent('1JC001Quiet Corner33');
  expect(table).not.toHaveTextContent('Tied');
  expect(table).not.toHaveTextContent('100+ starts');
});

test('describes verified tools in plain language with disclosure for exact inputs', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{type:'result',data:complete}])));
  render(<AgentPanel period="2026-02" command="Investigate" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  expect(await screen.findByText('Station change breakdown')).toBeInTheDocument();
  expect(screen.getByText('Verified aggregate results. Tool activity shows calculations and their inputs, not private model reasoning.')).toBeInTheDocument();
  expect(screen.getByText('Exact tool identity and inputs')).toBeInTheDocument();
});


test('asks for an explicit station ID and resubmits it with the original request', async () => {
  const clarification = { ...complete, status: 'refused', error_code: 'ERR_STATION_SELECTION', report_html: '', candidate_id: null, station_choices: [], warning: 'Select an explicit station.' };
  const fetcher = vi.fn().mockResolvedValueOnce(stream([{ type: 'result', data: clarification }])).mockResolvedValueOnce(stream([{ type: 'result', data: complete }]));
  vi.stubGlobal('fetch', fetcher);
  render(<AgentPanel period="2026-07" command="Show station starts for July 2026" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  expect(await screen.findByRole('region', { name: 'Choose a station' })).toBeInTheDocument();
  expect(screen.getByText('Choose a station to continue.')).toBeInTheDocument();
  expect(screen.queryByText('Request refused.')).not.toBeInTheDocument();
  const submit = screen.getByRole('button', { name: 'Use station ID' });
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByRole('textbox', { name: 'Station ID' }), { target: { value: '  HB107  ' } });
  fireEvent.click(submit);
  await screen.findByTitle('Agent report for 2026-07');
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ period: { year: 2026, month: 7 }, command: 'Show station starts for July 2026', station_id: 'HB107' });
});

test('hides clarification on context change and clears a previous station entry', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{ type: 'result', data: { ...complete, status: 'refused', error_code: 'ERR_STATION_SELECTION', report_html: '', station_choices: [] } }])));
  const { rerender } = render(<AgentPanel period="2026-07" command="Show station starts" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  fireEvent.change(await screen.findByRole('textbox', { name: 'Station ID' }), { target: { value: 'HB107' } });
  rerender(<AgentPanel period="2026-06" command="Show station starts" busy={false} />);
  expect(screen.queryByRole('region', { name: 'Choose a station' })).not.toBeInTheDocument();
  rerender(<AgentPanel period="2026-07" command="Show station starts" busy={true} />);
  expect(screen.getByRole('textbox', { name: 'Station ID' })).toHaveValue('');
  fireEvent.change(screen.getByRole('textbox', { name: 'Station ID' }), { target: { value: 'HB107' } });
  expect(screen.getByRole('button', { name: 'Use station ID' })).toBeDisabled();
});

test('disables the station dropdown while busy and resets it when the request changes', async () => {
  const choices = [{station_id:'A',station_name:'Park'}, {station_id:'B',station_name:'Park'}];
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{type:'result',data:{...complete,status:'refused',report_html:'',station_choices:choices}}])));
  const {rerender} = render(<AgentPanel period="2026-07" command="Show station starts" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  const select = await screen.findByRole('combobox',{name:'Matching station'});
  expect(screen.getByRole('option',{name:'Park (A)'})).toBeInTheDocument();
  expect(screen.getByRole('option',{name:'Park (B)'})).toBeInTheDocument();
  fireEvent.change(select,{target:{value:'B'}});
  rerender(<AgentPanel period="2026-07" command="Show station starts" busy={true}/>);
  expect(select).toBeDisabled();
  expect(screen.getByRole('button',{name:'Analyze selected station'})).toBeDisabled();
  rerender(<AgentPanel period="2026-06" command="Show station starts" busy={false}/>);
  expect(screen.queryByRole('combobox',{name:'Matching station'})).not.toBeInTheDocument();
  rerender(<AgentPanel period="2026-07" command="Show station starts" busy={false}/>);
  expect(screen.getByRole('combobox',{name:'Matching station'})).toHaveValue('');
});

test('shows an intentionally empty partial response with the backend failure stages', async () => {
  const failedStages = [{name:'Data Ingest',status:'complete'},{name:'Agent Planning',status:'failed'},{name:'Tool Execution',status:'skipped'},{name:'Final Report Generation',status:'skipped'}];
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{type:'result',data:{...complete,status:'partial',report_html:'',warning:'No report was added.',validation_reason:'invalid_plan',stages:failedStages}}])));
  render(<AgentPanel period="2026-08" command="Generate a standard report for August 2026" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  expect(await screen.findByText('Agent analysis stopped before a report was added.')).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('The model did not choose the allowed tools.');
  expect(screen.getByText('Data Ingest: complete')).toBeInTheDocument();
  expect(screen.getByText(/Agent Planning: failed/)).toBeInTheDocument();
  expect(screen.getByText('Tool Execution: skipped')).toBeInTheDocument();
  expect(screen.getByText('Final Report Generation: skipped')).toBeInTheDocument();
  expect(screen.queryByText(/invalid report/)).not.toBeInTheDocument();
});

test('retains confirmed progress and ends unconfirmed stages after a stream error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{type:'stage',name:'Data Ingest',status:'complete'},{type:'error',message:'Service interrupted.'}])));
  render(<AgentPanel period="2026-08" command="Standard report" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Service interrupted.');
  expect(screen.getByText('Data Ingest: complete')).toBeInTheDocument();
  expect(screen.getByText('Agent Planning: failed')).toBeInTheDocument();
  expect(screen.getByText('Tool Execution: skipped')).toBeInTheDocument();
  expect(screen.getByText('Final Report Generation: skipped')).toBeInTheDocument();
});

test('rejects a complete response without HTML while keeping completed stages', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([...stages.map(stage=>({type:'stage',...stage})),{type:'result',data:{...complete,report_html:''}}])));
  render(<AgentPanel period="2026-08" command="Standard report" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('invalid report');
  expect(screen.getByText('Data Ingest: complete')).toBeInTheDocument();
  expect(screen.getByText('Agent Planning: complete')).toBeInTheDocument();
  expect(screen.getByText('Tool Execution: complete')).toBeInTheDocument();
  expect(screen.getByText('Final Report Generation: complete')).toBeInTheDocument();
});
