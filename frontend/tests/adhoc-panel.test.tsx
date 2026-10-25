import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import AdhocPanel from '../components/adhoc-panel';
afterEach(() => vi.unstubAllGlobals());
const reply = (data: unknown) => ({ ok: true, json: async () => ({ success: true, data }) });
test('requires month and station for station starts', () => {
 const { rerender } = render(<AdhocPanel period="" busy={false}/>);
 expect(screen.getByRole('button', {name:'Run supported query'})).toBeDisabled();
 rerender(<AdhocPanel period="2026-02" busy={false}/>);
 fireEvent.change(screen.getByLabelText('Supported metric'), {target:{value:'station_starts'}});
 expect(screen.getByRole('button', {name:'Run supported query'})).toBeDisabled();
});
test('resubmits the complete request on station selection and isolates HTML', async () => {
 const fetcher = vi.fn().mockResolvedValueOnce(reply({status:'needs_station_selection', message:'Choose a station.', station_choices:[{station_id:'A',station_name:'Park'},{station_id:'B',station_name:'Park'}]})).mockResolvedValueOnce(reply({status:'success',message:'Answer ready.',html:'<h1>Answer</h1>'}));
 vi.stubGlobal('fetch', fetcher);
 render(<AdhocPanel period="2026-02" busy={false}/>);
 fireEvent.change(screen.getByLabelText('Supported metric'), {target:{value:'station_starts'}});
 fireEvent.change(screen.getByLabelText('Station name or ID'), {target:{value:'Park'}});
 fireEvent.click(screen.getByLabelText('Compare with previous month'));
 fireEvent.click(screen.getByLabelText('Include chart'));
 fireEvent.click(screen.getByRole('button',{name:'Run supported query'}));
 fireEvent.click(await screen.findByRole('button',{name:'Park (A)'}));
 expect(await screen.findByTitle('Supported query report for 2026-02')).toHaveAttribute('sandbox','');
 expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({period:{year:2026,month:2},metric:'station_starts',station_query:'Park',station_id:'A',comparison:true,chart:true});
});
test.each(['refused','invalid','network'])('handles %s without fabricated report',async(mode)=>{
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async()=>{if(mode==='network')throw Error('Offline');return reply(mode==='refused'?{status:'refused',message:'Comparison data missing.'}:{status:'success',html:4});}));
 render(<AdhocPanel period="2026-02" busy={false}/>);
 fireEvent.click(screen.getByRole('button',{name:'Run supported query'}));
 await waitFor(()=>expect(screen.getByRole(mode==='refused'?'status':'alert')).toHaveTextContent(mode==='refused'?'Comparison data missing.':mode==='invalid'?'invalid response':'Offline'));
});
test('does not show prior request choices after context changes',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(reply({status:'needs_station_selection',message:'Choose a station.',station_choices:[{station_id:'A',station_name:'Park'}]})));
 const {rerender}=render(<AdhocPanel period="2026-02" busy={false}/>);
 fireEvent.click(screen.getByRole('button',{name:'Run supported query'}));
 await screen.findByRole('button',{name:'Park (A)'});
 rerender(<AdhocPanel period="2026-03" busy={false}/>);
 expect(screen.queryByRole('button',{name:'Park (A)'})).not.toBeInTheDocument();
});

test('omits station context when switching to an aggregate metric',async()=>{
 const fetcher=vi.fn().mockResolvedValue(reply({status:'success',message:'Ready',html:'<h1>Answer</h1>'}));vi.stubGlobal('fetch',fetcher);
 render(<AdhocPanel period="2026-02" busy={false}/>);
 fireEvent.change(screen.getByLabelText('Supported metric'),{target:{value:'station_starts'}});
 fireEvent.change(screen.getByLabelText('Station name or ID'),{target:{value:'Park'}});
 fireEvent.change(screen.getByLabelText('Supported metric'),{target:{value:'total_trips'}});
 expect(screen.getByLabelText('Station name or ID')).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Run supported query'}));
 await screen.findByTitle('Supported query report for 2026-02');
 expect(JSON.parse(fetcher.mock.calls[0][1].body)).not.toHaveProperty('station_query');
 expect(JSON.parse(fetcher.mock.calls[0][1].body).comparison).toBe(false);
});
