import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ChatPage from '../ChatPage';
import * as client from '../../../api/client';
import { useChatStore, type ChatSession } from '../../../stores/chatStore';
import { useProjectStore } from '../../../stores/projectStore';

const initialChatState = useChatStore.getState();
const initialProjectState = useProjectStore.getState();
const fixtureProjectId = 'project-history-fixture';
const storedSession: ChatSession = {
  id: 'stored-conversation',
  title: '저장된 대화',
  updatedAt: '2026-10-03T00:00:00.000Z',
  messages: [{ id: 'stored-user-message', role: 'user', content: '저장된 작업 내용' }],
  conversationRevision: 4,
};

function deferHydration() {
  let finish = () => {};
  const promise = new Promise<void>((resolve) => { finish = resolve; });
  return { hydrate: () => promise, finish } as const;
}

async function renderChatPage() {
  await act(async () => { render(<MemoryRouter><ChatPage /></MemoryRouter>); });
}

describe('ChatPage initial project history restoration', () => {
  let hydration = deferHydration();

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(`antigravity_chat_${fixtureProjectId}`, JSON.stringify({
      sessions: [storedSession],
      activeSessionId: storedSession.id,
    }));
    hydration = deferHydration();
    useChatStore.setState({
      sessions: [], activeSessionId: null, activeSession: null, messages: [],
      conversationRevision: 0, isStreaming: false, currentAssistantContent: '',
    });
    useProjectStore.setState({
      activeProjectId: null,
      activeProjectName: '테스트 프로젝트',
      activeProjectPath: '/fixture/project',
      hydrated: false,
      switchEpoch: 0,
      hydrateFromServer: hydration.hydrate,
    });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })));
    vi.spyOn(client, 'fetchModels').mockResolvedValue([]);
    vi.spyOn(client, 'fetchLocalModels').mockResolvedValue({ ok: true, total: 0, models: [] });
    vi.spyOn(client, 'fetchConversationHistory').mockRejectedValue(
      new client.ConversationRequestError('Local fixture has no server record', 'conversation_not_found', 404),
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    useChatStore.setState(initialChatState, true);
    useProjectStore.setState(initialProjectState, true);
    localStorage.clear();
  });

  async function finishInitialHydration() {
    await act(async () => {
      useProjectStore.setState({ activeProjectId: fixtureProjectId, hydrated: true });
      hydration.finish();
    });
  }

  it('restores ID-scoped local history when initial hydration resolves without a project switch', async () => {
    // Given
    await renderChatPage();
    expect(useChatStore.getState().sessions).toEqual([]);
    // When
    await finishInitialHydration();
    // Then
    expect(useProjectStore.getState().switchEpoch).toBe(0);
    expect(useChatStore.getState().activeSessionId).toBe(storedSession.id);
    expect(useChatStore.getState().sessions).toEqual([storedSession]);
    expect(screen.getByRole('region', { name: '대화 내용' })).toHaveTextContent('저장된 작업 내용');
  });

  it('keeps an early user-created conversation when initial hydration resolves', async () => {
    // Given
    await renderChatPage();
    act(() => { useChatStore.getState().createNewSession(); });
    const earlySessionId = useChatStore.getState().activeSessionId;
    // When
    await finishInitialHydration();
    // Then
    expect(useChatStore.getState().activeSessionId).toBe(earlySessionId);
    expect(useChatStore.getState().sessions.map((session) => session.id)).toEqual([earlySessionId]);
  });

  it('keeps an early draft when initial hydration resolves', async () => {
    // Given
    await renderChatPage();
    const textarea = screen.getByRole('textbox', { name: '메시지 입력' });
    fireEvent.change(textarea, { target: { value: '작업 초안' } });
    // When
    await finishInitialHydration();
    // Then
    expect(textarea).toHaveValue('작업 초안');
    expect(useChatStore.getState().sessions).toEqual([]);
  });
});
