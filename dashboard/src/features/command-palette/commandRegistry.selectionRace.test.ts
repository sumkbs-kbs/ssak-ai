import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useProjectStore } from '../../stores/projectStore';
import { useWikiStore } from '../../stores/wikiStore';
import { searchNoteCommands } from './commandRegistry';

const projectSnapshot = useProjectStore.getState();
const wikiSnapshot = useWikiStore.getState();

function deferredResponse() {
  let finish: ((response: Response) => void) | null = null;
  const promise = new Promise<Response>((resolve) => { finish = resolve; });
  return {
    promise,
    resolve: (response: Response) => {
      if (finish === null) throw new TypeError('Response resolver is unavailable.');
      finish(response);
    },
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  useProjectStore.setState({ activeProjectId: 'synthetic-selection-project', switchEpoch: 41 });
  window.sessionStorage.setItem('ag_access_token', 'synthetic-selection-token');
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  useProjectStore.setState(projectSnapshot);
  useWikiStore.setState(wikiSnapshot);
});

describe('note selection ownership', () => {
  it('keeps a newer login when an old selected-note request later receives 401', async () => {
    // Given: a selected-note read is delayed while another login succeeds.
    const read = deferredResponse();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ keyword_results: ['expired.md'] }))
      .mockImplementationOnce(() => read.promise));
    const [command] = await searchNoteCommands('expired');
    if (command === undefined) throw new TypeError('Selection fixture is missing.');
    const dispatch = vi.spyOn(window, 'dispatchEvent');

    // When: the old request fails after the current credential is replaced.
    const selection = Promise.resolve(command.execute());
    window.sessionStorage.setItem('ag_access_token', 'synthetic-new-login');
    read.resolve(jsonResponse({}, 401));
    await selection;

    // Then: the old response cannot request recovery for the current login.
    expect(dispatch).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem('ag_access_token')).toBe('synthetic-new-login');
  });
  it.each([
    { scope: 'project', change: () => useProjectStore.setState({ switchEpoch: 42 }) },
    { scope: 'credential', change: () => window.sessionStorage.removeItem('ag_access_token') },
  ])('retains the visible note when $scope changes before the read completes', async ({ change }) => {
    // Given: selection reads are delayed behind a visible existing note.
    const read = deferredResponse();
    const currentDoc = { path: 'current.md', content: 'current scope', metadata: {} };
    useWikiStore.setState({ currentDoc });
    vi.stubGlobal('fetch', vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ keyword_results: ['previous.md'] }))
      .mockImplementationOnce(() => read.promise));
    const [command] = await searchNoteCommands('previous');
    if (command === undefined) throw new TypeError('Selection fixture is missing.');
    const dispatch = vi.spyOn(window, 'dispatchEvent');

    // When: scope changes while a selected note response is still pending.
    const selection = Promise.resolve(command.execute());
    change();
    read.resolve(jsonResponse({ content: 'previous scope', metadata: {} }));
    await selection;

    // Then: the response cannot change the current scope's document or route.
    expect(useWikiStore.getState().currentDoc).toEqual(currentDoc);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('retains the newest selected note when an earlier read finishes last', async () => {
    // Given: two actual search results have independently delayed reads.
    const first = deferredResponse();
    const second = deferredResponse();
    vi.stubGlobal('fetch', vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ keyword_results: ['first.md', 'second.md'] }))
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise));
    const [firstCommand, secondCommand] = await searchNoteCommands('notes');
    if (firstCommand === undefined || secondCommand === undefined) throw new TypeError('Selection fixtures are missing.');
    const dispatch = vi.spyOn(window, 'dispatchEvent');

    // When: the newer selection resolves before the older one.
    const firstSelection = Promise.resolve(firstCommand.execute());
    const secondSelection = Promise.resolve(secondCommand.execute());
    second.resolve(jsonResponse({ content: 'new selection', metadata: {} }));
    await secondSelection;
    first.resolve(jsonResponse({ content: 'stale selection', metadata: {} }));
    await firstSelection;

    // Then: the current document and only navigation belong to the newer selection.
    expect(useWikiStore.getState().currentDoc?.path).toBe('second.md');
    expect(useWikiStore.getState().currentDoc?.content).toBe('new selection');
    expect(dispatch).toHaveBeenCalledOnce();
  });
});
