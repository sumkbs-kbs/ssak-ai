import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { persistAccessToken } from '../utils/accessPinCredential';
import { useProjectStore } from '../stores/projectStore';
import { CLIENT_SESSION_STORAGE_KEY } from '../api/clientSession';
import SkillsPage from './SkillsPage';

const identity = { token: 'synthetic-skills-token', project: 'synthetic-skills-project', revision: 13, session: 'synthetic-skills-session' };
const initialProject = useProjectStore.getState();
const pinRequired = vi.fn();
const contracts = [
  { tab: 'All Skills', path: '/api/system/skills', payload: { ok: true, skills: [{ id: 'qa-skill', name: 'Synthetic Local Skill', source: 'local' }] }, row: 'Synthetic Local Skill' },
  { tab: 'Marketplace', path: '/api/system/skills/installed', payload: { ok: true, installed: [{ name: 'Synthetic Market Skill', version: '1.0.0', is_loaded: true }] }, row: 'Synthetic Market Skill' },
  { tab: 'MCP Servers', path: '/api/system/skills/mcp', payload: { ok: true, servers: [{ name: 'Synthetic MCP', status: 'active', tools: ['synthetic_tool'] }] }, row: 'Synthetic MCP' },
] as const;

function wire(targetPath: string, targetResponse?: () => Response, extra: Readonly<Record<string, () => Response>> = {}) {
  const calls: { readonly path: string; readonly headers: Headers; readonly body: unknown }[] = [];
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    const path = String(input);
    const headers = new Headers(options?.headers);
    calls.push({ path, headers, body: typeof options?.body === 'string' ? JSON.parse(options.body) : null });
    if (headers.get('Authorization') !== `Bearer ${identity.token}` || headers.get('X-AGK-Project-Id') !== identity.project) {
      return Response.json({ ok: false }, { status: 401, statusText: 'Unauthorized' });
    }
    if (path === targetPath && targetResponse) return targetResponse();
    const extraResponse = extra[path];
    if (extraResponse) return extraResponse();
    const contract = contracts.find(candidate => candidate.path === path);
    return Response.json(contract?.payload ?? { ok: true, results: [] });
  }));
  return calls;
}

function selectTab(tab: string): void {
  if (tab !== 'All Skills') fireEvent.click(screen.getByRole('button', { name: new RegExp(tab) }));
}

