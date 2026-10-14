/**
 * CR-07 · 화면 오류 복구와 잘못된 경로 (실제 production build 브라우저)
 * ==================================================================
 * 발견 F03: lazy/Suspense만 있고 오류 경계·404가 없어서
 *   ① 없는 경로는 빈 화면, ② 페이지 하나의 렌더 예외는 셸 전체를 지웠다.
 *
 * 이 스펙은 실제 chromium + production 빌드(dashboard_dist)에서
 *   1) lazy 청크 요청 차단 → 복구 화면(새로고침) → 해제 후 복구
 *   2) 렌더 중 예외를 던지는 청크 fixture → 재시도 UI + 셸 보존
 *   3) 잘못된 deep link → 404 + 홈 복귀 + 뒤로가기
 *   4) 오류/복구가 대화·로컬 히스토리 저장소를 지우지 않음
 *
 * 을 확인한다. 서버는 hermetic 백엔드(격리 `.env`)이고 실패는 **테스트가 요청을
 * 가로채** 결정적으로 만든다 — 앱 코드에 테스트용 분기를 넣지 않는다.
 */
import { expect, test, type Page } from '@playwright/test';
import { startNoAuthServer, type HermeticServer } from '../helpers/hermeticBackend';

process.env.AGK_SEC_DEV_NO_PIN_ALLOW = '1';

const RECOVERY = '[data-testid="cr07-recovery"]';
const ERROR_ID = '[data-testid="cr07-error-id"]';
const RETRY = '[data-testid="cr07-retry"]';
const RELOAD = '[data-testid="cr07-reload"]';
const NOT_FOUND = '[data-testid="cr07-not-found"]';
const SHELL = '[aria-label="Codex Desktop Navigation"]';

const CHAT_STORAGE_KEY = 'antigravity_chat_cr07-fixture';
const HISTORY_STORAGE_KEY = 'agk_local_history:v1';
const RENDER_FIXTURE = 'cr07-e2e-render-fixture';

async function gotoPath(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await page.waitForLoadState('domcontentloaded');
}

test('a blocked page chunk shows a reload recovery screen and recovers after reload', async ({ browser }) => {
  test.setTimeout(90_000);
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  let blocked = true;
  await page.route('**/assets/HistoryPage-*.js', route => (blocked ? route.abort() : route.continue()));
  try {
    await gotoPath(page, '/history');

    await expect(page.locator(RECOVERY)).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(RECOVERY)).toHaveAttribute('data-error-kind', 'chunk');
    // 청크 실패는 같은 URL 재시도로 복구되지 않으므로 재시도를 약속하지 않는다.
    await expect(page.locator(RETRY)).toHaveCount(0);
    await expect(page.locator(RELOAD)).toBeVisible();
    // 셸(사이드바)은 살아 있다.
    await expect(page.locator(SHELL)).toBeVisible();
    // 원문 오류/스택이 화면에 없다.
    await expect(page.locator('body')).not.toContainText('HistoryPage-');
    await expect(page.locator(ERROR_ID)).toContainText(/E-[0-9A-F]{8}/);

    blocked = false;
    await page.locator(RELOAD).click();
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator(RECOVERY)).toHaveCount(0, { timeout: 20_000 });
    await expect(page.getByRole('heading', { name: /파일 히스토리|예약 작업 관리/ })).toBeVisible({ timeout: 20_000 });
  } finally {
    await context.close();
    await server.cleanup();
  }
});

test('a page that throws while rendering keeps the shell and offers retry', async ({ browser }) => {
  test.setTimeout(90_000);
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  // ModelHubPage 청크를 "렌더 중 예외를 던지는 모듈"로 바꿔치기한다(앱 코드 무변경).
  await page.route('**/assets/ModelHubPage-*.js', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: `export default function Cr07Boom() { throw new Error('${RENDER_FIXTURE}'); }`,
    }),
  );
  try {
    await gotoPath(page, '/models');

    await expect(page.locator(RECOVERY)).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(RECOVERY)).toHaveAttribute('data-error-kind', 'render');
    // 셸은 남고, 원문 예외 메시지는 화면에 없다.
    await expect(page.locator(SHELL)).toBeVisible();
    await expect(page.locator('body')).not.toContainText(RENDER_FIXTURE);

    await page.locator(RETRY).click();
    await expect(page.locator(RECOVERY)).toBeVisible();
    await expect(page.locator('[data-testid="cr07-attempts"]')).toContainText('2');

    // 다른 화면으로 이동하면 경계가 초기화되어 정상 화면이 뜬다.
    await gotoPath(page, '/settings');
    await expect(page.locator(RECOVERY)).toHaveCount(0, { timeout: 20_000 });
    await expect(page.getByRole('heading', { name: '시스템 설정' })).toBeVisible({ timeout: 20_000 });
  } finally {
    await context.close();
    await server.cleanup();
  }
});

test('an unknown deep link shows a not-found screen with home and back', async ({ browser }) => {
  test.setTimeout(90_000);
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  try {
    await gotoPath(page, '/definitely-not-a-route');

    await expect(page.locator(NOT_FOUND)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('cr07-not-found-path')).toContainText('/definitely-not-a-route');
    await expect(page.locator(SHELL)).toBeVisible();

    await page.getByTestId('cr07-not-found-home').click();
    await expect(page.locator(NOT_FOUND)).toHaveCount(0, { timeout: 20_000 });
    await expect(page.getByTestId('hero-headline')).toBeVisible({ timeout: 20_000 });
    expect(new URL(page.url()).pathname).toBe('/');

    // 브라우저 뒤로가기로 404 화면에 다시 도달할 수 있다.
    await page.goBack();
    await expect(page.locator(NOT_FOUND)).toBeVisible({ timeout: 20_000 });
  } finally {
    await context.close();
    await server.cleanup();
  }
});

test('a crash and recovery keep stored conversations and local history', async ({ browser }) => {
  test.setTimeout(90_000);
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  const chatPayload = JSON.stringify({ sessions: [{ id: 'cr07-session', title: '보존 대상' }] });
  const historyPayload = JSON.stringify({ snapshots: [{ id: 'cr07-snapshot' }] });
  await page.addInitScript(
    ([chatKey, chatValue, historyKey, historyValue]: [string, string, string, string]) => {
      window.localStorage.setItem(chatKey, chatValue);
      window.localStorage.setItem(historyKey, historyValue);
    },
    [CHAT_STORAGE_KEY, chatPayload, HISTORY_STORAGE_KEY, historyPayload] as const,
  );
  let blocked = true;
  await page.route('**/assets/HistoryPage-*.js', route => (blocked ? route.abort() : route.continue()));
  try {
    await gotoPath(page, '/history');
    await expect(page.locator(RECOVERY)).toBeVisible({ timeout: 20_000 });

    expect(await page.evaluate(key => window.localStorage.getItem(key), CHAT_STORAGE_KEY)).toBe(chatPayload);
    expect(await page.evaluate(key => window.localStorage.getItem(key), HISTORY_STORAGE_KEY)).toBe(historyPayload);

    blocked = false;
    await page.locator(RELOAD).click();
    await page.waitForLoadState('domcontentloaded');

    expect(await page.evaluate(key => window.localStorage.getItem(key), CHAT_STORAGE_KEY)).toBe(chatPayload);
    expect(await page.evaluate(key => window.localStorage.getItem(key), HISTORY_STORAGE_KEY)).toBe(historyPayload);
  } finally {
    await context.close();
    await server.cleanup();
  }
});
