'use client';
import { useEffect, useState } from 'react';
import type { components } from '../src/generated/api';
type Dataset = components['schemas']['DatasetReference'];
type Result = components['schemas']['MonthIngestionResult'];
const monthLabel = (period: {year:number;month:number}) => `${period.year}-${String(period.month).padStart(2,'0')}`;
const exclusions = ['invalid_timestamp_rows','outside_month_rows','duplicate_rows','missing_station_rows','invalid_duration_rows','unknown_member_rows','unknown_bike_rows'] as const;

export default function UploadPanel({period,onBusy}:{period:string;onBusy:(busy:boolean)=>void}) {
  const [files,setFiles]=useState<File[]>([]);
  const [error,setError]=useState('');
  const [periodError,setPeriodError]=useState('');
  const [periods,setPeriods]=useState<Dataset[]>([]);
  const [results,setResults]=useState<Result[]>([]);
  const [busy,setBusy]=useState(false);
  async function loadPeriods(signal?:AbortSignal) {
    try {
      const response=await fetch('/api/periods',{cache:'no-store',signal});
      const body=await response.json();
      if(!response.ok || !body.success || !Array.isArray(body.data?.periods)) throw new Error('Unavailable');
      if(signal?.aborted) return;
      setPeriods(body.data.periods);setPeriodError('');
    } catch { if(!signal?.aborted) setPeriodError('Available months could not be loaded.'); }
  }
  useEffect(()=>{const controller=new AbortController();const timer=setTimeout(()=>void loadPeriods(controller.signal),0);return()=>{clearTimeout(timer);controller.abort();};},[]);
  function chooseFiles(selected:FileList|null) {
    const next=Array.from(selected??[]);setFiles([]);
    if(next.length<1||next.length>2){setError('Choose one or two files.');return;}
    if(next.some(file=>!/\.(csv|zip)$/i.test(file.name))){setError('Only CSV and ZIP files are accepted.');return;}
    if(next.some(file=>file.size>25_000_000)||next.reduce((total,file)=>total+file.size,0)>50_000_000){setError('Limit: 25 MB per file and 50 MB total.');return;}
    setError('');setFiles(next);
  }
  async function ingest(source:'upload'|'fetch') {
    setBusy(true);onBusy(true);setError('');setResults([]);
    try {
      const form=new FormData();files.forEach(file=>form.append('files',file));
      const [year,month]=period.split('-').map(Number);
      const response=await fetch(source==='upload'?'/api/ingestions':'/api/ingestions/fetch',source==='upload'?{method:'POST',body:form}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({period:{year,month}})});
      const body=await response.json();
      if(!response.ok||!body.success||!Array.isArray(body.data?.results)) throw new Error(body.error?.message || 'Ingestion failed. Retry after checking the data service.');
      setResults(body.data.results);await loadPeriods();
    } catch(error) {setError(error instanceof Error?error.message:'Ingestion failed.');}
    finally {setBusy(false);onBusy(false);}
  }
  return <section aria-labelledby="data-heading" className="panel">
    <h2 id="data-heading">1. Select data</h2>
    <div data-testid="drop-area" className="my-4 rounded-lg border-2 border-dashed border-slate-400 p-5" onDragOver={event=>event.preventDefault()} onDrop={event=>{event.preventDefault();if(!busy)chooseFiles(event.dataTransfer.files);}}>
      <label htmlFor="data-files" className="block font-medium">Choose data files</label>
      <p id="upload-help" className="my-2 text-sm text-slate-700">Drop or choose one or two CSV/ZIP files. Maximum 25 MB per file, 50 MB total. Server validates all limits.</p>
      <input id="data-files" type="file" accept=".csv,.zip" multiple disabled={busy} aria-describedby="upload-help" onChange={event=>chooseFiles(event.target.files)}/>
    </div>
    {files.length>0&&<ul aria-label="Selected files">{files.map((file,index)=><li key={`${file.name}-${index}`}>{file.name}</li>)}</ul>}
    <button type="button" disabled={busy||files.length===0} onClick={()=>void ingest('upload')}>Upload selected files</button>
    <p className="my-3 text-sm">Or fetch the explicitly selected reporting month from public Citi Bike S3.</p>
    <button type="button" disabled={busy||!period} onClick={()=>void ingest('fetch')}>Fetch public Citi Bike data</button>
    {busy&&<p aria-live="polite">Validating and loading data…</p>}
    {error&&<p role="alert" className="text-red-800">{error}</p>}
    {results.map((result,index)=><article className="mt-4 border-t pt-3" key={index} aria-label={`Ingestion result ${index+1}`}>
      <h3>{result.period?monthLabel(result.period):'Unidentified month'}: {result.status}</h3>
      <p>{result.message}</p>
      {result.status==='rejected'&&<p>Previous active version, if any, is preserved.</p>}
      <p>Source rows: {result.quality.source_rows}</p><p>Valid trips: {result.quality.valid_rows}</p><p>Excluded rows: {result.quality.excluded_rows}</p>
      <p>Month threshold denominator: {result.quality.month_threshold_denominator}</p><p>Station threshold denominator: {result.quality.station_threshold_denominator}</p>
      {result.status==='rejected'&&<><p>Candidate rows, not accepted trips: {result.quality.candidate_rows}</p><p>Stopped stage: {result.quality.stopped_stage}</p><p>{result.quality.rejection_reason}</p></>}
      <ul aria-label="Source coverage">{result.quality.source_filenames.map((name,i)=><li key={i}>{name}: {result.quality.per_csv_parsed_counts[i]} parsed rows</li>)}</ul>
      <dl>{exclusions.map(key=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{result.quality[key]}</dd></div>)}</dl>
      {result.quality.source_labels_truncated&&<p>Long source names are shortened for display.</p>}
    </article>)}
    <h3 className="mt-4 font-semibold">Available months</h3>
    {periodError?<><p>{periodError}</p><button type="button" disabled={busy} onClick={()=>void loadPeriods()}>Refresh available months</button></>:periods.length===0?<p>No accepted datasets available.</p>:<ul>{periods.map(dataset=><li key={dataset.version_id}>{monthLabel(dataset.period)} · version {dataset.version_id}</li>)}</ul>}
  </section>;
}
