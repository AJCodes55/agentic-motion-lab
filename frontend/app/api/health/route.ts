export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const response = await fetch(new URL('/health', process.env.BACKEND_URL || 'http://127.0.0.1:8000'), {
      cache: 'no-store', signal: AbortSignal.timeout(5000),
    });
    const body = await response.json();
    if (!response.ok || body.success !== true || body.data?.status !== 'ok' || body.data?.service !== 'citibike-analytics') {
      throw new Error('Invalid health response');
    }
    const requestId = response.headers.get('X-Request-ID');
    return Response.json(body, { headers: { 'Cache-Control': 'no-store', ...(requestId ? { 'X-Request-ID': requestId } : {}) } });
  } catch {
    return Response.json({ success: false, data: null, error: { code: 'BACKEND_UNAVAILABLE', message: 'Backend unavailable. Check the service and retry.' } }, { status: 503, headers: { 'Cache-Control': 'no-store' } });
  }
}
