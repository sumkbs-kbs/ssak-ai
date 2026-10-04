const ACCESS_PIN_KEY = 'ag_access_pin';
const ACCESS_TOKEN_KEY = 'ag_access_token';

function clearLegacyAccessPin(): void {
  try {
    window.localStorage.removeItem(ACCESS_PIN_KEY);
  } finally {
    document.cookie = `${ACCESS_PIN_KEY}=; path=/; max-age=0; SameSite=Strict${
      window.location.protocol === 'https:' ? '; Secure' : ''
    }`;
  }
}

export function readStoredAccessToken(): string | null {
  if (typeof window === 'undefined') return null;

  try {
    const token = window.sessionStorage.getItem(ACCESS_TOKEN_KEY)?.trim() ?? '';
    return token.length > 0 ? token : null;
  } catch {
    return null;
  }
}

export function readLegacyAccessPin(): string | null {
  if (typeof window === 'undefined') return null;

  try {
    const pin = window.localStorage.getItem(ACCESS_PIN_KEY)?.trim() ?? '';
    return pin.length > 0 ? pin : null;
  } catch {
    return null;
  }
}

export function createAccessPinHeaders(initial?: HeadersInit): Headers {
  const headers = new Headers(initial);
  const token = readStoredAccessToken();
  if (token !== null) headers.set('Authorization', `Bearer ${token}`);
  return headers;
}

export function persistAccessToken(token: string): void {
  window.sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
  clearLegacyAccessPin();
}

export function clearAccessCredential(): void {
  try {
    window.sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  } finally {
    clearLegacyAccessPin();
  }
}

export const clearAccessPin = clearAccessCredential;

export class AccessPinLoginError extends Error {
  readonly name = 'AccessPinLoginError';

  constructor(readonly kind: 'invalid_pin' | 'locked' | 'rate_limited' | 'network' | 'service_unavailable' | 'invalid_response' | 'request_failed') {
    super('PIN authentication failed.');
  }
}

export async function loginWithAccessPin(pin: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin }),
    });
  } catch (error) {
    if (error instanceof TypeError || error instanceof DOMException) throw new AccessPinLoginError('network');
    throw error;
  }
  if (!response.ok) {
    switch (response.status) {
      case 401: throw new AccessPinLoginError('invalid_pin');
      case 403: throw new AccessPinLoginError('locked');
      case 429: throw new AccessPinLoginError('rate_limited');
      default: throw new AccessPinLoginError(response.status >= 500 && response.status < 600 ? 'service_unavailable' : 'request_failed');
    }
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch (error) {
    if (error instanceof Error) throw new AccessPinLoginError('invalid_response');
    throw error;
  }
  if (
    typeof payload !== 'object' ||
    payload === null ||
    !('access_token' in payload) ||
    typeof payload.access_token !== 'string' ||
    payload.access_token.trim().length === 0
  ) {
    throw new AccessPinLoginError('invalid_response');
  }

  const token = payload.access_token.trim();
  persistAccessToken(token);
  return token;
}
