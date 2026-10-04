import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { persistAccessToken } from '../../utils/accessPinCredential';
import { installSkill, loadInstalledSkills, loadMcpSkills, loadSkills, removeSkill, searchSkills } from './skillsApi';

const contracts = [
  { run: loadSkills, path: '/api/system/skills', payload: { ok: true, skills: [] }, body: null },
  { run: loadInstalledSkills, path: '/api/system/skills/installed', payload: { ok: true, installed: [] }, body: null },
  { run: loadMcpSkills, path: '/api/system/skills/mcp', payload: { ok: true, servers: [] }, body: null },
  { run: () => searchSkills('synthetic'), path: '/api/system/skills/search?q=synthetic&limit=20', payload: { ok: true, results: [] }, body: null },
  { run: () => installSkill('synthetic-package'), path: '/api/system/skills/install', payload: { ok: true }, body: { package_name: 'synthetic-package' } },
  { run: () => removeSkill('synthetic-skill'), path: '/api/system/skills/remove', payload: { ok: true }, body: { skill_name: 'synthetic-skill' } },
] as const;

describe('Skills API authenticated wire boundary', () => {
  beforeEach(() => {
    sessionStorage.clear();
    persistAccessToken('synthetic-skills-boundary-token');
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it.each(contracts)('authenticates $path and preserves its request contract', async contract => {
    // Given a wire that rejects absent credentials and accepts the actual envelope.
    const calls: { path: string; method: string; body: unknown }[] = [];
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
      const headers = new Headers(options?.headers);
      calls.push({ path: String(input), method: options?.method ?? 'GET', body: typeof options?.body === 'string' ? JSON.parse(options.body) : null });
      return headers.get('Authorization') === 'Bearer synthetic-skills-boundary-token'
        ? Response.json(contract.payload) : Response.json({ ok: false }, { status: 401 });
    }));
    // When the user-facing action crosses its API boundary.
    await contract.run();
    // Then credentials, path, method and payload are correct without real mutation.
    expect(calls).toEqual([{ path: contract.path, method: contract.body ? 'POST' : 'GET', body: contract.body }]);
  });

  it.each(contracts)('rejects HTTP 200 application failure for $path', async contract => {
    // Given a transport success containing an explicit application failure.
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => Response.json({ ok: false, error: 'synthetic-failure' })));
    // When the same action returns that response.
    const outcome = contract.run();
    // Then failure cannot be mistaken for an empty or completed action.
    await expect(outcome).rejects.toBeInstanceOf(Error);
  });
});
