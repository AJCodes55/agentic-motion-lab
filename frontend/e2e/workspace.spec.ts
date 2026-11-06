import { expect, test } from '@playwright/test';
test('fetch wheel respects its action, reduced motion, and small screens', async ({ page }) => {
 let release!: () => void;
 const pending = new Promise<void>(resolve => { release = resolve; });
 await page.route('**/api/ingestions/fetch', async route => {
  await pending;
  await route.fulfill({status:503,json:{success:false,error:{message:'Data unavailable.'}}});
 });
 await page.goto('/');
 const wheel = page.getByRole('button', {name:'Fetch public Citi Bike data'}).locator('svg');
 const pageWheel = page.getByTestId('mobility-wheel-page');
 await expect(page.getByRole('button', {name:/Pause wheel animation/})).toHaveCount(0);
 await expect(wheel).toHaveCSS('animation-play-state', 'paused');
 await page.getByLabel('Reporting month').fill('2026-02');
 await page.getByRole('button', {name:'Fetch public Citi Bike data'}).click();
 await expect(wheel).toHaveCSS('animation-play-state', 'running');
 await expect(pageWheel).toHaveCSS('animation-play-state', 'paused');
 await page.emulateMedia({reducedMotion:'reduce'});
 await expect(wheel).toHaveCSS('animation-name', 'none');
 for (const viewport of [{width:375,height:812},{width:812,height:375},{width:1440,height:900}]) {
  await page.setViewportSize(viewport);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.getByRole('heading', {level:1})).toBeVisible();
 }
 release();
 await expect(page.getByText('Data unavailable.', {exact:true})).toBeVisible();
 await expect(wheel).toHaveAttribute('data-active','false');
});
test('agent button and right semicircle turn only until analysis ends', async ({ page }) => {
 let release!: () => void;
 const pending = new Promise<void>(resolve => { release = resolve; });
 await page.route('**/api/agent-runs/stream', async route => {
  await pending;
  await route.fulfill({contentType:'application/x-ndjson',body:JSON.stringify({type:'result',data:{
   run_id:'wheel-run',status:'complete',report_html:'<h1>Verified mobility report</h1>',
   stages:['Data Ingest','Agent Planning','Tool Execution','Final Report Generation'].map(name => ({name,status:'complete'})),
   trace:[{tool_name:'get_available_periods',status:'success',arguments:{current_period:null}}]
  }})+'\n'});
 });
 await page.setViewportSize({width:1440,height:1000});
 await page.goto('/');
 const pageWheel = page.getByTestId('mobility-wheel-page');
 await expect(pageWheel).toHaveCSS('animation-play-state', 'paused');
 const frame = await pageWheel.locator('..').boundingBox();
 expect(frame?.width).toBe(360);
 await page.getByLabel('Reporting month').fill('2026-02');
 await page.getByLabel('Analysis request').fill('Show monthly trends');
 const run = page.getByRole('button', {name:'Run agent analysis'});
 await run.focus();
 await page.keyboard.press('Enter');
 await expect(pageWheel).toHaveCSS('animation-play-state', 'running');
 const buttonWheel = page.getByRole('button', {name:'Running agent analysis…'}).locator('svg');
 await expect(buttonWheel).toHaveCSS('animation-play-state', 'running');
 await expect(page.getByRole('button', {name:'Running agent analysis…'})).toHaveCSS('border-radius','9999px');
 const progress = page.getByRole('list', {name:'Agent stages'});
 const runningStage = progress.locator('[data-state="running"]');
 await expect(runningStage).toHaveText('Running');
 await expect(runningStage.locator('.stage-indicator')).toHaveCSS('animation-name','stage-spin');
 await expect(page.getByRole('button', {name:'Fetch public Citi Bike data'}).locator('svg')).toHaveCSS('animation-play-state', 'paused');
 await page.screenshot({path:'/tmp/citibike-refinement-desktop.png'});
 await page.emulateMedia({reducedMotion:'reduce'});
 await expect(pageWheel).toHaveCSS('animation-name','none');
 await expect(buttonWheel).toHaveCSS('animation-name','none');
 await expect(runningStage.locator('.stage-indicator')).toHaveCSS('animation-name','none');
 release();
 await expect(page.frameLocator('iframe[title="Agent report for 2026-02"]').getByRole('heading', {name:'Verified mobility report'})).toBeVisible();
 await expect(pageWheel).toHaveAttribute('data-active','false');
 await expect(progress.locator('[data-state="complete"]')).toHaveCount(4);
 await expect(progress.locator('[data-state="running"]')).toHaveCount(0);
 await expect(page.getByRole('button', {name:'Run agent analysis'}).locator('svg')).toHaveAttribute('data-active','false');
 await expect(page.getByRole('region', {name:'Agent tool activity'})).toHaveCount(0);
 await page.setViewportSize({width:375,height:812});
 await page.getByRole('button', {name:'Run agent analysis'}).scrollIntoViewIfNeeded();
 await page.screenshot({path:'/tmp/citibike-refinement-mobile.png'});
});
test('shows connection status, handles outage and retry', async ({ page }) => {
 await page.route('**/api/health',route=>route.fulfill({status:503,json:{success:false}}));
 await page.goto('/');
 await expect(page.getByRole('region', { name: 'Service connection' }).getByRole('status')).toHaveText('Backend unavailable. Check the service and retry.');
 await page.unroute('**/api/health');
 await page.route('**/api/health',route=>route.fulfill({json:{success:true,data:{status:'ok',service:'citibike-analytics'},error:null}}));
 await page.getByRole('button',{name:'Check connection'}).click();
 await expect(page.getByRole('region', { name: 'Service connection' }).getByRole('status')).toHaveText('Backend connected');
 await expect(page.getByLabel('Reporting month')).toHaveValue('');
 await expect(page.getByRole('button',{name:'Generate baseline report'})).toBeDisabled();
});
test('connects through the frontend proxy to the live backend',async({page})=>{
 await page.goto('/');
 await expect(page.getByRole('region', { name: 'Service connection' }).getByRole('status')).toHaveText('Backend connected');
 const health=await page.request.get('/api/health');
 expect(health.ok()).toBeTruthy();
 expect(health.headers()['x-request-id']).toBeTruthy();
});
