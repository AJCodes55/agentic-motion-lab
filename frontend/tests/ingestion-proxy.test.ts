// @vitest-environment node
import { afterEach, expect, test, vi } from 'vitest';
import { POST } from '../app/api/ingestions/route';
import { POST as generateReport } from '../app/api/reports/route';
import { POST as runAgent } from '../app/api/agent-runs/route';
import { GET } from '../app/api/periods/route';
import { POST as fetchMonth } from '../app/api/ingestions/fetch/route';
afterEach(()=>vi.unstubAllGlobals());
test('rejects oversized upload before forwarding',async()=>{
 const upstream=vi.fn();vi.stubGlobal('fetch',upstream);
 const response=await POST(new Request('http://local/api/ingestions',{method:'POST',headers:{'content-length':'51000001','content-type':'multipart/form-data; boundary=x'},body:'x'}));
 expect(response.status).toBe(413);expect(upstream).not.toHaveBeenCalled();
});
test('forwards upload only to configured backend',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({success:true,data:{results:[]}})));
 const response=await POST(new Request('http://local/api/ingestions',{method:'POST',headers:{'content-type':'multipart/form-data; boundary=x'},body:'x'}));
 expect(response.status).toBe(200);expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('/ingestions');
});
test('returns available periods without caching',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({success:true,data:{periods:[]}})));
 expect((await GET()).headers.get('cache-control')).toBe('no-store');
});
test('reports backend outage',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));
 expect((await GET()).status).toBe(503);
});
test('fetch month forwards JSON and preserves rejection status',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({success:false,error:{message:'Invalid month'}},{status:422})));
 expect((await fetchMonth(new Request('http://local',{method:'POST',headers:{'content-type':'application/json'},body:'{"period":{"year":2026,"month":2}}'}))).status).toBe(422);
});
test('rejects wrong content type',async()=>{
 expect((await POST(new Request('http://local',{method:'POST',body:'x'}))).status).toBe(415);
});
test('bounds actual streamed request bytes and cancels overflow',async()=>{
 const cancel=vi.fn();
 const body=new ReadableStream({start(controller){controller.enqueue(new Uint8Array(50_100_001));},cancel});
 const request=new Request('http://local',{method:'POST',headers:{'content-type':'multipart/form-data; boundary=x'},body,duplex:'half'} as RequestInit);
 expect((await POST(request)).status).toBe(413);expect(cancel).toHaveBeenCalled();
});
test.each(['<html>oops</html>','{}','x'.repeat(1_000_001)])('hides malformed upstream data',async(body)=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(body)));
 const response=await GET();expect(response.status).toBe(503);expect(await response.text()).not.toContain('<html>');
});
test('accepts a chunked JSON body with no content length',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({success:true,data:{results:[]}})));
 const response=await fetchMonth(new Request('http://local',{method:'POST',headers:{'content-type':'application/json'},body:'{}'}));
 expect(response.status).toBe(200);
});
test('times out a stalled incoming stream and cancels it',async()=>{
 vi.useFakeTimers();
 try {
  const cancel=vi.fn();
  const request=new Request('http://local',{method:'POST',headers:{'content-type':'application/json'},body:new ReadableStream({cancel}),duplex:'half'} as RequestInit);
  const response=fetchMonth(request);await vi.advanceTimersByTimeAsync(30_000);
  expect((await response).status).toBe(503);expect(cancel).toHaveBeenCalled();
 } finally {vi.useRealTimers();}
});

test('report proxy preserves explicit period and request ID with fixed upstream path',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({success:true,data:{html:'<h1>Report</h1>'}},{headers:{'X-Request-ID':'report-request'}})));
 const body=JSON.stringify({period:{year:2026,month:1}});
 const response=await generateReport(new Request('http://local/api/reports',{method:'POST',headers:{'content-type':'application/json'},body}));
 expect(response.status).toBe(200);expect(response.headers.get('x-request-id')).toBe('report-request');
 const [url,options]=vi.mocked(fetch).mock.calls[0];expect(new URL(String(url)).pathname).toBe('/reports');expect(new TextDecoder().decode(options?.body as Uint8Array)).toBe(body);
});

test('agent proxy forwards JSON to fixed backend path and accepts a larger trace response',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({success:true,data:{report_html:'x'.repeat(1_100_000)}})));
 const body=JSON.stringify({period:{year:2026,month:2},command:'Investigate HB106'});
 const response=await runAgent(new Request('http://local/api/agent-runs',{method:'POST',headers:{'content-type':'application/json'},body}));
 expect(response.status).toBe(200);
 const [url,options]=vi.mocked(fetch).mock.calls[0];
 expect(new URL(String(url)).pathname).toBe('/agent-runs');
 expect(new TextDecoder().decode(options?.body as Uint8Array)).toBe(body);
});

test('agent proxy rejects oversized commands before backend call',async()=>{
 const upstream=vi.fn();vi.stubGlobal('fetch',upstream);
 const response=await runAgent(new Request('http://local/api/agent-runs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({command:'x'.repeat(4100)})}));
 expect(response.status).toBe(413);expect(upstream).not.toHaveBeenCalled();
});
