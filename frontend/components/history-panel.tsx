'use client';

import { useState } from 'react';

type Entry = { report_id: string; report_kind: 'baseline' | 'agent' | 'adhoc'; status: string; period: { year: number; month: number } };
const monthLabel = (entry: Entry) => `${entry.period.year}-${String(entry.period.month).padStart(2, '0')}`;

export default function HistoryPanel() {
  const [reports, setReports] = useState<Entry[] | null>(null);
  const [archive, setArchive] = useState<{ id: string; html: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function refresh() {
    setLoading(true); setError('');
    try {
      const response = await fetch('/api/reports/history', { cache: 'no-store', signal: AbortSignal.timeout(30_000) });
      const body = await response.json();
      if (!response.ok || body.success !== true) throw new Error(body.error?.message || 'History unavailable. Retry.');
      if (!Array.isArray(body.data?.reports) || !body.data.reports.every((entry: Entry) => typeof entry.report_id === 'string' && typeof entry.status === 'string' && ['baseline', 'agent', 'adhoc'].includes(entry.report_kind) && Number.isInteger(entry.period?.year) && Number.isInteger(entry.period?.month) && entry.period.month >= 1 && entry.period.month <= 12)) throw new Error('History service returned an invalid response. Retry.');
      setReports(body.data.reports);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'History unavailable. Retry.'); }
    finally { setLoading(false); }
  }

  async function open(entry: Entry) {
    setLoading(true); setError(''); setArchive(null);
    try {
      const response = await fetch(`/api/reports/history/${encodeURIComponent(entry.report_id)}?kind=${entry.report_kind}`, { cache: 'no-store', signal: AbortSignal.timeout(30_000) });
      const body = await response.json();
      if (!response.ok || body.success !== true) throw new Error(body.error?.message || 'Archived report unavailable. Retry.');
      if (typeof body.data?.html !== 'string' || !body.data.html.trim()) throw new Error('Archive service returned an invalid report. Retry.');
      setArchive({ id: entry.report_id, html: body.data.html });
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Archived report unavailable. Retry.'); }
    finally { setLoading(false); }
  }

  return <section aria-labelledby="history-heading" className="panel mt-6">
    <h2 id="history-heading">Report history</h2>
    <p className="mt-2 text-sm text-slate-700">Open a saved report with its original dataset evidence, even after a corrected upload.</p>
    <button type="button" className="mt-4" disabled={loading} onClick={() => void refresh()}>Refresh report history</button>
    {loading && <p role="status">Loading archived reports…</p>}
    {error && <p role="alert" className="mt-3">{error}</p>}
    {reports?.length === 0 && <p className="mt-3">No archived reports yet.</p>}
    {reports && reports.length > 0 && <ul className="mt-3 space-y-2">{reports.map(entry => <li key={`${entry.report_kind}-${entry.report_id}`}><button type="button" disabled={loading} onClick={() => void open(entry)}>Open {entry.report_kind} report for {monthLabel(entry)} ({entry.report_id})</button> <span>{entry.status}</span></li>)}</ul>}
    {archive && <iframe title={`Archived report ${archive.id}`} sandbox="" referrerPolicy="no-referrer" srcDoc={archive.html} className="mt-4 min-h-[36rem] w-full border-0" />}
  </section>;
}
