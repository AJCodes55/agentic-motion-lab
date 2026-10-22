import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { defineConfig } from '@playwright/test';
const dataRoot=mkdtempSync(join(tmpdir(),'mobility-e2e-'));
export default defineConfig({
 testDir:'./e2e',
 use:{baseURL:'http://127.0.0.1:3000',channel:'chromium'},
 webServer:[
  {command:`${process.env.PYTHON || '../backend/.venv/bin/python'} -m uvicorn mobility.app:app --host 127.0.0.1 --port 8000 --no-access-log`,url:'http://127.0.0.1:8000/health',env:{MOBILITY_DATA_ROOT:dataRoot},reuseExistingServer:false},
  {command:'npm run dev -- --hostname 127.0.0.1',url:'http://127.0.0.1:3000',reuseExistingServer:!process.env.CI}
 ]
});
