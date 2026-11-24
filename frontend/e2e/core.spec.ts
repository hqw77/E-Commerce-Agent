import { expect, test } from '@playwright/test';
import { login, readFixture } from './helpers';

test.describe('admin core pages', () => {
  test.beforeEach(async ({ page }) => {
    const fixture = readFixture();
    test.skip(!fixture, 'Run task014_e2e_seed.py before core E2E tests');
    if (!fixture) return;
    await login(page, fixture.admin.email, fixture.admin.password);
  });

  test('product page displays seeded data and category management is absent', async ({ page }) => {
    const fixture = readFixture();
    if (!fixture) return;

    await page.goto('/products');
    await expect(page.getByRole('heading', { name: '商品管理' })).toBeVisible();
    await expect(page.getByRole('link', { name: '分类管理' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: '知识库' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Agent Trace' })).toHaveCount(0);
    await page.getByRole('link', { name: fixture.product.product_no }).click();
    await expect(page.getByText(fixture.product.product_no).first()).toBeVisible();
    await expect(page.getByText(fixture.sku.sku_code).first()).toBeVisible();
  });

  test('inventory, order, and after-sales pages load', async ({ page }) => {
    const fixture = readFixture();
    if (!fixture) return;

    await page.goto('/inventory');
    await expect(page.getByRole('heading', { name: '库存管理' })).toBeVisible();
    await expect(page.getByText(fixture.sku.sku_code).first()).toBeVisible();

    await page.getByRole('button', { name: /入\s*库/ }).first().click();
    const inventoryDialog = page.getByRole('dialog');
    await expect(inventoryDialog).toBeVisible();
    await inventoryDialog.getByRole('spinbutton').fill('1');
    await inventoryDialog.getByRole('button', { name: /确\s*定/ }).click();
    await expect(page.getByText(/库存操作已/)).toBeVisible({ timeout: 30_000 });

    await page.goto('/orders');
    await expect(page.getByRole('heading', { name: '订单管理' })).toBeVisible();
    await page.getByRole('link', { name: fixture.order.order_no }).click();
    await expect(page.getByRole('heading', { name: new RegExp(fixture.order.order_no) })).toBeVisible();
    await expect(page.getByText('履约状态').first()).toBeVisible();

    await page.goto('/after-sales');
    await expect(page.getByRole('heading', { name: '售后管理' })).toBeVisible();
  });
});
