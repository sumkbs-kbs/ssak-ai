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

  it.each([
    ['provider_protocol_error', 'incomplete_stream'],
    ['agent_execution_error', 'task_failed'],
  ])('preserves the queue and partial answer for %s with the real parser', async (type, code) => {
    // Given
    vi.mocked(client.streamChatCompletion).mockRestore();
    const encoder = new TextEncoder();
    const wire = new TransformStream<Uint8Array, Uint8Array>();
    const writer = wire.writable.getWriter();
    const chatRequests: string[] = [];
    vi.mocked(fetch).mockImplementation(async (input) => {
      if (input === '/v1/chat/completions') {
        chatRequests.push(input);
        return new Response(wire.readable, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
      }
      return new Response('{}', { status: 200 });
    });
    await act(async () => render(<MemoryRouter><ChatPage /></MemoryRouter>));
    const input = screen.getByRole('textbox', { name: '메시지 입력' });
    fireEvent.change(input, { target: { value: 'first-turn' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(chatRequests).toHaveLength(1));
    await act(async () => writer.write(encoder.encode('data: {"choices":[{"delta":{"content":"partial-answer"}}]}\n\n')));
    fireEvent.change(input, { target: { value: 'queued-turn' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByText('queued-turn')).toBeInTheDocument();

    // When
    await act(async () => {
      await writer.write(encoder.encode(`event: error\ndata: ${JSON.stringify({ error: { type, code, message: 'Incomplete stream' } })}\n\n`));
      await writer.close();
    });
    await waitFor(() => expect(useChatStore.getState().isStreaming).toBe(false));

    // Then
    expect(chatRequests).toHaveLength(1);
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('partial-answer');
    expect(screen.getByText('queued-turn')).toBeInTheDocument();
    expect(screen.getByText('Incomplete stream')).toBeInTheDocument();
    expect(useChatStore.getState().messages.filter((message) => message.role === 'user')).toHaveLength(1);
  });

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
