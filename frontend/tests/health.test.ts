import { afterEach, expect, test, vi } from 'vitest';
import { GET } from '../app/api/health/route';
afterEach(()=>vi.unstubAllGlobals());
test('forwards backend health with request id',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({success:true,data:{status:'ok',service:'citibike-analytics'},error:null}),{headers:{'X-Request-ID':'abc'}})));
 const response=await GET();
 expect(response.status).toBe(200); expect(response.headers.get('X-Request-ID')).toBe('abc');
 expect(await response.json()).toMatchObject({success:true,data:{status:'ok'}});
});
test.each(['http','shape','throw'])('returns service unavailable for %s',async(mode)=>{
 vi.stubGlobal('fetch',mode==='throw'?vi.fn().mockRejectedValue(new Error('secret')):vi.fn().mockResolvedValue(new Response(JSON.stringify({unexpected:true}),{status:mode==='http'?500:200})));
 const response=await GET(); expect(response.status).toBe(503);
 expect(await response.json()).toEqual({success:false,data:null,error:{code:'BACKEND_UNAVAILABLE',message:'Backend unavailable. Check the service and retry.'}});
});
