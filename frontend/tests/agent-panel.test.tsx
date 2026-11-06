import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

test('updates running stage indicators to complete dots and preserves terminal failure states', async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true, body:new ReadableStream<Uint8Array>({start(value) { controller = value; }})}));
  render(<AgentPanel period="2026-02" command="Monthly report" busy={false} />);
  const list = screen.getByRole('list', {name:'Agent stages'});
  expect(within(list).getAllByText('Not started')).toHaveLength(4);
  fireEvent.click(screen.getByRole('button', {name:'Run agent analysis'}));
  await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledOnce());
  expect(screen.getByText('Data Ingest').closest('li')).toHaveTextContent('Running');
  expect(screen.getByText('Agent Planning').closest('li')).toHaveTextContent('Pending');
  await act(async () => controller.enqueue(new TextEncoder().encode(JSON.stringify({type:'stage',name:'Data Ingest',status:'running'})+'\n')));
  const running = within(list).getByText('Running');
  expect(running).toHaveAttribute('data-state','running');
  expect(running.querySelector('.stage-indicator')).toHaveAttribute('aria-hidden','true');
  await act(async () => controller.enqueue(new TextEncoder().encode(JSON.stringify({type:'stage',name:'Data Ingest',status:'complete'})+'\n')));
  expect(within(list).getByText('Complete')).toHaveAttribute('data-state','complete');
  expect(screen.getByText('Agent Planning').closest('li')).toHaveTextContent('Running');
  expect(screen.getByText('Tool Execution').closest('li')).toHaveTextContent('Pending');
  await act(async () => {
    controller.enqueue(new TextEncoder().encode(JSON.stringify({type:'result',data:{...complete,status:'partial',report_html:'',stages:[{name:'Data Ingest',status:'complete'},{name:'Agent Planning',status:'failed'},{name:'Tool Execution',status:'skipped'},{name:'Final Report Generation',status:'skipped'}]}})+'\n'));
    controller.close();
  });
  expect(within(list).getByText('Failed')).toHaveAttribute('data-state','failed');
  expect(within(list).getAllByText('Skipped')).toHaveLength(2);
  for (const skipped of within(list).getAllByText('Skipped')) expect(skipped).toHaveAttribute('data-state','skipped');
});

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
  expect(screen.queryByRole('region', { name: 'Agent tool activity' })).not.toBeInTheDocument();
  expect(screen.getByText('Mandatory investigation candidate: HB106')).toBeInTheDocument();
  expect(screen.queryByRole('list', { name: 'Variance breakdowns' })).not.toBeInTheDocument();
  expect(screen.getByTitle('Agent report for 2026-02')).toHaveAttribute('sandbox', '');
});

test('stops an explicitly running stage after a stream error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([
    {type:'stage',name:'Data Ingest',status:'complete'},
    {type:'stage',name:'Agent Planning',status:'running'},
    {type:'error',message:'Connection interrupted.'},
  ])));
  render(<AgentPanel period="2026-02" command="Monthly report" busy={false} />);
  fireEvent.click(screen.getByRole('button', {name:'Run agent analysis'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection interrupted.');
  const list = screen.getByRole('list', {name:'Agent stages'});
  expect(within(list).queryByText('Running')).not.toBeInTheDocument();
  expect(screen.getByText('Data Ingest').closest('li')).toHaveTextContent('Complete');
  expect(screen.getByText('Agent Planning').closest('li')).toHaveTextContent('Failed');
  expect(screen.getByText('Tool Execution').closest('li')).toHaveTextContent('Skipped');
  expect(screen.getByText('Final Report Generation').closest('li')).toHaveTextContent('Skipped');
});

test('does not infer another running stage after receiving a failure', async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true, body:new ReadableStream<Uint8Array>({start(value) { controller = value; }})}));
  render(<AgentPanel period="2026-02" command="Monthly report" busy={false} />);
  fireEvent.click(screen.getByRole('button', {name:'Run agent analysis'}));
  await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledOnce());
  await act(async () => {
    controller.enqueue(new TextEncoder().encode([
      {type:'stage',name:'Data Ingest',status:'complete'},
      {type:'stage',name:'Agent Planning',status:'failed'},
    ].map(event => JSON.stringify(event)).join('\n')+'\n'));
  });
  expect(screen.getByText('Agent Planning').closest('li')).toHaveTextContent('Failed');
  expect(screen.getByText('Tool Execution').closest('li')).toHaveTextContent('Pending');
  expect(within(screen.getByRole('list', {name:'Agent stages'})).queryByText('Running')).not.toBeInTheDocument();
  await act(async () => controller.close());
});

