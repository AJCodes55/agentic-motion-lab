import { afterEach, expect, test, vi } from 'vitest';
import { POST } from '../app/api/agent-runs/stream/route';

afterEach(() => vi.unstubAllGlobals());
const request = (body: string, contentType = 'application/json') => new Request('http://localhost/api/agent-runs/stream', {
  method: 'POST', headers: { 'Content-Type': contentType }, body,
});

test('forwards bounded JSON and streams backend events', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{"type":"result"}\n', {
    status: 200, headers: { 'Content-Type': 'application/x-ndjson' },
  }));
  vi.stubGlobal('fetch', fetchMock);
  const response = await POST(request('{"period":{"year":2026,"month":2},"command":"Report"}'));
  expect(response.status).toBe(200);
  expect(response.headers.get('content-type')).toBe('application/x-ndjson');
  expect(await response.text()).toBe('{"type":"result"}\n');
  expect(fetchMock).toHaveBeenCalledOnce();
  const [url, options] = fetchMock.mock.calls[0];
  expect(String(url)).toBe('http://127.0.0.1:8000/agent-runs/stream');
  expect(new TextDecoder().decode(options.body)).toContain('"command":"Report"');
});

test('rejects unsupported content type and oversized request without forwarding', async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  expect((await POST(request('{}', 'text/plain'))).status).toBe(415);
  expect((await POST(request('x'.repeat(4097)))).status).toBe(413);
  expect(fetchMock).not.toHaveBeenCalled();
});

test('returns a safe error when the backend fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('private traceback', { status: 503 })));
  const response = await POST(request('{}'));
  expect(response.status).toBe(503);
  expect(await response.text()).not.toContain('private traceback');
});

test('returns a safe error when the backend is unreachable', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private host')));
  const response = await POST(request('{}'));
  expect(response.status).toBe(503);
  expect(await response.text()).not.toContain('private host');
});
