import { proxy } from '../ingestion-proxy';
export const dynamic = 'force-dynamic';
export async function POST(request: Request) { return proxy('/adhoc', request); }
