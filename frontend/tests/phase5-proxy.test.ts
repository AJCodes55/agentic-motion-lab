// @vitest-environment node
import { afterEach, expect, test, vi } from 'vitest';
import { POST } from '../app/api/adhoc/route';
import { GET as history } from '../app/api/reports/history/route';
import { GET as archived } from '../app/api/reports/history/[id]/route';
afterEach(() => vi.unstubAllGlobals());
test('query forwards explicit request fields to fixed backend path', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ success: true, data: { status: 'success' } })));
  const body = JSON.stringify({ period: { year: 2026, month: 1 }, metric: 'total_trips', chart: true });
  expect((await POST(new Request('http://local/api/adhoc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body }))).status).toBe(200);
  const [url, options] = vi.mocked(fetch).mock.calls[0];
  expect(new URL(String(url)).pathname).toBe('/adhoc');
  expect(new TextDecoder().decode(options?.body as Uint8Array)).toBe(body);
});
test('history and archives are read without caching', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(Response.json({ success: true, data: { html: '<p>Saved</p>' } }))));
  expect((await history()).headers.get('cache-control')).toBe('no-store');
  const id = 'a'.repeat(32);
  expect((await archived(new Request('http://local'), { params: Promise.resolve({ id }) })).status).toBe(200);
  expect(new URL(String(vi.mocked(fetch).mock.calls[1][0])).pathname).toBe(`/reports/history/${id}`);
});
test.each(['../private', 'https://evil.test', 'a'.repeat(33)])('rejects invalid archive ID %s before forwarding', async id => {
  const upstream = vi.fn(); vi.stubGlobal('fetch', upstream);
  expect((await archived(new Request('http://local'), { params: Promise.resolve({ id }) })).status).toBe(404);
  expect(upstream).not.toHaveBeenCalled();
});
