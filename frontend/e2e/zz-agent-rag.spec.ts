import { expect, test } from '@playwright/test';
import { login, readFixture } from './helpers';

test('Agent RAG answer uses published knowledge source', async ({ page }) => {
  const fixture = readFixture();
  test.skip(
    !fixture?.knowledge.document_id,
    'Run task014_e2e_seed.py --knowledge-only before the Agent RAG E2E test',
  );
  if (!fixture?.knowledge.document_id) return;

  await login(page, fixture.user.email, fixture.user.password);
  await page.goto('/agent');
  await expect(page.getByRole('heading', { name: /业务对话/ })).toBeVisible();

  await page.getByPlaceholder('输入问题，Enter 发送，Shift + Enter 换行').fill('退款申请窗口是多少天？');
  await page.getByRole('button', { name: /发\s*送/ }).click();
  await expect(page.getByText(/TASK0\d+-KB/).first()).toBeVisible({
    timeout: 90_000,
  });
});

test('Agent READ tool query returns the seeded order', async ({ page }) => {
  const fixture = readFixture();
  test.skip(!fixture, 'Run task014_e2e_seed.py before Agent E2E tests');
  if (!fixture) return;

  await login(page, fixture.user.email, fixture.user.password);
  await page.goto('/agent');
  await page.getByPlaceholder('输入问题，Enter 发送，Shift + Enter 换行').fill(`查询订单 ${fixture.order.order_no}`);
  await page.getByRole('button', { name: /发\s*送/ }).click();
  await expect(page.getByText(fixture.order.order_no).first()).toBeVisible({
    timeout: 90_000,
  });
});
