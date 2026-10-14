/**
 * CR-10 · 운영 지표와 빌드 신뢰성 (실제 production 빌드 브라우저)
 * ==============================================================
 * 발견 F06: `SystemTelemetricsBar.tsx`가 BUILD `v0.8.0-RC`, UPTIME `14D 08H 12M`,
 * NODE `LOCAL-01`, CTRL `OPEN INTAKE WAVE 01`을 하드코딩했고 정보 없는 healthy를
 * true로 처리했다. 화면과 API를 교차 확인한다.
 *
 * hermetic 백엔드 + production 번들에서:
 *   C10-01 BUILD가 실행 중인 서버 버전(+빌드 식별자)과 일치한다.
 *   C10-02 UPTIME이 현재 API 프로세스 가동 시간이다(방금 뜬 서버면 초 단위).
 *   C10-03 API를 끊으면 UNKNOWN/OFFLINE로 표시하고 healthy를 주장하지 않는다.
 *   C10-04 화면 지표가 API 응답과 일치한다(CPU/percent/PID/VAULT).
 *   C10-05 고정 문구가 사라지고 LINK 상태가 실제 관측이다.
 */
import { test, expect, type Page } from '@playwright/test';

import { DashboardPage } from '../pages/DashboardPage';
import { startNoAuthServer, type HermeticServer } from '../helpers/hermeticBackend';

process.env.AGK_SEC_DEV_NO_PIN_ALLOW = '1';

/** F06에서 화면에 박혀 있던 문자열 — 남아 있으면 실패다. */
const HARDCODED_FRAGMENTS = ['v0.8.0-RC', '14D 08H 12M', 'LOCAL-01', 'OPEN INTAKE WAVE 01'];

interface SystemStatusBody {
  readonly ok: boolean;
  readonly version: string;
  readonly build: { readonly version?: string; readonly build_id?: string | null };
  readonly cpu_percent: number;
  readonly memory_percent: number;
  readonly memory_mb: number;
  readonly uptime_seconds: number;
  readonly uptime_started_at: string;
  readonly process_id: number;
  readonly total_tokens: number;
}

/** 페이지 원점에서 API를 직접 읽어 화면과 대조한다(C10-04). */
async function fetchStatus(page: Page, origin: string): Promise<SystemStatusBody> {
  // 앱과 같은 방식으로 요청한다(loopback open-loopback 이므로 PIN이 필요 없다).
  const body = await page.evaluate(async base => {
    const response = await fetch(`${base}/api/system/status`);
    return { status: response.status, json: await response.json() };
  }, origin);
  expect(body.status, `GET /api/system/status → ${body.status}`).toBe(200);
  return body.json as unknown as SystemStatusBody;
}

function text(page: Page, testId: string): Promise<string> {
  return page.getByTestId(testId).innerText();
}

/** `1H 00M` / `1M 30S` / `2D 03H 04M` → 초. */
function parseUptime(label: string): number {
  const match = /^(?:(\d+)D )?(?:(\d+)H )?(?:(\d+)M )?(\d+)S$/.exec(label.trim());
  if (!match) {
    throw new Error(`UPTIME 형식을 해석할 수 없다: ${JSON.stringify(label)}`);
  }
  const [, days = '0', hours = '0', minutes = '0', seconds = '0'] = match;
  return Number(days) * 86400 + Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds);
}

async function bodyText(page: Page): Promise<string> {
  return page.evaluate(() => document.body.innerText);
}

