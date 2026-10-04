import { act, renderHook, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationRevisionConflictError } from '../api/client';
import { useChatStore } from '../stores/chatStore';
import { useProjectStore } from '../stores/projectStore';

const api = vi.hoisted(() => ({
  fetchConversationHistory: vi.fn(),
  forkConversation: vi.fn(),
}));

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchConversationHistory: api.fetchConversationHistory,
  forkConversation: api.forkConversation,
}));

const { useConversationFork } = await import('./useConversationFork');

const SOURCE_MESSAGES = [{ id: 'source-message', role: 'user' as const, content: 'source history' }];

function resetStores(): void {
  useProjectStore.setState({
    activeProjectId: 'project-1',
    projectRevision: 7,
    switchEpoch: 3,
  });
  useChatStore.setState({
    sessions: [{
      id: 'source-1',
      title: '원본 대화',
      updatedAt: '2026-10-03T00:00:00.000Z',
      messages: SOURCE_MESSAGES,
      conversationRevision: 4,
    }],
    activeSessionId: 'source-1',
    activeSession: {
      id: 'source-1',
      title: '원본 대화',
      updatedAt: '2026-10-03T00:00:00.000Z',
      messages: SOURCE_MESSAGES,
      conversationRevision: 4,
    },
    messages: SOURCE_MESSAGES,
    conversationRevision: 4,
    isStreaming: false,
    currentAssistantContent: '',
  });
}

function forkSnapshot() {
  return {
    conversation_id: 'fork-1',
    project_id: 'project-1',
    revision: 0,
    message_count: 2,
  };
}

function forkHistory() {
  return {
    snapshot: forkSnapshot(),
    messages: [
      { id: 'fork-user', role: 'user' as const, content: 'source history' },
      { id: 'fork-tool', role: 'tool' as const, content: 'tool provenance' },
    ],
  };
}

