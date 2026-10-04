/**
 * File Explorer E2E Test (Agent Workspace composition)
 * ====================================================
 * The legacy IDE explorer panel was replaced by the right-hand 환경 rail
 * (EnvironmentPanel). File browsing now lives in:
 *   - 환경 tab  → agent monitor (status / activity / tokens)
 *   - 코드 tab  → editor + Git (file activity from git status, or empty-state)
 *   - 변경 tab  → the change review panel (ChangePanel)
 *
 * Scenario:
 *   1. Navigate to chat page
 *   2. Open the inspection panel (환경 tab selected)
 *   3. Open the 코드 tab — git file activity (or empty-state) lives here after redesign
 *   4. Verify the editor mounts on 코드
 *   5. Open the 변경 tab and verify the change panel mounts
 *   6. Toggle the rail closed and re-open
 *
 * CR-14 F-47 (attempt-037): file activity is on the 코드 tab (CodeTabWithGit),
 * not the redesigned 환경 AgentMonitorTab. Clean trees render `.env-sub-empty`.
 */

import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';

test.describe('Environment Rail — file browsing', () => {
  let dashboard: DashboardPage;

  test.beforeEach(async ({ page }) => {
    dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.goToChat();
  });

  test('should keep the canvas clear until inspection is opened', async () => {
    await expect(dashboard.page.locator('.agk-env-panel')).toHaveCount(0);
    await dashboard.page.getByRole('button', { name: '환경 패널 토글' }).click();
    const rail = dashboard.page.locator('.agk-env-panel');
    await expect(rail).toBeVisible({ timeout: 5000 });

    const envTab = rail.locator('.env-tab').filter({ hasText: '환경' });
    await expect(envTab).toHaveClass(/active/);
  });

  test('should show file activity from git status', async () => {
    await dashboard.page.getByRole('button', { name: '환경 패널 토글' }).click();
    const rail = dashboard.page.locator('.agk-env-panel');
    await expect(rail).toBeVisible({ timeout: 5000 });

    // After redesign, git file activity lives on the 코드 tab (not 환경).
    await rail.locator('.env-tab').filter({ hasText: '코드' }).click();

    const fileActivity = rail.locator('[data-testid="env-file-activity"]');
    await expect(fileActivity).toBeVisible({ timeout: 8000 });

    // Either git files render, or the empty state when the tree is clean
    const fileRows = fileActivity.locator('.env-file-row');
    const empty = fileActivity.locator('.env-sub-empty');
    await expect(fileRows.or(empty).first()).toBeVisible({ timeout: 8000 });
  });

  test('should mount the editor from the 코드 tab', async () => {
    await dashboard.page.getByRole('button', { name: '환경 패널 토글' }).click();
    const rail = dashboard.page.locator('.agk-env-panel');
    await rail.locator('.env-tab').filter({ hasText: '코드' }).click();

    const editor = dashboard.page.locator('.ide-editor');
    await expect(editor).toBeVisible({ timeout: 8000 });
  });

  test('should mount the change panel from the 변경 tab', async () => {
    await dashboard.page.getByRole('button', { name: '환경 패널 토글' }).click();
    const rail = dashboard.page.locator('.agk-env-panel');
    await rail.locator('.env-tab').filter({ hasText: '변경' }).click();

    const changePanel = dashboard.page.locator('.change-panel');
    await expect(changePanel).toBeVisible({ timeout: 8000 });
  });

  test('should toggle the environment rail closed and open', async () => {
    const toggle = dashboard.page.locator('[aria-label="환경 패널 토글"]');
    await expect(toggle).toBeVisible({ timeout: 5000 });

    await expect(dashboard.page.locator('.agk-env-panel')).toHaveCount(0);
    await toggle.click();
    await expect(dashboard.page.locator('.agk-env-panel')).toBeVisible();
    await dashboard.page.getByRole('button', { name: '패널 닫기' }).click();
    await expect(dashboard.page.locator('.agk-env-panel')).toHaveCount(0);

    await toggle.click();
    await expect(dashboard.page.locator('.agk-env-panel')).toBeVisible();
  });
});
