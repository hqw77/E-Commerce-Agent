import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Page } from '@playwright/test';

export interface E2EFixture {
  run_id: string;
  admin: { id: number; email: string; password: string };
  user: { id: number; email: string; password: string };
  category: { id: number; name: string };
  product: { id: number; product_no: string };
  sku: { id: number; sku_code: string };
  order: { order_no: string };
  knowledge: { document_id: number | null; version_id: number | null; version_status: string | null };
}

const fixturePath = resolve(
  process.env.E2E_FIXTURE ?? '.tmp/task014-e2e.json',
);

export function readFixture(): E2EFixture | null {
  if (!existsSync(fixturePath)) return null;
  return JSON.parse(readFileSync(fixturePath, 'utf8')) as E2EFixture;
}

export async function login(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('邮箱').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/dashboard');
  await page.waitForLoadState('networkidle');
}

export async function logout(page: Page): Promise<void> {
  await page.getByText('退出').click();
  await page.waitForURL('**/login');
}
