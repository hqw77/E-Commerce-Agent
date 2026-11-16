import { expect, test } from '@playwright/test';
import { resolve } from 'node:path';
import { login, readFixture } from './helpers';

test('knowledge version publish and non-empty retrieval', async ({ page }) => {
  const fixture = readFixture();
  test.skip(
    !fixture?.knowledge.document_id,
    'Run task014_e2e_seed.py --knowledge-only before the RAG E2E test',
  );
  if (!fixture?.knowledge.document_id) return;

  await login(page, fixture.admin.email, fixture.admin.password);
  await page.goto(`/knowledge/${fixture.knowledge.document_id}`);
  await expect(page.getByText('文档信息')).toBeVisible();

  const publish = page.getByRole('button', { name: '发布' });
  if (await publish.count()) {
    await publish.first().click();
    await expect(page.getByText('版本已发布')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('PUBLISHED').first()).toBeVisible({ timeout: 30_000 });
  }

  await page.getByRole('button', { name: /上\s*传\s*新\s*版\s*本/ }).click();
  const uploadDialog = page.getByRole('dialog');
  await expect(uploadDialog).toBeVisible();
  await uploadDialog.locator('input[type="file"]').setInputFiles(
    resolve(process.cwd(), '../docs/04-testing/TASK-014/fixtures/task014-refund-policy.md'),
  );
  await uploadDialog.getByRole('button', { name: /确\s*定/ }).click();
  await expect(page.getByText('新版本已上传')).toBeVisible({ timeout: 120_000 });

  await page.goto('/knowledge');
  await page.getByRole('button', { name: '检索测试' }).click();
  const query = page.getByPlaceholder('输入问题，调用真实 /knowledge/retrieve');
  await query.fill('TASK014 退款申请窗口是多少天？');
  await page.getByRole('dialog').getByRole('button', { name: /检\s*索/ }).click();
  await expect(page.getByText(/TASK0\d+-KB/).first()).toBeVisible({ timeout: 30_000 });
});
