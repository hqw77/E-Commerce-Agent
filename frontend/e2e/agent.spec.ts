test('Agent general chat responds', async ({ page }) => {
  const fixture = readFixture();
  test.skip(!fixture, 'Run task014_e2e_seed.py before Agent E2E tests');
  if (!fixture) return;

  await login(page, fixture.user.email, fixture.user.password);
  await page.goto('/agent');
  await expect(page.getByRole('heading', { name: /业务对话/ })).toBeVisible();

  await page.getByPlaceholder('输入问题，Enter 发送，Shift + Enter 换行').fill('你好，请介绍一下你能做什么。');
  await page.getByRole('button', { name: /发\s*送/ }).click();
  await expect(page.locator('.chat-row.assistant .chat-answer').last()).toBeVisible({
    timeout: 90_000,
  });
  await expect(page.locator('.chat-row.assistant .chat-answer').last()).not.toBeEmpty();
});

import { expect, test } from '@playwright/test';
import { login, readFixture } from './helpers';

test('Agent query, Prepare, and Confirm cancel a seeded order', async ({ page }) => {
  const fixture = readFixture();
  test.skip(!fixture, 'Run task014_e2e_seed.py before Agent E2E tests');
  if (!fixture) return;

  await login(page, fixture.user.email, fixture.user.password);
  await page.goto('/agent');
  await expect(page.getByRole('heading', { name: '业务对话' })).toBeVisible();

  const input = page.getByPlaceholder('输入问题，Enter 发送，Shift + Enter 换行');
  await input.fill('查询我的订单');
  await page.getByRole('button', { name: '发送' }).click();
  await expect(page.getByText(fixture.order.order_no).first()).toBeVisible({ timeout: 90_000 });

  await input.fill(`帮我取消未发货订单 ${fixture.order.order_no}`);
  await page.getByRole('button', { name: '发送' }).click();
  await expect(page.locator('.pending-card')).toBeVisible({ timeout: 90_000 });
  await page.locator('.pending-card button.ant-btn-primary').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: '确认执行' }).click();
  await expect(page.getByText(/订单已取消/).first()).toBeVisible({ timeout: 90_000 });
});