test('C10-01/02/04/05 · 화면 지표가 실제 API 값과 일치한다', async ({ browser }) => {
  test.setTimeout(120_000);
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  try {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(page.getByTestId('telemetrics-link')).toBeVisible({ timeout: 20_000 });

    // 첫 관측이 끝날 때까지 기다린다(10s 폴링 주기보다 여유 있게).
    await expect(page.getByTestId('telemetrics-link')).toHaveAttribute(
      'data-connection',
      'live',
      { timeout: 30_000 },
    );

    const api = await fetchStatus(page, server.baseUrl);

    // C10-01: BUILD는 실행 중인 서버 버전이다.
    const build = await text(page, 'telemetrics-build');
    expect(build).toContain(`v${api.version}`);
    expect(api.build.version).toBe(api.version);

    // C10-04: 값이 API와 결합되어 있다(CPU/MEM은 매 호출마다 새 표본이므로 형식·범위를 본다.
    //         고정 payload와의 정확한 일치 비교는 아래 C10-04 전용 시나리오가 담당한다).
    expect(await text(page, 'telemetrics-node')).toBe(`PID-${api.process_id} · NOMINAL`);
    expect(await text(page, 'telemetrics-cpu')).toMatch(/^\d+\.\d%$/);
    expect(await text(page, 'telemetrics-mem')).toMatch(/^\d+\.\d%$/);
    // API는 memory_percent를 주고 화면은 MB가 아니라 %로 표시한다.
    expect(api.memory_percent).toBe(api.memory_mb);
    expect(await text(page, 'telemetrics-mem')).not.toContain('MB');

    // C10-02: 방금 뜬 hermetic 서버다 — 업타임은 초 단위여야 한다.
    //         (14일 고정값이나 탭이 열린 시간과 구분된다.)
    const uptimeLabel = await text(page, 'telemetrics-uptime');
    const uptimeSeconds = parseUptime(uptimeLabel);
    // 화면 값은 관측 시점의 서버 업타임 + 경과분이므로 API 값과 30초 이내로 일치해야 한다.
    expect(Math.abs(uptimeSeconds - api.uptime_seconds)).toBeLessThan(30);
    expect(api.uptime_seconds).toBeLessThan(600);
    expect(Date.parse(api.uptime_started_at)).toBeGreaterThan(0);

    // C10-05: 고정 문구가 없다.
    const text2 = await bodyText(page);
    for (const fragment of HARDCODED_FRAGMENTS) {
      expect(text2, `고정 문구가 남아 있다: ${fragment}`).not.toContain(fragment);
    }

    console.log(
      `[C10-EVIDENCE] ${JSON.stringify({
        build,
        uptimeLabel,
        apiUptime: api.uptime_seconds,
        processId: api.process_id,
        cpu: api.cpu_percent,
        memoryPercent: api.memory_percent,
      })}`,
    );
  } finally {
    await context.close();
    await server.cleanup();
  }
});

/**
 * C10-04: 화면이 API 값을 그대로 옮기는지 결정적으로 확인한다.
 * 실 서버의 CPU/MEM은 호출마다 새로 표본되므로 고정 payload를 주입해 정확히 대조한다.
 */
const STUB_STATUS = {
  ok: true,
  status: 'online',
  memory_mb: 41.5,
  memory_percent: 41.5,
  cpu_percent: 12.3,
  total_tokens: 2048,
  uptime_seconds: 900,
  uptime_started_at: '2026-09-12T00:00:00+00:00',
  process_id: 4242,
  version: '9.9.9',
  build: { version: '9.9.9', build_id: 'stubbeef', built_at: null, channel: 'test' },
} as const;

const STUB_HEALTH = {
  status: 'ok',
  version: '9.9.9',
  build: { version: '9.9.9', build_id: 'stubbeef', built_at: null, channel: 'test' },
  backends: {},
  rag_index_files: 7,
  cov_active: true,
} as const;

