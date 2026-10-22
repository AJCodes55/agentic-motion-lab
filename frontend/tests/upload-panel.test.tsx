import { afterEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import UploadPanel from '../components/upload-panel';
afterEach(()=>vi.unstubAllGlobals());
const dataset={period:{year:2026,month:2},version_id:'v1',sha256:'a'.repeat(64)};
const quality={source_rows:10,valid_rows:9,excluded_rows:1,candidate_rows:0,source_filenames:['month.csv'],per_csv_parsed_counts:[10]};
function mocks(result:unknown){vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url)=>({ok:true,json:async()=>({success:true,data: String(url)==='/api/periods'?{periods:[dataset]}:result})})));}
test('uploads a file and shows real quality and available version',async()=>{
 mocks({results:[{period:dataset.period,status:'accepted',dataset,quality,message:'Activated'}]});
 render(<UploadPanel period="2026-02" onBusy={()=>{}}/>);
 fireEvent.change(screen.getByLabelText('Choose data files'),{target:{files:[new File(['a'],'month.csv')]}});
 fireEvent.click(screen.getByRole('button',{name:'Upload selected files'}));
 expect(await screen.findByText('Activated')).toBeInTheDocument();
 expect(screen.getByText('Valid trips: 9')).toBeInTheDocument();
 expect(await screen.findByText(/2026-02 · version v1/)).toBeInTheDocument();
});
test('rejected correction preserves previous version and exposes candidate rows',async()=>{
 mocks({results:[{period:dataset.period,status:'rejected',dataset:null,quality:{...quality,valid_rows:0,candidate_rows:9,rejection_reason:'Wrong month',stopped_stage:'month'},message:'Rejected'}]});
 render(<UploadPanel period="2026-02" onBusy={()=>{}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Fetch public Citi Bike data'}));
 expect(await screen.findByText('Previous active version, if any, is preserved.')).toBeInTheDocument();
 expect(screen.getByText('Candidate rows, not accepted trips: 9')).toBeInTheDocument();
 expect(await screen.findByText(/2026-02 · version v1/)).toBeInTheDocument();
});
test('requires explicit month for fetch and validates file limits',async()=>{
 mocks({results:[]});render(<UploadPanel period="" onBusy={()=>{}}/>);
 expect(screen.getByRole('button',{name:'Fetch public Citi Bike data'})).toBeDisabled();
 const file=new File(['x'],'big.csv');Object.defineProperty(file,'size',{value:25_000_001});
 fireEvent.change(screen.getByLabelText('Choose data files'),{target:{files:[file]}});
 expect(screen.getByRole('alert')).toHaveTextContent('Limit: 25 MB per file and 50 MB total.');
 await screen.findByText(/2026-02 · version v1/);
});
test('shows service errors and allows retry',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));
 render(<UploadPanel period="2026-02" onBusy={()=>{}}/>);
 expect(await screen.findByText('Available months could not be loaded.')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Fetch public Citi Bike data'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('offline');
 mocks({results:[]});fireEvent.click(screen.getByRole('button',{name:'Refresh available months'}));
 expect(await screen.findByText(/2026-02 · version v1/)).toBeInTheDocument();
});
test('renders partial success and source coverage without private mapping dictionaries',async()=>{
 mocks({results:[{period:null,status:'rejected',dataset:null,quality:{...quality,valid_rows:0,candidate_rows:9},message:'Bad file'},{period:dataset.period,status:'accepted',dataset,quality,message:'Good file'}]});
 render(<UploadPanel period="2026-02" onBusy={()=>{}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Fetch public Citi Bike data'}));
 expect(await screen.findByText('Good file')).toBeInTheDocument();expect(screen.getByText('Bad file')).toBeInTheDocument();expect(screen.getAllByText('month.csv: 10 parsed rows')).toHaveLength(2);
});
test('handles HTTP rejection without claiming activation',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({success:false,error:{message:'Busy. Retry later.'}})}));
 render(<UploadPanel period="2026-02" onBusy={()=>{}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Fetch public Citi Bike data'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Busy. Retry later.');
});
