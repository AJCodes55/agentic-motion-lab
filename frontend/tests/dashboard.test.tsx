import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, afterEach, expect, test, vi } from 'vitest';
import Dashboard from '../components/dashboard';
const healthy=async()=>({ok:true,json:async()=>({success:true,data:{status:'ok',service:'citibike-analytics'},error:null})} as Response);
beforeEach(() => vi.stubGlobal('fetch', vi.fn().mockImplementation(healthy)));
afterEach(() => vi.unstubAllGlobals());
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
