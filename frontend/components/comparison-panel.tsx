'use client';

import { useEffect, useRef, useState } from 'react';
import WheelButton from './wheel-button';
import type { components } from '../src/generated/api';

type Trace = components['schemas']['ToolResult'];
type PythonBaseline = components['schemas']['PythonBaseline'];
type Comparison = components['schemas']['ComparisonResult'];
type RecordValue = Record<string, unknown>;
const record = (value: unknown): value is RecordValue => value !== null && typeof value === 'object' && !Array.isArray(value);
const periodValue = (value: unknown) => record(value) && Number.isInteger(value.year) && Number.isInteger(value.month) && Number(value.month) >= 1 && Number(value.month) <= 12;
const datasetValue = (value: unknown) => record(value) && typeof value.version_id === 'string' && periodValue(value.period);
const traceValue = (value: unknown): value is RecordValue => record(value) && typeof value.tool_name === 'string' && typeof value.status === 'string' && Array.isArray(value.values);
const count = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0;
function isBaseline(value: unknown): value is PythonBaseline {
  return record(value) && record(value.monthly_totals) && ['2026-01', '2026-02'].every(month => count((value.monthly_totals as RecordValue)[month]))
    && Array.isArray(value.top_stations) && value.top_stations.every(station => record(station) && typeof station.station_id === 'string' && typeof station.station_name === 'string' && count(station.ride_count))
    && Array.isArray(value.inputs) && value.inputs.every(input => record(input) && datasetValue(input.dataset));
}
function isComparison(value: unknown): value is Comparison {
  if (!record(value) || typeof value.report_id !== 'string' || !isBaseline(value.baseline) || !record(value.period) || value.period.year !== 2026 || value.period.month !== 2
      || (!Array.isArray(value.datasets) || !value.datasets.every(datasetValue)) || !Array.isArray(value.rows) || value.rows.length !== 2 || !record(value.agent) || !record(value.agent.counters) || !record(value.timing_seconds)) return false;
  const agent = value.agent;
  return ['complete', 'partial', 'refused'].includes(String(agent.status)) && typeof agent.report_html === 'string' && Array.isArray(agent.trace) && agent.trace.every(traceValue) && Array.isArray(agent.stages) && (agent.warning === null || typeof agent.warning === 'string') && (agent.candidate_id == null || typeof agent.candidate_id === 'string')
    && ['llm_calls', 'tool_calls', 'input_tokens', 'output_tokens'].every(key => count((agent.counters as RecordValue)[key]))
    && ['shared_preparation', 'python_calculation', 'agent_workflow'].every(key => typeof (value.timing_seconds as RecordValue)[key] === 'number' && Number.isFinite((value.timing_seconds as RecordValue)[key]) && Number((value.timing_seconds as RecordValue)[key]) >= 0)
    && value.rows.every((row, index) => record(row) && row.month === ['2026-01', '2026-02'][index] && count(row.python_total)
      && (row.agent_total === null || count(row.agent_total)) && (row.difference === null || Number.isSafeInteger(row.difference))
      && ['match', 'mismatch', 'unavailable'].includes(String(row.status))) ;
}
const number = (value: number | null) => value === null ? 'Unavailable' : new Intl.NumberFormat('en-US', {maximumFractionDigits: 2}).format(value);

export default function ComparisonPanel(props: {period: string; busy: boolean}) {
  return <ComparisonSession key={props.period} {...props}/>;
}

