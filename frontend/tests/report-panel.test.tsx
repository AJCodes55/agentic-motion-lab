import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import ReportPanel from '../components/report-panel';
afterEach(()=>vi.unstubAllGlobals());
test('posts explicit period and displays isolated HTML',async()=>{
 const fetcher=vi.fn().mockResolvedValue({ok:true,json:async()=>({success:true,data:{html:'<h1>Monthly report</h1>'}})});vi.stubGlobal('fetch',fetcher);
 const {rerender}=render(<ReportPanel period="" busy={false}/>);
 expect(screen.getByRole('button',{name:'Generate baseline report'})).toBeDisabled();
 rerender(<ReportPanel period="2026-01" busy={false}/>);
 fireEvent.click(screen.getByRole('button',{name:'Generate baseline report'}));
 await waitFor(()=>expect(screen.getByTitle('Baseline report for 2026-01')).toHaveAttribute('srcdoc','<h1>Monthly report</h1>'));
 expect(screen.getByTitle('Baseline report for 2026-01')).toHaveAttribute('sandbox','');
 expect(fetcher).toHaveBeenCalledWith('/api/reports',expect.objectContaining({body:'{"period":{"year":2026,"month":1}}'}));
});
test('shows backend errors and permits retry',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({success:false,error:{message:'No dataset for selected month.'}})}));
 render(<ReportPanel period="2026-01" busy={false}/>);fireEvent.click(screen.getByRole('button',{name:'Generate baseline report'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('No dataset for selected month.');
 expect(screen.getByRole('button',{name:'Generate baseline report'})).toBeEnabled();
});
test('disables generation during ingestion',()=>{
 render(<ReportPanel period="2026-01" busy/>);expect(screen.getByRole('button',{name:'Generate baseline report'})).toBeDisabled();
});
test('rejects malformed report responses',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({success:true,data:{html:42}})}));
 render(<ReportPanel period="2026-01" busy={false}/>);fireEvent.click(screen.getByRole('button',{name:'Generate baseline report'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('invalid report');
 expect(screen.queryByTitle('Baseline report for 2026-01')).not.toBeInTheDocument();
});
test('shows running state while request is pending',()=>{
 vi.stubGlobal('fetch',vi.fn().mockImplementation(()=>new Promise(()=>{})));
 render(<ReportPanel period="2026-01" busy={false}/>);fireEvent.click(screen.getByRole('button',{name:'Generate baseline report'}));
 expect(screen.getByRole('status')).toHaveTextContent('Computing verified monthly metrics');
 expect(screen.getByRole('button',{name:'Generating baseline report…'})).toBeDisabled();
});
