import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import PublishTab from '../PublishTab';

function skillsResponse(name = 'confirmed-skill'): Response {
  return new Response(JSON.stringify({ ok: true, skills: [{
    name, path: `.agent/skills/${name}`, source: 'local', version: '1.0.0',
    tool_count: 0, warnings: [], valid: true, has_skill_md: true, has_readme: true,
  }] }), { headers: { 'Content-Type': 'application/json' } });
}

function deferredResponse() {
  let resolveResponse: (response: Response) => void = () => {};
  const promise = new Promise<Response>(resolve => { resolveResponse = resolve; });
  return { promise, resolve: resolveResponse };
}

describe('PublishTab overlapping local requests', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('retains the latest successful list when an older request fails later', async () => {
    // Given: initial loading is pending and the next poll returns confirmed skills.
    const older = deferredResponse();
    fetchMock.mockImplementationOnce(() => older.promise);
    fetchMock.mockImplementation(async () => skillsResponse());
    render(<PublishTab />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(screen.getByText('confirmed-skill')).toBeInTheDocument();

    // When: the older initial request returns a failure after the successful poll.
    await act(async () => { older.resolve(new Response(null, { status: 503 })); });

    // Then: the confirmed list stays successful.
    expect(screen.getByText('confirmed-skill')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('retains the latest failure and cached list when an older poll succeeds later', async () => {
    // Given: confirmed cached skills and a pending poll followed by a failed newer poll.
    const older = deferredResponse();
    fetchMock.mockImplementationOnce(async () => skillsResponse());
    fetchMock.mockImplementationOnce(() => older.promise);
    fetchMock.mockImplementation(async () => new Response(null, { status: 503 }));
    render(<PublishTab />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(screen.getByRole('alert')).toBeInTheDocument();

    // When: the older poll returns a different list after the latest failure.
    await act(async () => { older.resolve(skillsResponse('outdated-skill')); });

    // Then: the latest failure and last confirmed data remain visible.
    expect(screen.getByRole('alert')).toHaveTextContent(/503/);
    expect(screen.getByText('confirmed-skill')).toBeInTheDocument();
    expect(screen.queryByText('outdated-skill')).not.toBeInTheDocument();
  });

  it('keeps the current request pending when an older request finishes', async () => {
    // Given: confirmed skills and two overlapping polls with controlled responses.
    const older = deferredResponse();
    const current = deferredResponse();
    fetchMock.mockImplementationOnce(async () => skillsResponse());
    fetchMock.mockImplementationOnce(() => older.promise);
    fetchMock.mockImplementationOnce(() => current.promise);
    render(<PublishTab />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });

    // When: only the older poll finishes.
    await act(async () => { older.resolve(skillsResponse()); });

    // Then: refresh remains disabled until the latest request finishes.
    expect(screen.getByRole('button', { name: /새로고침/ })).toBeDisabled();
    expect(screen.getByText(/확인 중/)).toBeInTheDocument();
    await act(async () => { current.resolve(skillsResponse()); });
  });
});