function ComparisonSession({period, busy}: {period: string; busy: boolean}) {
  const active = useRef<AbortController | null>(null);
  const [monthsReady, setMonthsReady] = useState(false);
  const [monthsMessage, setMonthsMessage] = useState('Checking accepted demo months…');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      if (busy) return;
      try {
        const response = await fetch('/api/periods', {cache: 'no-store', signal: controller.signal});
        const body: unknown = await response.json();
        if (!response.ok || !record(body) || body.success !== true || !record(body.data) || !Array.isArray(body.data.periods)) throw new Error('Unavailable');
        const ready = [1, 2].every(month => (body.data as RecordValue).periods instanceof Array && ((body.data as RecordValue).periods as unknown[]).some(item => record(item) && periodValue(item.period) && (item.period as RecordValue).year === 2026 && (item.period as RecordValue).month === month));
        if (!controller.signal.aborted) { setMonthsReady(ready); setMonthsMessage(ready ? 'January and February 2026 accepted datasets available.' : 'Load accepted January and February 2026 data before running the demo.'); }
      } catch { if (!controller.signal.aborted) { setMonthsReady(false); setMonthsMessage('Accepted demo months could not be checked. Refresh to retry.'); } }
    }, 0);
    return () => {clearTimeout(timer); controller.abort();};
  }, [busy, refresh]);
  const [running, setRunning] = useState(false);
  const [baseline, setBaseline] = useState<PythonBaseline | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [progress, setProgress] = useState('');
  const [trace, setTrace] = useState<Trace[]>([]);
  const [error, setError] = useState('');
  const [requestPeriod, setRequestPeriod] = useState('');
  useEffect(() => () => { active.current?.abort(); active.current = null; }, []);
  const visible = requestPeriod === period;

  async function compare() {
    if (active.current || !monthsReady || busy || period !== '2026-02') return;
    const controller = new AbortController();
    active.current = controller;
    const current = () => active.current === controller && !controller.signal.aborted;
    setRunning(true); setBaseline(null); setComparison(null); setError(''); setTrace([]);
    setProgress('Preparing one shared January/February snapshot…'); setRequestPeriod(period);
    try {
      const response = await fetch('/api/comparisons/stream', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({period: {year: 2026, month: 2}}),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(180_000)]),
      });
      if (!response.ok || !response.body) throw new Error('Comparison could not start. Confirm both accepted months are available and retry.');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffered = ''; let bytes = 0; const result: {data?: Comparison} = {};
      function consume(line: string) {
        if (!line.trim() || !current()) return;
        const event: unknown = JSON.parse(line);
        if (!record(event)) throw new Error('Comparison service returned an invalid event. Retry.');
        if (event.type === 'baseline') {
          if (!isBaseline(event.data)) throw new Error('Comparison service returned an invalid Python baseline. Retry.');
          setBaseline(event.data); setProgress('Python baseline ready. Agent workflow in progress.');
        } else if (event.type === 'stage' && typeof event.name === 'string' && typeof event.status === 'string') {
          setProgress(`${event.name}: ${event.status}`);
        } else if (event.type === 'tool' && traceValue(event.data)) {
          setTrace(previous => [...previous, event.data as Trace]);
        } else if (event.type === 'candidate' && typeof event.candidate_id === 'string') {
          setProgress(`Investigating station ${event.candidate_id}.`);
        } else if (event.type === 'result') {
          if (!isComparison(event.data)) throw new Error('Comparison service returned an invalid result. Retry.');
          result.data = event.data;
        } else if (event.type === 'error') throw new Error(typeof event.message === 'string' ? event.message : 'Comparison failed. Retry.');
      }
      try {
        while (current()) {
          const {done, value} = await reader.read();
          if (done) break;
          bytes += value.byteLength;
          if (bytes > 2_000_000) throw new Error('Comparison response exceeded its limit.');
          buffered += decoder.decode(value, {stream: true});
          const lines = buffered.split('\n'); buffered = lines.pop() || '';
          for (const line of lines) consume(line);
        }
        buffered += decoder.decode();
        if (buffered) consume(buffered);
        if (!current()) return;
        if (!result.data) throw new Error('Comparison interrupted. Python baseline remains available; agent result is unavailable. Retry.');
        setComparison(result.data); setBaseline(result.data.baseline);
      } finally { await reader.cancel(); }
    } catch (failure) {
      if (current()) setError(failure instanceof Error ? failure.message : 'Comparison unavailable. Retry.');
    } finally {
      if (current()) { setRunning(false); active.current = null; }
    }
  }

  const shownBaseline = visible ? baseline : null;
  const shown = visible ? comparison : null;
  const activity = shown?.agent.trace || (visible ? trace : []);
  return <section id="comparison" aria-labelledby="comparison-heading" className="panel mt-6">
    <h2 id="comparison-heading">Baseline vs Agent</h2>
    <p>Fixed demo: January and February 2026, with February as reporting month. Both accepted datasets are required before model dispatch.</p>
    <p className="mt-2 text-sm">One shared pinned snapshot feeds independent Python calculations and the configured live agent. The combined station ranking and agent investigation have different scopes.</p>
    <WheelButton type="button" className="mt-4" disabled={period !== '2026-02' || !monthsReady || busy || running} onAction={compare}>{running && visible ? 'Running demo comparison…' : 'Run demo comparison'}</WheelButton>
    <p className="mt-2 text-sm">{monthsMessage}</p>
    <WheelButton type="button" className="mt-2" busy={monthsMessage === 'Checking accepted demo months…' && !busy} disabled={busy || running} onClick={() => {setMonthsReady(false); setMonthsMessage('Checking accepted demo months…'); setRefresh(value => value + 1);}}>Refresh demo months</WheelButton>
    {period !== '2026-02' && <p className="mt-2">Select February 2026 above to run the demo.</p>}
    {visible && running && <p role="status" className="mt-3">{progress}</p>}
    {visible && error && <p role="alert" className="mt-3">{error}</p>}
    {shown && <p role="status" className="mt-3">{shown.agent.status === 'complete' ? 'Agent analysis complete. Numerical agreement is shown separately below.' : shown.agent.status === 'partial' ? 'Agent analysis partial. Verified totals do not establish agent completion.' : 'Agent request refused. Verified totals do not establish agent completion.'}</p>}
    {shown?.agent.warning && <p role="alert" className="mt-2">{shown.agent.warning}</p>}
    {shownBaseline && <>
      <div className="mt-4 overflow-x-auto" role="region" aria-label="Monthly totals comparison" tabIndex={0}>
        <table className="w-full text-left"><caption className="mb-2 text-left font-semibold">Monthly totals · agent minus Python difference</caption><thead><tr>{['Month', 'Python baseline', 'Agent tool result', 'Difference', 'Status'].map(label => <th key={label} scope="col" className="p-2">{label}</th>)}</tr></thead>
          <tbody>{['2026-01', '2026-02'].map(month => {
            const row = shown?.rows.find(row => row.month === month);
            return <tr key={month}><th scope="row" className="p-2">{month}</th><td className="p-2">{number(shownBaseline.monthly_totals[month])}</td><td className="p-2">{number(row?.agent_total ?? null)}</td><td className="p-2">{number(row?.difference ?? null)}</td><td className="p-2">{row?.status === 'match' ? 'Match' : row?.status === 'mismatch' ? 'Mismatch' : 'Unavailable'}</td></tr>;
          })}</tbody></table>
      </div>
      <div className="mt-6 grid min-w-0 gap-6 md:grid-cols-2" data-testid="comparison-panels">
        <section aria-labelledby="python-comparison-heading" className="min-w-0">
          <h3 id="python-comparison-heading" className="font-semibold">Independent Python baseline</h3>
          <p className="mt-2">Zero model calls. Zero agent-selected tool calls.</p>
          <h4 className="mt-4 font-semibold">Baseline-only analysis</h4>
          <p>Top five start stations across January + February combined. Ties use ascending station ID.</p>
          <ol className="mt-2 list-inside list-decimal">{shownBaseline.top_stations.map(station => <li key={station.station_id}>{station.station_name} ({station.station_id}): {number(station.ride_count)} starts</li>)}</ol>
          <details className="mt-4"><summary>Shared pinned dataset versions</summary><ul>{shownBaseline.inputs.map(input => <li key={input.dataset.version_id}>{input.dataset.period.year}-{String(input.dataset.period.month).padStart(2, '0')} · {input.dataset.version_id}</li>)}</ul></details>
        </section>
        <section aria-labelledby="agent-comparison-heading" className="min-w-0">
          <h3 id="agent-comparison-heading" className="font-semibold">Additional agent analysis</h3>
          <p className="mt-2">Station investigation and adaptive follow-up. Only successful attributed tool evidence supplies comparison totals.</p>
          {shown?.agent.candidate_id && <p className="mt-2">Investigation candidate: {shown.agent.candidate_id}</p>}
          {activity.length > 0 && <details open className="mt-3"><summary>Verified evidence and tool activity</summary><ol>{activity.map((step, index) => <li key={index} className="my-2 border-b pb-2"><strong>{step.tool_name.replaceAll('_', ' ')}</strong>: {step.status}<details><summary>Exact evidence and inputs</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(step, null, 2)}</pre></details></li>)}</ol></details>}
          {shown && <p className="mt-3">Model calls: {shown.agent.counters.llm_calls}/6 · Tool calls: {shown.agent.counters.tool_calls}/10<br/>Input tokens: {shown.agent.counters.input_tokens} · Output tokens: {shown.agent.counters.output_tokens} (reported responses only; failed calls may have unreported usage)<br/>Dollar cost: unavailable; no verified pricing.</p>}
          {shown?.agent.report_html && <iframe title="Comparison agent report for 2026-02" sandbox="" referrerPolicy="no-referrer" srcDoc={shown.agent.report_html} className="mt-4 min-h-[36rem] w-full"/>}
        </section>
      </div>
    </>}
    {shown && <section aria-label="Comparison timings" className="mt-6"><h3 className="font-semibold">Separately measured timings</h3><p>Shared preparation: {number(shown.timing_seconds.shared_preparation)} s · Python calculation: {number(shown.timing_seconds.python_calculation)} s · Agent workflow: {number(shown.timing_seconds.agent_workflow)} s</p><p className="text-sm">Shared preparation includes the standard dashboard and pinning. Agent workflow includes model and tool work. These scopes do not establish a speed winner.</p><p className="mt-2 text-sm">Archived comparison: {shown.report_id}</p></section>}
  </section>;
}
