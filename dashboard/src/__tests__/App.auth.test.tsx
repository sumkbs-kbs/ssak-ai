import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../App';
import { useUiStore } from '../stores/uiStore';

const unauthorizedFetch = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async () => (
  new Response(JSON.stringify({ detail: 'Invalid or missing credentials', ok: false }), {
    status: 401,
    headers: { 'Content-Type': 'application/json' },
  })
));

const protectedSocketUrls: string[] = [];

class RecordingWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;

  readonly url: string;
  readyState = RecordingWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string | URL) {
    this.url = url.toString();
    protectedSocketUrls.push(this.url);
  }

  close() {
    this.readyState = 3;
  }
}

function protectedRequestPaths(): string[] {
  return unauthorizedFetch.mock.calls
    .map(([input]) => new URL(input.toString(), window.location.origin).pathname)
    .filter(path => ['/api/', '/v1/', '/ws/', '/ide/'].some(prefix => path.startsWith(prefix)));
}

describe('dashboard access gate', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    document.cookie = 'ag_access_pin=; path=/; max-age=0; SameSite=Strict';
    useUiStore.setState({ pinModalVisible: true });
    unauthorizedFetch.mockReset().mockImplementation(async () => new Response(
      JSON.stringify({ detail: 'Invalid or missing credentials', ok: false }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    ));
    protectedSocketUrls.length = 0;
    vi.stubGlobal('fetch', unauthorizedFetch);
    vi.stubGlobal('WebSocket', RecordingWebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('does not start protected traffic when no access PIN is stored', async () => {
    render(<App />);

    expect(await screen.findByRole('dialog', { name: 'PIN 인증' })).toBeVisible();
    expect(protectedRequestPaths()).toEqual(['/api/session/info']);
    expect(protectedSocketUrls).toEqual([]);
  });

  it('rejects a stale stored token before starting dashboard traffic', async () => {
    sessionStorage.setItem('ag_access_token', 'stale-token');
    useUiStore.setState({ pinModalVisible: false });
    render(<App />);

    expect(await screen.findByRole('dialog', { name: 'PIN 인증' })).toBeVisible();
    expect(protectedRequestPaths()).toEqual(['/api/session/info']);
    expect(protectedSocketUrls).toEqual([]);
    expect(sessionStorage.getItem('ag_access_token')).toBeNull();
    expect(screen.getByLabelText('PIN 번호')).toHaveFocus();
    expect(screen.getByRole('button', { name: '잠금 해제' })).toBeEnabled();
  });

  it('does not persist a rejected PIN across reloads', async () => {
    render(<App />);

    fireEvent.change(await screen.findByLabelText('PIN 번호'), { target: { value: 'wrong-pin' } });
    fireEvent.click(screen.getByRole('button', { name: '잠금 해제' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('PIN 번호가 올바르지 않습니다.');
    expect(localStorage.getItem('ag_access_pin')).toBeNull();
    expect(sessionStorage.getItem('ag_access_token')).toBeNull();
    expect(document.cookie).not.toContain('ag_access_pin=');
    expect(protectedSocketUrls).toEqual([]);
  });

  it.each([
    { name: 'a connection failure', response: () => Promise.reject(new TypeError('Failed to fetch')), message: '서버에 연결할 수 없습니다. 서버 실행 상태와 네트워크를 확인하세요.' },
    { name: 'an unavailable authentication service', response: async () => new Response('', { status: 503 }), message: '인증 서버를 사용할 수 없습니다. 잠시 후 다시 시도하세요.' },
    { name: 'a locked authentication attempt', response: async () => new Response('', { status: 403 }), message: '인증 시도가 잠겼습니다. 잠시 후 다시 시도하세요.' },
    { name: 'too many authentication requests', response: async () => new Response('', { status: 429 }), message: '인증 요청이 너무 많습니다. 잠시 후 다시 시도하세요.' },
    { name: 'a missing success token', response: async () => new Response('{}', { status: 200 }), message: '인증 응답을 확인할 수 없습니다. 잠시 후 다시 시도하세요.' },
    { name: 'malformed success JSON', response: async () => new Response('not json', { status: 200 }), message: '인증 응답을 확인할 수 없습니다. 잠시 후 다시 시도하세요.' },
    { name: 'another rejected request', response: async () => new Response('private backend detail', { status: 400 }), message: '인증을 완료할 수 없습니다. 잠시 후 다시 시도하세요.' },
  ])('shows the specific failure when login encounters $name', async ({ response, message }) => {
    // Given: a locked dashboard and the failing login boundary.
    render(<App />);
    fireEvent.change(await screen.findByLabelText('PIN 번호'), { target: { value: 'test-pin' } });
    unauthorizedFetch.mockImplementation(response);

    // When: the user submits the PIN.
    fireEvent.click(screen.getByRole('button', { name: '잠금 해제' }));

    // Then: the failure category is visible and authentication stays locked.
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(screen.getByRole('dialog', { name: 'PIN 인증' })).toBeVisible();
    expect(sessionStorage.getItem('ag_access_token')).toBeNull();
    expect(protectedSocketUrls).toEqual([]);
  });

  it('mounts the dashboard only after a stored PIN is successfully validated', async () => {
    sessionStorage.setItem('ag_access_token', 'valid-token');
    unauthorizedFetch.mockImplementation(async (input: RequestInfo | URL) => {
      const path = new URL(input.toString(), window.location.origin).pathname;
      return new Response(JSON.stringify(path === '/api/session/info'
        ? { ok: true, session: {} }
        : { ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    render(<App />);

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'PIN 인증' })).not.toBeInTheDocument());
    await waitFor(() => expect(protectedSocketUrls).not.toEqual([]));
    expect(protectedRequestPaths()[0]).toBe('/api/session/info');
  });
});
