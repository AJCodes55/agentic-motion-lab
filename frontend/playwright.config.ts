import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { defineConfig } from '@playwright/test';
const dataRoot=mkdtempSync(join(tmpdir(),'mobility-e2e-'));
function port(value:string) {
 const number=Number(value);
 if(!/^\d+$/.test(value)||!Number.isInteger(number)||number<1||number>65535) throw new Error(`Invalid E2E port: ${value}`);
 return number;
}
const backendPort=port(process.env.E2E_BACKEND_PORT || '8000');
const frontendPort=port(process.env.E2E_FRONTEND_PORT || '3000');
const python=process.env.PYTHON || '../backend/.venv/bin/python';
if(!/^[A-Za-z0-9_./-]+$/.test(python)) throw new Error('Invalid PYTHON command');
const backendURL=`http://127.0.0.1:${backendPort}`;
const frontendURL=`http://127.0.0.1:${frontendPort}`;
export default defineConfig({
 testDir:'./e2e',
 // All tests share one backend store, whose approved policy permits one ingestion.
 workers:1,
 use:{baseURL:frontendURL,channel:'chromium'},
 webServer:[
  {command:`${python} -m uvicorn mobility.app:app --host 127.0.0.1 --port ${backendPort} --no-access-log`,url:`${backendURL}/health`,env:{MOBILITY_DATA_ROOT:dataRoot},reuseExistingServer:false},
  {command:`npm run build && npm run start -- --hostname 127.0.0.1 --port ${frontendPort}`,url:frontendURL,env:{BACKEND_URL:backendURL},reuseExistingServer:false,timeout:120_000}
 ]
});