describe('useConversationFork', () => {
  beforeEach(() => {
    resetStores();
    api.fetchConversationHistory.mockReset();
    api.forkConversation.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('adopts the canonical fork history and leaves the source session unchanged', async () => {
    api.forkConversation.mockResolvedValue(forkSnapshot());
    api.fetchConversationHistory.mockResolvedValue(forkHistory());

    const { result } = renderHook(() => useConversationFork({ isCompacting: false }));

    await act(async () => {
      await result.current.forkActiveConversation();
    });

    const state = useChatStore.getState();
    const source = state.sessions.find((session) => session.id === 'source-1');
    const fork = state.sessions.find((session) => session.id === 'fork-1');
    expect(source).toMatchObject({
      id: 'source-1',
      title: '원본 대화',
      messages: SOURCE_MESSAGES,
      conversationRevision: 4,
    });
    expect(fork).toMatchObject({
      id: 'fork-1',
      conversationRevision: 0,
      messages: [
        { id: 'fork-user', role: 'user', content: 'source history' },
        { id: 'fork-tool', role: 'system', content: 'tool provenance' },
      ],
    });
    expect(state.activeSessionId).toBe('fork-1');
    expect(result.current.status.kind).toBe('success');
  });

  it('does not adopt a late server result after the user selects another conversation', async () => {
    let resolveFork: ((value: ReturnType<typeof forkSnapshot>) => void) | undefined;
    api.forkConversation.mockImplementation(() => new Promise((resolve) => {
      resolveFork = resolve;
    }));
    api.fetchConversationHistory.mockResolvedValue(forkHistory());

    const { result } = renderHook(() => useConversationFork({ isCompacting: false }));
    let request: Promise<void> | undefined;
    act(() => {
      request = result.current.forkActiveConversation();
    });
    useChatStore.setState({
      sessions: [
        ...useChatStore.getState().sessions,
        { id: 'other-1', title: '다른 대화', updatedAt: '2026-10-03T00:01:00.000Z', messages: [], conversationRevision: 0 },
      ],
    });
    useChatStore.getState().switchSession('other-1');
    resolveFork?.(forkSnapshot());
    await act(async () => {
      await request;
    });

    expect(useChatStore.getState().sessions.some((session) => session.id === 'fork-1')).toBe(false);
    expect(useChatStore.getState().activeSessionId).toBe('other-1');
    expect(result.current.isForking).toBe(false);
  });

  it('does not adopt a result after returning to the source session', async () => {
    let resolveFork: ((value: ReturnType<typeof forkSnapshot>) => void) | undefined;
    api.forkConversation.mockImplementation(() => new Promise((resolve) => {
      resolveFork = resolve;
    }));

    const { result } = renderHook(() => useConversationFork({ isCompacting: false }));
    let request: Promise<void> | undefined;
    act(() => {
      request = result.current.forkActiveConversation();
    });
    useChatStore.setState({
      sessions: [
        ...useChatStore.getState().sessions,
        { id: 'other-1', title: '다른 대화', updatedAt: '2026-10-03T00:01:00.000Z', messages: [], conversationRevision: 0 },
      ],
    });
    useChatStore.getState().switchSession('other-1');
    useChatStore.getState().switchSession('source-1');
    resolveFork?.(forkSnapshot());
    await act(async () => {
      await request;
    });

    expect(useChatStore.getState().sessions.some((session) => session.id === 'fork-1')).toBe(false);
    expect(useChatStore.getState().activeSessionId).toBe('source-1');
  });

  it('does not adopt a result after a new stream starts and ends', async () => {
    let resolveFork: ((value: ReturnType<typeof forkSnapshot>) => void) | undefined;
    api.forkConversation.mockImplementation(() => new Promise((resolve) => {
      resolveFork = resolve;
    }));

    const { result } = renderHook(() => useConversationFork({ isCompacting: false }));
    let request: Promise<void> | undefined;
    act(() => {
      request = result.current.forkActiveConversation();
    });
    useChatStore.getState().setStreaming(true);
    useChatStore.getState().setStreaming(false);
    resolveFork?.(forkSnapshot());
    await act(async () => {
      await request;
    });

    expect(useChatStore.getState().sessions.some((session) => session.id === 'fork-1')).toBe(false);
    expect(useChatStore.getState().activeSessionId).toBe('source-1');
  });

  it('works after Strict Mode replays the effect setup', async () => {
    api.forkConversation.mockResolvedValue(forkSnapshot());
    api.fetchConversationHistory.mockResolvedValue(forkHistory());

    const { result } = renderHook(() => useConversationFork({ isCompacting: false }), {
      wrapper: StrictMode,
    });

    await act(async () => {
      await result.current.forkActiveConversation();
    });

    expect(useChatStore.getState().activeSessionId).toBe('fork-1');
    expect(result.current.status.kind).toBe('success');
  });

  it('does not adopt a result after the hook unmounts', async () => {
    let resolveFork: ((value: ReturnType<typeof forkSnapshot>) => void) | undefined;
    api.forkConversation.mockImplementation(() => new Promise((resolve) => {
      resolveFork = resolve;
    }));

    const { result, unmount } = renderHook(() => useConversationFork({ isCompacting: false }));
    let request: Promise<void> | undefined;
    act(() => {
      request = result.current.forkActiveConversation();
    });
    unmount();
    resolveFork?.(forkSnapshot());
    await act(async () => {
      await request;
    });

    expect(useChatStore.getState().sessions.some((session) => session.id === 'fork-1')).toBe(false);
  });

  it('refreshes only the captured active source after a stale CAS conflict', async () => {
    api.forkConversation.mockRejectedValue(new ConversationRevisionConflictError({
      ok: false,
      error: 'stale_conversation_revision',
      detail: 'stale source',
      conversation_id: 'source-1',
      expected_revision: 4,
      current_revision: 5,
    }));
    api.fetchConversationHistory.mockResolvedValue({
      snapshot: { conversation_id: 'source-1', project_id: 'project-1', revision: 5, message_count: 1 },
      messages: [{ id: 'server-current', role: 'assistant' as const, content: 'authoritative history' }],
    });

    const { result } = renderHook(() => useConversationFork({ isCompacting: false }));

    await act(async () => {
      await result.current.forkActiveConversation();
    });

    await waitFor(() => expect(useChatStore.getState().conversationRevision).toBe(5));
    expect(useChatStore.getState().activeSessionId).toBe('source-1');
    expect(useChatStore.getState().messages).toEqual([
      { id: 'server-current', role: 'assistant', content: 'authoritative history' },
    ]);
    expect(result.current.status.kind).toBe('error');
  });
});
