import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ChatStreamHandlers } from '../../../api/client';
import * as client from '../../../api/client';
import { useChatStore, type ChatSession } from '../../../stores/chatStore';
import { useProjectStore } from '../../../stores/projectStore';
import { useUiStore } from '../../../stores/uiStore';
import ChatPage from '../ChatPage';

type DeferredStream = Readonly<{ handlers: ChatStreamHandlers; finish: () => void }>;

describe('ChatPage stream channel ownership', () => {
  const streams: DeferredStream[] = [];

  beforeEach(() => {
    streams.length = 0;
    localStorage.clear();
    const session: ChatSession = {
      id: 'channel-conversation', title: 'channel-test', updatedAt: '2026-10-03',
      messages: [], conversationRevision: 0,
    };
    useProjectStore.setState({
      activeProjectId: 'channel-project', activeProjectName: 'channel-test',
      activeProjectPath: '/fixture/channel-test', hydrated: true, switchEpoch: 0,
      hydrateFromServer: async () => undefined,
    });
    useChatStore.setState({
      sessions: [session], activeSessionId: session.id, activeSession: session,
      messages: [], conversationRevision: 0, isStreaming: false,
      currentAssistantContent: '', isAdaptiveMode: false,
    });
    useUiStore.setState({ toasts: [] });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })));
    vi.spyOn(client, 'fetchModels').mockResolvedValue([]);
    vi.spyOn(client, 'fetchLocalModels').mockResolvedValue({ ok: true, total: 0, models: [] });
    vi.spyOn(client, 'fetchConversationHistory').mockRejectedValue(
      new client.ConversationRequestError('fixture has no server record', 'conversation_not_found', 404),
    );
    vi.spyOn(client, 'streamChatCompletion').mockImplementation((_payload, handlers) => (
      new Promise<void>((resolve) => streams.push({ handlers, finish: resolve }))
    ));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  async function send(text: string): Promise<void> {
    const input = screen.getByRole('textbox', { name: '메시지 입력' });
    fireEvent.change(input, { target: { value: text } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(client.streamChatCompletion).toHaveBeenCalled());
  }

  it('shows progress as accessible working status without adding it to the assistant body', async () => {
    // Given
    await act(async () => render(<MemoryRouter><ChatPage /></MemoryRouter>));
    await send('status-turn');

    // When
    act(() => streams[0]?.handlers.onStatus?.('stage-running'));

    // Then
    expect(screen.getByRole('status', { name: '에이전트 작업 중' })).toHaveTextContent('stage-running');
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('');
    await act(async () => streams[0]?.finish());
  });

  it('replaces the streaming draft with the authoritative final and clears working status', async () => {
    // Given
    await act(async () => render(<MemoryRouter><ChatPage /></MemoryRouter>));
    await send('final-turn');
    act(() => {
      streams[0]?.handlers.onChunk('draft-answer');
      streams[0]?.handlers.onStatus?.('stage-running');
    });

    // When
    act(() => streams[0]?.handlers.onFinalContent?.('{"ok":true}'));
    await act(async () => streams[0]?.finish());

    // Then
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('{"ok":true}');
    expect(useChatStore.getState().currentAssistantContent).toBe('{"ok":true}');
    expect(screen.queryByText('draft-answer')).not.toBeInTheDocument();
    expect(screen.queryByText('stage-running')).not.toBeInTheDocument();
  });

  it('ignores late final and status events from a stopped run while the next run owns the conversation', async () => {
    // Given
    await act(async () => render(<MemoryRouter><ChatPage /></MemoryRouter>));
    await send('old-turn');
    fireEvent.click(screen.getByRole('button', { name: '생성 중단' }));
    await send('new-turn');
    await waitFor(() => expect(client.streamChatCompletion).toHaveBeenCalledTimes(2));
    act(() => {
      streams[1]?.handlers.onChunk('new-answer');
      streams[1]?.handlers.onStatus?.('new-stage');
    });

    // When
    act(() => {
      streams[0]?.handlers.onFinalContent?.('stale-answer');
      streams[0]?.handlers.onStatus?.('stale-stage');
    });
    await act(async () => streams[0]?.finish());

    // Then
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('new-answer');
    expect(screen.getByRole('status', { name: '에이전트 작업 중' })).toHaveTextContent('new-stage');
    await act(async () => streams[1]?.finish());
  });
});
