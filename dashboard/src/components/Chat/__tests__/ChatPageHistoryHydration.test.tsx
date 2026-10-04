import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import * as client from '../../../api/client';
import { useChatStore, type ChatSession } from '../../../stores/chatStore';
import { useProjectStore } from '../../../stores/projectStore';
import { useUiStore } from '../../../stores/uiStore';
import ChatPage from '../ChatPage';

const projectId = 'history-hydration-project';
const projectPath = '/fixture/history-hydration';
const canonicalHistory: Awaited<ReturnType<typeof client.fetchConversationHistory>> = {
  snapshot: {
    conversation_id: 'history-conversation', project_id: projectId,
    revision: 8, message_count: 4,
  },
  messages: [
    { id: 'first-user', role: 'user', content: 'first-turn', created_at: 1 },
    { id: 'first-answer', role: 'assistant', content: 'shared-answer', created_at: 2 },
    { id: 'second-user', role: 'user', content: 'correction-turn', created_at: 3 },
    { id: 'second-answer', role: 'assistant', content: 'shared-answer', created_at: 4 },
  ],
  token_estimate: 8,
};

describe('ChatPage authoritative history hydration', () => {
  beforeEach(() => {
    localStorage.clear();
    const cached: ChatSession = {
      id: 'history-conversation', title: 'history-test', updatedAt: '2026-10-03',
      conversationRevision: 6,
      messages: [
        { role: 'user', content: 'first-turn' },
        { role: 'assistant', content: 'shared-answer' },
        { role: 'user', content: 'correction-turn' },
        { role: 'assistant', content: 'shared-answer' },
      ],
    };
    localStorage.setItem('agk_active_project', projectPath);
    localStorage.setItem(`antigravity_chat_${projectPath}`, JSON.stringify({
      sessions: [cached], activeSessionId: cached.id,
    }));
    useProjectStore.setState({
      activeProjectId: null, activeProjectName: '', activeProjectPath: '',
      hydrated: false, switchEpoch: 0, hydrateFromServer: async () => undefined,
    });
    useChatStore.setState({
      sessions: [], activeSessionId: null, activeSession: null, messages: [],
      conversationRevision: 0, isStreaming: false, currentAssistantContent: '', isAdaptiveMode: false,
    });
    useUiStore.setState({ toasts: [] });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })));
    vi.spyOn(client, 'fetchModels').mockResolvedValue([]);
    vi.spyOn(client, 'fetchLocalModels').mockResolvedValue({ ok: true, total: 0, models: [] });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('renders exactly canonical ordered messages when repeated cached replies receive server IDs after delayed project hydration', async () => {
    // Given
    let completeHistory: (history: typeof canonicalHistory) => void = () => undefined;
    const pendingHistory = new Promise<typeof canonicalHistory>((resolve) => { completeHistory = resolve; });
    vi.spyOn(client, 'fetchConversationHistory').mockReturnValue(pendingHistory);
    await act(async () => render(<MemoryRouter><ChatPage /></MemoryRouter>));
    act(() => useProjectStore.setState({
      activeProjectId: projectId, activeProjectName: 'history-test',
      activeProjectPath: projectPath, hydrated: true,
    }));
    await waitFor(() => expect(client.fetchConversationHistory).toHaveBeenCalledWith('history-conversation', projectId));
    const draft = screen.getByRole('textbox', { name: '메시지 입력' });
    fireEvent.change(draft, { target: { value: 'unsent-draft' } });

    // When
    await act(async () => completeHistory(canonicalHistory));

    // Then
    expect(useChatStore.getState().messages.map(({ id, role, content }) => ({ id, role, content }))).toEqual(
      canonicalHistory.messages.map(({ id, role, content }) => ({ id, role, content })),
    );
    const articles = within(screen.getByRole('region', { name: '대화 내용' })).getAllByRole('article');
    expect(articles.map((article) => article.getAttribute('aria-label'))).toEqual([
      '내 메시지', 'SSAK-AI 응답', '내 메시지', 'SSAK-AI 응답',
    ]);
    expect(draft).toHaveValue('unsent-draft');
  });
});
