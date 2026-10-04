/**
 * Chat Store (Zustand)
 * =====================
 * Manages chat sessions, messages, streaming state, and model selection.
 */

import { create } from 'zustand';
import { useProjectStore } from './projectStore';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  id?: string;
  agentMeta?: {
    used_web?: boolean;
    used_graphify?: boolean;
    steps?: number;
    total_seconds?: number;
    passed?: boolean | null;
    mode?: string;
  };
}

export interface ChatSession {
  id: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
  /** Authoritative server revision (CTX-01). Client projection only. */
  conversationRevision: number;
}

export type ForkedConversationSession = Readonly<{
  sourceConversationId: string;
  conversationId: string;
  revision: number;
  messages: readonly ChatMessage[];
}>;

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 8);
}

export function generateChatTitle(content: string): string {
  if (!content) return '새 대화';
  // Strip code blocks, think blocks, html tags, markdown formatting
  const cleaned = content
    .replace(/```[\s\S]*?```/g, '')
    .replace(/<think>[\s\S]*?<\/think>/g, '')
    .replace(/^#+\s*/, '')
    .replace(/^[>\s*-]+/gm, '')
    .trim();

  const firstLine = cleaned.split('\n').map(l => l.trim()).find(l => l.length > 0) || content.trim();
  if (firstLine.length <= 28) {
    return firstLine;
  }
  return firstLine.slice(0, 26) + '...';
}

export interface ChatState {
  // Sessions
  sessions: ChatSession[];
  activeSessionId: string | null;
  activeSession: ChatSession | null;

  // Messages
  messages: ChatMessage[];
  /** Active conversation revision mirrored from server CAS (CTX-01). */
  conversationRevision: number;
  isStreaming: boolean;
  currentAssistantContent: string;

  // Models
  models: Array<{ id: string; role?: string; description?: string }>;
  selectedModel: string;

  // ToDos
  isPlanMode: boolean;
  isTddMode: boolean;
  isAdaptiveMode: boolean;

  // Actions
  createNewSession: () => void;
  switchSession: (id: string) => void;
  deleteSession: (id: string) => void;
  updateSessionTitle: (id: string, title: string) => void;
  addMessage: (msg: ChatMessage) => void;
  updateLastAssistantMessage: (content: string, agentMeta?: ChatMessage['agentMeta']) => void;
  setConversationRevision: (revision: number) => void;
  applyServerSnapshot: (snapshot: {
    conversation_id: string;
    revision: number;
    summary?: string | null;
    retained_message_ids?: string[];
    messages?: ChatMessage[];
  }) => void;
  adoptForkedSession: (fork: ForkedConversationSession) => boolean;
  setStreaming: (val: boolean) => void;
  setCurrentAssistantContent: (content: string) => void;
  appendToCurrentAssistantContent: (chunk: string) => void;
  setModels: (models: Array<{ id: string; role?: string; description?: string }>) => void;
  setSelectedModel: (model: string) => void;
  setPlanMode: (val: boolean) => void;
  setTddMode: (val: boolean) => void;
  setAdaptiveMode: (val: boolean) => void;
  loadFromStorage: () => void;
  saveToStorage: () => void;
  clearForProjectSwitch: () => void;
}

const STORAGE_KEY_PREFIX = 'antigravity_chat_';
const MODEL_PREFERENCE_KEY = 'agk_chat_selected_model';

/**
 * 서버가 대화 id 없이 들어온 요청에 붙이는 **폴백** id(`project_binding` 계약).
 *
 * NX-09: 이것은 정체성이 아니다. 클라이언트가 이 값을 자기 대화 id 로 채택하면 서로 다른
 * 사용자/창의 첫 대화가 **한 레코드로 합쳐지고**(거기서 삭제하면 남의 이력도 함께 지워진다),
 * 이력 목록에는 그 대화가 없다(세션 항목이 만들어지지 않았으므로).
 */
export const SERVER_FALLBACK_CONVERSATION_ID = 'conv_unspecified';

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  activeSession: null,
  messages: [],
  conversationRevision: 0,
  isStreaming: false,
  currentAssistantContent: '',
  models: [],
  selectedModel: 'default',
  isPlanMode: false,
  isTddMode: false,
  isAdaptiveMode: false,

  createNewSession: () => {
    const id = generateId();
    const session: ChatSession = {
      id,
      title: '새 대화',
      updatedAt: new Date().toISOString(),
      messages: [],
      conversationRevision: 0,
    };
    set({
      activeSessionId: id,
      activeSession: session,
      messages: [],
      conversationRevision: 0,
      sessions: [session, ...get().sessions.filter(s => s.id !== id)],
    });
    get().saveToStorage();
  },

  switchSession: (id: string) => {
    const session = get().sessions.find(s => s.id === id);
    if (session) {
      set({
        activeSessionId: id,
        activeSession: session,
        messages: session.messages,
        conversationRevision: session.conversationRevision ?? 0,
      });
    }
  },

  deleteSession: (id: string) => {
    const { sessions, activeSessionId } = get();
    const filtered = sessions.filter(s => s.id !== id);
    set({ sessions: filtered });

    if (activeSessionId === id) {
      if (filtered.length > 0) {
        get().switchSession(filtered[0].id);
      } else {
        get().createNewSession();
      }
    } else {
      get().saveToStorage();
    }
  },

  updateSessionTitle: (id: string, title: string) => {
    const trimmed = title.trim();
    if (!trimmed) return;
    const { sessions, activeSessionId, activeSession } = get();
    const updatedSessions = sessions.map(s =>
      s.id === id ? { ...s, title: trimmed, updatedAt: new Date().toISOString() } : s
    );
    const updatedActive = activeSession && activeSession.id === id
      ? { ...activeSession, title: trimmed, updatedAt: new Date().toISOString() }
      : activeSession;
    set({ sessions: updatedSessions, activeSession: updatedActive });
    get().saveToStorage();
  },

  addMessage: (msg: ChatMessage) => {
    const { messages, activeSessionId, sessions, activeSession } = get();
    const newMessages = [...messages, msg];

    // NX-09: 세션이 없는 상태에서 첫 메시지가 들어오면 **클라이언트가** 대화 id 를 만든다.
    // (그러지 않으면 요청에 conversation_id 가 없고, 서버 폴백을 정체성으로 채택한다 —
    //  첫 대화가 이력 목록에도 없고 다른 창의 첫 대화와 한 레코드로 섞인다.)
    if (!activeSessionId) {
      const id = generateId();
      const title = msg.role === 'user' && msg.content.trim()
        ? generateChatTitle(msg.content)
        : '새 대화';
      const session: ChatSession = {
        id,
        title,
        updatedAt: new Date().toISOString(),
        messages: newMessages,
        conversationRevision: 0,
      };
      set({
        activeSessionId: id,
        activeSession: session,
        messages: newMessages,
        sessions: [session, ...sessions],
      });
      get().saveToStorage();
      return;
    }

    let derivedTitle: string | undefined;
    const currentSession = sessions.find(s => s.id === activeSessionId) || activeSession;
    const isDefaultTitle = !currentSession?.title ||
      currentSession.title === 'New Chat' ||
      currentSession.title === '새 작업' ||
      currentSession.title === '새 채팅' ||
      currentSession.title === '새 대화' ||
      currentSession.title === '대화';

    if (msg.role === 'user' && isDefaultTitle && msg.content.trim()) {
      derivedTitle = generateChatTitle(msg.content);
    }

    const updatedSessions = sessions.map(s => {
      if (s.id !== activeSessionId) return s;
      return {
        ...s,
        messages: newMessages,
        title: derivedTitle || s.title,
        updatedAt: new Date().toISOString(),
      };
    });

    const updatedActive = activeSession && activeSession.id === activeSessionId
      ? {
          ...activeSession,
          messages: newMessages,
          title: derivedTitle || activeSession.title,
          updatedAt: new Date().toISOString(),
        }
      : activeSession;

    set({ messages: newMessages, sessions: updatedSessions, activeSession: updatedActive });
    get().saveToStorage();
  },

  updateLastAssistantMessage: (content: string, agentMeta?: ChatMessage['agentMeta']) => {
    const { messages, activeSessionId, sessions } = get();
    const newMessages = [...messages];
    if (newMessages.length > 0 && newMessages[newMessages.length - 1].role === 'assistant') {
      newMessages[newMessages.length - 1] = {
        ...newMessages[newMessages.length - 1],
        content,
        ...(agentMeta !== undefined ? { agentMeta } : {}),
      };
    } else {
      newMessages.push({ role: 'assistant', content, ...(agentMeta !== undefined ? { agentMeta } : {}) });
    }
    const updatedSessions = sessions.map(s =>
      s.id === activeSessionId
        ? { ...s, messages: newMessages, updatedAt: new Date().toISOString() }
        : s
    );
    set({ messages: newMessages, sessions: updatedSessions });
  },

  setConversationRevision: (revision: number) => {
    const safe = Number.isFinite(revision) && revision >= 0 ? Math.floor(revision) : 0;
    const { activeSessionId, sessions, activeSession } = get();
    const updatedSessions = sessions.map(s =>
      s.id === activeSessionId ? { ...s, conversationRevision: safe } : s
    );
    const updatedActive = activeSession && activeSession.id === activeSessionId
      ? { ...activeSession, conversationRevision: safe }
      : activeSession;
    set({
      conversationRevision: safe,
      sessions: updatedSessions,
      activeSession: updatedActive,
    });
    get().saveToStorage();
  },

  applyServerSnapshot: (snapshot) => {
    const revision = Math.max(0, Math.floor(snapshot.revision ?? 0));
    const { activeSessionId, sessions, activeSession, messages } = get();
    const nextMessages = snapshot.messages && snapshot.messages.length > 0
      ? snapshot.messages
      : messages;
    // NX-09: 서버 폴백 id 는 **정체성이 아니다** — 채택하면 클라이언트 id 가 사라지고
    // 모든 첫 대화가 한 레코드로 합쳐진다. 응답이 폴백을 돌려주면 현재 id 를 유지한다.
    const serverId = snapshot.conversation_id === SERVER_FALLBACK_CONVERSATION_ID
      ? ''
      : snapshot.conversation_id;
    const updatedSessions = sessions.map(s => {
      if (s.id !== activeSessionId && s.id !== serverId) return s;
      return {
        ...s,
        id: serverId || s.id,
        messages: nextMessages,
        conversationRevision: revision,
        updatedAt: new Date().toISOString(),
      };
    });
    const updatedActive = activeSession
      ? {
          ...activeSession,
          id: serverId || activeSession.id,
          messages: nextMessages,
          conversationRevision: revision,
          updatedAt: new Date().toISOString(),
        }
      : activeSession;
    set({
      messages: nextMessages,
      conversationRevision: revision,
      activeSessionId: serverId || activeSessionId,
      sessions: updatedSessions,
      activeSession: updatedActive,
    });
    get().saveToStorage();
  },

  adoptForkedSession: (fork) => {
    const { sessions } = get();
    const source = sessions.find((session) => session.id === fork.sourceConversationId);
    if (!source || source.id === fork.conversationId || sessions.some((session) => session.id === fork.conversationId)) {
      return false;
    }
    const revision = Number.isFinite(fork.revision) && fork.revision >= 0
      ? Math.floor(fork.revision)
      : 0;
    const forkedSession: ChatSession = {
      id: fork.conversationId,
      title: `${source.title} · 분기`,
      updatedAt: new Date().toISOString(),
      messages: [...fork.messages],
      conversationRevision: revision,
    };
    set({
      sessions: [forkedSession, ...sessions],
      activeSessionId: forkedSession.id,
      activeSession: forkedSession,
      messages: forkedSession.messages,
      conversationRevision: forkedSession.conversationRevision,
    });
    get().saveToStorage();
    return true;
  },

  setStreaming: (val: boolean) => set({ isStreaming: val }),
  setCurrentAssistantContent: (content: string) => set({ currentAssistantContent: content }),
  appendToCurrentAssistantContent: (chunk: string) =>
    set(state => ({ currentAssistantContent: state.currentAssistantContent + chunk })),

  setModels: (models) => set({ models }),
  setSelectedModel: (model) => {
    set({ selectedModel: model });
    try {
      localStorage.setItem(MODEL_PREFERENCE_KEY, model);
    } catch (error) {
      if (!(error instanceof DOMException)) throw error;
      console.error('[ChatStore] Failed to save model preference:', error);
    }
  },
  setPlanMode: (val: boolean) => set({ isPlanMode: val }),
  setTddMode: (val: boolean) => set({ isTddMode: val }),
  setAdaptiveMode: (val: boolean) => set({ isAdaptiveMode: val }),

  loadFromStorage: () => {
    try {
      const selectedModel = localStorage.getItem(MODEL_PREFERENCE_KEY);
      if (selectedModel) set({ selectedModel });
      const project = useProjectStore.getState();
      const storageKey = project.activeProjectId
        || project.activeProjectPath
        || localStorage.getItem('agk_active_project')
        || '/';
      const saved = localStorage.getItem(STORAGE_KEY_PREFIX + storageKey);
      if (!saved) return;

      const parsed = JSON.parse(saved);
      if (parsed.sessions && parsed.sessions.length > 0) {
        const sessions = parsed.sessions;
        const activeSessionId = parsed.activeSessionId || sessions[0].id;
        const activeSession = sessions.find((s: ChatSession) => s.id === activeSessionId) || sessions[0];
        const normalized = sessions.map((s: ChatSession) => ({
          ...s,
          conversationRevision: s.conversationRevision ?? 0,
        }));
        const active = normalized.find((s: ChatSession) => s.id === activeSessionId) || normalized[0];
        set({
          sessions: normalized,
          activeSessionId,
          activeSession: active,
          messages: active.messages || [],
          conversationRevision: active.conversationRevision ?? 0,
        });
      }
    } catch (e) {
      console.error('[ChatStore] Failed to load from storage:', e);
    }
  },

  clearForProjectSwitch: () => {
    set({
      sessions: [],
      activeSessionId: null,
      activeSession: null,
      messages: [],
      conversationRevision: 0,
      isStreaming: false,
      currentAssistantContent: '',
    });
  },

  saveToStorage: () => {
    try {
      const project = useProjectStore.getState();
      const storageKey = project.activeProjectId
        || project.activeProjectPath
        || localStorage.getItem('agk_active_project')
        || '/';
      const { sessions, activeSessionId } = get();
      const payload = { sessions, activeSessionId };
      localStorage.setItem(STORAGE_KEY_PREFIX + storageKey, JSON.stringify(payload));
    } catch (e) {
      console.error('[ChatStore] Failed to save to storage:', e);
    }
  },
}));
