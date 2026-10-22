const headers = { 'Cache-Control': 'no-store' };
function failure(status: number, code: string, message: string) {
  return Response.json({ success: false, data: null, error: { code, message } }, { status, headers });
}

export async function proxy(path: '/ingestions' | '/ingestions/fetch' | '/periods' | '/reports' | '/agent-runs', request?: Request) {
  try {
    const limit = path === '/ingestions' ? 50_100_000 : path === '/agent-runs' ? 4096 : 1024;
    let body: Uint8Array | undefined;
    if (request) {
      const type = request.headers.get('content-type') || '';
      if (!(path === '/ingestions' ? /^multipart\/form-data;\s*boundary=/i : /^application\/json(?:;|$)/i).test(type)) {
        return failure(415, 'CONTENT_TYPE', 'Unsupported request content type.');
      }
      const length = request.headers.get('content-length');
      if (length && (!/^\d+$/.test(length) || Number(length) > limit)) {
        return failure(413, 'UPLOAD_LIMIT', 'Request exceeds the upload limit.');
      }
      const reader = request.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader) {
        let interrupt: () => void = () => {};
        const interrupted = new Promise<never>((_, reject) => {
          interrupt = () => { void reader.cancel(); reject(new Error('Upload timed out or cancelled')); };
        });
        const timer = setTimeout(interrupt, 30_000);
        request.signal.addEventListener('abort', interrupt, { once: true });
        try {
          if (request.signal.aborted) throw new Error('Upload cancelled');
          while (true) {
            const { done, value } = await Promise.race([reader.read(), interrupted]);
            if (done) break;
            size += value.byteLength;
            if (size > limit) { await reader.cancel(); return failure(413, 'UPLOAD_LIMIT', 'Request exceeds the upload limit.'); }
            chunks.push(value);
          }
        } finally {
          clearTimeout(timer);
          request.signal.removeEventListener('abort', interrupt);
        }
      }
      body = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
    }
    const response = await fetch(new URL(path, process.env.BACKEND_URL || 'http://127.0.0.1:8000'), {
      method: request ? 'POST' : 'GET', cache: 'no-store', signal: AbortSignal.timeout(path === '/agent-runs' ? 180_000 : 120_000),
      ...(request ? { headers: { 'Content-Type': request.headers.get('content-type')! }, body: body as BodyInit } : {}),
    });
    const responseReader = response.body?.getReader();
    let responseText = '';
    let responseBytes = 0;
    const decoder = new TextDecoder();
    if (!responseReader) throw new Error('Empty backend response');
    while (true) {
      const { done, value } = await responseReader.read();
      if (done) break;
      responseBytes += value.byteLength;
      if (responseBytes > (path === '/agent-runs' ? 4_000_000 : 1_000_000)) { await responseReader.cancel(); throw new Error('Oversized backend response'); }
      responseText += decoder.decode(value, { stream: true });
    }
    responseText += decoder.decode();
    const result = JSON.parse(responseText);
    if (typeof result?.success !== 'boolean' || (result.success ? !result.data : typeof result.error?.message !== 'string')) {
      throw new Error('Invalid backend envelope');
    }
    const requestId = response.headers.get('X-Request-ID');
    return Response.json(result, { status: response.status, headers: { ...headers, ...(requestId ? { 'X-Request-ID': requestId } : {}) } });
  } catch {
    return failure(503, 'BACKEND_UNAVAILABLE', 'Data service unavailable. Check the service and retry.');
  }
}
