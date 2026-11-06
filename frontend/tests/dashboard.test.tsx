import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, afterEach, expect, test, vi } from 'vitest';
import Dashboard from '../components/dashboard';
const healthy=async()=>({ok:true,json:async()=>({success:true,data:{status:'ok',service:'citibike-analytics'},error:null})} as Response);
beforeEach(() => vi.stubGlobal('fetch', vi.fn().mockImplementation(healthy)));
afterEach(() => vi.unstubAllGlobals());
test('only the fetch button wheel turns during public retrieval', async () => {
 let finish!: (response: Response) => void;
 vi.mocked(fetch).mockImplementation(async url => url === '/api/ingestions/fetch'
  ? new Promise<Response>(resolve => { finish = resolve; }) : healthy());
 render(<Dashboard />);
 expect(screen.getByRole('heading', {level:1}).closest('header')?.querySelector('svg')).toBeNull();
 const pageWheel = screen.getByTestId('mobility-wheel-page');
 const fetchButton = screen.getByRole('button', {name:'Fetch public Citi Bike data'});
 const fetchWheel = fetchButton.querySelector('svg')!;
 const agentWheel = screen.getByRole('button', {name:'Run agent analysis'}).querySelector('svg')!;
 expect(fetchWheel).toHaveAttribute('data-active', 'false');
 expect(fetchWheel).toHaveAttribute('aria-hidden', 'true');
 expect(screen.queryByRole('button', {name:/Pause wheel animation/})).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Reporting month'), {target:{value:'2026-02'}});
 fireEvent.click(fetchButton);
 await waitFor(() => expect(fetchWheel).toHaveAttribute('data-active', 'true'));
 expect(agentWheel).toHaveAttribute('data-active', 'false');
 expect(pageWheel).toHaveAttribute('data-active', 'false');
 expect(screen.getByText('Validating and loading data…')).toBeInTheDocument();
 finish({ok:false,json:async()=>({success:false,error:{message:'Fetch failed.'}})} as Response);
 await screen.findByText('Fetch failed.');
 expect(fetchWheel).toHaveAttribute('data-active', 'false');
});
test('wheel stops after an active agent stream fails', async () => {
 let stream!: ReadableStreamDefaultController<Uint8Array>;
 vi.mocked(fetch).mockImplementation(async url => url === '/api/agent-runs/stream'
  ? {ok:true,body:new ReadableStream<Uint8Array>({start(controller) { stream = controller; }})} as Response : healthy());
 render(<Dashboard />);
 fireEvent.change(screen.getByLabelText('Reporting month'), {target:{value:'2026-02'}});
 fireEvent.change(screen.getByLabelText('Analysis request'), {target:{value:'Show monthly trends'}});
 fireEvent.click(screen.getByRole('button', {name:'Run agent analysis'}));
 const wheel = screen.getByTestId('mobility-wheel-page');
 const agentWheel = screen.getByRole('button', {name:'Running agent analysis…'}).querySelector('svg')!;
 await waitFor(() => expect(wheel).toHaveAttribute('data-active', 'true'));
 expect(agentWheel).toHaveAttribute('data-active', 'true');
 expect(screen.getByRole('button', {name:'Fetch public Citi Bike data'}).querySelector('svg')).toHaveAttribute('data-active', 'false');
 stream.enqueue(new TextEncoder().encode(JSON.stringify({type:'error',message:'Agent unavailable.'})+'\n'));
 stream.close();
 await waitFor(() => expect(wheel).toHaveAttribute('data-active', 'false'));
 expect(screen.getByRole('button', {name:'Run agent analysis'})).toBeEnabled();
 expect(agentWheel).toHaveAttribute('data-active', 'false');
});
test('checks backend without inventing datasets or reports', async () => {
 render(<Dashboard />);
 expect(await screen.findByText('Backend connected')).toBeInTheDocument();
 expect(screen.getByLabelText('Reporting month')).toHaveValue('');
 expect(screen.getByRole('button', {name:'Generate baseline report'})).toBeDisabled();
 expect(screen.getByText('No report yet.')).toBeInTheDocument();
});
test('shows clear unavailable error and can retry', async () => {
 let failed=false;vi.mocked(fetch).mockImplementation(async(url)=>{if(url==='/api/health'&&!failed){failed=true;throw new Error('offline');}return healthy();});
 render(<Dashboard />);
 expect(await screen.findByText('Backend unavailable. Check the service and retry.')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Check connection'}));
 expect(await screen.findByText('Backend connected')).toBeInTheDocument();
});
test('validates one or two CSV/ZIP files and requires explicit month', async () => {
 render(<Dashboard />);
 const upload=screen.getByLabelText('Choose data files');
 fireEvent.change(upload,{target:{files:[new File(['a'],'one.csv')]}});
 expect(screen.getByText('one.csv')).toBeInTheDocument();
 fireEvent.change(upload,{target:{files:[new File(['a'],'one.csv'),new File(['a'],'two.zip')]}});
 expect(screen.getByText('two.zip')).toBeInTheDocument();
 fireEvent.change(upload,{target:{files:[new File(['a'],'a.csv'),new File(['a'],'b.csv'),new File(['a'],'c.csv')]}});
 expect(screen.getByRole('alert')).toHaveTextContent('Choose one or two files.');
 fireEvent.change(upload,{target:{files:[new File(['a'],'script.exe')]}});
 expect(screen.getByRole('alert')).toHaveTextContent('Only CSV and ZIP files are accepted.');
 fireEvent.change(screen.getByLabelText('Reporting month'),{target:{value:'2026-02'}});
 fireEvent.change(screen.getByLabelText('Analysis request'),{target:{value:'Show February trends'}});
 expect(screen.getByLabelText('Reporting month')).toHaveValue('2026-02');
 expect(screen.getByLabelText('Analysis request')).toHaveValue('Show February trends');
 await waitFor(()=>expect(screen.getByText('Backend connected')).toBeInTheDocument());
});
test('accepts drag and drop and rejects an empty selection', async () => {
 render(<Dashboard />);
 const area=screen.getByTestId('drop-area');
 fireEvent.dragOver(area);
 fireEvent.drop(area,{dataTransfer:{files:[new File(['a'],'drop.csv')]}});
 expect(screen.getByText('drop.csv')).toBeInTheDocument();
 fireEvent.drop(area,{dataTransfer:{files:[]}});
 expect(screen.getByRole('alert')).toHaveTextContent('Choose one or two files.');
 await screen.findByText('Backend connected');
});
test.each(['http','shape'])('shows unavailable for %s response',async(mode)=>{
 vi.mocked(fetch).mockImplementation(async(url)=>url==='/api/health'?{ok:mode!=='http',json:async()=>({success:false})} as Response:healthy());
 render(<Dashboard />);
 expect(await screen.findByText('Backend unavailable. Check the service and retry.')).toBeInTheDocument();
});
test('aborts an in-flight check when unmounted',async()=>{
 vi.mocked(fetch).mockImplementation((_url, options)=>new Promise((_resolve,reject)=>{
  options?.signal?.addEventListener('abort',()=>reject(new Error('aborted')));
 }));
 const {unmount}=render(<Dashboard />);
 await waitFor(()=>expect(vi.mocked(fetch).mock.calls.some(call=>call[0]==='/api/health')).toBe(true));
 const signal=vi.mocked(fetch).mock.calls.find(call=>call[0]==='/api/health')?.[1]?.signal;
 unmount();
 expect(signal?.aborted).toBe(true);
});
test('places retrieval beside analysis and agent results before comparison', async () => {
 render(<Dashboard />);
 const request = screen.getByRole('region', {name:'2. Describe the report'});
 const run = screen.getByRole('button', {name:'Run agent analysis'});
 const retrieve = screen.getByRole('button', {name:'Fetch public Citi Bike data'});
 expect(request).toContainElement(retrieve);
 expect(run.parentElement).toBe(retrieve.parentElement);
 expect(run.compareDocumentPosition(retrieve) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
 const agent = screen.getByRole('region', {name:'Agent analysis'});
 expect(agent.compareDocumentPosition(document.getElementById('comparison')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
 expect(retrieve).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Reporting month'),{target:{value:'2026-02'}});
 fireEvent.click(retrieve);
 await waitFor(()=>expect(vi.mocked(fetch).mock.calls.some(call=>call[0]==='/api/ingestions/fetch')).toBe(true));
 await screen.findByText('Backend connected');
});


test('places a collapsed trace after report history', async () => {
 const result = {run_id:'trace-test',status:'refused',report_html:'',stages:[],trace:[]};
 vi.mocked(fetch).mockImplementation(async url => url === '/api/agent-runs/stream' ? {ok:true,body:new ReadableStream({start(controller) {
  controller.enqueue(new TextEncoder().encode(JSON.stringify({type:'result',data:result})+'\n')); controller.close();
 }})} as Response : healthy());
 render(<Dashboard/>);
 fireEvent.change(screen.getByLabelText('Reporting month'), {target:{value:'2026-07'}});
 fireEvent.change(screen.getByLabelText('Analysis request'), {target:{value:'Test query'}});
 fireEvent.click(screen.getByRole('button', {name:'Run agent analysis'}));
 const trace = await screen.findByRole('region', {name:'Trace'});
 expect(document.querySelector('main')?.lastElementChild).toBe(trace);
 const disclosure = trace.querySelector('details')!;
 expect(disclosure).not.toHaveAttribute('open');
 fireEvent.click(screen.getByText('Show more'));
 expect(disclosure).toHaveAttribute('open');
 fireEvent.click(screen.getByText('Show less'));
 expect(disclosure).not.toHaveAttribute('open');
});
