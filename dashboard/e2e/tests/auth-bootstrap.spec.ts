import { mkdir } from 'node:fs/promises';
import path from 'node:path';

import { expect, test } from '@playwright/test';
import { z } from 'zod';
import { DashboardPage } from '../pages/DashboardPage';
import { authPin, startAuthServer, startNoAuthServer } from '../helpers/hermeticBackend';

const TokenSchema = z.object({ access_token: z.string().min(1) });

test.beforeEach(async ({}, testInfo) => {
  await mkdir(testInfo.outputDir, { recursive: true });
});

test('no-auth loopback bootstrap starts the dashboard without credentials', async ({ browser }, testInfo) => {
  test.setTimeout(60_000);
  const server = await startNoAuthServer();
  try {
    const context = await browser.newContext({ baseURL: server.baseUrl });
    const page = await context.newPage();
    const login = await page.request.post('/api/auth/login', { data: { pin: '0000' } });
    expect(login.status()).toBe(503);
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.expectAppRoot();
    await expect(dashboard.pinModal).toHaveCount(0);
    await page.screenshot({ path: path.join(testInfo.outputDir, 'no-auth-bootstrap.png'), fullPage: true });
    await context.close();
  } finally {
    await server.cleanup();
  }
});

test('unavailable legacy PIN authentication leaves no credential behind', async ({ browser }, testInfo) => {
  test.setTimeout(60_000);
  const server = await startNoAuthServer();
  try {
    const context = await browser.newContext({ baseURL: server.baseUrl });
    const page = await context.newPage();
    const dashboard = new DashboardPage(page);
    await dashboard.goto({ kind: 'legacyPin', value: '0000' });
    await dashboard.submitPin('0000');
    await expect(page.getByRole('alert')).toContainText('인증 서버를 사용할 수 없습니다');
    expect(await page.evaluate(() => sessionStorage.getItem('ag_access_token'))).toBeNull();
    expect(await page.evaluate(() => localStorage.getItem('ag_access_pin'))).toBeNull();
    await page.screenshot({ path: path.join(testInfo.outputDir, 'invalid-legacy-pin.png'), fullPage: true });
    await context.close();
  } finally {
    await server.cleanup();
  }
});

test('configured PIN authenticates through the real UI login contract', async ({ browser }, testInfo) => {
  test.setTimeout(60_000);
  const server = await startAuthServer(1);
  try {
    const context = await browser.newContext({ baseURL: server.baseUrl });
    const page = await context.newPage();
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.submitPin(authPin);
    await dashboard.expectAppRoot();
    await expect(dashboard.pinModal).toHaveCount(0);
    expect((await page.evaluate(() => sessionStorage.getItem('ag_access_token'))) ?? '').not.toBe('');
    await page.screenshot({ path: path.join(testInfo.outputDir, 'configured-auth.png'), fullPage: true });
    await context.close();
  } finally {
    await server.cleanup();
  }
});

test('expired token falls back to the PIN dialog', async ({ browser }, testInfo) => {
  test.setTimeout(60_000);
  const server = await startAuthServer(0);
  try {
    const context = await browser.newContext({ baseURL: server.baseUrl });
    const page = await context.newPage();
    const dashboard = new DashboardPage(page);
    const login = await page.request.post('/api/auth/login', { data: { pin: authPin } });
    const token = TokenSchema.parse(await login.json()).access_token;
    await dashboard.goto({ kind: 'token', value: token });
    await expect(dashboard.pinModal).toBeVisible();
    await expect(page.getByLabel('PIN 번호')).toBeFocused();
    await page.screenshot({ path: path.join(testInfo.outputDir, 'expired-token.png'), fullPage: true });
    await context.close();
  } finally {
    await server.cleanup();
  }
});
