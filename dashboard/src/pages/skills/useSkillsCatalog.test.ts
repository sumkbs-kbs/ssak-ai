import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook } from '@testing-library/react';
import { persistAccessToken } from '../../utils/accessPinCredential';
import { useSkillsCatalog } from './useSkillsCatalog';

const cases = [
  { tab: 'all', path: '/api/system/skills', field: 'skills', initial: { ok: true, skills: [{ name: 'Initial', source: 'local' }] }, latest: { ok: true, skills: [{ name: 'Latest', source: 'local' }] } },
  { tab: 'marketplace', path: '/api/system/skills/installed', field: 'marketSkills', initial: { ok: true, installed: [{ name: 'Initial' }] }, latest: { ok: true, installed: [{ name: 'Latest' }] } },
  { tab: 'mcp', path: '/api/system/skills/mcp', field: 'mcpServers', initial: { ok: true, servers: [{ name: 'Initial' }] }, latest: { ok: true, servers: [{ name: 'Latest' }] } },
] as const;

describe('Skills catalog request ordering', () => {
  beforeEach(() => { vi.useFakeTimers(); persistAccessToken('synthetic-ordering-token'); });
  afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it.each(cases)('keeps the latest $tab result when an older response finishes later', async scenario => {
    // Given an older pending request followed by a successful latest request.
    let release: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>(resolve => { release = resolve; });
    let requests = 0;
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
      if (String(input) !== scenario.path) return Response.json({ ok: true, results: [] });
      requests += 1;
      if (requests === 2) return pending;
      return Response.json(requests === 1 ? scenario.initial : scenario.latest);
    }));
    const hook = renderHook(() => useSkillsCatalog(scenario.tab));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { void hook.result.current.loadTab(scenario.tab); });
    await act(async () => { await hook.result.current.loadTab(scenario.tab); });
    // When the earlier request eventually settles with obsolete data.
    await act(async () => { release(Response.json(scenario.initial)); });
    // Then the latest catalog remains authoritative.
    expect(hook.result.current[scenario.field]?.[0]?.name).toBe('Latest');
  });

  it.each(cases)('ignores an old $tab failure after a successful retry', async scenario => {
    // Given an older pending request followed by a successful latest request.
    let release: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>(resolve => { release = resolve; });
    let requests = 0;
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
      if (String(input) !== scenario.path) return Response.json({ ok: true, results: [] });
      requests += 1;
      if (requests === 2) return pending;
      return Response.json(requests === 1 ? scenario.initial : scenario.latest);
    }));
    const hook = renderHook(() => useSkillsCatalog(scenario.tab));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { void hook.result.current.loadTab(scenario.tab); });
    await act(async () => { await hook.result.current.loadTab(scenario.tab); });
    // When the older request fails after the successful retry.
    await act(async () => { release(Response.json({ ok: false }, { status: 503 })); });
    // Then its error cannot replace the recovered state.
    expect(hook.result.current.status).toEqual({ loading: false, error: null });
  });

  it('clears an obsolete recommendation failure when installed skills become available', async () => {
    // Given an empty installed catalog with a failed recommendation search.
    let installed = false;
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => String(input).includes('/installed')
      ? Response.json({ ok: true, installed: installed ? [{ name: 'Now Installed' }] : [] })
      : Response.json({ ok: false })));
    const hook = renderHook(() => useSkillsCatalog('marketplace'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(hook.result.current.recommendationStatus.error).not.toBeNull();
    installed = true;
    // When a new installed catalog makes recommendations unnecessary.
    await act(async () => { await hook.result.current.loadTab('marketplace'); });
    // Then the obsolete recommendation failure is cleared.
    expect(hook.result.current.recommendationStatus).toEqual({ loading: false, error: null });
  });

  it('ends an obsolete recommendation spinner when a newer installed request fails', async () => {
    // Given a recommendation request still pending for an empty installed catalog.
    let release: (response: Response) => void = () => undefined;
    const recommendation = new Promise<Response>(resolve => { release = resolve; });
    let failed = false;
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => String(input).includes('/installed')
      ? failed ? Response.json({ ok: false }, { status: 503 }) : Response.json({ ok: true, installed: [] })
      : recommendation));
    const hook = renderHook(() => useSkillsCatalog('marketplace'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(hook.result.current.recommendationStatus.loading).toBe(true);
    failed = true;
    // When a newer installed request fails and the obsolete recommendation settles.
    await act(async () => { await hook.result.current.loadTab('marketplace'); });
    await act(async () => { release(Response.json({ ok: true, results: [] })); });
    // Then the obsolete operation cannot leave its spinner running forever.
    expect(hook.result.current.recommendationStatus.loading).toBe(false);
  });
});
