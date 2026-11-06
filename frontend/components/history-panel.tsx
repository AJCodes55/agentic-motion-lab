'use client';

import { useState } from 'react';
import WheelButton from './wheel-button';

type Entry = { report_id: string; report_kind: 'baseline' | 'agent' | 'adhoc'; status: string; period: { year: number; month: number } };
const monthLabel = (entry: Entry) => `${new Intl.DateTimeFormat('en-US', { month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2000, entry.period.month - 1)))} ${entry.period.year}`;
const kindLabel = { baseline: 'Baseline', agent: 'Agent', adhoc: 'Ad hoc' };

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
      if (!Array.isArray(body.data?.reports) || !body.data.reports.every((entry: Entry) => typeof entry.report_id === 'string' && typeof entry.status === 'string' && ['baseline', 'agent', 'adhoc'].includes(entry.report_kind) && Number.isInteger(entry.period?.year) && entry.period.year >= 1 && entry.period.year <= 9999 && Number.isInteger(entry.period?.month) && entry.period.month >= 1 && entry.period.month <= 12)) throw new Error('History service returned an invalid response. Retry.');
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

  return <section id="history" aria-labelledby="history-heading" className="panel mt-6">
    <h2 id="history-heading">Report history</h2>
    <p className="mt-2 text-sm text-slate-700">Open a saved report with its original dataset evidence, even after a corrected upload.</p>
    <WheelButton type="button" className="mt-4" disabled={loading} onAction={refresh}>Refresh report history</WheelButton>
    {reports === null && !loading && <p className="mt-3">Refresh history to browse saved reports.</p>}
    {loading && <p role="status">Loading archived reports…</p>}
    {error && <p role="alert" className="mt-3">{error}</p>}
    {reports?.length === 0 && <p className="mt-3">No archived reports yet.</p>}
    {reports && reports.length > 0 && <ul className="mt-3 divide-y divide-slate-200">{reports.map(entry => <li className="flex flex-wrap items-baseline gap-x-3 py-1" key={`${entry.report_kind}-${entry.report_id}`}><WheelButton type="button" className="report-title" disabled={loading} onAction={() => open(entry)}>{monthLabel(entry)} — {kindLabel[entry.report_kind]} report</WheelButton> <span className="text-sm capitalize text-slate-600">{entry.status}</span></li>)}</ul>}
    {archive && <p role="status" className="mt-3">Archived report ready with its original saved evidence.</p>}
    {archive && <iframe title={`Archived report ${archive.id}`} sandbox="" referrerPolicy="no-referrer" srcDoc={archive.html} className="mt-4 min-h-[36rem] w-full border-0" />}
  </section>;
}
