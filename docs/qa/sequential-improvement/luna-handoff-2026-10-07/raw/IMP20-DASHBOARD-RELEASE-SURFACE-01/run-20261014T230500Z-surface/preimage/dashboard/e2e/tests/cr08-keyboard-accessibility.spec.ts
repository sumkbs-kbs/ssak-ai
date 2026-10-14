/**
 * CR-08 · 설정과 명령 팔레트 키보드/접근성 (실제 production build 브라우저)
 * ======================================================================
 * 발견 F04: ① SettingsPage provider 비밀 입력에 label 연결이 없어 여섯 입력의
 * 접근성 이름이 같았고, ② CommandPalette는 초기 focus만 있고 dialog modal
 * 계약(aria-modal/배경 inert/Tab 순환/focus 복귀)이 없었으며, ③ 한글 IME 조합을
 * 확정하는 Enter가 명령 실행으로 오인됐다.
 *
 * 이 스펙은 실제 chromium + production 빌드(dashboard_dist) + hermetic 백엔드에서
 *   C08-01 provider accessible name
 *   C08-02 팔레트 modal 격리/복귀
 *   C08-03 검색/Enter/ESC 동작과 IME 조합 Enter 구분
 *   C08-04 데스크톱·좁은 화면 확인과 axe 심각·치명 0
 * 을 확인한다. axe 전 impact 0은 기존 hard gate(UI-02)가 담당한다.
 */
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

import { startNoAuthServer, type HermeticServer } from '../helpers/hermeticBackend';

process.env.AGK_SEC_DEV_NO_PIN_ALLOW = '1';

const PALETTE_DIALOG = '[role="dialog"][aria-label="명령 팔레트"]';
const PALETTE_INPUT = `${PALETTE_DIALOG} [role="combobox"]`;
const SHELL_LAYOUT = '.app-layout';
const NOT_FOUND = '[data-testid="cr07-not-found"]';
const RECOVERY = '[data-testid="cr07-recovery"]';

const PROVIDERS: Array<{ key: string; brand: RegExp }> = [
  { key: 'OPENROUTER_API_KEY', brand: /openrouter/i },
  { key: 'NVIDIA_API_KEY', brand: /nvidia/i },
  { key: 'OPENAI_API_KEY', brand: /openai/i },
  { key: 'GEMINI_API_KEY', brand: /gemini/i },
  { key: 'ZAI_API_KEY', brand: /zhipu/i },
  { key: 'ANTHROPIC_API_KEY', brand: /anthropic/i },
];

/**
 * 팔레트 fade-in 애니메이션(cmd-in 0.15s)이 끝날 때까지 기다린다.
 * 애니메이션 도중에 axe를 돌리면 opacity가 낮은 상태로 색이 측정되어
 * 멀쩡한 색 대비가 일시적으로 미달로 보고된다(실측: #8b949e → #60676d, 3.39:1).
 * 판정을 애니메이션 타이밍에 의존시키지 않기 위한 대기다.
 */
async function waitForPaletteSettled(page: Page): Promise<void> {
  await expect(page.locator('.command-palette')).toHaveCSS('opacity', '1', { timeout: 10_000 });
}

async function openPalette(page: Page): Promise<void> {
  await page.locator('aside').first().waitFor({ state: 'visible', timeout: 20_000 });
  await page.keyboard.press('ControlOrMeta+k');
  await expect(page.locator(PALETTE_INPUT)).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(PALETTE_INPUT)).toBeFocused({ timeout: 10_000 });
}

async function criticalSeriousViolations(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'])
    .analyze();
  return results.violations
    .filter(violation => violation.impact === 'critical' || violation.impact === 'serious')
    .map(violation => `[${violation.impact}] ${violation.id}: ${violation.help} (${violation.nodes.length})`);
}

test('C08-01 · provider 비밀 입력이 각각 고유한 접근성 이름을 갖는다', async ({ browser }) => {
  test.setTimeout(90_000);
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  try {
    await page.goto('/settings');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByRole('heading', { name: '시스템 설정' })).toBeVisible({ timeout: 20_000 });

    for (const { key, brand } of PROVIDERS) {
      const input = page.getByTestId(`api-key-input-${key}`);
      await expect(input, `${key} 입력이 없다`).toBeVisible();
      await expect(page.getByLabel(brand), `${key}: provider 이름으로 입력을 찾을 수 없다`).toHaveJSProperty(
        'tagName',
        'INPUT',
      );
      // 이름으로 찾은 요소가 정확히 그 입력이어야 한다.
      expect(await page.getByLabel(brand).getAttribute('data-testid')).toBe(`api-key-input-${key}`);
    }
  } finally {
    await context.close();
    await server.cleanup();
  }
});

