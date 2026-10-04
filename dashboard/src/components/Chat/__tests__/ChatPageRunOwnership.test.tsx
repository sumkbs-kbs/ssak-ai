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
  signal: AbortSignal | undefined;
  finish: () => void;
}>;

const projectId = 'run-ownership-project';

function session(id: string, title: string): ChatSession {
  return {
    id,
    title,
    updatedAt: '2026-10-03T00:00:00.000Z',
    messages: [],
    conversationRevision: 0,
  };
}

async function renderPage(): Promise<void> {
  await act(async () => {
    render(<MemoryRouter><ChatPage /></MemoryRouter>);
  });
}

async function send(text: string): Promise<void> {
  const input = screen.getByRole('textbox', { name: '메시지 입력' });
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: 'Enter' });
  await waitFor(() => expect(client.streamChatCompletion).toHaveBeenCalled());
}

describe('ChatPage conversation run ownership', () => {
  const streams: DeferredStream[] = [];

  beforeEach(() => {
    streams.length = 0;
    localStorage.clear();
    const first = session('conversation-a', '대화 A');
    const second = session('conversation-b', '대화 B');
    useProjectStore.setState({
      activeProjectId: projectId,
      activeProjectName: '실행 소유권',
      activeProjectPath: '/fixture/run-ownership',
      hydrated: true,
      switchEpoch: 0,
      hydrateFromServer: async () => undefined,
    });
    useChatStore.setState({
      sessions: [first, second],
      activeSessionId: first.id,
      activeSession: first,
      messages: [],
      conversationRevision: 0,
      isStreaming: false,
      currentAssistantContent: '',
      isAdaptiveMode: false,
    });
    useUiStore.setState({ toasts: [] });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })));
    vi.spyOn(client, 'fetchModels').mockResolvedValue([]);
    vi.spyOn(client, 'fetchLocalModels').mockResolvedValue({ ok: true, total: 0, models: [] });
    vi.spyOn(client, 'fetchConversationHistory').mockRejectedValue(
      new client.ConversationRequestError('fixture has no server record', 'conversation_not_found', 404),
    );
    vi.spyOn(client, 'streamChatCompletion').mockImplementation((_payload, handlers, signal) => (
      new Promise<void>((resolve) => {
        streams.push({ handlers, signal, finish: resolve });
      })
    ));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('renders two chunks progressively in the single assistant message before completion', async () => {
    // Given
    await renderPage();
    await send('점진 응답');

    // When
    act(() => {
      streams[0]?.handlers.onChunk('첫 조각');
      streams[0]?.handlers.onChunk('과 둘째 조각');
    });

    // Then
    expect(screen.getByRole('region', { name: '대화 내용' })).toHaveTextContent('첫 조각과 둘째 조각');
    expect(useChatStore.getState().messages.filter((message) => message.role === 'assistant')).toHaveLength(1);

    await act(async () => streams[0]?.finish());
    expect(useChatStore.getState().messages.filter((message) => message.role === 'assistant')).toHaveLength(1);
  });

  it('keeps the reading position when scrolled away and offers a latest-response action', async () => {
    // Given
    await renderPage();
    await send('긴 응답');
    const feed = screen.getByRole('region', { name: '대화 내용' });
    Object.defineProperty(feed, 'scrollHeight', { configurable: true, value: 1200 });
    Object.defineProperty(feed, 'clientHeight', { configurable: true, value: 400 });
    fireEvent.scroll(feed, { target: { scrollTop: 200 } });

    // When
    act(() => streams[0]?.handlers.onChunk('새 조각'));

    // Then
    const latest = screen.getByRole('button', { name: '최신 응답 보기' });
    expect(feed.scrollTop).toBe(200);
    fireEvent.click(latest);
    expect(feed.scrollTop).toBe(1200);
    expect(screen.queryByRole('button', { name: '최신 응답 보기' })).not.toBeInTheDocument();
    await act(async () => streams[0]?.finish());
  });

  it('does not reacquire ownership after switching away and back before late events arrive', async () => {
    // Given
    await renderPage();
    await send('대화 A 작업');
    act(() => streams[0]?.handlers.onChunk('A의 일부'));

    // When
    act(() => {
      useChatStore.getState().switchSession('conversation-b');
      useChatStore.getState().switchSession('conversation-a');
    });
    act(() => streams[0]?.handlers.onChunk('늦은 A 조각'));
    await act(async () => streams[0]?.finish());

    // Then
    expect(streams[0]?.signal?.aborted).toBe(true);
    expect(useChatStore.getState().activeSessionId).toBe('conversation-a');
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('A의 일부');
    expect(useChatStore.getState().sessions.find((item) => item.id === 'conversation-b')?.messages).toEqual([]);
  });

  it('does not resurrect a deleted running conversation when late events arrive', async () => {
    // Given
    await renderPage();
    await send('삭제할 대화 작업');
    act(() => streams[0]?.handlers.onChunk('삭제 전 일부'));

    // When
    act(() => useChatStore.getState().deleteSession('conversation-a'));
    act(() => streams[0]?.handlers.onChunk('삭제 뒤 늦은 조각'));
    await act(async () => streams[0]?.finish());

    // Then
    expect(useChatStore.getState().sessions.some((item) => item.id === 'conversation-a')).toBe(false);
    expect(useChatStore.getState().activeSessionId).toBe('conversation-b');
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it('does not write a running response into a newly created conversation', async () => {
    // Given
    await renderPage();
    await send('기존 대화 작업');
    act(() => streams[0]?.handlers.onChunk('기존 대화 일부'));

    // When
    act(() => useChatStore.getState().createNewSession());
    const newSessionId = useChatStore.getState().activeSessionId;
    act(() => streams[0]?.handlers.onChunk('새 대화로 새면 안 됨'));
    await act(async () => streams[0]?.finish());

    // Then
    expect(useChatStore.getState().activeSessionId).toBe(newSessionId);
    expect(useChatStore.getState().messages).toEqual([]);
    expect(useChatStore.getState().sessions.find((item) => item.id === 'conversation-a')?.messages.at(-1)?.content).toBe('기존 대화 일부');
  });

  it('keeps a new run authoritative after Stop even when the stopped stream finishes late', async () => {
    // Given
    await renderPage();
    await send('첫 실행');
    act(() => streams[0]?.handlers.onChunk('중단 전 일부'));
    fireEvent.click(screen.getByRole('button', { name: '생성 중단' }));

    // When
    await send('두 번째 실행');
    act(() => streams[1]?.handlers.onChunk('새 실행 답변'));
    act(() => streams[0]?.handlers.onChunk('중단 뒤 늦은 조각'));
    await act(async () => streams[0]?.finish());

    // Then
    expect(useChatStore.getState().isStreaming).toBe(true);
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('새 실행 답변');
    await act(async () => streams[1]?.finish());
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('새 실행 답변');
  });

  it('keeps each queued image with the prompt that owned it', async () => {
    // Given
    await renderPage();
    await send('현재 실행');
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!(fileInput instanceof HTMLInputElement)) {
      throw new TypeError('Expected the chat attachment input.');
    }

    // When
    fireEvent.change(fileInput, {
      target: { files: [new File(['one'], 'one.png', { type: 'image/png' })] },
    });
    await waitFor(() => expect(screen.getByTestId('chat-attachment-chip')).toHaveAttribute('data-attachment-name', 'one.png'));
    await send('첫 이미지 질문');
    fireEvent.change(fileInput, {
      target: { files: [new File(['two'], 'two.png', { type: 'image/png' })] },
    });
    await waitFor(() => expect(screen.getAllByTestId('chat-attachment-chip')).toHaveLength(1));
    await send('둘째 이미지 질문');
    fireEvent.click(screen.getByRole('button', { name: '위로 이동' }));
    await act(async () => streams[0]?.finish());
    await waitFor(() => expect(client.streamChatCompletion).toHaveBeenCalledTimes(2));
    await act(async () => streams[1]?.finish());
    await waitFor(() => expect(client.streamChatCompletion).toHaveBeenCalledTimes(3));

    // Then
    expect(vi.mocked(client.streamChatCompletion).mock.calls[1]?.[0]).toEqual(expect.objectContaining({
      attachments: [expect.objectContaining({ name: 'two.png' })],
    }));
    expect(vi.mocked(client.streamChatCompletion).mock.calls[2]?.[0]).toEqual(expect.objectContaining({
      attachments: [expect.objectContaining({ name: 'one.png' })],
    }));
    await act(async () => streams[2]?.finish());
  });

  it('keeps an attachment-owned dependent turn editable when its parent stream fails', async () => {
    // Given
    await renderPage();
    await send('부모 실행');
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!(fileInput instanceof HTMLInputElement)) {
      throw new TypeError('Expected the chat attachment input.');
    }
    fireEvent.change(fileInput, {
      target: { files: [new File(['dependent'], 'dependent.png', { type: 'image/png' })] },
    });
    await waitFor(() => expect(screen.getByTestId('chat-attachment-chip')).toHaveAttribute('data-attachment-name', 'dependent.png'));
    await send('부모 결과에 의존하는 후속 질문');

    // When
    act(() => streams[0]?.handlers.onError(new Error('provider failed')));
    await act(async () => streams[0]?.finish());

    // Then
    expect(client.streamChatCompletion).toHaveBeenCalledTimes(1);
    expect(screen.getByText('부모 결과에 의존하는 후속 질문')).toBeInTheDocument();
    expect(useUiStore.getState().toasts.at(-1)?.message).toContain(
      '부모 실행이 실패해 후속 대기 메시지를 자동 전송하지 않았습니다',
    );
    fireEvent.click(screen.getByRole('button', { name: '대기 메시지 편집' }));
    expect(screen.getByRole('textbox', { name: '메시지 입력' })).toHaveValue('부모 결과에 의존하는 후속 질문');
    expect(screen.getByTestId('chat-attachment-chip')).toHaveAttribute('data-attachment-name', 'dependent.png');
  });

  it('does not drain the dependent queue after a conversation revision conflict', async () => {
    // Given
    await renderPage();
    await send('충돌할 부모 실행');
    await send('충돌 뒤 다시 검토할 후속 질문');

    // When
    act(() => streams[0]?.handlers.onError(new client.ConversationRevisionConflictError({
      ok: false,
      error: 'stale_conversation_revision',
      detail: 'revision conflict',
      conversation_id: 'conversation-a',
      expected_revision: 0,
      current_revision: 1,
    })));
    await act(async () => streams[0]?.finish());

    // Then
    expect(client.streamChatCompletion).toHaveBeenCalledTimes(1);
    expect(screen.getByText('충돌 뒤 다시 검토할 후속 질문')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '대기 메시지 편집' })).toBeEnabled();
  });

  it('does not drain the dependent queue after an Adaptive failure', async () => {
    // Given
    let resolveAgent = (_value: Awaited<ReturnType<typeof client.askAgent>>) => {};
    const pendingAgent = new Promise<Awaited<ReturnType<typeof client.askAgent>>>((resolve) => {
      resolveAgent = resolve;
    });
    vi.spyOn(client, 'askAgent').mockReturnValue(pendingAgent);
    useChatStore.setState({ isAdaptiveMode: true });
    await renderPage();
    const input = screen.getByRole('textbox', { name: '메시지 입력' });
    fireEvent.change(input, { target: { value: 'Adaptive 부모 실행' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(client.askAgent).toHaveBeenCalledTimes(1));
    fireEvent.change(input, { target: { value: 'Adaptive 후속 질문' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(screen.getByText('Adaptive 후속 질문')).toBeInTheDocument());

    // When
    await act(async () => resolveAgent({
      ok: false,
      task: 'Adaptive 부모 실행',
      answer: '',
      used_web: false,
      used_graphify: false,
      steps: 1,
      total_seconds: 0.1,
      passed: false,
      mode: 'adaptive',
      error: 'adaptive failed',
    }));

    // Then
    expect(client.askAgent).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Adaptive 후속 질문')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '대기 메시지 편집' })).toBeEnabled();
  });

  it('deletes one queued turn and clears the remaining turns without sending them', async () => {
    // Given
    await renderPage();
    await send('현재 실행');
    await send('삭제할 대기 턴');
    await send('남길 대기 턴');
    await send('함께 비울 대기 턴');

    // When
    fireEvent.click(screen.getAllByRole('button', { name: '대기 메시지 삭제' })[0]);
    expect(screen.queryByText('삭제할 대기 턴')).not.toBeInTheDocument();
    expect(screen.getByText('남길 대기 턴')).toBeInTheDocument();
    fireEvent.click(screen.getByText('대기열 모두 비우기'));
    await act(async () => streams[0]?.finish());

    // Then
    expect(screen.queryByText('Queued Messages')).not.toBeInTheDocument();
    expect(client.streamChatCompletion).toHaveBeenCalledTimes(1);
  });

  it('ignores a stale compaction result after navigating away and back', async () => {
    // Given
    let resolveCompaction = (_value: Awaited<ReturnType<typeof client.compactConversation>>) => {};
    const pendingCompaction = new Promise<Awaited<ReturnType<typeof client.compactConversation>>>((resolve) => {
      resolveCompaction = resolve;
    });
    vi.spyOn(client, 'compactConversation').mockReturnValue(pendingCompaction);
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: '대화 압축: 대화 A' }));
    await waitFor(() => expect(client.compactConversation).toHaveBeenCalledTimes(1));

    // When
    act(() => {
      useChatStore.getState().switchSession('conversation-b');
      useChatStore.getState().switchSession('conversation-a');
    });
    await act(async () => resolveCompaction({
      conversation_id: 'conversation-a',
      project_id: projectId,
      revision: 99,
      message_count: 0,
      summary: 'stale summary',
      retained_message_ids: [],
    }));

    // Then
    expect(useChatStore.getState().conversationRevision).toBe(0);
    expect(screen.getByRole('button', { name: '대화 압축: 대화 A' })).not.toHaveAttribute('aria-busy', 'true');
  });

  it('ignores stale server history after navigating away and back', async () => {
    // Given
    await renderPage();
    let resolveHistory = (_value: Awaited<ReturnType<typeof client.fetchConversationHistory>>) => {};
    const pendingHistory = new Promise<Awaited<ReturnType<typeof client.fetchConversationHistory>>>((resolve) => {
      resolveHistory = resolve;
    });
    vi.mocked(client.fetchConversationHistory).mockReturnValueOnce(pendingHistory);

    // When
    act(() => useChatStore.getState().switchSession('conversation-b'));
    await waitFor(() => expect(client.fetchConversationHistory).toHaveBeenCalledWith('conversation-b', projectId));
    act(() => useChatStore.getState().switchSession('conversation-a'));
    await act(async () => resolveHistory({
      snapshot: {
        conversation_id: 'conversation-b',
        project_id: projectId,
        revision: 77,
        message_count: 1,
      },
      messages: [{
        id: 'stale-b-message',
        role: 'assistant',
        content: '오래된 B 이력',
        created_at: 1,
      }],
      token_estimate: 4,
    }));

    // Then
    expect(useChatStore.getState().activeSessionId).toBe('conversation-a');
    expect(useChatStore.getState().messages).toEqual([]);
    expect(useChatStore.getState().conversationRevision).toBe(0);
  });

  it('does not start a history refresh while a new conversation run is streaming', async () => {
    // Given
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      activeSession: null,
      messages: [],
      conversationRevision: 0,
      isStreaming: false,
      currentAssistantContent: 'previous-run-buffer',
    });
    await renderPage();
    await send('새 대화 첫 실행');
    const createdConversationId = useChatStore.getState().activeSessionId;

    // When
    act(() => {
      streams[0]?.handlers.onChunk('최신 스트림 답변');
      streams[0]?.handlers.onConversationSnapshot?.({
        conversation_id: createdConversationId ?? '',
        project_id: projectId,
        revision: 1,
        message_count: 2,
      });
    });

    // Then
    expect(client.fetchConversationHistory).not.toHaveBeenCalled();
    expect(useChatStore.getState().conversationRevision).toBe(1);
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('최신 스트림 답변');
    expect(useChatStore.getState().currentAssistantContent).toBe('최신 스트림 답변');
    await act(async () => streams[0]?.finish());
  });

  it('does not apply an idle history response after the source revision advances', async () => {
    // Given
    let resolveHistory = (_value: Awaited<ReturnType<typeof client.fetchConversationHistory>>) => {};
    const pendingHistory = new Promise<Awaited<ReturnType<typeof client.fetchConversationHistory>>>((resolve) => {
      resolveHistory = resolve;
    });
    vi.mocked(client.fetchConversationHistory).mockReturnValueOnce(pendingHistory);
    await renderPage();
    await waitFor(() => expect(client.fetchConversationHistory).toHaveBeenCalledWith('conversation-a', projectId));

    // When
    act(() => useChatStore.getState().applyServerSnapshot({
      conversation_id: 'conversation-a',
      revision: 3,
      messages: [{ id: 'newer-message', role: 'assistant', content: '더 최신인 답변' }],
    }));
    await act(async () => resolveHistory({
      snapshot: {
        conversation_id: 'conversation-a',
        project_id: projectId,
        revision: 2,
        message_count: 1,
      },
      messages: [{
        id: 'stale-history-message',
        role: 'assistant',
        content: '오래된 이력 답변',
        created_at: 1,
      }],
      token_estimate: 4,
    }));

    // Then
    expect(useChatStore.getState().conversationRevision).toBe(3);
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('더 최신인 답변');
  });
});
