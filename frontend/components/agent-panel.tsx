'use client';

import { useEffect, useId, useRef, useState } from 'react';
import TracePanel, { isTraceEvent, type QueryTrace, type TraceEvent } from './trace-panel';
import WheelButton from './wheel-button';
import StageStatus from './stage-status';

type Stage = { name: string; status: string };
type Trace = { tool_name: string; status: string; arguments?: Record<string, unknown>; values?: unknown[] };
type AgentRun = { run_id: string; status: 'complete' | 'partial' | 'refused'; report_html: string; warning?: string | null; error_code?: string | null; validation_reason?: string | null; candidate_id?: string | null; stages: Stage[]; trace: Trace[]; station_choices?: { station_id: string; station_name: string }[] };

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
      <WheelButton type="submit" className="mt-2" disabled={disabled || !selectedStation}>Analyze selected station</WheelButton>
    </form>}
    <form className="mt-3" onSubmit={event => { event.preventDefault(); if (!disabled && stationId.trim()) onSelect(stationId.trim()); }}>
      <label htmlFor={inputId} className="block font-medium">Station ID</label>
      <input id={inputId} name="station_id" value={stationId} onChange={event => setStationId(event.target.value)} disabled={disabled} autoComplete="off" />
      <WheelButton type="submit" className="mt-2" disabled={disabled || !stationId.trim()}>Use station ID</WheelButton>
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
  const activeStage = liveForCurrent && !liveStages.some(stage => stage.status === 'failed')
    ? stageNames.find(name => !liveStages.some(stage => stage.name === name && ['complete', 'failed', 'skipped'].includes(stage.status)))
    : undefined;
  const failedForCurrent = !!error && attemptForCurrent;
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
          const terminalStages = previous.filter(stage => ['complete', 'failed', 'skipped'].includes(stage.status));
          const firstUnconfirmed = stageNames.findIndex(name => !terminalStages.some(stage => stage.name === name));
          return stageNames.map((name, index) => terminalStages.find(stage => stage.name === name)
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
    {showButton && <WheelButton type="button" className="mt-4" busy={running} disabled={!validPeriod || !command.trim() || busy || running} onAction={() => analyze()}>{running ? 'Running agent analysis…' : 'Run agent analysis'}</WheelButton>}
    {showButton && (!validPeriod || !command.trim()) && <p className="mt-3">Select a reporting month and enter an analysis request above.</p>}
    {liveForCurrent && <p role="status" className="mt-3">Analysis in progress for {runningPeriod}. {liveStages.at(-1)?.name || 'Preparing request'}: {liveStages.at(-1)?.status || 'starting'}.</p>}
    {error && runningPeriod === period && runningCommand === command && <p role="alert" className="mt-3">{error}</p>}
    <h3 className="mt-6 font-semibold">Progress</h3>
    {failedForCurrent && <p className="mt-2 text-sm text-slate-700">Progress retains confirmed server statuses. Unconfirmed stages are marked failed or skipped because the request ended.</p>}
    <ol className="agent-stage-list" aria-label="Agent stages">
      {stageNames.map(name => {
        const status = visibleRun?.stages.find(stage => stage.name === name)?.status || (liveForCurrent || failedForCurrent ? liveStages.find(stage => stage.name === name)?.status || (name === activeStage ? 'running' : 'pending') : 'idle');
        const problem = visibleRun?.stages.find(stage => stage.status === 'failed' || stage.status === 'skipped')?.name;
        const detail = visibleRun?.validation_reason ? failureDetail[visibleRun.validation_reason] : '';
        const reason = name === problem ? [...new Set([visibleRun?.warning, detail].filter(Boolean))].join(' ') : '';
        return <li key={name} className="stage-row" aria-live="polite" aria-atomic="true">
          <span className="stage-name">{name}</span>
          <StageStatus status={status} />
          {reason && <p className="stage-reason">{reason}</p>}
        </li>;
      })}
    </ol>
    {visibleRun && (visibleRun.warning || visibleRun.validation_reason) && <p role="alert" className="mt-4">{[...new Set([visibleRun.warning, visibleRun.validation_reason ? failureDetail[visibleRun.validation_reason] : ''].filter(Boolean))].join(' ')}</p>}
    {visibleRun && <>
      <p role="status" className="mt-4">{visibleRun.status === 'complete' ? `Agent report ready for ${runPeriod}.` : visibleRun.status === 'partial' ? (visibleRun.report_html ? 'Agent analysis partial. Baseline report available.' : 'Agent analysis stopped before a report was added.') : needsStation ? 'Choose a station to continue.' : 'Request refused.'}</p>
    </>}
    {visibleRun && needsStation && <StationClarification key={`${visibleRun.run_id}:${period}:${command}`} choices={visibleRun.station_choices || []} disabled={busy || running} onSelect={stationId => void analyze(stationId)} />}
    {(visibleRun?.candidate_id || (liveForCurrent && liveCandidate)) && <p className="mt-2">Mandatory investigation candidate: {visibleRun?.candidate_id || liveCandidate}</p>}
      {visibleRun?.report_html && <iframe title={`Agent report for ${runPeriod}`} sandbox="" referrerPolicy="no-referrer" srcDoc={visibleRun.report_html} className="mt-4 min-h-[48rem] w-full border-0" />}
    {liveForCurrent && liveTrace.length > 0 && <p className="mt-3" role="status">{liveTrace.length} aggregate tool {liveTrace.length === 1 ? 'call' : 'calls'} received.</p>}
  </section>
    {!onTrace && queryTrace && <TracePanel trace={queryTrace} />}
  </>;
}