test('C08-02 · 팔레트가 modal 의미·focus 순환·복귀·배경 inert를 지킨다', async ({ browser }) => {
  test.setTimeout(90_000);
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  try {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const sidebarLink = page.locator('aside a').first();
    await sidebarLink.waitFor({ state: 'visible', timeout: 20_000 });
    await sidebarLink.focus();
    await expect(sidebarLink).toBeFocused();

    await openPalette(page);

    // modal 의미
    await expect(page.locator(PALETTE_DIALOG)).toHaveAttribute('aria-modal', 'true');

    /*
     * 배경 inert — 팔레트 오버레이는 레이아웃 안쪽에 마운트되므로(실측)
     * 같은 레벨의 사이드바·본문과 상위 레벨의 형제가 모두 비활성이어야 한다.
     */
    await expect(page.locator('aside').first()).toHaveAttribute('inert');
    await expect(page.locator(SHELL_LAYOUT).locator('.app-right-panel')).toHaveAttribute('inert');
    expect(await page.evaluate(() => document.querySelectorAll('[inert]').length)).toBeGreaterThan(0);

    // Tab 순환 — 마지막 항목에서 Tab을 누르면 첫 요소(검색 입력)로 돌아온다.
    const options = page.locator(`${PALETTE_DIALOG} [role="option"]`);
    const count = await options.count();
    expect(count, '팔레트 옵션이 없다').toBeGreaterThan(0);
    await options.nth(count - 1).evaluate(element => (element as HTMLElement).focus());
    await page.keyboard.press('Tab');
    await expect(page.locator(PALETTE_INPUT)).toBeFocused();

    // Shift+Tab — 첫 요소에서 뒤로 가면 마지막 항목으로 간다.
    await page.keyboard.press('Shift+Tab');
    expect(
      await page.evaluate(() => document.activeElement?.getAttribute('role')),
      'Shift+Tab이 마지막 옵션으로 순환하지 않았다',
    ).toBe('option');

    // ESC 닫기 + 열기 전 focus 복귀
    await page.keyboard.press('Escape');
    await expect(page.locator(PALETTE_DIALOG)).toHaveCount(0, { timeout: 10_000 });
    await expect(sidebarLink).toBeFocused();
    await expect(page.locator('aside').first()).not.toHaveAttribute('inert');
    // 모달이 아닐 때 배경 inert가 남지 않는다.
    expect(await page.evaluate(() => document.querySelectorAll('[inert]').length)).toBe(0);
  } finally {
    await context.close();
    await server.cleanup();
  }
});

test('C08-03 · 검색/Enter 실행과 IME 조합 Enter를 구분한다', async ({ browser }) => {
  test.setTimeout(90_000);
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  try {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await openPalette(page);

    await page.locator(PALETTE_INPUT).fill('goal');
    await expect(page.locator(`${PALETTE_DIALOG} [role="option"]`).first()).toBeVisible({ timeout: 10_000 });

    // 방향키 내비게이션은 aria-activedescendant로 노출된다.
    await page.keyboard.press('ArrowDown');
    const activeDescendant = await page.locator(PALETTE_INPUT).getAttribute('aria-activedescendant');
    expect(activeDescendant, 'aria-activedescendant가 없다').toBeTruthy();

    // 한글 IME 조합 확정 Enter(isComposing)는 실행이 아니다 → 팔레트가 열린 채로 남는다.
    await page.locator(PALETTE_INPUT).evaluate(element => {
      element.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true, cancelable: true }),
      );
    });
    await page.waitForTimeout(200);
    await expect(page.locator(PALETTE_DIALOG), '조합 중 Enter가 팔레트를 닫았다').toHaveCount(1);

    // 조합이 아닌 Enter는 실행된다.
    await page.keyboard.press('Enter');
    await expect(page.locator(PALETTE_DIALOG)).toHaveCount(0, { timeout: 10_000 });
  } finally {
    await context.close();
    await server.cleanup();
  }
});

for (const viewport of [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'narrow', width: 390, height: 844 },
] as const) {
  test(`C08-04 · ${viewport.name} — 팔레트·404·복구 화면 확인과 axe 심각·치명 0`, async ({ browser }) => {
    test.setTimeout(120_000);
    const server: HermeticServer = await startNoAuthServer();
    const context = await browser.newContext({
      baseURL: server.baseUrl,
      viewport: { width: viewport.width, height: viewport.height },
    });
    const page = await context.newPage();
    try {
      /* 1) 팔레트 — 좁은 화면에서도 viewport 안에 들어오고 axe 심각·치명 0 */
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');
      await openPalette(page);

      const box = await page.locator(PALETTE_DIALOG).boundingBox();
      expect(box, '팔레트 박스를 얻지 못했다').not.toBeNull();
      if (box !== null) {
        expect(box.x, '팔레트가 왼쪽으로 넘쳤다').toBeGreaterThanOrEqual(0);
        expect(box.x + box.width, '팔레트가 오른쪽으로 넘쳤다').toBeLessThanOrEqual(viewport.width + 1);
      }

      await waitForPaletteSettled(page);
      const paletteViolations = await criticalSeriousViolations(page);
      expect(paletteViolations, `팔레트 axe 위반: ${paletteViolations.join(', ')}`).toHaveLength(0);

      await page.keyboard.press('Escape');
      await expect(page.locator(PALETTE_DIALOG)).toHaveCount(0, { timeout: 10_000 });

      /* 2) 없는 경로(CR-07 404) — 셸 안에서 안내되고 axe 심각·치명 0 */
      await page.goto('/cr08-unknown-route');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator(NOT_FOUND)).toBeVisible({ timeout: 20_000 });
      const notFoundViolations = await criticalSeriousViolations(page);
      expect(notFoundViolations, `404 화면 axe 위반: ${notFoundViolations.join(', ')}`).toHaveLength(0);

      /* 3) 오류 복구 화면 — 실제 청크 차단으로 띄우고 axe 심각·치명 0 */
      let blocked = true;
      await page.route('**/assets/HistoryPage-*.js', route => (blocked ? route.abort() : route.continue()));
      await page.goto('/history');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator(RECOVERY)).toBeVisible({ timeout: 20_000 });
      const recoveryViolations = await criticalSeriousViolations(page);
      expect(recoveryViolations, `복구 화면 axe 위반: ${recoveryViolations.join(', ')}`).toHaveLength(0);
      blocked = false;
    } finally {
      await context.close();
      await server.cleanup();
    }
  });
}
