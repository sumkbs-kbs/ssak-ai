import { afterEach, describe, expect, it, vi } from 'vitest';

import { BUILTIN_COMMANDS, filterPaletteCommands } from './commandRegistry';
import { useChatStore } from '../../stores/chatStore';

const chatSnapshot = useChatStore.getState();

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, '', '/');
  useChatStore.setState(chatSnapshot);
});

describe('typed command registry', () => {
  it('opens the existing wiki search surface when Search Notes is selected', async () => {
    // Given: the built-in note action is discovered outside the wiki.
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const command = BUILTIN_COMMANDS.find(candidate => candidate.id === 'search');
    if (command === undefined) throw new TypeError('Search command is missing.');

    // When: the user selects Search Notes.
    await command.execute();

    // Then: the actual wiki route opens rather than closing the palette without an action.
    expect(dispatch.mock.calls[0]?.[0]).toMatchObject({ type: 'agk:navigate', detail: '/wiki' });
  });

  it('opens the note creation form without writing a note', async () => {
    // Given: the note action is discovered from another page.
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const fetch = vi.spyOn(globalThis, 'fetch');
    const command = BUILTIN_COMMANDS.find(candidate => candidate.id === 'new_note');
    if (command === undefined) throw new TypeError('New note command is missing.');

    // When: the user selects the note creation command.
    await command.execute();

    // Then: the wiki form is requested, with no write before its submission.
    expect(dispatch.mock.calls[0]?.[0]).toMatchObject({ type: 'agk:navigate', detail: '/wiki?new=1' });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('keeps Self-Test disabled when there is no dashboard execution surface', () => {
    // Given: the command is advertised in the evaluation list.
    const command = BUILTIN_COMMANDS.find(candidate => candidate.id === 'selftest');

    // When / Then: the consumer sees an unavailable action, not a fake successful launch.
    expect(command?.disabled).toBe(true);
  });

  it('opens TDD chat mode without submitting or replacing the current draft', async () => {
    // Given: the user has a draft and has not enabled TDD.
    const snapshot = useChatStore.getState();
    useChatStore.setState({ isTddMode: false, isAdaptiveMode: true });
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const fetch = vi.spyOn(globalThis, 'fetch');
    const command = BUILTIN_COMMANDS.find(candidate => candidate.id === 'tdd_loop');
    if (command === undefined) throw new TypeError('TDD command is missing.');

    // When: the user chooses the TDD mode action.
    await command.execute();

    // Then: existing chat mode is configured, while sending remains the user's action.
    expect(useChatStore.getState().isTddMode).toBe(true);
    expect(useChatStore.getState().isAdaptiveMode).toBe(false);
    expect(dispatch.mock.calls.map(([event]) => event.type)).toEqual(['agk:navigate']);
    expect(dispatch.mock.calls[0]?.[0]).toMatchObject({ detail: '/chat' });
    expect(fetch).not.toHaveBeenCalled();
    useChatStore.setState(snapshot);
  });
  it('requests the active conversation fork from the chat surface', async () => {
    // Given: a user finds the fork action on the chat page.
    window.history.replaceState(null, '', '/chat');
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const command = filterPaletteCommands(BUILTIN_COMMANDS, 'fork').find(candidate => candidate.id === 'conversation_fork');
    if (command === undefined) throw new TypeError('Conversation fork command is missing.');

    // When: the user executes the discovered action.
    await command.execute();

    // Then: the mounted chat owns the mutation, rather than a new request layer.
    expect(dispatch.mock.calls.map(([event]) => event.type)).toEqual(['agk:conversation-fork']);
  });

  it('opens chat without forking an unseen conversation from another page', async () => {
    // Given: the fork action is discovered outside the chat surface.
    window.history.replaceState(null, '', '/settings');
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const command = BUILTIN_COMMANDS.find(candidate => candidate.id === 'conversation_fork');
    if (command === undefined) throw new TypeError('Conversation fork command is missing.');

    // When: the user executes the action.
    await command.execute();

    // Then: navigation makes the source visible before its fork control is used.
    const emitted = dispatch.mock.calls[0]?.[0];
    if (!(emitted instanceof CustomEvent)) throw new TypeError('Expected a navigation event.');
    expect(emitted.type).toBe('agk:navigate');
    expect(emitted.detail).toBe('/chat');
    expect(dispatch.mock.calls.some(([event]) => event.type === 'agk:conversation-fork')).toBe(false);
  });
  it('keeps command identifiers unique and searches id, title, and keywords', () => {
    expect(new Set(BUILTIN_COMMANDS.map((command) => command.id)).size).toBe(BUILTIN_COMMANDS.length);
    expect(filterPaletteCommands(BUILTIN_COMMANDS, 'benchmark').map((command) => command.id)).toEqual([
      'benchmark',
    ]);
    expect(filterPaletteCommands(BUILTIN_COMMANDS, '환경 설정').map((command) => command.id)).toEqual([
      'settings',
    ]);
    expect(filterPaletteCommands(BUILTIN_COMMANDS, '작업').map((command) => command.id)).toEqual([
      'job_operations',
    ]);
  });

  it('navigates to the job operations console', async () => {
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const command = BUILTIN_COMMANDS.find((candidate) => candidate.id === 'job_operations');
    if (command === undefined) throw new TypeError('Job operations command fixture is missing.');

    await command.execute();

    const emitted = dispatch.mock.calls[0]?.[0];
    if (!(emitted instanceof CustomEvent)) throw new TypeError('Expected a custom browser event.');
    expect(emitted.type).toBe('agk:navigate');
    expect(emitted.detail).toBe('/plugins/job-operations');
  });

  it('executes a slash command through its typed browser event contract', async () => {
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const command = BUILTIN_COMMANDS.find((candidate) => candidate.id === 'goal');
    if (command === undefined) throw new TypeError('Goal command fixture is missing.');

    await command.execute();

    const emitted = dispatch.mock.calls[0]?.[0];
    if (!(emitted instanceof CustomEvent)) throw new TypeError('Expected a custom browser event.');
    expect(emitted.type).toBe('agk:chat-slash');
    expect(emitted.detail).toEqual({ text: '/goal ' });
  });
});
