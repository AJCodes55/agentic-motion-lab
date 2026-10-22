'use client';

import type { components } from '../src/generated/api';
import UploadPanel from './upload-panel';
import ReportPanel from './report-panel';
import AgentPanel from './agent-panel';
import { useEffect, useRef, useState } from 'react';

export default function Dashboard() {
  const activeCheck = useRef<AbortController | null>(null);
  const [connection, setConnection] = useState('Checking backend…');
  const [checking, setChecking] = useState(true);
  const [ingesting, setIngesting] = useState(false);
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

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8">
        <p className="text-sm font-semibold uppercase tracking-widest text-teal-800">Citi Bike · Jersey City</p>
        <h1 className="mt-2 text-3xl font-bold">Mobility reporting workspace</h1>
        <p className="mt-3 text-slate-700">Upload monthly data or fetch it from public Citi Bike S3.</p>
      </header>
      <section aria-labelledby="service-heading" className="panel mb-6 flex flex-wrap items-center justify-between gap-4">
        <div><h2 id="service-heading">Service connection</h2><p role="status" aria-live="polite">{connection}</p></div>
        <button type="button" onClick={() => { setChecking(true); setConnection('Checking backend…'); void checkConnection(); }} disabled={checking}>Check connection</button>
      </section>
      <div className="grid gap-6 md:grid-cols-2">
        <UploadPanel period={period} onBusy={setIngesting} />
        <section aria-labelledby="request-heading" className="panel">
          <h2 id="request-heading">2. Describe the report</h2>
          <label htmlFor="period" className="mt-4 block font-medium">Reporting month</label>
          <input id="period" type="month" required value={period} onChange={event => setPeriod(event.target.value)} aria-describedby="period-help" />
          <p id="period-help" className="mt-1 text-sm text-slate-700">Choose a month explicitly for public retrieval and baseline reports.</p>
          <label htmlFor="command" className="mt-4 block font-medium">Analysis request</label>
          <textarea aria-describedby="command-help" id="command" value={command} onChange={event => setCommand(event.target.value)} rows={3} placeholder="Describe the metrics and stations to explore" maxLength={2000} />
          <p id="command-help" className="mt-2 text-sm text-slate-700">Ask the agent to investigate verified monthly or station trends.</p>
        </section>
      </div>
      <AgentPanel period={period} command={command} busy={ingesting} />
      <ReportPanel period={period} busy={ingesting} />
    </main>
  );
}
