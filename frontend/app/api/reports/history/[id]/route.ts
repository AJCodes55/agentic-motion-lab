import { proxy } from '../../../ingestion-proxy';
export const dynamic = 'force-dynamic';
export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^[a-f0-9]{32}$/.test(id)) return Response.json({ success: false, data: null, error: { message: 'Invalid report identifier.' } }, { status: 404 });
  return proxy(`/reports/history/${id}`);
}