describe('SkillsPage authenticated catalog', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    persistAccessToken(identity.token);
    sessionStorage.setItem(CLIENT_SESSION_STORAGE_KEY, identity.session);
    useProjectStore.setState({ activeProjectId: identity.project, projectRevision: identity.revision });
    vi.spyOn(console, 'error').mockImplementation(() => {});
    pinRequired.mockClear();
    window.addEventListener('agk:pin-required', pinRequired);
  });
  afterEach(() => {
    cleanup();
    useProjectStore.setState(initialProject);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.removeEventListener('agk:pin-required', pinRequired);
  });

  it.each(contracts)('loads $tab using authenticated project-scoped requests', async contract => {
    // Given the wire rejects requests missing the authenticated project identity.
    const calls = wire(contract.path);
    render(<SkillsPage />);
    // When the user opens a catalog tab.
    selectTab(contract.tab);
    // Then real response data and identity reach the tab.
    await screen.findByText(contract.row);
    const request = calls.find(call => call.path === contract.path);
    expect(request?.headers.get('Authorization')).toBe(`Bearer ${identity.token}`);
    expect(request?.headers.get('X-AGK-Project-Id')).toBe(identity.project);
    expect(request?.headers.get('X-AGK-Project-Revision')).toBe(String(identity.revision));
    expect(request?.headers.get('X-AGK-Session-Id')).toBe(identity.session);
  });

  it.each(contracts)('shows $tab authentication failure and retries after PIN recovery', async contract => {
    // Given the server initially denies an otherwise authenticated request.
    let denied = true;
    wire(contract.path, () => denied ? Response.json({ ok: false }, { status: 401 }) : Response.json(contract.payload));
    render(<SkillsPage />);
    selectTab(contract.tab);
    const alert = await screen.findByRole('alert');
    expect(pinRequired).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/로드된 스킬이 없습니다|설치된 마켓 스킬이 없습니다|MCP 서버가 없습니다/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: new RegExp(contract.tab) })).not.toHaveTextContent('0');
    denied = false;
    // When the user retries after recovering their credential.
    fireEvent.click(within(alert).getByRole('button'));
    // Then the successful response clears the error.
    await screen.findByText(contract.row);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each(contracts)('rejects $tab application failures returned with HTTP 200', async contract => {
    // Given a failed application envelope despite a successful transport.
    wire(contract.path, () => Response.json({ ok: false, error: 'synthetic-catalog-error' }));
    render(<SkillsPage />);
    // When the selected catalog returns the failed envelope.
    selectTab(contract.tab);
    // Then failure is visible and does not become an empty catalog.
    await screen.findByRole('alert');
    expect(screen.queryByText(/로드된 스킬이 없습니다|설치된 마켓 스킬이 없습니다|MCP 서버가 없습니다/)).not.toBeInTheDocument();
  });

  it('retains a previous catalog beside a failed refresh', async () => {
    // Given a loaded catalog whose next request fails.
    let failed = false;
    wire('/api/system/skills', () => failed ? Response.json({ ok: false }, { status: 503 }) : Response.json(contracts[0].payload));
    render(<SkillsPage />);
    await screen.findByText(contracts[0].row);
    failed = true;
    // When the user refreshes.
    fireEvent.click(screen.getByRole('button', { name: /새로고침/ }));
    // Then stale data remains readable with the explicit failure.
    await screen.findByRole('alert');
    expect(screen.getByText(contracts[0].row)).toBeInTheDocument();
  });

  it('rejects malformed catalog data rather than hiding missing fields as zero', async () => {
    // Given a success envelope missing its required catalog array.
    wire('/api/system/skills', () => Response.json({ ok: true }));
    // When the page loads the catalog.
    render(<SkillsPage />);
    // Then it exposes a contract error rather than an empty state.
    await screen.findByRole('alert');
    expect(screen.queryByText(/로드된 스킬이 없습니다/)).not.toBeInTheDocument();
  });

  it('renders an actual empty catalog only after a valid success response', async () => {
    // Given an authenticated, valid empty catalog.
    wire('/api/system/skills', () => Response.json({ ok: true, skills: [] }));
    // When the catalog loads.
    render(<SkillsPage />);
    // Then zero and the empty state describe real server data.
    await screen.findByText(/로드된 스킬이 없습니다/);
    expect(screen.getByRole('button', { name: /All Skills/ })).toHaveTextContent('0');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('authenticates explicit npm search and exposes failed searches', async () => {
    // Given a synthetic query rejected by the application envelope.
    const path = '/api/system/skills/search?q=synthetic%20query&limit=20';
    const calls = wire(path, () => Response.json({ ok: false, error: 'synthetic-search-error' }));
    render(<SkillsPage />);
    await screen.findByText(contracts[0].row);
    fireEvent.click(screen.getByRole('button', { name: /Search npm/ }));
    fireEvent.change(screen.getByRole('textbox', { name: 'npm 스킬 검색' }), { target: { value: 'synthetic query' } });
    // When the user explicitly searches.
    fireEvent.click(screen.getByRole('button', { name: '검색' }));
    // Then failure is visible and the actual query is sent with credentials.
    await screen.findByRole('alert');
    await waitFor(() => expect(calls.find(call => call.path === path)?.headers.get('Authorization')).toBe(`Bearer ${identity.token}`));
  });

  it('searches the selected example without using a stale previous query', async () => {
    // Given a loaded page with an empty search input.
    const path = '/api/system/skills/search?q=testing&limit=20';
    const calls = wire(path, () => Response.json({ ok: true, results: [{ name: 'Synthetic Search Skill', version: '1.0.0' }] }));
    render(<SkillsPage />);
    await screen.findByText(contracts[0].row);
    fireEvent.click(screen.getByRole('button', { name: /Search npm/ }));
    // When the user selects an example query.
    fireEvent.click(screen.getByRole('button', { name: 'testing' }));
    // Then that query reaches the authenticated wire and its result renders.
    await screen.findAllByText('Synthetic Search Skill');
    expect(calls.some(call => call.path === path)).toBe(true);
    expect(screen.getByRole('textbox', { name: 'npm 스킬 검색' })).toHaveValue('testing');
  });

  it('preserves authenticated Marketplace recommendations for an empty installed catalog', async () => {
    // Given no installed marketplace skills and a valid recommendation search.
    const path = '/api/system/skills/search?q=skill&limit=10';
    const calls = wire('/api/system/skills/installed', () => Response.json({ ok: true, installed: [] }), {
      [path]: () => Response.json({ ok: true, results: [{ name: 'Synthetic Recommendation', version: '1.0.0' }] }),
    });
    render(<SkillsPage />);
    await screen.findByText(contracts[0].row);
    // When the user opens Marketplace.
    selectTab('Marketplace');
    // Then the existing recommendations remain available and authenticated.
    await screen.findAllByText('Synthetic Recommendation');
    expect(calls.find(call => call.path === path)?.headers.get('Authorization')).toBe(`Bearer ${identity.token}`);
    expect(screen.getByRole('button', { name: /Marketplace/ })).toHaveTextContent('0');
  });

  it('separates recommendation failure from the successful installed catalog', async () => {
    // Given a valid empty installed catalog and a temporarily failing recommendation search.
    const path = '/api/system/skills/search?q=skill&limit=10';
    let failed = true;
    wire('/api/system/skills/installed', () => Response.json({ ok: true, installed: [] }), {
      [path]: () => Response.json(failed ? { ok: false } : { ok: true, results: [{ name: 'Recovered Recommendation', version: '1.0.0' }] }),
    });
    render(<SkillsPage />);
    await screen.findByText(contracts[0].row);
    selectTab('Marketplace');
    const alert = await screen.findByRole('alert');
    expect(screen.getByText(/설치된 마켓 스킬이 없습니다/)).toBeInTheDocument();
    failed = false;
    // When the user retries recommendation discovery.
    fireEvent.click(within(alert).getByRole('button'));
    // Then the recommendation recovers without treating the installed list as unavailable.
    await screen.findAllByText('Recovered Recommendation');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
