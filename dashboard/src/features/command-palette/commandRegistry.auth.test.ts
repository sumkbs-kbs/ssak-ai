import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiHttpError } from '../../api/client';
import { useProjectStore } from '../../stores/projectStore';
import { useUiStore } from '../../stores/uiStore';
import { useWikiStore } from '../../stores/wikiStore';
import { BUILTIN_COMMANDS, CommandSearchError, searchNoteCommands } from './commandRegistry';

const NativeRequest = Request;
const projectSnapshot = useProjectStore.getState();
const wikiSnapshot = useWikiStore.getState();
const uiSnapshot = useUiStore.getState();

function requestDetails(input: RequestInfo | URL, init?: RequestInit) {
  return {
    url: new URL(input instanceof Request ? input.url : String(input), window.location.origin),
    headers: new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined)),
    method: init?.method ?? (input instanceof Request ? input.method : 'GET'),
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status, statusText: status === 401 ? 'Unauthorized' : 'OK',
    headers: { 'Content-Type': 'application/json' },
  });
}

function commandById(id: string) {
  const command = BUILTIN_COMMANDS.find(candidate => candidate.id === id);
  if (command === undefined) throw new TypeError(`Missing command: ${id}`);
  return command;
}

beforeEach(() => {
  // The browser resolves relative URLs before constructing ky's Request.
  vi.stubGlobal('Request', class BrowserRequest extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(typeof input === 'string' ? new URL(input, window.location.origin) : input, init);
    }
  });
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  window.sessionStorage.setItem('ag_access_token', 'synthetic-palette-token');
  window.sessionStorage.setItem('agk_client_session_id', 'synthetic-palette-session');
  useProjectStore.setState({ activeProjectId: 'synthetic-palette-project', projectRevision: 12 });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  useProjectStore.setState(projectSnapshot);
  useWikiStore.setState(wikiSnapshot);
  useUiStore.setState(uiSnapshot);
});

