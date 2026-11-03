export type TraceEvent = {
  sequence: number;
  stage: string;
  operation: string;
  status: 'started' | 'success' | 'failed';
  source: 'application' | 'model' | 'tool';
  summary: string;
  inputs?: unknown;
  output?: unknown;
};

export type QueryTrace = { command: string; period: string; events: TraceEvent[]; error: string; incomplete: boolean };

export function isTraceEvent(value: unknown): value is TraceEvent {
  if (!value || typeof value !== 'object') return false;
  const event = value as Record<string, unknown>;
  return Number.isSafeInteger(event.sequence) && Number(event.sequence) > 0
    && typeof event.stage === 'string' && typeof event.operation === 'string' && typeof event.summary === 'string'
    && typeof event.status === 'string' && ['started', 'success', 'failed'].includes(event.status)
    && typeof event.source === 'string' && ['application', 'model', 'tool'].includes(event.source);
}

const sources = { application: 'Application rule', model: 'Model', tool: 'Tool' };
const statuses = { started: 'Started', success: 'Success', failed: 'Failed' };

function Payload({ label, value }: { label: string; value: unknown }) {
  return <details className="mt-3 rounded border border-slate-300 bg-white p-3">
    <summary className="cursor-pointer font-medium">{label}</summary>
    <pre tabIndex={0} aria-label={label} className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(value, null, 2)}</pre>
  </details>;
}

export default function TracePanel({ trace }: { trace: QueryTrace }) {
  return <section id="trace" aria-labelledby="trace-heading" className="panel mt-6 min-w-0">
    <h2 id="trace-heading">Trace</h2>
    <details className="trace-disclosure">
      <summary><span className="trace-show-more">Show more</span><span className="trace-show-less">Show less</span></summary>
    <p className="mt-2 break-words"><strong>Submitted query:</strong> {trace.command}</p>
    <p className="text-sm text-slate-700">Reporting month: {trace.period} · Current session only</p>
    <p className="mt-2 text-sm text-slate-700">Recorded decisions and execution results. Explanations identify their source; private model reasoning is unavailable.</p>
    {trace.incomplete && <p className="mt-3 font-medium text-amber-900">Trace incomplete. Only the steps received before the request ended are available.</p>}
    {trace.error && <p className="mt-2 text-red-800">{trace.error}</p>}
    {trace.events.length === 0 && <p className="mt-3">No detailed trace events were received.</p>}
    <ol aria-label="Query trajectory" className="mt-4 space-y-3">
      {trace.events.map(event => <li key={event.sequence} className="min-w-0 rounded border border-slate-300 bg-slate-50 p-4">
        <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
          <strong className="break-all">{event.sequence}. {event.operation}</strong>
          <span className={event.status === 'failed' ? 'font-semibold text-red-800' : 'font-medium text-slate-700'}>{statuses[event.status]}</span>
        </p>
        <p className="mt-1 text-xs text-slate-700">{sources[event.source]} · {event.stage}</p>
        <p className="mt-2 break-words">{event.summary}</p>
        {event.inputs !== undefined && <Payload label="Inputs" value={event.inputs} />}
        {event.output !== undefined && <Payload label="Output" value={event.output} />}
      </li>)}
    </ol>
    </details>
  </section>;
}
