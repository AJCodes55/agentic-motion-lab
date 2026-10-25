import { expect, test } from '@playwright/test';
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
