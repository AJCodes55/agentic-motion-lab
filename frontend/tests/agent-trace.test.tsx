import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import AgentPanel from '../components/agent-panel';
import { isTraceEvent } from '../components/trace-panel';

afterEach(() => vi.unstubAllGlobals());
const result = { run_id: 'run', status: 'complete', report_html: '<h1>Report</h1>', stages: [], trace: [] };
const decision = { sequence: 1, stage: 'routing', operation: 'RequestIntent', status: 'success', source: 'model', summary: 'Classified station request.', inputs: { command: 'OC8765 rides' }, output: { station_id: 'JC001' } };
const encode = (event: unknown) => new TextEncoder().encode(`${JSON.stringify(event)}\n`);
function response(events: unknown[]) {
  return { ok: true, body: new ReadableStream<Uint8Array>({ start(controller) { events.forEach(event => controller.enqueue(encode(event))); controller.close(); } }) };
}
function submit() { fireEvent.click(screen.getByRole('button', { name: 'Run agent analysis' })); }

test('reveals exact trace only after completion and clears it on the next submission', async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start(value) { controller = value; } });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ ok: true, body }).mockResolvedValueOnce(response([{ type: 'result', data: result }])));
  render(<AgentPanel period="2026-07" command="OC8765 rides" busy={false} />);
  submit();
  await act(async () => { controller.enqueue(encode({ type: 'trace', data: decision })); });
  expect(screen.queryByText('Classified station request.')).not.toBeInTheDocument();
  await act(async () => { controller.enqueue(encode({ type: 'result', data: result })); controller.close(); });
  const trace = await screen.findByRole('region', { name: 'Trace' });
  expect(within(trace).getByText('Classified station request.')).toBeInTheDocument();
  expect(within(trace).getByText(/"station_id": "JC001"/)).toBeInTheDocument();
  expect(within(trace).getByText(/Model/)).toBeInTheDocument();
  submit();
  expect(screen.queryByText('Classified station request.')).not.toBeInTheDocument();
  await screen.findByText('Agent report ready for 2026-07.');
});

test('retains received steps on transport failure and marks the trace incomplete', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([{ type: 'trace', data: decision }, { type: 'error', message: 'Connection ended.' }])));
  render(<AgentPanel period="2026-07" command="OC8765 rides" busy={false} />);
  submit();
  const trace = await screen.findByRole('region', { name: 'Trace' });
  expect(within(trace).getByText('Classified station request.')).toBeInTheDocument();
  expect(within(trace).getByText(/Trace incomplete/)).toBeInTheDocument();
  expect(within(trace).getByText('Connection ended.')).toBeInTheDocument();
});

test('keeps outputs above the old 2 MB limit and renders markup as text', async () => {
  const output = '<script>window.injected=true</script>' + 'x'.repeat(2_000_001);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([{ type: 'trace', data: { ...decision, source: 'tool', output } }, { type: 'result', data: result }])));
  render(<AgentPanel period="2026-07" command="Analyze" busy={false} />);
  submit();
  const trace = await screen.findByRole('region', { name: 'Trace' });
  expect(trace.querySelectorAll('pre')[1].textContent).toBe(JSON.stringify(output, null, 2));
  expect(trace.querySelector('script')).toBeNull();
});

test('rejects invalid trace events and explicitly reports the 16 MiB limit', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response([{ type: 'trace', data: { ...decision, sequence: 'bad' } }])).mockResolvedValueOnce(response([{ type: 'trace', data: decision }, { padding: 'x'.repeat(16 * 1024 * 1024) }])));
  render(<AgentPanel period="2026-07" command="Analyze" busy={false} />);
  submit();
  expect(await screen.findByRole('alert')).toHaveTextContent('invalid trace');
  submit();
  expect(await screen.findByRole('alert')).toHaveTextContent('16 MiB');
  expect(screen.getByText(/Trace incomplete/)).toBeInTheDocument();
});

test('refreshing the component drops trace state and editing the next query preserves the submitted trace', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([{ type: 'trace', data: decision }, { type: 'result', data: result }])));
  const view = render(<AgentPanel period="2026-07" command="OC8765 rides" busy={false} />);
  submit();
  await screen.findByText('Classified station request.');
  view.rerender(<AgentPanel period="2026-08" command="Next request" busy={false} />);
  expect(screen.getByText('Classified station request.')).toBeInTheDocument();
  view.unmount();
  render(<AgentPanel period="2026-07" command="OC8765 rides" busy={false} />);
  expect(screen.queryByText('Classified station request.')).not.toBeInTheDocument();
});


test('requires literal status and source strings at the stream boundary', () => {
  expect(isTraceEvent({ ...decision, status: ['success'] })).toBe(false);
  expect(isTraceEvent({ ...decision, source: ['tool'] })).toBe(false);
});

test('ignores a superseded response when a new run token submits another query', async () => {
  let finishOld!: (value: unknown) => void;
  const oldResponse = new Promise(resolve => { finishOld = resolve; });
  vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(oldResponse).mockResolvedValueOnce(response([{ type: 'trace', data: { ...decision, summary: 'Latest query.' } }, { type: 'result', data: result }])));
  const view = render(<AgentPanel period="2026-07" command="Old request" busy={false} runToken={1} />);
  view.rerender(<AgentPanel period="2026-08" command="New request" busy={false} runToken={2} />);
  await screen.findByText('Latest query.');
  await act(async () => { finishOld(response([{ type: 'trace', data: decision }, { type: 'result', data: result }])); });
  expect(screen.getByText('Latest query.')).toBeInTheDocument();
  expect(screen.queryByText('Classified station request.')).not.toBeInTheDocument();
});
