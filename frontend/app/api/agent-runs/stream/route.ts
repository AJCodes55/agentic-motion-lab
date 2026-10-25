import { backendUrl } from '../../../../lib/backend-url';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    if (!/^application\/json(?:;|$)/i.test(request.headers.get('content-type') || '')) {
      return Response.json({ error: 'Unsupported request content type.' }, { status: 415 });
    }
    const reader = request.body?.getReader();
    if (!reader) return Response.json({ error: 'Request body is required.' }, { status: 400 });
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 4096) {
        await reader.cancel();
        return Response.json({ error: 'Request exceeds the analysis limit.' }, { status: 413 });
      }
      chunks.push(value);
    }
    const body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
    const backend = await fetch(backendUrl('/agent-runs/stream'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
      cache: 'no-store', signal: AbortSignal.timeout(180_000),
    });
    if (!backend.ok || !backend.body) {
      return Response.json({ error: 'Agent service could not start the analysis.' }, { status: backend.status || 503 });
    }
    return new Response(backend.body, {
      status: 200, headers: { 'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-store' },
    });
  } catch {
    return Response.json({ error: 'Agent service unavailable. Retry.' }, { status: 503 });
  }
}
