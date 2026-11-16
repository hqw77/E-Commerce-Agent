import { expect, test } from '@playwright/test';
import { login, readFixture } from './helpers';

test.describe('admin core pages', () => {
  test.beforeEach(async ({ page }) => {
    const fixture = readFixture();
    test.skip(!fixture, 'Run task014_e2e_seed.py before core E2E tests');
    if (!fixture) return;
    await login(page, fixture.admin.email, fixture.admin.password);
  });

  test('category and product pages display seeded data', async ({ page }) => {
    const fixture = readFixture();
    if (!fixture) return;

    await page.goto('/categories');
    await expect(page.getByRole('heading', { name: '分类管理' })).toBeVisible();
    await expect(page.getByRole('cell', { name: fixture.category.name })).toBeVisible();

    await page.getByRole('button', { name: /编\s*辑/ }).first().click();
    const editDialog = page.getByRole('dialog');
    await expect(editDialog).toBeVisible();
    const categoryName = editDialog.locator('input').first();
    await categoryName.fill(`${fixture.category.name}-edited`);
    await editDialog.getByRole('button', { name: /确\s*定/ }).click();
    await expect(page.getByText('分类已更新')).toBeVisible();

    const uiCategory = `TASK015-UI-${fixture.run_id}`;
    await page.getByRole('button', { name: /新\s*增\s*分\s*类/ }).click();
    const createDialog = page.getByRole('dialog');
    await expect(createDialog).toBeVisible();
    await createDialog.locator('input').first().fill(uiCategory);
    await createDialog.getByRole('button', { name: /确\s*定/ }).click();
    await expect(page.getByText('分类已创建')).toBeVisible();
    await expect(page.getByRole('cell', { name: uiCategory })).toBeVisible();

    await page.goto('/products');
    await expect(page.getByRole('heading', { name: '商品管理' })).toBeVisible();
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

    await page.goto('/orders');
    await expect(page.getByRole('heading', { name: '订单管理' })).toBeVisible();
    await page.getByRole('link', { name: fixture.order.order_no }).click();
    await expect(page.getByRole('heading', { name: new RegExp(fixture.order.order_no) })).toBeVisible();
    await expect(page.getByText('支付状态').first()).toBeVisible();

    await page.goto('/after-sales');
    await expect(page.getByRole('heading', { name: '售后管理' })).toBeVisible();
  });
});
