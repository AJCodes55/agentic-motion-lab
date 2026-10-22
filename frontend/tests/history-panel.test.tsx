import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import HistoryPanel from '../components/history-panel';
afterEach(()=>vi.unstubAllGlobals());
test('browses and opens an immutable archived report',async()=>{
 const fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({success:true,data:{reports:[{report_id:'abc',report_kind:'adhoc',status:'complete',period:{year:2026,month:2}}]}})}).mockResolvedValueOnce({ok:true,json:async()=>({success:true,data:{html:'<h1>Archive</h1>'}})});
 vi.stubGlobal('fetch',fetcher);render(<HistoryPanel/>);
 fireEvent.click(screen.getByRole('button',{name:'Refresh report history'}));
 fireEvent.click(await screen.findByRole('button',{name:'Open adhoc report for 2026-02 (abc)'}));
 expect(await screen.findByTitle('Archived report abc')).toHaveAttribute('srcdoc','<h1>Archive</h1>');
 expect(screen.getByTitle('Archived report abc')).toHaveAttribute('sandbox','');
 expect(fetcher.mock.calls[1][0]).toBe('/api/reports/history/abc?kind=adhoc');
});
test.each(['empty','failed','invalid','badarchive'])('handles %s history',async(mode)=>{
 const fetcher=vi.fn().mockResolvedValueOnce({ok:mode!=='failed',json:async()=>({success:mode!=='failed',data:{reports:mode==='empty'?[]:mode==='invalid'?42:[{report_id:'a',report_kind:'baseline',status:'complete',period:{year:2026,month:1}}]},error:{message:'Unavailable'}})}).mockResolvedValue({ok:true,json:async()=>({success:true,data:{html:4}})});
 vi.stubGlobal('fetch',fetcher);render(<HistoryPanel/>);fireEvent.click(screen.getByRole('button',{name:'Refresh report history'}));
 if(mode==='badarchive')fireEvent.click(await screen.findByRole('button',{name:/Open baseline/}));
 expect(await screen.findByText(mode==='empty'?'No archived reports yet.':mode==='failed'?'Unavailable':mode==='invalid'?'History service returned an invalid response. Retry.':'Archive service returned an invalid report. Retry.')).toBeInTheDocument();
});
test('rejects malformed status before rendering history', async () => {
 vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async()=>({success:true,data:{reports:[{report_id:'a',report_kind:'adhoc',status:{bad:true},period:{year:2026,month:2}}]}})}));
 render(<HistoryPanel/>);fireEvent.click(screen.getByRole('button',{name:'Refresh report history'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('History service returned an invalid response. Retry.');
});
