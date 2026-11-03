'use client';

import { useEffect, useId, useRef, useState } from 'react';
import TracePanel, { isTraceEvent, type QueryTrace, type TraceEvent } from './trace-panel';

type Stage = { name: string; status: string };
type Ranking = { ranked_by: string; order: 'top' | 'bottom'; rank: number; tied: boolean; station_name: string };
type Value = { entity_id?: string; metric_type: string; dimension?: string | null; category?: string | null; unit?: string; exact_tool_value?: number | null; eligible?: boolean; eligibility_reason?: string | null; ranking?: Ranking | null };
type Trace = { tool_name: string; status: string; arguments?: Record<string, unknown>; values?: Value[] };
type AgentRun = { run_id: string; status: 'complete' | 'partial' | 'refused'; report_html: string; warning?: string | null; error_code?: string | null; validation_reason?: string | null; candidate_id?: string | null; stages: Stage[]; trace: Trace[]; station_choices?: { station_id: string; station_name: string }[] };

const toolLabels: Record<string, string> = { kpi_summary: 'Monthly metrics', compare_periods: 'Month comparison', daily_trend: 'Daily trip starts', station_analysis: 'Station rankings', retrieve_context: 'Reporting guidance', validate_and_load_file: 'Data validation', station_movers: 'Station changes', analyze_station_variance: 'Station change breakdown', generate_standard_dashboard: 'Standard monthly dashboard', get_available_periods: 'Available reporting months', resolve_station: 'Station lookup', make_chart: 'Verified chart', rank_stations: 'Station leaderboard' };
const rankedMetric: Record<string, { type: string; label: string; rate: boolean }> = {
  total_starts: { type: 'current_volume', label: 'Total starts', rate: false },
  total_ends: { type: 'end_volume', label: 'Trip ends', rate: false },
  ebike_share_pct: { type: 'share', label: 'E-bike share', rate: true },
  casual_share_pct: { type: 'share', label: 'Casual share', rate: true },
  avg_duration_min: { type: 'average_duration_minutes', label: 'Average duration', rate: true },
};
const shownArguments = ['station_id', 'period', 'current_period', 'comparison_period', 'prior_period', 'metric', 'order', 'top_n'];
const readable = (name: string) => name.replaceAll('_', ' ');
const contextValue = (value: unknown) => {
  if (value && typeof value === 'object' && 'year' in value && 'month' in value) return `${value.year}-${String(value.month).padStart(2, '0')}`;
  return typeof value === 'string' ? value : JSON.stringify(value);
};
const stageNames = ['Data Ingest', 'Agent Planning', 'Tool Execution', 'Final Report Generation'];
const failureDetail: Record<string, string> = {
  route_schema_mismatch: 'The model reply was not in the required format, so planning did not start.',
  invalid_plan: 'The model did not choose the allowed tools.',
  missing_required_tool: 'The model left out a required tool.',
  duplicate_tool: 'The model named the same tool twice.',
  unsupported_tool: 'The model named a tool this report cannot use.',
  available_periods_failed: 'The pinned months could not be read.',
  initial_tool_failed: 'A selected tool failed.',
  invalid_follow_up: 'The model did not investigate the required station.',
  follow_up_schema_mismatch: 'The station follow-up reply was not in the required format.',
  ungrounded_claim: 'The written sentences did not match the tool numbers, so they were not added.',
  draft_schema_mismatch: 'The report draft was not in the required format.',
  artifact_persistence_failed: 'The report could not be saved.',
};
const formatPercent = (value: number | null | undefined) => typeof value === 'number' ? `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)}%` : 'unavailable';
const formatValue = (value: Value) => value.eligible && typeof value.exact_tool_value === 'number'
  ? `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value.exact_tool_value)} ${value.unit || ''}`
  : value.eligibility_reason?.replaceAll('_', ' ') || 'unavailable';