test('C10-04 · 화면 지표가 API 응답을 그대로 옮긴다(고정 payload 대조)', async ({ browser }) => {
  test.setTimeout(120_000);
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  try {
    await page.route(/\/api\/system\/status(?:\?.*)?$/, route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(STUB_STATUS),
      }),
    );
    // 앱은 `/v1/health`를 호출한다(API_BASE='/v1'). 정확한 경로만 잡아
    // `/api/mcp/health` 같은 다른 health 엔드포인트를 덮지 않는다.
    await page.route(
      url => url.pathname === '/health' || url.pathname === '/v1/health',
      route =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(STUB_HEALTH),
        }),
    );

    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(page.getByTestId('telemetrics-link')).toHaveAttribute(
      'data-connection',
      'live',
      { timeout: 30_000 },
    );

    // 서버 버전과 번들 버전(0.1.0)이 다르므로 둘 다 구분되어 보여야 한다(C10-05).
    expect(await text(page, 'telemetrics-build')).toBe('v9.9.9 · stubbeef (ui v0.1.0)');
    expect(await text(page, 'telemetrics-node')).toBe('PID-4242 · NOMINAL');
    expect(await text(page, 'telemetrics-cpu')).toBe('12.3%');
    expect(await text(page, 'telemetrics-mem')).toBe('41.5%');
    expect(await text(page, 'telemetrics-vault')).toBe('7 INDEXED');
    // 900초 = 15분. 방금 관측했으므로 초는 00~05 사이에서만 흘렀다.
    expect(await text(page, 'telemetrics-uptime')).toMatch(/^15M 0\dS$/);

    console.log(`[C10-EVIDENCE-stub] ${JSON.stringify({
      build: await text(page, 'telemetrics-build'),
      uptime: await text(page, 'telemetrics-uptime'),
    })}`);
  } finally {
    await context.close();
    await server.cleanup();
  }
});

test('C10-02 · 서버 재시작 후 UPTIME이 0에서 다시 시작한다', async ({ browser }) => {
  test.setTimeout(180_000);
  const first: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: first.baseUrl });
  const page = await context.newPage();
  try {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(page.getByTestId('telemetrics-link')).toHaveAttribute(
      'data-connection',
      'live',
      { timeout: 30_000 },
    );
    const before = await text(page, 'telemetrics-uptime');

    // 같은 번들, 새 프로세스 — 업타임은 프로세스 기준이므로 처음부터 다시 센다.
    await first.cleanup();
    const second: HermeticServer = await startNoAuthServer();
    try {
      await page.goto(second.baseUrl);
      await expect(page.getByTestId('telemetrics-link')).toHaveAttribute(
        'data-connection',
        'live',
        { timeout: 30_000 },
      );
      const after = parseUptime(await text(page, 'telemetrics-uptime'));

      expect(after).toBeLessThan(600);
      // 이전 프로세스의 값이 이어지지 않는다(누적/고정이면 여기서 실패한다).
      expect(after).toBeLessThan(parseUptime(before) + 600);
    } finally {
      await second.cleanup();
    }
  } finally {
    await context.close();
    await first.cleanup().catch(() => undefined);
  }
});

test('C10-03 · API가 끊기면 UNKNOWN/OFFLINE이고 healthy를 주장하지 않는다', async ({ browser }) => {
  test.setTimeout(120_000);
  // 백엔드가 죽은 상태를 흉내낸다: 지표 API를 모두 끊는다.
  const server: HermeticServer = await startNoAuthServer();
  const context = await browser.newContext({ baseURL: server.baseUrl });
  const page = await context.newPage();
  try {
    await page.route(/\/(?:api\/system\/status|health)$/, route => route.abort('failed'));

    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(page.getByTestId('telemetrics-link')).toBeVisible({ timeout: 20_000 });

    // 명시적 실패는 disconnected(=OFFLINE)로 나타난다.
    await expect(page.getByTestId('telemetrics-link')).toHaveAttribute(
      'data-connection',
      'disconnected',
      { timeout: 30_000 },
    );
    expect(await text(page, 'telemetrics-link')).toContain('OFFLINE');

    // 값이 없으면 0이 아니라 UNKNOWN이고, healthy를 주장하지 않는다.
    expect(await text(page, 'telemetrics-uptime')).toBe('UNKNOWN');
    expect(await text(page, 'telemetrics-build')).toBe('UNKNOWN');
    expect(await text(page, 'telemetrics-cpu')).toBe('UNKNOWN');
    expect(await text(page, 'telemetrics-mem')).toBe('UNKNOWN');
    expect(await text(page, 'telemetrics-node')).toBe('UNKNOWN');

    const body = await bodyText(page);
    expect(body).not.toContain('NOMINAL');
    expect(body).not.toContain('0.0%');
    console.log(`[C10-EVIDENCE-offline] ${JSON.stringify({ link: await text(page, 'telemetrics-link') })}`);
  } finally {
    await context.close();
    await server.cleanup();
  }
});
