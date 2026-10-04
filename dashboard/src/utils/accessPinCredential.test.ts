// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearAccessCredential,
  createAccessPinHeaders,
  loginWithAccessPin,
  readLegacyAccessPin,
  readStoredAccessToken,
} from './accessPinCredential';

describe('createAccessPinHeaders', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('does not invent a predictable PIN when no credential is stored', () => {
    const headers = createAccessPinHeaders({ 'Content-Type': 'application/json' });

    expect(headers.get('Content-Type')).toBe('application/json');
    expect(headers.has('X-Access-Pin')).toBe(false);
  });

  it('adds the stored bearer token and never reads the legacy PIN', () => {
    window.localStorage.setItem('ag_access_pin', 'operator-secret');
    window.sessionStorage.setItem('ag_access_token', 'token-value');

    const headers = createAccessPinHeaders();

    expect(headers.get('Authorization')).toBe('Bearer token-value');
    expect(headers.has('X-Access-Pin')).toBe(false);
  });

  it('migrates a legacy PIN through login and stores only the returned token', async () => {
    window.localStorage.setItem('ag_access_pin', 'operator-secret');
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({ access_token: 'token-value', token_type: 'bearer', expires_in: 3600 }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(loginWithAccessPin('operator-secret')).resolves.toBe('token-value');
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ pin: 'operator-secret' }),
    }));
    expect(readStoredAccessToken()).toBe('token-value');
    expect(readLegacyAccessPin()).toBeNull();
    expect(window.sessionStorage.getItem('ag_access_pin')).toBeNull();
    clearAccessCredential();
    vi.unstubAllGlobals();
  });
});

describe('loginWithAccessPin failure categories', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  afterEach(() => vi.unstubAllGlobals());

  it.each([
    { status: 401, kind: 'invalid_pin' },
    { status: 403, kind: 'locked' },
    { status: 429, kind: 'rate_limited' },
    { status: 500, kind: 'service_unavailable' },
    { status: 503, kind: 'service_unavailable' },
    { status: 400, kind: 'request_failed' },
  ])('preserves the $kind category when login returns HTTP $status', async ({ status, kind }) => {
    // Given: the login boundary rejects the request.
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response(
      'private backend detail', { status, statusText: 'private status detail' },
    )));

    // When: authentication is attempted.
    const result = loginWithAccessPin('test-pin');

    // Then: only a safe typed category crosses the boundary.
    await expect(result).rejects.toMatchObject({ name: 'AccessPinLoginError', kind });
    await expect(result).rejects.toHaveProperty('message', 'PIN authentication failed.');
    expect(readStoredAccessToken()).toBeNull();
  });

  it('reports a network failure when the fetch boundary rejects', async () => {
    // Given: the fetch transport cannot connect.
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new TypeError('private transport detail')));

    // When: authentication is attempted.
    const result = loginWithAccessPin('test-pin');

    // Then: no transport detail is exposed as an invalid PIN.
    await expect(result).rejects.toMatchObject({ name: 'AccessPinLoginError', kind: 'network' });
    await expect(result).rejects.toHaveProperty('message', 'PIN authentication failed.');
  });

  it.each(['{}', 'not json'])('reports an invalid response when a success payload is %s', async body => {
    // Given: transport succeeds with an unusable authentication response.
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response(body, { status: 200 })));

    // When: authentication is attempted.
    const result = loginWithAccessPin('test-pin');

    // Then: response failures retain their distinction from connectivity failures.
    await expect(result).rejects.toMatchObject({ name: 'AccessPinLoginError', kind: 'invalid_response' });
    expect(readStoredAccessToken()).toBeNull();
  });
});