function Leaderboard({ values }: { values: Value[] }) {
  const ranked = values.filter(value => value.ranking && value.metric_type === rankedMetric[value.ranking.ranked_by]?.type);
  if (ranked.length === 0) return null;
  const metric = rankedMetric[ranked[0].ranking!.ranked_by];
  const starts = (row: Value) => metric.type === 'current_volume' ? row.exact_tool_value
    : values.find(value => value.ranking && value.entity_id === row.entity_id && value.metric_type === 'current_volume')?.exact_tool_value;
  const number = (value: number | null | undefined) => typeof value === 'number' ? new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value) : 'unavailable';
  return <div className="mt-2 overflow-x-auto"><table className="w-full text-left text-sm" aria-label="Station leaderboard">
    <thead><tr><th scope="col">Rank</th><th scope="col">Station ID</th><th scope="col">Station name</th><th scope="col">{metric.label}</th><th scope="col">Total starts</th><th scope="col">Notes</th></tr></thead>
    <tbody>{ranked.map(row => <tr key={row.entity_id}>
      <td>{row.ranking!.rank}</td><td>{row.entity_id}</td><td>{row.ranking!.station_name}</td>
      <td>{number(row.exact_tool_value)}{row.unit === 'percent' ? '%' : row.unit === 'minutes' ? ' min' : ''}</td>
      <td>{number(starts(row))}</td>
      <td>{row.ranking!.tied && <span className="mr-1 rounded bg-amber-100 px-1">Tied</span>}{metric.rate && <span className="rounded bg-slate-100 px-1">100+ starts</span>}</td>
    </tr>)}</tbody>
  </table></div>;
}

function StationClarification({ choices, disabled, onSelect }: { choices: { station_id: string; station_name: string }[]; disabled: boolean; onSelect: (stationId: string) => void }) {
  const [stationId, setStationId] = useState('');
  const inputId = useId();
  const selectId = useId();
  const [selectedStation, setSelectedStation] = useState('');
  return <section aria-label="Choose a station" className="mt-4 rounded border border-slate-300 p-4">
    <h3 className="font-semibold">Choose a station</h3>
    <p className="mt-2">Select a matching station or enter its ID below. Your original request and selected month will be submitted again with that station.</p>
    {choices.length > 0 && <form className="mt-3" onSubmit={event => {
      event.preventDefault();
      if (!disabled && choices.some(choice => choice.station_id === selectedStation)) onSelect(selectedStation);
    }}>
      <label htmlFor={selectId} className="block font-medium">Matching station</label>
      <select id={selectId} value={selectedStation} onChange={event => setSelectedStation(event.target.value)} disabled={disabled} required>
        <option value="" disabled>Choose a station…</option>
        {choices.map(choice => <option key={choice.station_id} value={choice.station_id}>{choice.station_name} ({choice.station_id})</option>)}
      </select>
      <button type="submit" className="mt-2" disabled={disabled || !selectedStation}>Analyze selected station</button>
    </form>}
    <form className="mt-3" onSubmit={event => { event.preventDefault(); if (!disabled && stationId.trim()) onSelect(stationId.trim()); }}>
      <label htmlFor={inputId} className="block font-medium">Station ID</label>
      <input id={inputId} name="station_id" value={stationId} onChange={event => setStationId(event.target.value)} disabled={disabled} autoComplete="off" />
      <button type="submit" className="mt-2" disabled={disabled || !stationId.trim()}>Use station ID</button>
    </form>
  </section>;
}

