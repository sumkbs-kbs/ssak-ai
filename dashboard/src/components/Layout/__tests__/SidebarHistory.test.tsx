import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useEffect } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Sidebar } from '../Sidebar';
import { ChatPage } from '../../Chat/ChatPage';
import * as client from '../../../api/client';
import { useChatStore, type ChatSession, type ChatState } from '../../../stores/chatStore';
import { useProjectStore } from '../../../stores/projectStore';
import { useGitStore } from '../../../stores/gitStore';
import { useUiStore } from '../../../stores/uiStore';

const initialChatState = useChatStore.getState();
const initialProjectState = useProjectStore.getState();
const initialGitState = useGitStore.getState();
const initialUiState = useUiStore.getState();
const projectId = 'project-sidebar-history';
const projectPath = '/fixture/sidebar-project';
const storedSession = {
  id: 'stored-sidebar-conversation',
  title: '저장된 프로젝트 대화',
  updatedAt: '2026-10-03T00:00:00.000Z',
  messages: [{ id: 'stored-message', role: 'user', content: '저장된 작업' }],
  conversationRevision: 4,
} satisfies ChatSession;
const liveSession = {
  id: 'live-sidebar-conversation',
  title: '진행 중인 대화',
  updatedAt: '2026-10-03T01:00:00.000Z',
  messages: [{ id: 'live-message', role: 'user', content: '현재 작업' }],
  conversationRevision: 1,
} satisfies ChatSession;

function saveHistory(key: string, session: ChatSession): void {
  localStorage.setItem(`antigravity_chat_${key}`, JSON.stringify({
    sessions: [session], activeSessionId: session.id,
  }));
}

function renderSidebar(pathname: string): void {
  render(<MemoryRouter initialEntries={[pathname]}><Sidebar /></MemoryRouter>);
}

function EarlyConversation(): null {
  useEffect(() => {
    useChatStore.setState({
      sessions: [liveSession], activeSessionId: liveSession.id,
      activeSession: liveSession, messages: liveSession.messages,
    });
  }, []);
  return null;
}

beforeEach(() => {
  localStorage.clear();
  saveHistory(projectId, storedSession);
  useChatStore.setState({
    ...initialChatState,
    sessions: [], activeSessionId: null, activeSession: null, messages: [],
    isStreaming: false, currentAssistantContent: '',
  }, true);
  useProjectStore.setState({
    ...initialProjectState, activeProjectId: projectId, activeProjectPath: projectPath,
    hydrateFromServer: vi.fn().mockResolvedValue(undefined),
  }, true);
  useGitStore.setState({ ...initialGitState, fetchStatus: vi.fn().mockResolvedValue(undefined) }, true);
  useUiStore.setState({ ...initialUiState, commandPaletteVisible: false, folderBrowserVisible: false }, true);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  useChatStore.setState(initialChatState, true);
  useProjectStore.setState(initialProjectState, true);
  useGitStore.setState(initialGitState, true);
  useUiStore.setState(initialUiState, true);
  localStorage.clear();
});

describe('Sidebar project history restoration', () => {
  it.each(['/studio', '/wiki', '/settings'])('restores saved conversations on a cold %s load', pathname => {
    // Given
    // When
    renderSidebar(pathname);
    // Then
    expect(screen.getByRole('button', { name: storedSession.title })).toHaveAttribute('aria-current', 'page');
    expect(useChatStore.getState().messages).toEqual(storedSession.messages);
  });

  it('waits for the project ID instead of adopting the initial legacy path cache', () => {
    // Given
    const legacySession = { ...liveSession, id: 'legacy-path-conversation', title: '이전 경로 대화' };
    saveHistory(projectPath, legacySession);
    useProjectStore.setState({ activeProjectId: null });
    renderSidebar('/studio');
    expect(useChatStore.getState().sessions).toEqual([]);
    // When
    act(() => { useProjectStore.setState({ activeProjectId: projectId, hydrated: true }); });
    // Then
    expect(screen.getByRole('button', { name: storedSession.title })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: legacySession.title })).toBeNull();
  });

  it.each(['/', '/chat', '/chat/'])('leaves history restoration to ChatPage on %s', pathname => {
    // Given
    // When
    renderSidebar(pathname);
    // Then
    expect(useChatStore.getState().sessions).toEqual([]);
    expect(screen.queryByRole('button', { name: storedSession.title })).toBeNull();
  });

  it.each([
    { name: 'session list', state: { sessions: [liveSession] } },
    { name: 'active session ID', state: { activeSessionId: liveSession.id } },
    { name: 'active session', state: { activeSession: liveSession } },
    { name: 'messages', state: { messages: liveSession.messages } },
    { name: 'stream', state: { isStreaming: true } },
  ] satisfies readonly { readonly name: string; readonly state: Partial<ChatState> }[])(
    'preserves an existing $name on a non-chat load', ({ state }) => {
      // Given
      useChatStore.setState(state);
      // When
      renderSidebar('/wiki');
      // Then
      expect(useChatStore.getState()).toMatchObject(state);
      expect(useChatStore.getState().sessions).not.toContainEqual(storedSession);
    },
  );

  it('checks current state when an early conversation is created before the sidebar effect', () => {
    // Given
    // When
    render(<MemoryRouter initialEntries={['/settings']}><EarlyConversation /><Sidebar /></MemoryRouter>);
    // Then
    expect(screen.getByRole('button', { name: liveSession.title })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('button', { name: storedSession.title })).toBeNull();
  });

  it('keeps an older conversation selected when a click from settings mounts ChatPage', async () => {
    // Given
    const olderSession = { ...liveSession, conversationRevision: 37 };
    const sessions = [
      storedSession,
      ...Array.from({ length: 4 }, (_, index) => ({
        ...storedSession, id: `other-conversation-${index}`, title: `다른 대화 ${index}`,
        conversationRevision: index + 10,
      })),
      olderSession,
    ];
    localStorage.setItem(`antigravity_chat_${projectId}`, JSON.stringify({
      sessions, activeSessionId: storedSession.id,
    }));
    useChatStore.getState().setSelectedModel('fixture-preserved-model');
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })));
    vi.spyOn(client, 'fetchModels').mockResolvedValue([]);
    vi.spyOn(client, 'fetchLocalModels').mockResolvedValue({ ok: true, total: 0, models: [] });
    vi.spyOn(client, 'fetchConversationHistory').mockRejectedValue(
      new client.ConversationRequestError('Fixture has no server record', 'conversation_not_found', 404),
    );
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <Sidebar />
        <Routes>
          <Route path="/settings" element={<main>설정</main>} />
          <Route path="/chat" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>,
    );
    // When
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: olderSession.title })); });
    // Then
    expect(useChatStore.getState()).toMatchObject({
      activeSessionId: olderSession.id,
      activeSession: olderSession,
      messages: olderSession.messages,
      conversationRevision: 37,
      selectedModel: 'fixture-preserved-model',
      sessions,
    });
    expect(screen.getByRole('button', { name: olderSession.title })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('region', { name: '대화 내용' })).toHaveTextContent('현재 작업');
  });
});
