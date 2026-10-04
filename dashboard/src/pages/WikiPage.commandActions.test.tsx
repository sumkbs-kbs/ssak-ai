import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import WikiPage from './WikiPage';
import { useWikiStore } from '../stores/wikiStore';

const snapshot = useWikiStore.getState();

beforeEach(() => {
  useWikiStore.setState({ vaultPath: '', treeData: [], currentDoc: null });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useWikiStore.setState(snapshot);
});

describe('wiki command navigation', () => {
  it('loads the existing vault tree without restoring config through a write on navigation', () => {
    // Given: the stored vault config can differ from the server's active config.
    const initialize = vi.spyOn(useWikiStore.getState(), 'initVault').mockResolvedValue();
    const tree = vi.spyOn(useWikiStore.getState(), 'loadTree').mockResolvedValue();

    // When: a command opens the wiki.
    render(<MemoryRouter initialEntries={['/wiki']}><WikiPage /></MemoryRouter>);

    // Then: navigation performs a read without invoking config restoration.
    expect(tree).toHaveBeenCalledOnce();
    expect(initialize).not.toHaveBeenCalled();
  });

  it('opens the real note form without creating a document for the command query', () => {
    // Given: the command requests a new note form.
    vi.spyOn(useWikiStore.getState(), 'initVault').mockResolvedValue();
    vi.spyOn(useWikiStore.getState(), 'loadTree').mockResolvedValue();
    const create = vi.spyOn(useWikiStore.getState(), 'createDocument');

    // When: the command route mounts.
    render(<MemoryRouter initialEntries={['/wiki?new=1']}><WikiPage /></MemoryRouter>);

    // Then: the actual form controls render while creation remains unsubmitted.
    expect(screen.getByRole('button', { name: '생성' })).toBeDisabled();
    expect(create).not.toHaveBeenCalled();
  });
});
