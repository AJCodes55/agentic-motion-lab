'use client';

import type { components } from '../src/generated/api';
import { useEffect, useRef, useState } from 'react';

export default function Dashboard() {
  const activeCheck = useRef<AbortController | null>(null);
  const [connection, setConnection] = useState('Checking backend…');
  const [checking, setChecking] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState('');
  const [period, setPeriod] = useState('');
  const [command, setCommand] = useState('');

  async function checkConnection() {
    activeCheck.current?.abort();
    const controller = new AbortController();
    activeCheck.current = controller;
    try {
      const response = await fetch('/api/health', { cache: 'no-store', signal: controller.signal });
      const body: components['schemas']['ApiResponse_HealthData_'] = await response.json();
      if (!response.ok || body.success !== true || body.data?.status !== 'ok') throw new Error('Unavailable');
      if (!controller.signal.aborted) setConnection('Backend connected');
    } catch {
      if (!controller.signal.aborted) setConnection('Backend unavailable. Check the service and retry.');
    } finally {
      if (!controller.signal.aborted) setChecking(false);
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => void checkConnection(), 0);
    return () => { clearTimeout(timer); activeCheck.current?.abort(); };
  }, []);

  function chooseFiles(selected: FileList | null) {
    const next = Array.from(selected ?? []);
    setFiles([]);
    if (next.length < 1 || next.length > 2) { setError('Choose one or two files.'); return; }
    if (next.some(file => !/\.(csv|zip)$/i.test(file.name))) { setError('Only CSV and ZIP files are accepted.'); return; }
    setError('');
    setFiles(next);
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8">
        <p className="text-sm font-semibold uppercase tracking-widest text-teal-800">Citi Bike · Jersey City</p>
        <h1 className="mt-2 text-3xl font-bold">Mobility reporting workspace</h1>
        <p className="mt-3 text-slate-700">Application foundation. Data ingestion and analysis are coming in later phases.</p>
      </header>
      <section aria-labelledby="service-heading" className="panel mb-6 flex flex-wrap items-center justify-between gap-4">
        <div><h2 id="service-heading">Service connection</h2><p role="status" aria-live="polite">{connection}</p></div>
        <button type="button" onClick={() => { setChecking(true); setConnection('Checking backend…'); void checkConnection(); }} disabled={checking}>Check connection</button>
      </section>
      <div className="grid gap-6 md:grid-cols-2">
        <section aria-labelledby="data-heading" className="panel">
          <h2 id="data-heading">1. Select data</h2>
          <div data-testid="drop-area" className="my-4 rounded-lg border-2 border-dashed border-slate-400 p-5" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); chooseFiles(event.dataTransfer.files); }}>
            <label htmlFor="data-files" className="block font-medium">Choose data files</label>
            <p id="upload-help" className="my-2 text-sm text-slate-700">Drop or choose one or two CSV/ZIP files. Files stay in your browser; ingestion is not implemented yet.</p>
            <input id="data-files" type="file" accept=".csv,.zip" multiple aria-describedby="upload-help" onChange={event => chooseFiles(event.target.files)} />
          </div>
          {error && <p role="alert" className="text-red-800">{error}</p>}
          {files.length > 0 && <ul aria-label="Selected files">{files.map((file, index) => <li key={`${file.name}-${index}`}>{file.name}</li>)}</ul>}
          <p className="mt-4 text-sm text-slate-700">Public Citi Bike S3 retrieval will be available with ingestion.</p>
        </section>
        <section aria-labelledby="request-heading" className="panel">
          <h2 id="request-heading">2. Describe the report</h2>
          <label htmlFor="period" className="mt-4 block font-medium">Reporting month</label>
          <input id="period" type="month" required value={period} onChange={event => setPeriod(event.target.value)} aria-describedby="period-help" />
          <p id="period-help" className="mt-1 text-sm text-slate-700">Choose a month explicitly. Data availability is not yet checked.</p>
          <label htmlFor="command" className="mt-4 block font-medium">Analysis request</label>
          <textarea id="command" value={command} onChange={event => setCommand(event.target.value)} rows={3} placeholder="Describe the metrics and stations to explore" />
          <button type="button" disabled className="mt-4">Generate report</button>
          <p className="mt-2 text-sm text-slate-700">Report generation is not implemented yet.</p>
        </section>
      </div>
      <section aria-labelledby="progress-heading" className="panel mt-6"><h2 id="progress-heading">Progress</h2><p>No analysis is running.</p><ol className="mt-3 grid gap-2 sm:grid-cols-2"><li>Data Ingest: idle</li><li>Agent Planning: idle</li><li>Tool Execution: idle</li><li>Final Report Generation: idle</li></ol></section>
      <section aria-labelledby="report-heading" className="panel mt-6"><h2 id="report-heading">Report</h2><p>No report yet.</p><p className="text-sm text-slate-700">Verified results will appear here after analysis is implemented.</p></section>
    </main>
  );
}
