import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PublishTab from '../PublishTab';

const localSkill = {
  name: 'test-skill', path: '.agent/skills/test-skill', source: 'local',
  version: '1.0.0', tool_count: 3, warnings: [], valid: true,
  has_skill_md: true, has_readme: true,
} as const;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  });
}

function localSkillsResponse(): Response {
  return jsonResponse({ ok: true, skills: [localSkill], count: 1 });
}

describe('PublishTab authenticated requests', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    sessionStorage.setItem('ag_access_token', 'publish-test-token');
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('sends the stored bearer when loading local skills', async () => {
    // Given: a valid local-skills response and an authenticated session.
    fetchMock.mockImplementation(async () => localSkillsResponse());

    // When: the publish tab loads.
    render(<PublishTab />);
    await screen.findByText('test-skill');

    // Then: the protected local endpoint receives the bearer.
    const [url, options] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/system/skills/local');
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer publish-test-token');
  });

  it('opens PIN guidance instead of an empty list when local loading is unauthorized', async () => {
    // Given: the protected endpoint rejects the session.
    fetchMock.mockImplementation(async () => jsonResponse({ error: 'unauthorized' }, 401));
    const pinRequired = vi.fn();
    window.addEventListener('agk:pin-required', pinRequired);

    try {
      // When: the publish tab loads.
      render(<PublishTab />);

      // Then: authentication and retry are visible, without a false empty state.
      expect(await screen.findByRole('alert')).toHaveTextContent(/PIN/);
      expect(pinRequired).toHaveBeenCalledOnce();
      expect(screen.getByRole('button', { name: '로컬 스킬 다시 시도' })).toBeEnabled();
      expect(screen.queryByText(/로컬 스킬이 없습니다/)).not.toBeInTheDocument();
    } finally {
      window.removeEventListener('agk:pin-required', pinRequired);
    }
  });

  it('shows a request error instead of empty when local loading fails', async () => {
    // Given: an unavailable server.
    fetchMock.mockImplementation(async () => jsonResponse({ error: 'unavailable' }, 503));

    // When: the publish tab loads.
    render(<PublishTab />);

    // Then: the failure remains visible and retryable.
    expect(await screen.findByRole('alert')).toHaveTextContent(/503/);
    expect(screen.queryByText(/로컬 스킬이 없습니다/)).not.toBeInTheDocument();
  });

  it('shows an application failure when local loading returns an unsuccessful envelope', async () => {
    // Given: the backend reports a failure through its HTTP 200 response.
    fetchMock.mockImplementation(async () => jsonResponse({ ok: false, skills: [], count: 0, error: 'local load failed' }));

    // When: the publish tab loads.
    render(<PublishTab />);

    // Then: the unsuccessful response remains an error rather than an empty list.
    expect(await screen.findByRole('alert')).toHaveTextContent('local load failed');
    expect(screen.queryByText(/로컬 스킬이 없습니다/)).not.toBeInTheDocument();
  });

  it('shows a response error when the local skill payload is malformed', async () => {
    // Given: a successful HTTP response with invalid skill data.
    fetchMock.mockImplementation(async () => jsonResponse({ ok: true, skills: [{ name: 'broken' }], count: 1 }));

    // When: the publish tab loads.
    render(<PublishTab />);

    // Then: malformed data does not become a usable card or empty state.
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('broken')).not.toBeInTheDocument();
    expect(screen.queryByText(/로컬 스킬이 없습니다/)).not.toBeInTheDocument();
  });

  it('retains cached skills when refreshing fails and clears the error after retry', async () => {
    // Given: an existing local list followed by a failed refresh.
    fetchMock.mockImplementationOnce(async () => localSkillsResponse());
    fetchMock.mockImplementationOnce(async () => jsonResponse({ error: 'unavailable' }, 503));
    fetchMock.mockImplementation(async () => localSkillsResponse());
    render(<PublishTab />);
    await screen.findByText('test-skill');

    // When: the user refreshes, then retries the failed load.
    fireEvent.click(screen.getByRole('button', { name: /새로고침/ }));
    await screen.findByRole('alert');
    expect(screen.getByText('test-skill')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '로컬 스킬 다시 시도' }));

    // Then: the confirmed list remains available and the failure clears.
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByText('test-skill')).toBeInTheDocument();
  });

  it.each([
    { mode: 'npm', path: '/api/system/skills/publish-npm', action: 'npm_publish' },
    { mode: 'github', path: '/api/system/skills/publish-github', action: 'github_pr' },
  ])('sends the bearer to $mode validation when publishing is requested', async ({ mode, path, action }) => {
    // Given: a local skill and an HTTP fake for the publish operation.
    fetchMock.mockImplementation(async url => String(url) === '/api/system/skills/local'
      ? localSkillsResponse()
      : jsonResponse({ ok: true, publish_result: {
        success: true, action, skill_name: 'test-skill', errors: [], warnings: [], summary: 'validated',
        package_name: null, version: null, npm_url: null, pr_url: null,
      } }));
    render(<PublishTab />);
    fireEvent.click(await screen.findByRole('button', { name: /test-skill/ }));
    if (mode === 'github') fireEvent.click(screen.getByRole('button', { name: /GitHub PR/ }));

    // When: the user requests dry-run validation through the UI.
    fireEvent.click(screen.getByRole('button', { name: /Validate & Dry-run/ }));

    // Then: the original route/body and bearer reach the HTTP boundary.
    await screen.findByText('validated');
    const [, options] = fetchMock.mock.calls.find(([url]) => url === path) ?? [];
    expect(options?.method).toBe('POST');
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer publish-test-token');
    expect(JSON.parse(String(options?.body))).toMatchObject({ skill_name: 'test-skill', dry_run: true });
  });

  it('shows PIN guidance and permits retry when publishing is unauthorized', async () => {
    // Given: a local skill and an unauthorized HTTP fake for publishing.
    fetchMock.mockImplementation(async url => String(url) === '/api/system/skills/local'
      ? localSkillsResponse()
      : jsonResponse({ error: 'unauthorized' }, 401));
    const pinRequired = vi.fn();
    window.addEventListener('agk:pin-required', pinRequired);
    render(<PublishTab />);
    fireEvent.click(await screen.findByRole('button', { name: /test-skill/ }));

    try {
      // When: dry-run validation receives a 401.
      fireEvent.click(screen.getByRole('button', { name: /Validate & Dry-run/ }));

      // Then: the failure explains authentication and enables an explicit retry.
      expect(await screen.findByRole('alert')).toHaveTextContent(/PIN/);
      expect(pinRequired).toHaveBeenCalledOnce();
      expect(screen.getByRole('button', { name: /Validate & Dry-run/ })).toBeEnabled();
    } finally {
      window.removeEventListener('agk:pin-required', pinRequired);
    }
  });
});
