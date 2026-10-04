/**
 * CR-07 — 화면 오류 복구와 잘못된 경로 (계약 스위트)
 * ================================================
 * 발견 F03: lazy/Suspense만 있고 오류 경계와 404가 없어서
 *   ① 없는 경로는 아무 안내 없이 빈 화면이 되고
 *   ② 페이지 하나가 던진 예외가 셸 전체(사이드바·로그인 이후 UI)를 지웠다.
 *
 * 이 스위트는 그 두 결함과 다음 계약을 고정한다.
 *   C07-01 chunk 로드 실패 → 안내 + 안전 재로드
 *   C07-02 render 예외 → 오류 식별자 + 재시도/새로고침, stack/secret 미노출
 *   C07-03 없는 경로 → 404 안내 + 홈 복귀(+뒤로가기)
 *   C07-04 오류가 대화/로컬 히스토리 저장소를 지우지 않는다
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import React from 'react';

/* 페이지 하나가 렌더 중 예외를 던지는 fixture. */
vi.mock('../pages/HistoryPage', () => ({
  default: () => {
    throw new Error('cr07-fixture-render-error');
  },
}));

import App from '../App';
import AppErrorBoundary from '../components/UI/AppErrorBoundary';
import NotFoundPage from '../pages/NotFoundPage';
import { useUiStore } from '../stores/uiStore';

const CHAT_STORAGE_KEY = 'antigravity_chat_default';
const HISTORY_STORAGE_KEY = 'agk_local_history:v1';

function ThrowOnce({ fail }: { fail: { current: boolean } }): React.ReactElement {
  if (fail.current) throw new Error('cr07-fixture-render-error');
  return <div data-testid="cr07-healthy-child">정상 렌더</div>;
}

function ChunkFailure(): React.ReactElement {
  throw new Error('Failed to fetch dynamically imported module: /assets/HistoryPage-abc.js');
}

function okFetch(): ReturnType<typeof vi.fn> {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = input.toString();
    if (url.includes('/api/session/info')) {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
}

function renderAppAt(path: string): void {
  window.history.pushState({}, '', path);
  render(<App />);
}

describe('AppErrorBoundary · CR-07', () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    localStorage.clear();
    // jsdom은 경계가 잡은 예외도 console.error로 남긴다 — 테스트 출력에서 숨긴다.
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    consoleError.mockRestore();
  });

  // ── C07-02 ────────────────────────────────────────────────────
  it('replaces a throwing child with a recovery UI that leaks no error text', () => {
    render(
      <AppErrorBoundary scope="route">
        <ThrowOnce fail={{ current: true }} />
      </AppErrorBoundary>,
    );

    expect(screen.getByTestId('cr07-recovery')).toBeInTheDocument();
    // 식별자는 있지만 원문 메시지/스택은 화면에 없다.
    expect(screen.getByTestId('cr07-error-id').textContent).toMatch(/E-[0-9A-F]{8}/);
    expect(screen.queryByText(/cr07-fixture-render-error/)).not.toBeInTheDocument();
    expect(screen.queryByText(/at ThrowOnce|Error:/)).not.toBeInTheDocument();
    expect(document.body.textContent ?? '').not.toContain('cr07-fixture-render-error');
  });

  it('offers retry for a render error and recovers when the child stops throwing', () => {
    const fail = { current: true };
    render(
      <AppErrorBoundary scope="route">
        <ThrowOnce fail={fail} />
      </AppErrorBoundary>,
    );
    expect(screen.getByTestId('cr07-recovery')).toBeInTheDocument();

    fail.current = false;
    fireEvent.click(screen.getByTestId('cr07-retry'));

    expect(screen.getByTestId('cr07-healthy-child')).toBeInTheDocument();
    expect(screen.queryByTestId('cr07-recovery')).not.toBeInTheDocument();
  });

  it('counts repeated retries instead of pretending to recover', () => {
    render(
      <AppErrorBoundary scope="route">
        <ThrowOnce fail={{ current: true }} />
      </AppErrorBoundary>,
    );

    fireEvent.click(screen.getByTestId('cr07-retry'));
    fireEvent.click(screen.getByTestId('cr07-retry'));

    expect(screen.getByTestId('cr07-recovery')).toBeInTheDocument();
    expect(screen.getByTestId('cr07-attempts').textContent).toMatch(/3/);
  });

  it('calls the injected safe reload handler', () => {
    const onReload = vi.fn();
    render(
      <AppErrorBoundary scope="route" onReload={onReload}>
        <ThrowOnce fail={{ current: true }} />
      </AppErrorBoundary>,
    );

    fireEvent.click(screen.getByTestId('cr07-reload'));
    expect(onReload).toHaveBeenCalledOnce();
  });

  // ── C07-01 ────────────────────────────────────────────────────
  it('treats a chunk load failure as a redeploy/reload case, not a retry case', () => {
    render(
      <AppErrorBoundary scope="route">
        <ChunkFailure />
      </AppErrorBoundary>,
    );

    const recovery = screen.getByTestId('cr07-recovery');
    expect(recovery).toHaveAttribute('data-error-kind', 'chunk');
    expect(recovery.textContent).toMatch(/새 버전|배포|네트워크/);
    // 같은 URL의 실패한 모듈은 다시 import해도 실패하므로 재시도를 약속하지 않는다.
    expect(screen.queryByTestId('cr07-retry')).not.toBeInTheDocument();
    expect(screen.getByTestId('cr07-reload')).toBeInTheDocument();
  });

  it('marks a generic render error with the render kind', () => {
    render(
      <AppErrorBoundary scope="route">
        <ThrowOnce fail={{ current: true }} />
      </AppErrorBoundary>,
    );

    expect(screen.getByTestId('cr07-recovery')).toHaveAttribute('data-error-kind', 'render');
  });

  // ── C07-04 ────────────────────────────────────────────────────
  it('never clears the conversation or local history storage on error', () => {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify([{ id: 'm1', content: '보존되어야 함' }]));
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify([{ id: 's1' }]));
    const before: Record<string, string | null> = {};
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key !== null) before[key] = localStorage.getItem(key);
    }
    expect(Object.keys(before)).toContain(CHAT_STORAGE_KEY);

    render(
      <AppErrorBoundary scope="route">
        <ThrowOnce fail={{ current: true }} />
      </AppErrorBoundary>,
    );
    fireEvent.click(screen.getByTestId('cr07-retry'));

    for (const [key, value] of Object.entries(before)) {
      expect(localStorage.getItem(key)).toEqual(value);
    }
  });
});

