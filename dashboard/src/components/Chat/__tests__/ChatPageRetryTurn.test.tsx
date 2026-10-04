import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ChatStreamHandlers } from '../../../api/client';
import * as client from '../../../api/client';
import { useChatStore, type ChatSession } from '../../../stores/chatStore';
import { useProjectStore } from '../../../stores/projectStore';
import { useUiStore } from '../../../stores/uiStore';
import ChatPage from '../ChatPage';

type DeferredStream = Readonly<{
  handlers: ChatStreamHandlers;
  finish: () => void;
}>;

const projectId = 'retry-turn-project';
const history: Awaited<ReturnType<typeof client.fetchConversationHistory>> = {
  snapshot: {
    conversation_id: 'conversation-a',
    project_id: projectId,
    revision: 7,
    message_count: 2,
  },
  messages: [
    { id: 'old-user', role: 'user', content: 'old-turn', created_at: 1 },
    { id: 'old-answer', role: 'assistant', content: 'old-answer', created_at: 2 },
  ],
  token_estimate: 4,
};

function session(id: string): ChatSession {
  return { id, title: id, updatedAt: '2026-10-03T00:00:00.000Z', messages: [], conversationRevision: 0 };
}

describe('ChatPage failed turn retry', () => {
  const streams: DeferredStream[] = [];

  beforeEach(() => {
    streams.length = 0;
    localStorage.clear();
    const first = session('conversation-a');
    const second = session('conversation-b');
    useProjectStore.setState({
      activeProjectId: projectId,
      activeProjectName: 'retry-turn',
      activeProjectPath: '/fixture/retry-turn',
      hydrated: true,
      switchEpoch: 0,
      hydrateFromServer: async () => undefined,
    });
    useChatStore.setState({
      sessions: [first, second], activeSessionId: first.id, activeSession: first,
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

  async function failWithConflict(): Promise<void> {
    vi.mocked(client.fetchConversationHistory).mockResolvedValueOnce(history);
    act(() => streams[0]?.handlers.onError(new client.ConversationRevisionConflictError({
      ok: false, error: 'stale_conversation_revision', detail: 'revision conflict',
      conversation_id: 'conversation-a', expected_revision: 0, current_revision: 7,
    })));
    await act(async () => streams[0]?.finish());
    await waitFor(() => expect(screen.getByRole('button', { name: '다시 시도' })).toBeEnabled());
  }

  async function submitTurn(text: string): Promise<void> {
    const input = screen.getByRole('textbox', { name: '메시지 입력' });
    fireEvent.change(input, { target: { value: text } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(client.streamChatCompletion).toHaveBeenCalledTimes(1));
  }

  it('retries the rejected text and image with the refreshed revision when conflict sync removes the turn', async () => {
    // Given
    await act(async () => render(<MemoryRouter><ChatPage /></MemoryRouter>));
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!(fileInput instanceof HTMLInputElement)) throw new TypeError('Expected attachment input.');
    fireEvent.change(fileInput, {
      target: { files: [new File(['image'], 'retry.png', { type: 'image/png' })] },
    });
    await waitFor(() => expect(screen.getByTestId('chat-attachment-chip')).toBeInTheDocument());
    await submitTurn('rejected-turn');
    await failWithConflict();

    // When
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    await waitFor(() => expect(client.streamChatCompletion).toHaveBeenCalledTimes(2));

    // Then
    expect(vi.mocked(client.streamChatCompletion).mock.calls[1]?.[0]).toEqual(expect.objectContaining({
      new_turn: { role: 'user', content: 'rejected-turn' },
      conversation_id: 'conversation-a',
      conversation_revision: 7,
      attachments: [{ name: 'retry.png', mime_type: 'image/png', data_base64: 'aW1hZ2U=' }],
    }));
    await act(async () => streams[1]?.finish());
  });

  it('clears the failed turn and retry notice when switching conversations', async () => {
    // Given
    await act(async () => render(<MemoryRouter><ChatPage /></MemoryRouter>));
    await submitTurn('rejected-turn');
    await failWithConflict();

    // When
    act(() => {
      useChatStore.getState().switchSession('conversation-b');
      useChatStore.getState().switchSession('conversation-a');
    });

    // Then
    expect(screen.queryByRole('button', { name: '다시 시도' })).not.toBeInTheDocument();
    expect(client.streamChatCompletion).toHaveBeenCalledTimes(1);
  });
});