test('shows refusal without displaying a report', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{ type: 'result', data: {
    run_id: 'run-2', status: 'refused', report_html: '', warning: 'This request is outside the standard report scope. Try a standard monthly report.',
    stages: [{name:'Data Ingest',status:'complete'},{name:'Agent Planning',status:'failed'},{name:'Tool Execution',status:'skipped'},{name:'Final Report Generation',status:'skipped'}], trace: [],
  } }])));
  render(<AgentPanel period="2026-02" command="Analyze" busy={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Try a standard monthly report.');
  expect(screen.getByText('Agent Planning').closest('li')).toHaveTextContent('Failed');
  expect(screen.getByText('Agent Planning').closest('li')).toHaveTextContent('This request is outside the standard report scope');
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
test('does not duplicate ranked or variance tool results outside the completed report', async () => {
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
  expect(await screen.findByTitle('Agent report for 2026-02')).toHaveAttribute('srcdoc', complete.report_html);
  expect(screen.queryByRole('table', { name: 'Station leaderboard' })).not.toBeInTheDocument();
  expect(screen.queryByRole('list', { name: 'Variance breakdowns' })).not.toBeInTheDocument();
  expect(screen.queryByText('Station change breakdown')).not.toBeInTheDocument();
});

test('keeps the completed report without tool activity or exact input disclosures', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{type:'result',data:complete}])));
  render(<AgentPanel period="2026-02" command="Investigate" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  expect(await screen.findByTitle('Agent report for 2026-02')).toHaveAttribute('srcdoc', complete.report_html);
  expect(screen.queryByRole('region', { name: 'Agent tool activity' })).not.toBeInTheDocument();
  expect(screen.queryByText('Station change breakdown')).not.toBeInTheDocument();
  expect(screen.queryByText('Exact tool identity and inputs')).not.toBeInTheDocument();
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
  expect(screen.getByText('Data Ingest').closest('li')).toHaveTextContent('Complete');
  expect(screen.getByText('Agent Planning').closest('li')).toHaveTextContent('Failed');
  expect(screen.getByText('Tool Execution').closest('li')).toHaveTextContent('Skipped');
  expect(screen.getByText('Final Report Generation').closest('li')).toHaveTextContent('Skipped');
  expect(screen.queryByText(/invalid report/)).not.toBeInTheDocument();
});

test('retains confirmed progress and ends unconfirmed stages after a stream error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([{type:'stage',name:'Data Ingest',status:'complete'},{type:'error',message:'Service interrupted.'}])));
  render(<AgentPanel period="2026-08" command="Standard report" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Service interrupted.');
  expect(screen.getByText('Data Ingest').closest('li')).toHaveTextContent('Complete');
  expect(screen.getByText('Agent Planning').closest('li')).toHaveTextContent('Failed');
  expect(screen.getByText('Tool Execution').closest('li')).toHaveTextContent('Skipped');
  expect(screen.getByText('Final Report Generation').closest('li')).toHaveTextContent('Skipped');
});

test('rejects a complete response without HTML while keeping completed stages', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([...stages.map(stage=>({type:'stage',...stage})),{type:'result',data:{...complete,report_html:''}}])));
  render(<AgentPanel period="2026-08" command="Standard report" busy={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Run agent analysis'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('invalid report');
  expect(screen.getByText('Data Ingest').closest('li')).toHaveTextContent('Complete');
  expect(screen.getByText('Agent Planning').closest('li')).toHaveTextContent('Complete');
  expect(screen.getByText('Tool Execution').closest('li')).toHaveTextContent('Complete');
  expect(screen.getByText('Final Report Generation').closest('li')).toHaveTextContent('Complete');
});