describe('NotFoundPage · CR-07', () => {
  afterEach(cleanup);

  function renderNotFound(): void {
    render(
      <MemoryRouter initialEntries={['/definitely-missing?x=1']}>
        <Routes>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('explains the wrong path and offers a home action', () => {
    renderNotFound();

    expect(screen.getByTestId('cr07-not-found')).toBeInTheDocument();
    expect(screen.getByTestId('cr07-not-found-path').textContent).toContain('/definitely-missing');
    expect(screen.getByTestId('cr07-not-found-home')).toBeInTheDocument();
  });

  it('navigates home and back from the not-found screen', () => {
    const navigations: string[] = [];
    function Navigator(): React.ReactElement {
      const navigate = useNavigate();
      return (
        <button
          type="button"
          data-testid="cr07-goto-missing"
          onClick={() => navigate('/definitely-missing')}
        />
      );
    }
    function Home(): React.ReactElement {
      navigations.push('home');
      return <div data-testid="cr07-home" />;
    }

    render(
      <MemoryRouter initialEntries={['/definitely-missing']}>
        <Navigator />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('cr07-not-found-home'));
    expect(screen.getByTestId('cr07-home')).toBeInTheDocument();
  });
});

describe('App route recovery wiring · CR-07', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    useUiStore.setState({ pinModalVisible: false });
    vi.stubGlobal('fetch', okFetch());
    vi.stubGlobal('WebSocket', class {
      readyState = 1;
      onopen: (() => void) | null = null;
      onmessage: (() => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(public url: string) {}
      close() { this.readyState = 3; }
    });
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  // ── C07-03 ────────────────────────────────────────────────────
  it('renders a not-found screen inside the shell for an unknown deep link', async () => {
    renderAppAt('/cr07-definitely-missing');

    await waitFor(() => expect(screen.getByTestId('cr07-not-found')).toBeInTheDocument());
    // 셸은 그대로 남는다(로그인/사이드바가 fallback에 묻히지 않는다).
    await waitFor(() => expect(screen.getByLabelText('SSAK-AI 탐색')).toBeInTheDocument());
  });

  it('keeps the stored conversation when a not-found route is shown', async () => {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify([{ id: 'm1', content: '보존' }]));

    renderAppAt('/cr07-definitely-missing');
    await waitFor(() => expect(screen.getByTestId('cr07-not-found')).toBeInTheDocument());

    expect(localStorage.getItem(CHAT_STORAGE_KEY)).toBe(JSON.stringify([{ id: 'm1', content: '보존' }]));
  });

  // ── C07-02 (앱 통합) ──────────────────────────────────────────
  it('keeps the shell alive when a page throws during render', async () => {
    renderAppAt('/history');

    await waitFor(() => expect(screen.getByTestId('cr07-recovery')).toBeInTheDocument());
    expect(screen.getByLabelText('SSAK-AI 탐색')).toBeInTheDocument();
  });

  it('lets the user escape a broken page by navigating elsewhere', async () => {
    renderAppAt('/history');
    await waitFor(() => expect(screen.getByTestId('cr07-recovery')).toBeInTheDocument());

    // 다른 경로로 이동하면 route 경계가 초기화되어 정상 화면이 다시 뜬다.
    window.history.pushState({}, '', '/settings');
    window.dispatchEvent(new PopStateEvent('popstate'));

    await waitFor(() => expect(screen.queryByTestId('cr07-recovery')).not.toBeInTheDocument());
    expect(screen.getByLabelText('SSAK-AI 탐색')).toBeInTheDocument();
  });
});