describe('command palette request authentication', () => {
  it('finds notes when the server requires the active bearer and project identity', async () => {
    // Given: a wire boundary that only serves notes for the authenticated workspace.
    const wire = vi.fn<typeof fetch>(async (input, init) => {
      const request = requestDetails(input, init);
      if (request.headers.get('Authorization') !== 'Bearer synthetic-palette-token') return jsonResponse({}, 401);
      return jsonResponse({ semantic_results: [], keyword_results: ['qa-contract.md'] });
    });
    vi.stubGlobal('fetch', wire);

    // When: the user searches for a literal string containing query separators.
    const results = await searchNoteCommands('qa & project=other');

    // Then: the request carries the current identity and the query stays one parameter.
    expect(results.map(result => result.id)).toEqual(['note-keyword:qa-contract.md']);
    const call = wire.mock.calls[0];
    if (call === undefined) throw new TypeError('Note search did not reach the wire.');
    const request = requestDetails(...call);
    expect(request.url.pathname).toBe('/v1/notes/search');
    expect([...request.url.searchParams]).toEqual([['q', 'qa & project=other']]);
    expect(request.headers.get('X-AGK-Project-Id')).toBe('synthetic-palette-project');
    expect(request.headers.get('X-AGK-Project-Revision')).toBe('12');
    expect(request.headers.get('X-AGK-Session-Id')).toBe('synthetic-palette-session');
    expect(request.method).toBe('GET');
  });

  it('syncs the vault when the server requires the authenticated workspace', async () => {
    // Given: the sync boundary rejects missing credentials.
    const toast = vi.spyOn(useUiStore.getState(), 'addToast');
    const wire = vi.fn<typeof fetch>(async (input, init) => {
      const request = requestDetails(input, init);
      return request.headers.get('Authorization') === 'Bearer synthetic-palette-token'
        ? jsonResponse({ ok: true, commit: 'a123456789' }) : jsonResponse({}, 401);
    });
    vi.stubGlobal('fetch', wire);

    // When: the user explicitly executes vault sync.
    await commandById('sync').execute();

    // Then: sync has its intended method and project/session headers and reports real success.
    const call = wire.mock.calls[0];
    if (call === undefined) throw new TypeError('Vault sync did not reach the wire.');
    const request = requestDetails(...call);
    expect(request.url.pathname).toBe('/api/vault/sync');
    expect(request.method).toBe('POST');
    expect(request.headers.get('X-AGK-Project-Id')).toBe('synthetic-palette-project');
    expect(request.headers.get('X-AGK-Session-Id')).toBe('synthetic-palette-session');
    expect(toast.mock.calls.map(([, level]) => level)).toEqual(['success']);
  });

  it('requires login and leaves wiki data unchanged when note search is unauthorized', async () => {
    // Given: the bearer has expired and the existing note is visible.
    const currentDoc = { path: 'existing.md', content: 'existing content', metadata: {} };
    useWikiStore.setState({ currentDoc });
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({}, 401)));
    const dispatch = vi.spyOn(window, 'dispatchEvent');

    // When: a search is rejected by the server.
    const result = searchNoteCommands('unauthorized');

    // Then: the typed 401 and normal PIN event remain intact, with no note state mutation.
    await expect(result).rejects.toMatchObject({ cause: { status: 401 } });
    await expect(result).rejects.toBeInstanceOf(CommandSearchError);
    expect(dispatch.mock.calls.map(([event]) => event.type)).toEqual(['agk:pin-required']);
    expect(useWikiStore.getState().currentDoc).toEqual(currentDoc);
  });

  it('does not report vault success when sync is unauthorized', async () => {
    // Given: the server refuses the explicit sync request.
    const toast = vi.spyOn(useUiStore.getState(), 'addToast');
    const wire = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({}, 401));
    vi.stubGlobal('fetch', wire);
    const dispatch = vi.spyOn(window, 'dispatchEvent');

    // When: the user executes sync.
    await commandById('sync').execute();

    // Then: there is one denied request and the normal login flow, with no success side effect.
    expect(wire).toHaveBeenCalledOnce();
    expect(dispatch.mock.calls.map(([event]) => event.type)).toEqual(['agk:pin-required']);
    expect(toast.mock.calls.map(([, level]) => level)).toEqual(['error']);
  });

  it('opens a searched note through an authenticated read before navigating', async () => {
    // Given: the search supplies a real vault path and its read returns content.
    const wire = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ keyword_results: ['folder/note & draft.md'] }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, content: '# Read note', metadata: { title: 'read note' } }));
    vi.stubGlobal('fetch', wire);
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const results = await searchNoteCommands('draft');
    const result = results[0];
    if (result === undefined) throw new TypeError('The search result is missing.');

    // When: the user opens the search result.
    await result.execute();

    // Then: the selected document is the server response, and navigation emits no write.
    expect(useWikiStore.getState().currentDoc).toEqual({ path: 'folder/note & draft.md', content: '# Read note', metadata: { title: 'read note' } });
    const call = wire.mock.calls[1];
    if (call === undefined) throw new TypeError('The selected note was not read.');
    const request = requestDetails(...call);
    expect(request.url.pathname).toBe('/api/vault/read');
    expect(request.url.searchParams.get('path')).toBe('folder/note & draft.md');
    expect(request.headers.get('Authorization')).toBe('Bearer synthetic-palette-token');
    expect(request.method).toBe('GET');
    expect(dispatch.mock.calls[0]?.[0]).toMatchObject({ type: 'agk:navigate', detail: '/wiki' });
  });

  it('keeps the visible note and route when selection read is unauthorized', async () => {
    // Given: a selected result belongs to an expired login.
    const currentDoc = { path: 'existing.md', content: 'retained', metadata: {} };
    useWikiStore.setState({ currentDoc });
    vi.stubGlobal('fetch', vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ keyword_results: ['denied.md'] }))
      .mockResolvedValueOnce(jsonResponse({}, 401)));
    const results = await searchNoteCommands('denied');
    const result = results[0];
    if (result === undefined) throw new TypeError('The search result is missing.');
    const dispatch = vi.spyOn(window, 'dispatchEvent');

    // When: the user attempts to open it.
    await expect(result.execute()).rejects.toBeInstanceOf(ApiHttpError);

    // Then: login is required, but no note or navigation is applied.
    expect(useWikiStore.getState().currentDoc).toEqual(currentDoc);
    expect(dispatch.mock.calls.map(([event]) => event.type)).toEqual(['agk:pin-required']);
  });
});
