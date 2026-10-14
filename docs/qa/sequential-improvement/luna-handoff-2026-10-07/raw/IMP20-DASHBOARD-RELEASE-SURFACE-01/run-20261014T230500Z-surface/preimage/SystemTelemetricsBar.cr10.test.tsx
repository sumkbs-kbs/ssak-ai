/**
 * SystemTelemetricsBar · CR-10 운영 지표 계약
 * ============================================
 * BASELINE F06: "SystemTelemetricsBar.tsx BUILD v0.8.0-RC, UPTIME 14D 08H 12M 고정;
 * healthy 부재를 true 처리". 소스와 새 QA 서버 화면 교차 확인.
 *
 * 고정하는 계약:
 *  - C10-01: BUILD는 실행 중인 서버 버전(+빌드 식별자)을 그대로 쓴다. 하드코딩 금지.
 *  - C10-02: UPTIME은 **API 서버 프로세스** 가동 시간이다(탭 열린 시간이 아님).
 *  - C10-03: 미관측(UNKNOWN) / stale / offline / 유효한 0을 서로 구분한다.
 *  - C10-04: 화면 값이 API 의미와 일치한다(MEM은 percent, PID는 정수).
 *  - C10-05: 고정 문구(CTRL)를 제거하고 번들 버전이 서버와 다르면 함께 표시한다.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const uiBuild = vi.hoisted(() => ({
  info: { version: '0.1.0', buildId: 'abcdef0', builtAt: null as string | null },
}));

vi.mock('../../../utils/uiBuildInfo', () => ({
  getUiBuildInfo: () => uiBuild.info,
}));

import SystemTelemetricsBar, {
  STALE_AFTER_MS,
  deriveConnectionState,
  formatAge,
  formatUptime,
} from '../SystemTelemetricsBar';
import { useUiStore, type SystemStatus } from '../../../stores/uiStore';

const DEFAULTS: SystemStatus = {
  healthy: null,
  backends: {},
  ragFiles: null,
  covActive: false,
  cpuPercent: null,
  memoryPercent: null,
  totalTokens: null,
  version: null,
  buildId: null,
  uptimeSeconds: null,
  startedAt: null,
  processId: null,
  observedAt: null,
  state: 'unknown',
};

function setStatus(overrides: Partial<SystemStatus>): void {
  useUiStore.setState({ systemStatus: { ...DEFAULTS, ...overrides } });
}

function renderBar(): void {
  render(
    <MemoryRouter>
      <SystemTelemetricsBar />
    </MemoryRouter>,
  );
}

function value(testId: string): string {
  return screen.getByTestId(testId).textContent ?? '';
}

beforeEach(() => {
  uiBuild.info = { version: '0.1.0', buildId: 'abcdef0', builtAt: null };
  setStatus({});
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('CR-10 helper 계약', () => {
  it('formatUptime은 0초를 유효값으로 렌더한다(UNKNOWN이 아니다)', () => {
    expect(formatUptime(0)).toBe('0M 00S');
    expect(formatUptime(59)).toBe('0M 59S');
    expect(formatUptime(90)).toBe('1M 30S');
    expect(formatUptime(3600)).toBe('1H 00M');
    expect(formatUptime(90_000)).toBe('1D 01H 00M');
  });

  it('formatUptime은 음수를 0으로 클램프한다', () => {
    expect(formatUptime(-5)).toBe('0M 00S');
  });

  it('formatAge는 경과 시간을 사람이 읽는 형태로 만든다', () => {
    expect(formatAge(1_000, 1_500)).toBe('now');
    expect(formatAge(1_000, 6_000)).toBe('5s ago');
    expect(formatAge(1_000, 121_000)).toBe('2m ago');
    expect(formatAge(1_000, 3_601_000)).toBe('1h ago');
  });

  it('deriveConnectionState는 미관측/오래됨/단절을 구분한다', () => {
    const now = 1_000_000;
    expect(deriveConnectionState('unknown', null, now)).toBe('unknown');
    expect(deriveConnectionState('live', null, now)).toBe('unknown');
    expect(deriveConnectionState('live', now - 1_000, now)).toBe('live');
    expect(deriveConnectionState('live', now - STALE_AFTER_MS - 1, now)).toBe('stale');
    expect(deriveConnectionState('disconnected', now - 1_000, now)).toBe('disconnected');
    // 단절은 관측이 방금 전이어도 UNKNOWN/stale로 되돌아가지 않는다.
    expect(deriveConnectionState('disconnected', now, now)).toBe('disconnected');
  });
});

describe('SystemTelemetricsBar · CR-10', () => {
  it('C10-03: 관측 전에는 모든 지표가 UNKNOWN이고 하드코딩 값이 없다', () => {
    renderBar();

    for (const id of ['telemetrics-build', 'telemetrics-uptime', 'telemetrics-cpu', 'telemetrics-mem', 'telemetrics-vault']) {
      expect(value(id)).toBe('UNKNOWN');
    }
    expect(value('telemetrics-node')).toBe('UNKNOWN');
    expect(value('telemetrics-link')).toBe('UNKNOWN');

    const text = document.body.textContent ?? '';
    // F06의 고정 문자열이 화면에 남아 있으면 실패한다.
    expect(text).not.toContain('v0.8.0-RC');
    expect(text).not.toContain('14D 08H 12M');
    expect(text).not.toContain('LOCAL-01');
    expect(text).not.toContain('OPEN INTAKE WAVE 01');
    // 정보 없는 healthy 기본값 true도 금지.
    expect(text).not.toContain('NOMINAL');
  });

  it('C10-01/C10-04: 실제 서버 버전·PID·percent 값을 그대로 표시한다', () => {
    setStatus({
      state: 'live',
      observedAt: Date.now(),
      healthy: true,
      version: '0.1.0',
      buildId: 'abc1234',
      processId: 4242,
      cpuPercent: 12.3,
      memoryPercent: 41.5,
      ragFiles: 7,
      uptimeSeconds: 0,
    });
    renderBar();

    expect(value('telemetrics-build')).toBe('v0.1.0 · abc1234');
    expect(value('telemetrics-node')).toBe('PID-4242 · NOMINAL');
    expect(value('telemetrics-cpu')).toBe('12.3%');
    // API는 memory_percent를 준다 — MB로 표기하면 오해를 부른다.
    expect(value('telemetrics-mem')).toBe('41.5%');
    expect(value('telemetrics-vault')).toBe('7 INDEXED');
    expect(screen.getByTestId('telemetrics-link').dataset.connection).toBe('live');
  });

  it('C10-03: CPU 0과 uptime 0은 UNKNOWN이 아니라 유효값이다', () => {
    setStatus({
      state: 'live',
      observedAt: Date.now(),
      healthy: true,
      version: '0.1.0',
      buildId: null,
      processId: 1,
      cpuPercent: 0,
      memoryPercent: 0,
      ragFiles: 0,
      uptimeSeconds: 0,
    });
    renderBar();

    expect(value('telemetrics-cpu')).toBe('0.0%');
    expect(value('telemetrics-mem')).toBe('0.0%');
    expect(value('telemetrics-vault')).toBe('0 INDEXED');
    expect(value('telemetrics-uptime')).toMatch(/^0M 0\dS$/);
    expect(value('telemetrics-uptime')).not.toBe('UNKNOWN');
  });

  it('C10-02: uptime은 서버 값에서 관측 이후 경과분만 보간한다', () => {
    setStatus({
      state: 'live',
      observedAt: Date.now() - 5_000,
      healthy: true,
      version: '0.1.0',
      uptimeSeconds: 3_600,
    });
    renderBar();

    // 1H 00M (+ 관측 후 5초). 탭이 열린 시간(수 초)이 아니라 서버 uptime이다.
    expect(value('telemetrics-uptime')).toBe('1H 00M');
  });

  it('C10-03: 폴링이 오래 끊기면 STALE, 명시적 실패는 OFFLINE이다', () => {
    setStatus({
      state: 'live',
      observedAt: Date.now() - STALE_AFTER_MS - 5_000,
      healthy: true,
      version: '0.1.0',
      uptimeSeconds: 100,
    });
    renderBar();
    expect(screen.getByTestId('telemetrics-link').dataset.connection).toBe('stale');
    expect(value('telemetrics-link')).toContain('STALE');
    // stale이어도 마지막 관측 시각을 숨기지 않는다.
    expect(value('telemetrics-link')).toMatch(/\d+s ago/);
    // stale 중에는 마지막 값에서 uptime을 계속 늘리지 않는다.
    expect(value('telemetrics-uptime')).toBe('1M 40S');

    cleanup();
    setStatus({ state: 'disconnected', observedAt: Date.now() - 5_000, healthy: null });
    renderBar();
    expect(screen.getByTestId('telemetrics-link').dataset.connection).toBe('disconnected');
    expect(value('telemetrics-link')).toContain('OFFLINE');
    // 연결이 끊기면 health를 주장하지 않는다.
    expect(value('telemetrics-node')).toBe('UNKNOWN');
  });

  it('C10-05: 번들 버전이 서버와 다르면 오해 없게 함께 표시한다', () => {
    uiBuild.info = { version: '0.2.0', buildId: 'feedbee', builtAt: null };
    setStatus({
      state: 'live',
      observedAt: Date.now(),
      healthy: true,
      version: '0.1.0',
      buildId: 'abc1234',
    });
    renderBar();

    const build = value('telemetrics-build');
    expect(build).toContain('v0.1.0 · abc1234');
    expect(build).toContain('ui v0.2.0');
  });

  it('C10-04: 서버가 DEGRADED면 NOMINAL로 위장하지 않는다', () => {
    setStatus({
      state: 'live',
      observedAt: Date.now(),
      healthy: false,
      version: '0.1.0',
      processId: 9,
    });
    renderBar();

    expect(value('telemetrics-node')).toBe('PID-9 · DEGRADED');
    expect(screen.getByTestId('telemetrics-node').dataset.health).toBe('false');
    expect(document.body.textContent).not.toContain('NOMINAL');
  });
});