export default function AgentPanel({ period, command, busy, showButton = true, runToken = 0, onRunning, onTrace }: { period: string; command: string; busy: boolean; showButton?: boolean; runToken?: number; onRunning?: (running: boolean) => void; onTrace?: (trace: QueryTrace | null) => void }) {
  const [running, setRunning] = useState(false);
  const [queryTrace, setQueryTrace] = useState<QueryTrace | null>(null);
  const updateTrace = onTrace || setQueryTrace;
  const activeRequest = useRef<{ id: number; controller: AbortController } | null>(null);
  const requestSequence = useRef(0);
  useEffect(() => () => { activeRequest.current?.controller.abort(); activeRequest.current = null; }, []);
  const [runningPeriod, setRunningPeriod] = useState('');
  const [runningCommand, setRunningCommand] = useState('');
  const [error, setError] = useState('');
  const [run, setRun] = useState<AgentRun | null>(null);
  const [runPeriod, setRunPeriod] = useState('');
  const [runCommand, setRunCommand] = useState('');
  const [liveStages, setLiveStages] = useState<Stage[]>([]);
  const [liveTrace, setLiveTrace] = useState<Trace[]>([]);
  const [liveCandidate, setLiveCandidate] = useState<string | null>(null);
  const validPeriod = /^\d{4}-(0[1-9]|1[0-2])$/.test(period);
  const visibleRun = runPeriod === period && runCommand === command ? run : null;
  const needsStation = visibleRun && (visibleRun.error_code === 'ERR_STATION_SELECTION' || !!visibleRun.station_choices?.length);
  const attemptForCurrent = runningPeriod === period && runningCommand === command;
  const liveForCurrent = running && attemptForCurrent;
  const failedForCurrent = !!error && attemptForCurrent;
  const displayTrace = visibleRun?.trace || [];
  const analyzeRef = useRef<(stationId?: string) => void>(() => {});
  const seenToken = useRef(0);
  useEffect(() => { onRunning?.(running); }, [running, onRunning]);
  useEffect(() => { analyzeRef.current = analyze; });
  useEffect(() => {
    if (runToken === 0 || runToken === seenToken.current) return;
    seenToken.current = runToken;
    void analyzeRef.current();
  }, [runToken]);

  async function analyze(stationId?: string) {
    activeRequest.current?.controller.abort();
    const request = { id: ++requestSequence.current, controller: new AbortController() };
    activeRequest.current = request;
    const isCurrent = () => activeRequest.current === request;
    const events: TraceEvent[] = [];
    let traceError = '';
    let receivedResult = false;
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    updateTrace(null);
    setRunning(true); setError(''); setRun(null); setLiveStages([]); setLiveTrace([]); setLiveCandidate(null);
    setRunningPeriod(period); setRunningCommand(command);
    const [year, month] = period.split('-').map(Number);
    try {
      const response = await fetch('/api/agent-runs/stream', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: { year, month }, command: command.trim(), ...(stationId ? { station_id: stationId } : {}) }),
        signal: AbortSignal.any([request.controller.signal, AbortSignal.timeout(180_000)]),
      });
      if (!response.ok || !response.body) throw new Error('Agent analysis failed. Retry.');
      if (!isCurrent()) { await response.body.cancel(); return; }
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffered = '';
      let bytes = 0;
      const result: { data?: AgentRun } = {};
      function consume(line: string) {
        if (!isCurrent() || !line.trim()) return;
        const event = JSON.parse(line);
        if (event.type === 'trace') {
          if (!isTraceEvent(event.data) || event.data.sequence <= (events.at(-1)?.sequence || 0)) throw new Error('Agent service returned an invalid trace.');
          events.push(event.data);
        } else if (event.type === 'stage' && typeof event.name === 'string' && typeof event.status === 'string') {
          setLiveStages(previous => [...previous.filter(stage => stage.name !== event.name), { name: event.name, status: event.status }]);
        } else if (event.type === 'tool' && event.data?.tool_name) {
          setLiveTrace(previous => [...previous, event.data]);
        } else if (event.type === 'candidate' && typeof event.candidate_id === 'string') {
          setLiveCandidate(event.candidate_id);
        } else if (event.type === 'result') {
          result.data = event.data;
        } else if (event.type === 'error') {
          throw new Error(event.message || 'Agent analysis failed. Retry.');
        }
      }
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!isCurrent()) { await reader.cancel(); return; }
        bytes += value.byteLength;
        if (bytes > 16 * 1024 * 1024) { await reader.cancel(); throw new Error('Agent response exceeded the 16 MiB limit. Trace is incomplete.'); }
        buffered += decoder.decode(value, { stream: true });
        const lines = buffered.split('\n');
        buffered = lines.pop() || '';
        for (const line of lines) consume(line);
      }
      buffered += decoder.decode();
      if (buffered) consume(buffered);
      const data = result.data;
      if (!data || !['complete', 'partial', 'refused'].includes(data.status) || typeof data.report_html !== 'string' || (data.status === 'complete' && !data.report_html.trim()) || !Array.isArray(data.stages) || !Array.isArray(data.trace) || (data.station_choices !== undefined && (!Array.isArray(data.station_choices) || !data.station_choices.every(choice => typeof choice.station_id === 'string' && typeof choice.station_name === 'string')))) {
        throw new Error('Agent service returned an invalid report. Retry.');
      }
      if (!isCurrent()) return;
      receivedResult = true;
      setRunPeriod(period);
      setRunCommand(command);
      setRun(data);
    } catch (failure) {
      traceError = failure instanceof Error ? failure.message : 'Agent service unavailable. Retry.';
      if (isCurrent()) {
        setError(traceError);
        setLiveStages(previous => {
          const firstUnconfirmed = stageNames.findIndex(name => !previous.some(stage => stage.name === name));
          return stageNames.map((name, index) => previous.find(stage => stage.name === name)
            || { name, status: index === firstUnconfirmed ? 'failed' : 'skipped' });
        });
      }
      await reader?.cancel().catch(() => {});
    } finally {
      if (isCurrent()) {
        updateTrace({ command, period, events, error: traceError, incomplete: !receivedResult });
        setRunning(false);
      }
    }
  }

  return <><section id="agent" aria-labelledby="agent-heading" className="panel mt-6">
    <h2 id="agent-heading">Agent analysis</h2>
    <p className="mt-2 text-sm text-slate-700">The agent can investigate verified aggregate metrics. Reports use the selected month’s active dataset.</p>
    {showButton && <button type="button" className="mt-4" disabled={!validPeriod || !command.trim() || busy || running} onClick={() => void analyze()}>{running ? 'Running agent analysis…' : 'Run agent analysis'}</button>}
    {showButton && (!validPeriod || !command.trim()) && <p className="mt-3">Select a reporting month and enter an analysis request above.</p>}
    {liveForCurrent && <p role="status" className="mt-3">Analysis in progress for {runningPeriod}. {liveStages.at(-1)?.name || 'Preparing request'}: {liveStages.at(-1)?.status || 'starting'}.</p>}
    {error && runningPeriod === period && runningCommand === command && <p role="alert" className="mt-3">{error}</p>}
    <h3 className="mt-6 font-semibold">Progress</h3>
    {failedForCurrent && <p className="mt-2 text-sm text-slate-700">Progress retains confirmed server statuses. Unconfirmed stages are marked failed or skipped because the request ended.</p>}
    <ol className="mt-2 grid gap-2 sm:grid-cols-2" aria-label="Agent stages">
      {stageNames.map(name => {
        const status = visibleRun?.stages.find(stage => stage.name === name)?.status || (liveForCurrent || failedForCurrent ? liveStages.find(stage => stage.name === name)?.status || 'pending' : 'idle');
        const problem = visibleRun?.stages.find(stage => stage.status === 'failed' || stage.status === 'skipped')?.name;
        const detail = visibleRun?.validation_reason ? failureDetail[visibleRun.validation_reason] : '';
        const reason = name === problem ? [...new Set([visibleRun?.warning, detail].filter(Boolean))].join(' ') : '';
        return <li key={name}>{name}: {status}{reason ? `. ${reason}` : ''}</li>;
      })}
    </ol>
    {visibleRun && (visibleRun.warning || visibleRun.validation_reason) && <p role="alert" className="mt-4">{[...new Set([visibleRun.warning, visibleRun.validation_reason ? failureDetail[visibleRun.validation_reason] : ''].filter(Boolean))].join(' ')}</p>}
    {visibleRun && <>
      <p role="status" className="mt-4">{visibleRun.status === 'complete' ? `Agent report ready for ${runPeriod}.` : visibleRun.status === 'partial' ? (visibleRun.report_html ? 'Agent analysis partial. Baseline report available.' : 'Agent analysis stopped before a report was added.') : needsStation ? 'Choose a station to continue.' : 'Request refused.'}</p>
    </>}
    {visibleRun && needsStation && <StationClarification key={`${visibleRun.run_id}:${period}:${command}`} choices={visibleRun.station_choices || []} disabled={busy || running} onSelect={stationId => void analyze(stationId)} />}
    {(visibleRun?.candidate_id || (liveForCurrent && liveCandidate)) && <p className="mt-2">Mandatory investigation candidate: {visibleRun?.candidate_id || liveCandidate}</p>}
      {displayTrace.length > 0 && <section aria-label="Agent tool activity" className="mt-4">
        <h3 className="font-semibold">Tool activity</h3>
        <p className="text-sm">Verified aggregate results. Tool activity shows calculations and their inputs, not private model reasoning.</p>
        <ol className="mt-2 space-y-3">{displayTrace.map((step, index) => <li key={`${step.tool_name}-${index}`} className="rounded border border-slate-300 p-3">
          <p><strong>{toolLabels[step.tool_name] || readable(step.tool_name)}</strong>: {step.status}{step.tool_name.includes('variance') ? ' · adaptive follow-up' : ''}</p>
          {step.arguments && <dl className="mt-2 text-sm">{Object.entries(step.arguments).filter(([key, value]) => value != null && shownArguments.includes(key)).map(([key, value]) => <div key={key}><dt className="inline font-semibold">{readable(key)}: </dt><dd className="inline">{contextValue(value)}</dd></div>)}</dl>}
          <details className="text-sm"><summary>Exact tool identity and inputs</summary><p>{step.tool_name}</p>{step.arguments && <p>Arguments: {JSON.stringify(step.arguments)}</p>}</details>
          {step.tool_name === 'rank_stations' && step.values
            ? <Leaderboard values={step.values} />
            : step.tool_name === 'analyze_station_variance' && step.values?.some(value => value.metric_type === 'contribution')
            ? <ul className="text-sm" aria-label="Variance breakdowns">{step.values.filter(value => value.metric_type === 'contribution').map((value, i) =>
                <li key={i}>{value.dimension?.replaceAll('_', ' ')} · {value.category === 'Unknown' ? 'Unknown (unclassified)' : value.category}: {value.eligible ? formatPercent(value.exact_tool_value) : value.eligibility_reason?.replaceAll('_', ' ') || 'unavailable'}</li>)}</ul>
            : step.values && step.values.length > 0 && <><ul className="text-sm" aria-label="Aggregate results">{step.values.map((value, i) =>
                <li key={i}>{value.entity_id || 'Aggregate'} · {readable(value.metric_type)}: {formatValue(value)}</li>)}</ul>
</>}
        </li>)}</ol>
      </section>}
      {visibleRun?.report_html && <iframe title={`Agent report for ${runPeriod}`} sandbox="" referrerPolicy="no-referrer" srcDoc={visibleRun.report_html} className="mt-4 min-h-[48rem] w-full border-0" />}
    {liveForCurrent && liveTrace.length > 0 && <p className="mt-3" role="status">{liveTrace.length} aggregate tool {liveTrace.length === 1 ? 'call' : 'calls'} received.</p>}
  </section>
    {!onTrace && queryTrace && <TracePanel trace={queryTrace} />}
  </>;
}
