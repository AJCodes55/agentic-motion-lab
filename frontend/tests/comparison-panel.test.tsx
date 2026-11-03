import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import ComparisonPanel from '../components/comparison-panel';

afterEach(() => vi.unstubAllGlobals());
function install(fetcher: (...args: unknown[]) => unknown) {
 vi.stubGlobal('fetch', (url: string, ...options: unknown[]) => url === '/api/periods' ? Promise.resolve({ok:true,json:async()=>({success:true,data:{periods:[{period:{year:2026,month:1}},{period:{year:2026,month:2}}]}})}) : fetcher(url,...options));
}
async function clickStart() {const button=screen.getByRole('button',{name:'Run demo comparison'});await waitFor(()=>expect(button).toBeEnabled());fireEvent.click(button);}
const baseline = {monthly_totals:{'2026-01':100,'2026-02':80},top_stations:[{station_id:'001',station_name:'Park',ride_count:12}],inputs:[]};
const agent = {run_id:'run',status:'partial',period:{year:2026,month:2},datasets:[],report_html:'<h1>Baseline fallback</h1>',warning:'Narrative validation failed.',error_code:'ERR_UNGROUNDED_CLAIM',stages:[],trace:[],counters:{llm_calls:4,tool_calls:2,input_tokens:100,output_tokens:25}};
const result = {report_id:'report',period:{year:2026,month:2},datasets:[],baseline,agent,rows:[{month:'2026-01',python_total:100,agent_total:100,difference:0,status:'match'},{month:'2026-02',python_total:80,agent_total:null,difference:null,status:'unavailable'}],timing_seconds:{shared_preparation:1,python_calculation:0.1,agent_workflow:2},dollar_cost:null};
function startStream() {
 let controller:ReadableStreamDefaultController<Uint8Array>;
 const body=new ReadableStream<Uint8Array>({start(value){controller=value;}});
 const send=(event:object)=>controller.enqueue(new TextEncoder().encode(`${JSON.stringify(event)}\n`));
 return {response:{ok:true,body},send,close:()=>controller.close()};
}
test('requires explicit February selection and blocks ingestion',()=>{
 const {rerender}=render(<ComparisonPanel period="" busy={false}/>);
 expect(screen.getByRole('button',{name:'Run demo comparison'})).toBeDisabled();
 rerender(<ComparisonPanel period="2026-01" busy={false}/>);
 expect(screen.getByRole('button',{name:'Run demo comparison'})).toBeDisabled();
 rerender(<ComparisonPanel period="2026-02" busy={true}/>);
 expect(screen.getByRole('button',{name:'Run demo comparison'})).toBeDisabled();
});
test('shows early baseline, blocks duplicates, distinguishes partial and unavailable, sandboxes report',async()=>{
 const stream=startStream();const fetcher=vi.fn().mockResolvedValue(stream.response);install(fetcher);
 render(<ComparisonPanel period="2026-02" busy={false}/>);
 const button=screen.getByRole('button',{name:'Run demo comparison'});
 await waitFor(()=>expect(button).toBeEnabled());fireEvent.click(button);fireEvent.click(button);
 await waitFor(()=>expect(fetcher).toHaveBeenCalledOnce());
 expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({period:{year:2026,month:2}});
 await act(async()=>stream.send({type:'baseline',data:baseline}));
 expect(screen.getByText('Python baseline ready. Agent workflow in progress.')).toBeInTheDocument();
 expect(screen.getByText('Park (001): 12 starts')).toBeInTheDocument();
 await act(async()=>{stream.send({type:'result',data:result});stream.close();});
 expect(await screen.findByText('Agent analysis partial. Verified totals do not establish agent completion.')).toBeInTheDocument();
 expect(screen.getByRole('cell',{name:'Match'})).toBeInTheDocument();
 expect(screen.getAllByRole('cell',{name:'Unavailable'})).toHaveLength(3);
 expect(screen.getByTitle('Comparison agent report for 2026-02')).toHaveAttribute('sandbox','');
 expect(screen.getByText(/Input tokens: 100/)).toBeInTheDocument();
 expect(screen.getByText(/Dollar cost: unavailable/)).toBeInTheDocument();
});
test('suppresses results after month changes even if February is selected again',async()=>{
 const stream=startStream();install(vi.fn().mockResolvedValue(stream.response));
 const {rerender}=render(<ComparisonPanel period="2026-02" busy={false}/>);
 await clickStart();
 await waitFor(()=>expect(screen.getByRole('button',{name:'Running demo comparison…'})).toBeDisabled());
 rerender(<ComparisonPanel period="2026-01" busy={false}/>);
 rerender(<ComparisonPanel period="2026-02" busy={false}/>);
 await act(async()=>{stream.send({type:'baseline',data:baseline});stream.send({type:'result',data:result});stream.close();});
 expect(screen.queryByTitle('Comparison agent report for 2026-02')).not.toBeInTheDocument();
 expect(screen.queryByText('Park (001): 12 starts')).not.toBeInTheDocument();
});
test.each(['interrupted','error','invalid'])('keeps early baseline and reports %s stream',async(mode)=>{
 const stream=startStream();install(vi.fn().mockResolvedValue(stream.response));
 render(<ComparisonPanel period="2026-02" busy={false}/>);
 await clickStart();
 await waitFor(()=>expect(screen.getByRole('button',{name:'Running demo comparison…'})).toBeDisabled());
 await act(async()=>{stream.send({type:'baseline',data:baseline});if(mode==='error')stream.send({type:'error',message:'Both accepted months are required.'});if(mode==='invalid')stream.send({type:'result',data:{}});stream.close();});
 expect(await screen.findByRole('alert')).toBeInTheDocument();
 expect(screen.getByText('Park (001): 12 starts')).toBeInTheDocument();
 expect(screen.queryByTitle('Comparison agent report for 2026-02')).not.toBeInTheDocument();
});
test.each(['http','body'])('reports %s startup failure without inventing results',async(mode)=>{
 install(vi.fn().mockResolvedValue({ok:mode!=='http',body:null}));
 render(<ComparisonPanel period="2026-02" busy={false}/>);
 await clickStart();
 expect(await screen.findByRole('alert')).toHaveTextContent('Confirm both accepted months');
 expect(screen.queryByRole('table')).not.toBeInTheDocument();
});
test('old request settlement cannot clear a newer request',async()=>{
 const first=startStream();const second=startStream();
 const fetcher=vi.fn().mockResolvedValueOnce(first.response).mockResolvedValueOnce(second.response);install(fetcher);
 const {rerender}=render(<ComparisonPanel period="2026-02" busy={false}/>);
 await clickStart();
 await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(1));
 rerender(<ComparisonPanel period="2026-01" busy={false}/>);
 rerender(<ComparisonPanel period="2026-02" busy={false}/>);
 await clickStart();
 await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(2));
 await act(async()=>{first.send({type:'result',data:result});first.close();});
 expect(screen.getByRole('button',{name:'Running demo comparison…'})).toBeDisabled();
 expect(screen.queryByTitle('Comparison agent report for 2026-02')).not.toBeInTheDocument();
 await act(async()=>{second.send({type:'baseline',data:baseline});second.send({type:'result',data:result});second.close();});
 expect(await screen.findByTitle('Comparison agent report for 2026-02')).toBeInTheDocument();
});
test('renders progress and failed activity with explicit status, never as totals',async()=>{
 const stream=startStream();install(vi.fn().mockResolvedValue(stream.response));
 render(<ComparisonPanel period="2026-02" busy={false}/>);
 await clickStart();
 await waitFor(()=>expect(screen.getByRole('button',{name:'Running demo comparison…'})).toBeDisabled());
 await act(async()=>{stream.send({type:'baseline',data:baseline});stream.send({type:'stage',name:'Tool Execution',status:'complete'});stream.send({type:'tool',data:{tool_name:'compare_periods',status:'error',values:[]}});});
 expect(screen.getByRole('status')).toHaveTextContent('Tool Execution: complete');
 expect(screen.getByText('compare periods')).toBeInTheDocument();
 expect(screen.getAllByRole('cell',{name:'Unavailable'})).toHaveLength(6);
 await act(async()=>{stream.send({type:'error',message:'Agent workflow failed.'});stream.close();});
 expect(await screen.findByRole('alert')).toHaveTextContent('Agent workflow failed.');
});
