'use client';

import { useState } from 'react';

type Choice = { station_id: string; station_name: string };
type Result = { status: 'success' | 'needs_station_selection' | 'refused'; message: string; html?: string; station_choices?: Choice[] };
type Request = { period: { year: number; month: number }; metric: string; station_query?: string; station_id?: string; comparison: boolean; chart: boolean };

export default function AdhocPanel({ period, busy }: { period: string; busy: boolean }) {
  const [metric, setMetric] = useState('total_trips');
  const [station, setStation] = useState('');
  const [comparison, setComparison] = useState(false);
  const [chart, setChart] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [requestKey, setRequestKey] = useState('');
  const [pending, setPending] = useState<Request | null>(null);
  const contextKey = JSON.stringify({ period, metric, station, comparison, chart });
  const visible = requestKey === contextKey;
  const valid = /^\d{4}-(0[1-9]|1[0-2])$/.test(period) && (metric !== 'station_starts' || !!station.trim());

  async function submit(stationId?: string) {
    const [year, month] = period.split('-').map(Number);
    const request: Request = stationId && pending
      ? { ...pending, station_id: stationId }
      : { period: { year, month }, metric, ...(metric === 'station_starts' && station.trim() ? { station_query: station.trim() } : {}), comparison: metric === 'station_starts' && comparison, chart };
    setRunning(true); setError(''); setResult(null); setRequestKey(contextKey); setPending(request);
    try {
      const response = await fetch('/api/adhoc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal: AbortSignal.timeout(120_000) });
      const body = await response.json();
      if (!response.ok || body.success !== true) throw new Error(body.error?.message || 'Supported query failed. Retry.');
      const data = body.data;
      if (!data || !['success', 'needs_station_selection', 'refused'].includes(data.status) || typeof data.message !== 'string'
        || (data.status === 'success' && (typeof data.html !== 'string' || !data.html.trim()))
        || (data.status === 'needs_station_selection' && (!Array.isArray(data.station_choices) || !data.station_choices.length || !data.station_choices.every((choice: Choice) => typeof choice.station_id === 'string' && typeof choice.station_name === 'string')))) {
        throw new Error('Query service returned an invalid response. Retry.');
      }
      setResult(data);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Query service unavailable. Retry.'); }
    finally { setRunning(false); }
  }

  return <section aria-labelledby="adhoc-heading" className="panel mt-6">
    <h2 id="adhoc-heading">Supported queries</h2>
    <p className="mt-2 text-sm text-slate-700">Choose a metric for the selected reporting month. Each request includes its own month and station; comparisons use the previous month.</p>
    <label htmlFor="adhoc-metric" className="mt-4 block font-medium">Supported metric</label>
    <select id="adhoc-metric" value={metric} onChange={event => setMetric(event.target.value)}>
      <option value="total_trips">Total trips</option><option value="member_share">Member share</option><option value="fleet_share">Fleet share</option><option value="average_duration">Average duration</option><option value="station_starts">Station starts</option>
    </select>
    <label htmlFor="adhoc-station" className="mt-4 block font-medium">Station name or ID (optional)</label>
    <input id="adhoc-station" value={station} disabled={metric !== 'station_starts'} maxLength={500} onChange={event => setStation(event.target.value)} aria-describedby="adhoc-station-help" />
    <p id="adhoc-station-help" className="text-sm">Required for station starts. Ambiguous names require a station selection.</p>
    <label className="mt-3 block"><input type="checkbox" disabled={metric !== 'station_starts'} checked={metric === 'station_starts' && comparison} onChange={event => setComparison(event.target.checked)} /> Compare with previous month</label>
    <label className="mt-3 block"><input type="checkbox" checked={chart} onChange={event => setChart(event.target.checked)} /> Include chart</label>
    <button type="button" className="mt-4" disabled={!valid || busy || running} onClick={() => void submit()}>{running ? 'Running supported query…' : 'Run supported query'}</button>
    {visible && error && <p role="alert" className="mt-3">{error}</p>}
    {visible && result && <><p role="status" className="mt-3">{result.message}</p>
      {result.status === 'needs_station_selection' && <ul aria-label="Matching stations">{result.station_choices?.map(choice => <li key={choice.station_id}><button type="button" disabled={busy || running} onClick={() => void submit(choice.station_id)}>{choice.station_name} ({choice.station_id})</button></li>)}</ul>}
      {result.status === 'success' && <iframe title={`Supported query report for ${period}`} sandbox="" referrerPolicy="no-referrer" srcDoc={result.html} className="mt-4 min-h-[36rem] w-full border-0" />}
    </>}
  </section>;
}
