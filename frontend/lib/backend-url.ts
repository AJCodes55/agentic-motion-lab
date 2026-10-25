/** Resolve the server-only service binding when a request is handled. */
export function backendUrl(path: string): URL {
  const binding = process.env.BACKEND_URL;
  if (!binding && process.env.VERCEL) throw new Error('Backend binding is unavailable');
  const base = new URL(binding || 'http://127.0.0.1:8000');
  base.pathname = `${base.pathname.replace(/\/+$/, '')}/`;
  return new URL(path.replace(/^\/+/, ''), base);
}
