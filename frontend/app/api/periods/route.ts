import { proxy } from '../ingestion-proxy';
export const dynamic = 'force-dynamic';
export async function GET() { return proxy('/periods'); }
