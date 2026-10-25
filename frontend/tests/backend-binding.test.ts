// @vitest-environment node
import { afterEach, expect, test, vi } from 'vitest';
import { GET as health } from '../app/api/health/route';
import { GET as periods } from '../app/api/periods/route';
import { POST as stream } from '../app/api/agent-runs/stream/route';

const streamRequest = () => new Request('http://local/api/agent-runs/stream', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
});
const callers = [
  { name: 'health', call: health, path: 'health' },
  { name: 'ordinary proxy', call: periods, path: 'periods' },
  { name: 'stream', call: () => stream(streamRequest()), path: 'agent-runs/stream' },
];
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
function stubBackend() {
  const upstream = vi.fn().mockImplementation(() => Promise.resolve(Response.json({
    success: true, data: { status: 'ok', service: 'citibike-analytics' },
  })));
  vi.stubGlobal('fetch', upstream);
  return upstream;
}

test.each(callers)('$name reads the binding at request time and preserves its base path', async ({ call, path }) => {
  const upstream = stubBackend();
  vi.stubEnv('VERCEL', '1');
  for (const base of ['https://backend.internal/prefix', 'https://other.internal/prefix/']) {
    vi.stubEnv('BACKEND_URL', base);
    expect((await call()).status).toBe(200);
    expect(String(upstream.mock.lastCall?.[0])).toBe(`${base.replace(/\/$/, '')}/${path}`);
  }
});

test.each(callers)('$name returns a safe 503 without contacting localhost when the Vercel binding is missing', async ({ call }) => {
  vi.stubEnv('VERCEL', '1');
  vi.stubEnv('BACKEND_URL', '');
  const upstream = stubBackend();
  const response = await call();
  expect(response.status).toBe(503);
  expect(await response.text()).not.toMatch(/localhost|127\.0\.0\.1|BACKEND_URL/);
  expect(upstream).not.toHaveBeenCalled();
});

test('local requests retain the development fallback', async () => {
  vi.stubEnv('VERCEL', '');
  vi.stubEnv('BACKEND_URL', '');
  const upstream = stubBackend();
  expect((await periods()).status).toBe(200);
  expect(String(upstream.mock.lastCall?.[0])).toBe('http://127.0.0.1:8000/periods');
});
