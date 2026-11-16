import { expect, test } from '@playwright/test';
import { login, logout, readFixture } from './helpers';

test('unauthenticated business route redirects to login', async ({ page }) => {
  await page.goto('/products');
  await expect(page).toHaveURL(/\/login$/);
});

test('admin login, refresh, and logout flow', async ({ page }) => {
  const fixture = readFixture();
  test.skip(!fixture, 'Run task014_e2e_seed.py before authenticated E2E tests');
  if (!fixture) return;

  await login(page, fixture.admin.email, fixture.admin.password);
  await expect(page.getByText('首页概览').first()).toBeVisible();

  await page.evaluate(() => {
    localStorage.setItem('ecommerce_agent_access_token', 'broken-e2e-token');
  });
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText('首页概览').first()).toBeVisible();

  await logout(page);
  await expect(page).toHaveURL(/\/login$/);
});

test('regular user cannot access admin product API through the page', async ({ page }) => {
  const fixture = readFixture();
  test.skip(!fixture, 'Run task014_e2e_seed.py before authenticated E2E tests');
  if (!fixture) return;

  await login(page, fixture.user.email, fixture.user.password);
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  await expect(page.getByText(/没有该操作权限|权限/).first()).toBeVisible({ timeout: 15_000 });
});
