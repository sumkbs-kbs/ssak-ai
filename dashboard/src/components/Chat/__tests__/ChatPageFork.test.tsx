import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ChatPage from '../ChatPage';
import * as client from '../../../api/client';
import type { ConversationHistoryWire, ConversationSnapshotWire } from '../../../api/client';
import type { ChatSession } from '../../../stores/chatStore';
import { useChatStore } from '../../../stores/chatStore';
import { useProjectStore } from '../../../stores/projectStore';
import { useUiStore } from '../../../stores/uiStore';

const initialChatState = useChatStore.getState();
const initialProjectState = useProjectStore.getState();
const initialUiState = useUiStore.getState();

const sourceSession: ChatSession = {
  id: 'source-conversation',
  title: '원본 대화',
  updatedAt: '2026-10-03T00:00:00.000Z',
  messages: [
    { id: 'source-user', role: 'user', content: '원본 요청' },
    { id: 'source-assistant', role: 'assistant', content: '원본 응답' },
  ],
  conversationRevision: 4,
};

const forkSnapshot: ConversationSnapshotWire = {
  conversation_id: 'fork-conversation',
  project_id: 'project-fork',
  revision: 0,
  message_count: 2,
};

const forkHistory: ConversationHistoryWire = {
  snapshot: forkSnapshot,
  messages: [
    { id: 'fork-user', role: 'user', content: '원본 요청', created_at: 1 },
    { id: 'fork-tool', role: 'tool', content: '도구 근거', created_at: 2 },
  ],
  token_estimate: 8,
};

function sourceMissing(): client.ConversationRequestError {
  return new client.ConversationRequestError('fixture has no remote source record', 'conversation_not_found', 404);
}

function seedSource(streaming = false): void {
  useChatStore.setState({
    sessions: [sourceSession],
    activeSessionId: sourceSession.id,
    activeSession: sourceSession,
    messages: sourceSession.messages,
    conversationRevision: sourceSession.conversationRevision,
    isStreaming: streaming,
    currentAssistantContent: '',
  });
  useProjectStore.setState({
    activeProjectId: 'project-fork',
    activeProjectName: '분기 테스트 프로젝트',
    activeProjectPath: '/fixture/fork',
    projectRevision: 7,
    switchEpoch: 3,
    hydrated: true,
    hydrateFromServer: vi.fn().mockResolvedValue(undefined),
  });
}

async function renderChatPage(): Promise<void> {
  await act(async () => {
    render(<MemoryRouter><ChatPage /></MemoryRouter>);
  });
}

function forkButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /대화 분기:/ });
}

describe('ChatPage conversation fork integration', () => {
  beforeEach(() => {
    localStorage.clear();
    seedSource();
    useUiStore.setState({ toasts: [] });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })));
    vi.spyOn(client, 'fetchModels').mockResolvedValue([]);
    vi.spyOn(client, 'fetchLocalModels').mockResolvedValue({ ok: true, total: 0, models: [] });
    vi.spyOn(client, 'streamChatCompletion').mockResolvedValue(undefined);
    vi.spyOn(client, 'compactConversation').mockResolvedValue({
      conversation_id: sourceSession.id,
      project_id: 'project-fork',
      revision: 5,
      message_count: 2,
    });
    vi.spyOn(client, 'fetchConversationHistory').mockRejectedValue(sourceMissing());
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    useChatStore.setState(initialChatState, true);
    useProjectStore.setState(initialProjectState, true);
    useUiStore.setState(initialUiState, true);
    localStorage.clear();
  });

  it('forks through the native button with canonical history and preserves the original session', async () => {
    vi.spyOn(client, 'forkConversation').mockResolvedValue(forkSnapshot);
    vi.spyOn(client, 'fetchConversationHistory').mockImplementation((conversationId) => (
      conversationId === forkSnapshot.conversation_id
        ? Promise.resolve(forkHistory)
        : Promise.reject(sourceMissing())
    ));

    await renderChatPage();
    fireEvent.click(forkButton());

    await waitFor(() => expect(useChatStore.getState().activeSessionId).toBe(forkSnapshot.conversation_id));
    expect(client.forkConversation).toHaveBeenCalledWith({
      conversation_id: sourceSession.id,
      expected_revision: 4,
      project_id: 'project-fork',
    });
    expect(useChatStore.getState().sessions.find((session) => session.id === sourceSession.id)).toMatchObject({
      id: sourceSession.id,
      title: sourceSession.title,
      messages: sourceSession.messages,
      conversationRevision: 4,
    });
    expect(useChatStore.getState().messages).toEqual([
      { id: 'fork-user', role: 'user', content: '원본 요청' },
      { id: 'fork-tool', role: 'system', content: '도구 근거' },
    ]);
  });

  it('forks through the command event with the same canonical adoption path', async () => {
    vi.spyOn(client, 'forkConversation').mockResolvedValue(forkSnapshot);
    vi.spyOn(client, 'fetchConversationHistory').mockImplementation((conversationId) => (
      conversationId === forkSnapshot.conversation_id
        ? Promise.resolve(forkHistory)
        : Promise.reject(sourceMissing())
    ));

    await renderChatPage();
    act(() => {
      window.dispatchEvent(new Event('agk:conversation-fork'));
    });

    await waitFor(() => expect(useChatStore.getState().activeSessionId).toBe(forkSnapshot.conversation_id));
    expect(client.forkConversation).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().messages[1]).toMatchObject({ role: 'system', content: '도구 근거' });
  });

  it('keeps a draft and blocks Enter, send, and compact while a fork is pending', async () => {
    let resolveFork: ((value: ConversationSnapshotWire) => void) | undefined;
    vi.spyOn(client, 'forkConversation').mockImplementation(() => new Promise((resolve) => {
      resolveFork = resolve;
    }));

    await renderChatPage();
    const textarea = screen.getByRole('textbox', { name: '메시지 입력' });
    fireEvent.change(textarea, { target: { value: '분기 중에도 남아야 할 초안' } });
    fireEvent.click(forkButton());

    await waitFor(() => expect(forkButton()).toHaveAttribute('aria-busy', 'true'));
    const send = screen.getByRole('button', { name: '메시지 전송' });
    const compact = screen.getByRole('button', { name: /대화 압축:/ });
    expect(send).toBeDisabled();
    expect(compact).toBeDisabled();
    fireEvent.keyDown(textarea, { key: 'Enter' });
    fireEvent.click(compact);

    expect(textarea).toHaveValue('분기 중에도 남아야 할 초안');
    expect(client.streamChatCompletion).not.toHaveBeenCalled();
    expect(client.compactConversation).not.toHaveBeenCalled();

    resolveFork?.(forkSnapshot);
  });

  it('disables an empty conversation fork action', async () => {
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      activeSession: null,
      messages: [],
      conversationRevision: 0,
      isStreaming: false,
    });

    await renderChatPage();

    expect(forkButton()).toBeDisabled();
  });

  it('does not start a fork from the command event while the source is streaming', async () => {
    seedSource(true);
    const fork = vi.spyOn(client, 'forkConversation');

    await renderChatPage();
    expect(forkButton()).toBeDisabled();
    act(() => {
      window.dispatchEvent(new Event('agk:conversation-fork'));
    });

    expect(fork).not.toHaveBeenCalled();
  });
});
