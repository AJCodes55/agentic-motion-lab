'use client';

import { useState } from 'react';

export default function ReportPanel({ period, busy }: { period: string; busy: boolean }) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState<{ period: string; html: string } | null>(null);
  const validPeriod = /^\d{4}-(0[1-9]|1[0-2])$/.test(period);

  async function generate() {
    setRunning(true); setError(''); setReport(null);
    const [year, month] = period.split('-').map(Number);
    try {
      const response = await fetch('/api/reports', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: { year, month } }), signal: AbortSignal.timeout(120_000),
      });
      const body = await response.json();
      if (!response.ok || body.success !== true) throw new Error(body.error?.message || 'Report generation failed. Retry.');
      if (typeof body.data?.html !== 'string' || !body.data.html.trim()) throw new Error('Report service returned an invalid report. Retry.');
      setReport({ period, html: body.data.html });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Report service unavailable. Retry.');
    } finally { setRunning(false); }
  }

  return <section aria-labelledby="report-heading" className="panel mt-6">
    <h2 id="report-heading">Report</h2>
    <p className="mt-2 text-sm text-slate-700">Generate the standard monthly baseline from the selected month’s active dataset. No AI calls are used.</p>
    <button type="button" className="mt-4" disabled={!validPeriod || busy || running} onClick={() => void generate()}>{running ? 'Generating baseline report…' : 'Generate baseline report'}</button>
    {running && <p role="status">Computing verified monthly metrics…</p>}
    {error && <p role="alert">{error}</p>}
    {report ? <><p className="mt-3">Report ready for {report.period}.</p><iframe title={`Baseline report for ${report.period}`} sandbox="" referrerPolicy="no-referrer" srcDoc={report.html} className="mt-4 min-h-[48rem] w-full border-0" /></> : <p className="mt-3">No report yet.</p>}
  </section>;
}
