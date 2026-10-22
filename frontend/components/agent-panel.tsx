'use client';

import { useState } from 'react';

type Stage = { name: string; status: string };
type Value = { entity_id?: string; metric_type: string; dimension?: string | null; category?: string | null; unit?: string; exact_tool_value?: number | null; eligible?: boolean; eligibility_reason?: string | null };
type Trace = { tool_name: string; status: string; arguments?: Record<string, unknown>; values?: Value[] };
type AgentRun = { run_id: string; status: 'complete' | 'partial' | 'refused'; report_html: string; warning?: string | null; candidate_id?: string | null; stages: Stage[]; trace: Trace[] };

const stageNames = ['Data Ingest', 'Agent Planning', 'Tool Execution', 'Final Report Generation'];
const formatPercent = (value: number | null | undefined) => typeof value === 'number' ? `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)}%` : 'unavailable';
const formatValue = (value: Value) => value.eligible && typeof value.exact_tool_value === 'number'
  ? `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value.exact_tool_value)} ${value.unit || ''}`
  : value.eligibility_reason || 'unavailable';

export default function AgentPanel({ period, command, busy }: { period: string; command: string; busy: boolean }) {
  const [running, setRunning] = useState(false);
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
  const liveForCurrent = running && runningPeriod === period && runningCommand === command;
  const displayTrace = visibleRun?.trace || (liveForCurrent ? liveTrace : []);

  async function analyze() {
    setRunning(true); setError(''); setRun(null); setLiveStages([]); setLiveTrace([]); setLiveCandidate(null);
    setRunningPeriod(period); setRunningCommand(command);
    const [year, month] = period.split('-').map(Number);
    try {
      const response = await fetch('/api/agent-runs/stream', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: { year, month }, command: command.trim() }),
        signal: AbortSignal.timeout(180_000),
      });
      if (!response.ok || !response.body) throw new Error('Agent analysis failed. Retry.');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffered = '';
      let bytes = 0;
      const result: { data?: AgentRun } = {};
      function consume(line: string) {
        if (!line.trim()) return;
        const event = JSON.parse(line);
        if (event.type === 'stage' && typeof event.name === 'string' && typeof event.status === 'string') {
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
        bytes += value.byteLength;
        if (bytes > 2_000_000) { await reader.cancel(); throw new Error('Agent response exceeded its limit.'); }
        buffered += decoder.decode(value, { stream: true });
        const lines = buffered.split('\n');
        buffered = lines.pop() || '';
        for (const line of lines) consume(line);
      }
      buffered += decoder.decode();
      if (buffered) consume(buffered);
      const data = result.data;
      if (!data || !['complete', 'partial', 'refused'].includes(data.status) || typeof data.report_html !== 'string' || (data.status !== 'refused' && !data.report_html.trim()) || !Array.isArray(data.stages) || !Array.isArray(data.trace)) {
        throw new Error('Agent service returned an invalid report. Retry.');
      }
      setRunPeriod(period);
      setRunCommand(command);
      setRun(data);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Agent service unavailable. Retry.');
    } finally { setRunning(false); }
  }

  return <section aria-labelledby="agent-heading" className="panel mt-6">
    <h2 id="agent-heading">Agent analysis</h2>
    <p className="mt-2 text-sm text-slate-700">The agent can investigate verified aggregate metrics. Reports use the selected month’s active dataset.</p>
    <button type="button" className="mt-4" disabled={!validPeriod || !command.trim() || busy || running} onClick={() => void analyze()}>{running ? 'Running agent analysis…' : 'Run agent analysis'}</button>
    {error && runningPeriod === period && runningCommand === command && <p role="alert" className="mt-3">{error}</p>}
    <h3 className="mt-6 font-semibold">Progress</h3>
    <ol className="mt-2 grid gap-2 sm:grid-cols-2" aria-label="Agent stages">
      {stageNames.map(name => <li key={name}>{name}: {visibleRun?.stages.find(stage => stage.name === name)?.status || (liveForCurrent ? liveStages.find(stage => stage.name === name)?.status || 'pending' : 'idle')}</li>)}
    </ol>
    {visibleRun?.warning && <p role="alert" className="mt-4">{visibleRun.warning}</p>}
    {visibleRun && <>
      <p className="mt-4">{visibleRun.status === 'complete' ? `Agent report ready for ${runPeriod}.` : visibleRun.status === 'partial' ? 'Agent analysis partial. Baseline report available.' : 'Request refused.'}</p>
    </>}
    {(visibleRun?.candidate_id || (liveForCurrent && liveCandidate)) && <p className="mt-2">Mandatory investigation candidate: {visibleRun?.candidate_id || liveCandidate}</p>}
      {displayTrace.length > 0 && <section aria-label="Agent tool activity" className="mt-4">
        <h3 className="font-semibold">Tool activity</h3>
        <ol className="mt-2 space-y-3">{displayTrace.map((step, index) => <li key={`${step.tool_name}-${index}`} className="rounded border border-slate-300 p-3">
          <p><strong>{step.tool_name}</strong>: {step.status}{step.tool_name.includes('variance') ? ' · adaptive follow-up' : ''}</p>
          {step.arguments && Object.keys(step.arguments).length > 0 && <p className="text-sm">Arguments: {JSON.stringify(step.arguments)}</p>}
          {step.tool_name === 'analyze_station_variance' && step.values?.some(value => value.metric_type === 'contribution')
            ? <ul className="text-sm" aria-label="Variance breakdowns">{step.values.filter(value => value.metric_type === 'contribution').map((value, i) =>
                <li key={i}>{value.dimension?.replaceAll('_', ' ')} · {value.category}: {value.eligible ? formatPercent(value.exact_tool_value) : value.eligibility_reason || 'unavailable'}</li>)}</ul>
            : step.values && step.values.length > 0 && <><ul className="text-sm" aria-label="Aggregate results">{step.values.slice(0, 30).map((value, i) =>
                <li key={i}>{value.entity_id || 'Aggregate'} · {value.metric_type}: {formatValue(value)}</li>)}</ul>
                {step.values.length > 30 && <p className="text-sm">Additional aggregate values are stored in the run evidence.</p>}</>}
        </li>)}</ol>
      </section>}
      {visibleRun?.report_html && <iframe title={`Agent report for ${runPeriod}`} sandbox="" referrerPolicy="no-referrer" srcDoc={visibleRun.report_html} className="mt-4 min-h-[48rem] w-full border-0" />}
    {liveForCurrent && liveTrace.length > 0 && <p className="mt-3" role="status">{liveTrace.length} aggregate tool {liveTrace.length === 1 ? 'call' : 'calls'} received.</p>}
  </section>;
}
