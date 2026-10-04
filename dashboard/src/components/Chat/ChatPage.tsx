import React, { useEffect, useMemo, useRef, useCallback, useState } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { useProjectStore } from '../../stores/projectStore';
import { useUiStore } from '../../stores/uiStore';
import { useEditorStore } from '../../stores/editorStore';
import { useChangeStore } from '../../stores/changeStore';
import { useFileStore } from '../../stores/fileStore';
import {
  streamChatCompletion,
  ConversationRevisionConflictError,
  ConversationRequestError,
  compactConversation,
  fetchConversationHistory,
  fetchModels,
  fetchLocalModels,
  loadModel,
  askAgent,
  type ModelInfo,
  type LocalModelItem,
} from '../../api/client';
import { AppIcon } from '../UI/AppIcon';
import {
  WorkspaceContextSchema,
  AccessModeResponseSchema,
  McpServersResponseSchema,
  type McpServerItem,
} from '../../api/clientSchema';
import { useEventWebSocket } from '../../hooks/useEventWebSocket';
import { useConversationFork, type ConversationForkStatus } from '../../hooks/useConversationFork';
import { detectChangesFromAssistantContent, registerFileModification } from '../../utils/changeDetector';
import { firePluginHook } from '../../plugin/pluginRegistry';
import ChatMessage from './ChatMessage';
import ChatHistory from './ChatHistory';
import { ChatComposer } from './ChatComposer';
import { ChatComposerTools } from './ChatComposerTools';
import { ChatModelSelector, formatModelAmount } from './ChatModelSelector';
import ActivityTimeline from './ActivityTimeline';
import CodeEditor from '../Editor/Editor';
import ArtifactPreview from '../Editor/ArtifactPreview';
import ChangePanel from '../Editor/ChangePanel';
import EnvironmentPanel, { type EnvPanelTab } from './EnvironmentPanel';
import {
  WorkingIndicator,
  StreamErrorBanner,
  FileEditCard,
  QueuedMessagesCard,
} from './ChatActivity';
import { useActivityStore } from '../../stores/activityStore';
import {
  createProjectIdentityHeaders,
  isIdentityCurrent,
  withProjectIdentitySearchParams,
} from '../../api/projectIdentity';
import {
  createChatRunGate,
  createQueuedChatTurn,
  type ChatAttachment,
  type ChatRunIdentity,
  type QueuedChatTurn,
} from './chatRunOwnership';

/**
 * NX-09-F03 — 첨부는 **바이트를 함께 보낸다**.
 *
 * 예전에는 파일명 표식(`[첨부 파일: …]`)만 입력창에 넣고 바이트는 보내지 않았다. 사용자는
 * 이미지를 붙였다고 믿지만 모델은 파일명만 봤다 — 화면이 거짓말했다. 계약(이름·MIME·base64)은
 * 서버 `engine/multimodal.py`(ADR-0005)가 소유하고, 여기서는 **빠른 실패**만 한다(최종 판정은 서버).
 */
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const ALLOWED_IMAGE_MIME: readonly string[] = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];

/** 파일을 base64 로 읽는다 — 전송 형식은 서버 계약과 같다. */
function readAttachmentBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('파일을 읽지 못했습니다.'));
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const comma = result.indexOf(',');
      if (comma < 0) {
        reject(new Error('파일을 읽지 못했습니다.'));
        return;
      }
      resolve(result.slice(comma + 1));
    };
    reader.readAsDataURL(file);
  });
}

export const ChatPage: React.FC = () => {
  const {
    messages, isStreaming, selectedModel, isPlanMode, isTddMode, isAdaptiveMode,
    activeSession, activeSessionId, updateSessionTitle,
    addMessage, updateLastAssistantMessage, saveToStorage,
    applyServerSnapshot,
    setStreaming, appendToCurrentAssistantContent, setCurrentAssistantContent,
    loadFromStorage, setSelectedModel, clearForProjectSwitch,
  } = useChatStore();

  const { addToast, setCommandPaletteVisible } = useUiStore();
  const activeProjectId = useProjectStore((s) => s.activeProjectId);
  const activeProjectName = useProjectStore((s) => s.activeProjectName);
  const switchEpoch = useProjectStore((s) => s.switchEpoch);
  const hydrateProjects = useProjectStore((s) => s.hydrateFromServer);
  const projectSwitchEpochRef = useRef(switchEpoch);
  const initialHistoryRestoreEpochRef = useRef<number | null>(activeProjectId ? null : switchEpoch);
  const { previewVisible, openFile, clearForProjectSwitch: clearEditorForProjectSwitch } = useEditorStore();
  const { setPanelVisible: setChangePanelVisible, clearChanges } = useChangeStore();
  const pendingChangeCount = useChangeStore((s) => s.changes.filter((c) => c.status === 'pending').length);

  /* ─── States ─────────────────────────────────────────────── */
  const [inputText, setInputText] = useState<string>('');
  // 다음 턴에 실제로 전송될 첨부(바이트 포함). 전송 시점에 비운다.
  const [pendingAttachments, setPendingAttachments] = useState<ChatAttachment[]>([]);
  const pendingAttachmentsRef = useRef<ChatAttachment[]>([]);
  const [queuedMessages, setQueuedMessages] = useState<string[]>([]);
  const [queueCollapsed, setQueueCollapsed] = useState<boolean>(false);

  const [actionMenuOpen, setActionMenuOpen] = useState<boolean>(false);
  const [modelDropdownOpen, setModelDropdownOpen] = useState<boolean>(false);
  const [accessDropdownOpen, setAccessDropdownOpen] = useState<boolean>(false);
  const [mcpMenuOpen, setMcpMenuOpen] = useState<boolean>(false);
  const [mcpServerList, setMcpServerList] = useState<McpServerItem[]>([]);
  const [selectedMcp, setSelectedMcp] = useState<string[] | null>(null);
  const [webSearch, setWebSearch] = useState<boolean>(false);
  const [codeMode, setCodeMode] = useState<boolean>(false);
  const [accessMode, setAccessMode] = useState<'full_access' | 'restricted'>('full_access');

  const [envPanelOpen, setEnvPanelOpen] = useState<boolean>(false);
  const [isEditingTitle, setIsEditingTitle] = useState<boolean>(false);
  const [titleInput, setTitleInput] = useState<string>('');
  const [envTab, setEnvTab] = useState<EnvPanelTab>('env');
  const [historyVisible, setHistoryVisible] = useState<boolean>(false);

  const [streamError, setStreamError] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number>(0);
  const [isCompactingConversation, setIsCompactingConversation] = useState<boolean>(false);
  const [compactionStatus, setCompactionStatus] = useState<string | null>(null);
  const [showLatestAction, setShowLatestAction] = useState<boolean>(false);

  const handleForkStatus = useCallback((status: ConversationForkStatus) => {
    switch (status.kind) {
      case 'idle':
        return;
      case 'pending':
        setCompactionStatus(status.message);
        return;
      case 'success':
        setCompactionStatus(status.message);
        addToast(status.message, 'success');
        return;
      case 'error':
        setCompactionStatus(status.message);
        addToast(status.message, 'error');
        return;
    }
  }, [addToast]);
  const { forkActiveConversation, isForking } = useConversationFork({
    isCompacting: isCompactingConversation,
    onStatus: handleForkStatus,
  });

  useEffect(() => {
    const handleForkCommand = () => { void forkActiveConversation(); };
    window.addEventListener('agk:conversation-fork', handleForkCommand);
    return () => window.removeEventListener('agk:conversation-fork', handleForkCommand);
  }, [forkActiveConversation]);

  const [workspaceContext, setWorkspaceContext] = useState({
    project_name: activeProjectName || '',
    workspace_path: '.',
    target: '로컬',
    branch: '',
  });

  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [localModels, setLocalModels] = useState<LocalModelItem[]>([]);
  const [isScanningLocal, setIsScanningLocal] = useState<boolean>(false);

  const loadLocalModels = useCallback(async (refresh = false) => {
    try {
      const res = await fetchLocalModels(refresh);
      if (res.ok && res.models) {
        setIsScanningLocal(true);
        setLocalModels(res.models);
        const currentSelected = useChatStore.getState().selectedModel;
        const exists = res.models.some(m => m.id === currentSelected);
        if (!exists && res.models.length > 0) {
          const nextModel = res.recommended_default || res.models[0].id;
          setSelectedModel(nextModel);
        }
      }
    } catch (err) {
      console.error('Local model fetch error:', err);
    } finally {
      setIsScanningLocal(false);
    }
  }, [setSelectedModel]);

  // 스캔 시작을 렌더 단계가 아닌 첫 await 이후로 미룬다 —
  // effect 본문에서 동기 setState(cascading render)를 피하기 위함.

  const handleModelChoice = useCallback((modelId: string) => {
    setSelectedModel(modelId);
    setModelDropdownOpen(false);
    void loadModel(modelId).then((res) => {
      if (res.ok) {
        void loadLocalModels(false);
      }
    }).catch((err) => {
      console.warn('Background model load failed:', err);
    });
  }, [setSelectedModel, loadLocalModels]);

  /* ─── Refs ───────────────────────────────────────────────── */
  const abortRef = useRef<AbortController | null>(null);
  const runGateRef = useRef(createChatRunGate());
  const conversationTransitionRef = useRef(0);
  const mountedRef = useRef(true);
  const feedRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queueRef = useRef<QueuedChatTurn[]>([]);
  const retryTurnRef = useRef<QueuedChatTurn | null>(null);
  const shouldFollowOutputRef = useRef(true);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selectedModelRef = useRef(selectedModel);
  const isPlanModeRef = useRef(isPlanMode);
  const isTddModeRef = useRef(isTddMode);
  const isAdaptiveModeRef = useRef(isAdaptiveMode);
  const runRef = useRef<(turn: QueuedChatTurn) => Promise<void>>(async () => {});
  // 로컬 모델 로더의 최신 버전을 가리키는 레퍼런스 — init effect가 마운트 시 1회만
  // 실행되도록 하면서 effect 본문의 동기 setState(react-hooks/set-state-in-effect)를 피한다.
  const loadLocalModelsRef = useRef<(refresh?: boolean) => Promise<void>>(async () => {});
  // 워크스페이스 컨텍스트 리로더의 최신 버전 레퍼런스 — 동일 목적.
  const reloadWorkspaceContextRef = useRef<() => void>(() => {});

  useEffect(() => {
    selectedModelRef.current = selectedModel;
    isPlanModeRef.current = isPlanMode;
    isTddModeRef.current = isTddMode;
    isAdaptiveModeRef.current = isAdaptiveMode;
    loadLocalModelsRef.current = loadLocalModels;
  }, [isPlanMode, isTddMode, isAdaptiveMode, selectedModel, loadLocalModels]);

  /**
   * CTX-01: client projection 을 **서버 권위 revision** 에 맞춘다.
   *
   * NX-09: 이 함수는 init effect 안에서만 불렸고 그 effect 는 프로젝트 정체성에 의존하지 않았다.
   * 프로젝트 하이드레이션은 `hydrateProjects()` 의 **비동기** 완료로 들어오므로, 마운트 시점에는
   * `activeProjectId` 가 아직 null 인 것이 정상이다 — 그러면 이 동기화는 조용히 return 했고
   * **재시작 뒤 서버 이력이 한 번도 로드되지 않았다**(로컬 캐시가 비어 있으면 빈 대화로 보인다).
   * 정체성이 도착하는 순간에도 맞추도록 ref 에 담아 별도 effect 에서 부른다.
   */
  const syncConversationRef = useRef<() => Promise<void>>(async () => undefined);

  /* ─── Init ───────────────────────────────────────────────── */
  useEffect(() => {
    loadFromStorage();
    void loadLocalModelsRef.current(false);
    fetchModels()
      .then(models => setAvailableModels(models))
      .catch(() => {});

    const syncConversation = async () => {
      const chat = useChatStore.getState();
      const project = useProjectStore.getState();
      const projectId = project.activeProjectId;
      const requestEpoch = project.switchEpoch;
      const requestTransition = conversationTransitionRef.current;
      const requestRevision = chat.conversationRevision;
      const convId = chat.activeSessionId;
      if (!convId || !projectId || chat.isStreaming) return;
      try {
        const history = await fetchConversationHistory(convId, projectId);
        const currentChat = useChatStore.getState();
        const currentProject = useProjectStore.getState();
        if (
          !mountedRef.current ||
          conversationTransitionRef.current !== requestTransition ||
          currentChat.activeSessionId !== convId ||
          currentChat.isStreaming ||
          currentChat.conversationRevision !== requestRevision ||
          currentProject.activeProjectId !== projectId ||
          currentProject.switchEpoch !== requestEpoch
        ) return;
        useChatStore.getState().applyServerSnapshot({
          conversation_id: history.snapshot.conversation_id,
          revision: history.snapshot.revision,
          summary: history.snapshot.summary,
          retained_message_ids: history.snapshot.retained_message_ids,
          messages: history.messages.map((m) => ({
            id: m.id,
            role: m.role === "tool" ? "system" : m.role,
            content: m.content,
          })),
        });
      } catch (error: unknown) {
        const currentChat = useChatStore.getState();
        const currentProject = useProjectStore.getState();
        if (
          !mountedRef.current ||
          conversationTransitionRef.current !== requestTransition ||
          currentChat.activeSessionId !== convId ||
          currentChat.isStreaming ||
          currentChat.conversationRevision !== requestRevision ||
          currentProject.activeProjectId !== projectId ||
          currentProject.switchEpoch !== requestEpoch
        ) return;
        if (error instanceof ConversationRequestError && error.code === 'conversation_not_found') {
          // CR-01: 새 로컬 대화는 아직 서버에 없다. 로컬 투영을 유지하되 다른
          // 대화로 자동 대체하지 않는다.
          return;
        }
        // CR-01: 무결성/마이그레이션/서버 오류를 빈 대화로 숨기지 않고 알린다.
        const detail = error instanceof Error ? error.message : String(error);
        addToast(`서버 대화 이력을 확인하지 못했습니다: ${detail}`, 'error');
      }
    };
    syncConversationRef.current = syncConversation;
    void syncConversation();
  }, [loadFromStorage, loadLocalModels, addToast]);

  useEffect(() => {
    if (!activeProjectId || initialHistoryRestoreEpochRef.current === null) return;
    const initialEpoch = initialHistoryRestoreEpochRef.current;
    initialHistoryRestoreEpochRef.current = null;
    const chat = useChatStore.getState();
    if (
      initialEpoch !== switchEpoch || chat.activeSessionId || chat.activeSession ||
      chat.sessions.length > 0 || chat.messages.length > 0 || chat.isStreaming ||
      inputText.length > 0 || pendingAttachments.length > 0
    ) return;
    loadFromStorage();
  }, [activeProjectId, switchEpoch, inputText, pendingAttachments.length, loadFromStorage]);

  // NX-09: 프로젝트 정체성이 (하이드레이션으로) 도착하면 서버 이력과 한 번 맞춘다.
  // init effect 는 이 값을 의존성으로 갖지 않으므로 여기서 다시 부른다.
  useEffect(() => {
    if (!activeProjectId) return;
    void syncConversationRef.current();
  }, [activeProjectId, activeSessionId]);

  const reloadWorkspaceContext = useCallback(() => {
    const store = useProjectStore.getState();
    const capturedEpoch = store.switchEpoch;
    setWorkspaceContext((prev) => ({
      ...prev,
      project_name: store.activeProjectName || prev.project_name,
      workspace_path: store.activeProjectPath || prev.workspace_path,
    }));
    fetch('/api/workspace/context', { headers: createProjectIdentityHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(raw => {
        if (!isIdentityCurrent(capturedEpoch)) return;
        if (raw) {
          const parsed = WorkspaceContextSchema.safeParse(raw);
          if (parsed.success) {
            const latest = useProjectStore.getState();
            setWorkspaceContext({
              project_name: latest.activeProjectName || parsed.data.project_name,
              workspace_path: latest.activeProjectPath || parsed.data.workspace_path || '.',
              target: parsed.data.target,
              branch: parsed.data.branch,
            });
          }
        }
      })
      .catch(() => {});
  }, []);

  // reloadWorkspaceContext의 최신 버전을 ref에 동기화 — 아래 init effect와
  // 프로젝트 전환 effect가 마운트 시 1회 실행되면서도 항상 최신 클로저를 쓰게 한다.
  useEffect(() => {
    reloadWorkspaceContextRef.current = reloadWorkspaceContext;
  }, [reloadWorkspaceContext]);

  useEffect(() => {
    void hydrateProjects();
  }, [hydrateProjects]);

  useEffect(() => {
    reloadWorkspaceContextRef.current();
    // 실행 권한 모드 초기값 동기화 (읽기 전용이면 칩이 즉시 반영됨)
    fetch('/api/system/access-mode', { headers: createProjectIdentityHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(raw => {
        if (raw) {
          const parsed = AccessModeResponseSchema.safeParse(raw);
          if (parsed.success && parsed.data.mode === 'read_only') {
            setAccessMode('restricted');
          }
        }
      })
      .catch(() => {});
    // 구성된 MCP 서버 실목록 (환경 레일 "소스"와 동일한 소스)
    fetch('/api/mcp/servers', { headers: createProjectIdentityHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(raw => {
        if (raw) {
          const parsed = McpServersResponseSchema.safeParse(raw);
          if (parsed.success && parsed.data.ok) {
            setMcpServerList(parsed.data.servers);
            setSelectedMcp(parsed.data.servers.map((s) => s.name));
            return;
          }
        }
        setSelectedMcp([]);
      })
      .catch(() => setSelectedMcp([]));
  }, [reloadWorkspaceContext]);

  useEffect(() => {
    const feed = feedRef.current;
    if (!feed || !shouldFollowOutputRef.current) return;
    feed.scrollTop = feed.scrollHeight;
    setShowLatestAction(false);
  }, [messages]);

  const handleToggleAccessMode = async (mode: 'full_access' | 'restricted') => {
    try {
      const response = await fetch('/api/system/access-mode', {
        method: 'POST',
        headers: createProjectIdentityHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ mode }),
      });
      if (!response.ok) {
        setAccessDropdownOpen(false);
        addToast(`실행 권한을 변경하지 못했습니다 (HTTP ${response.status}). 기존 모드를 유지합니다.`, 'error');
        return;
      }
      setAccessMode(mode);
      setAccessDropdownOpen(false);
      addToast(mode === 'full_access' ? '전체 액세스 모드 허용' : '읽기 전용 샌드박스로 전환', 'info');
    } catch (error: unknown) {
      setAccessDropdownOpen(false);
      const detail = error instanceof Error ? error.message : '서버와 연결할 수 없습니다.';
      addToast(`실행 권한을 변경하지 못했습니다. 기존 모드를 유지합니다: ${detail}`, 'error');
    }
  };

  /* ─── WebSocket event listeners ──────────────────────────── */
  useEventWebSocket({
    onToolExecutionStarted: (data) => {
      useActivityStore.getState().recordToolStart(data);
    },
    onToolExecutionFinished: () => {
      useActivityStore.getState().recordToolEnd();
    },
    onFailureDetected: (data) => {
      useActivityStore.getState().recordError(data.error ?? data.message ?? '알 수 없는 오류');
    },
    onPlanningModeStarted: (data) => {
      useActivityStore.getState().recordPlan(data.goal ?? '');
    },
    onFileOpened: (data) => {
      const filePath = data?.filepath;
      if (filePath) {
        useActivityStore.getState().recordFileRead(filePath);
        const fileName = filePath.split(/[/\\]/).pop() || 'unknown';
        const capturedEpoch = useProjectStore.getState().switchEpoch;
        fetch(withProjectIdentitySearchParams(`/api/fs/read?file=${encodeURIComponent(filePath)}`), {
          headers: createProjectIdentityHeaders(),
        })
          .then(r => r.ok ? r.json() : null)
          .then(d => {
            if (!isIdentityCurrent(capturedEpoch)) return;
            if (d?.content !== undefined) {
              openFile(filePath, fileName, d.content);
              setEnvPanelOpen(true);
              setEnvTab('code');
            }
          })
          .catch(() => {});
      }
    },
    onFileModified: (data) => {
      const filePath = data?.filepath;
      if (filePath) {
        useActivityStore.getState().recordFileEdit(filePath);
        const fileName = filePath.split(/[/\\]/).pop() || 'unknown';
        const capturedEpoch = useProjectStore.getState().switchEpoch;
        fetch(withProjectIdentitySearchParams(`/api/fs/read?file=${encodeURIComponent(filePath)}`), {
          headers: createProjectIdentityHeaders(),
        })
          .then(r => r.ok ? r.json() : null)
          .then(d => {
            if (!isIdentityCurrent(capturedEpoch)) return;
            if (d?.content !== undefined) {
              openFile(filePath, fileName, d.content);
            }
          })
          .catch(() => {});
        registerFileModification(filePath, fileName)
          .then((registered) => {
            if (!isIdentityCurrent(capturedEpoch)) return;
            if (registered) addToast(`📋 변경 감지: ${fileName}`, 'info');
          })
          .catch(() => {});
      }
    },
  });

  /* ─── Elapsed timer while streaming ──────────────────────── */
  const startElapsedTimer = useCallback(() => {
    setElapsed(0);
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    elapsedTimerRef.current = setInterval(() => {
      setElapsed((v) => v + 1);
    }, 1000);
  }, []);

  const stopElapsedTimer = useCallback(() => {
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => stopElapsedTimer(), [stopElapsedTimer]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      conversationTransitionRef.current += 1;
      runGateRef.current.invalidate();
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);

  const syncQueuedMessages = useCallback(() => {
    setQueuedMessages(queueRef.current.map((turn) => turn.text));
  }, []);

  const invalidateCurrentRun = useCallback((clearQueue: boolean) => {
    runGateRef.current.invalidate();
    retryTurnRef.current = null;
    setStreamStatus(null);
    const controller = abortRef.current;
    abortRef.current = null;
    controller?.abort();
    if (clearQueue) {
      queueRef.current = [];
      setQueuedMessages([]);
    }
    setStreaming(false);
    setCurrentAssistantContent('');
    stopElapsedTimer();
    useActivityStore.getState().setSessionEnded();
  }, [setCurrentAssistantContent, setStreaming, stopElapsedTimer]);

  useEffect(() => {
    let observedSessionId = useChatStore.getState().activeSessionId;
    return useChatStore.subscribe((state) => {
      if (state.activeSessionId === observedSessionId) return;
      observedSessionId = state.activeSessionId;
      conversationTransitionRef.current += 1;
      retryTurnRef.current = null;
      setStreamError(null);
      setStreamStatus(null);
      const hadPending = Boolean(abortRef.current) || queueRef.current.length > 0;
      if (hadPending) {
        invalidateCurrentRun(true);
        addToast('대화를 전환해 이전 생성과 대기열을 취소했습니다.', 'info');
      }
      setIsCompactingConversation(false);
      setCompactionStatus(null);
      shouldFollowOutputRef.current = true;
      setShowLatestAction(false);
    });
  }, [addToast, invalidateCurrentRun]);

  /* ─── WS-04: project switch → cancel pending + reload context ─ */
  useEffect(() => {
    const prevEpoch = projectSwitchEpochRef.current;
    if (switchEpoch === prevEpoch) return;
    projectSwitchEpochRef.current = switchEpoch;

    const hadPending = Boolean(abortRef.current)
      || useChatStore.getState().isStreaming
      || queueRef.current.length > 0;
    invalidateCurrentRun(true);
    setStreamError(null);
    useActivityStore.getState().clear();

    clearEditorForProjectSwitch();
    clearChanges();
    useFileStore.getState().clearForProjectSwitch();

    clearForProjectSwitch();
    loadFromStorage();
    if (useChatStore.getState().sessions.length === 0) {
      useChatStore.getState().createNewSession();
    }

    reloadWorkspaceContext();

    if (hadPending) {
      addToast('프로젝트 전환: 이전 요청을 취소하고 컨텍스트를 다시 불러왔습니다.', 'info');
    }
  }, [
    switchEpoch,
    clearForProjectSwitch,
    clearEditorForProjectSwitch,
    clearChanges,
    loadFromStorage,
    reloadWorkspaceContext,
    addToast,
    invalidateCurrentRun,
  ]);

  /* ─── MCP allowlist (구성된 서버 기준 선택 집합) ─────────────── */
  const mcpAllowlist = useMemo(
    () => selectedMcp ?? [],
    [selectedMcp],
  );

  /* ─── Send / queue / run loop ────────────────────────────── */
  const runCompletion = useCallback(async (turn: QueuedChatTurn) => {
    const { text, attachments } = turn;
    const model = selectedModelRef.current;
    const planMode = isPlanModeRef.current;
    const tddMode = isTddModeRef.current;
    const adaptiveMode = isAdaptiveModeRef.current;
    const currentProject = useProjectStore.getState();
    const currentChat = useChatStore.getState();
    if (
      currentProject.switchEpoch !== turn.projectEpoch ||
      currentProject.activeProjectId !== turn.projectId ||
      (turn.sessionId !== null && currentChat.activeSessionId !== turn.sessionId)
    ) return;

    retryTurnRef.current = null;
    firePluginHook('chat:send', { text, model, planMode, tddMode, adaptiveMode });
    useActivityStore.getState().clear();
    useActivityStore.getState().setSessionStarted();
    addMessage({ role: 'user', content: text });
    const requestSessionId = useChatStore.getState().activeSessionId;
    if (!requestSessionId) return;
    conversationTransitionRef.current += 1;
    const runIdentity = runGateRef.current.begin({
      sessionId: requestSessionId,
      projectId: turn.projectId,
      projectEpoch: turn.projectEpoch,
    });
    const ownsRun = (identity: ChatRunIdentity) => {
      const chat = useChatStore.getState();
      const project = useProjectStore.getState();
      return runGateRef.current.owns(identity)
        && chat.activeSessionId === identity.sessionId
        && project.activeProjectId === identity.projectId
        && project.switchEpoch === identity.projectEpoch;
    };
    saveToStorage();
    setStreamError(null);
    setStreamStatus(null);
    setCurrentAssistantContent('');

    addMessage({ role: 'assistant', content: '' });
    setStreaming(true);
    startElapsedTimer();

    const abortController = new AbortController();
    abortRef.current = abortController;

    if (adaptiveMode) {
      let completedSuccessfully = false;
      try {
        const res = await askAgent({
          task: text,
          model: model === 'default' ? undefined : model,
          adaptive: true,
          use_web: webSearch,
          project_id: turn.projectId ?? undefined,
        });

        if (!ownsRun(runIdentity)) return;

        if (res.ok) {
          completedSuccessfully = true;
          updateLastAssistantMessage(res.answer, {
            used_web: res.used_web,
            used_graphify: res.used_graphify,
            steps: res.steps,
            total_seconds: res.total_seconds,
            passed: res.passed,
            mode: res.mode,
          });
          detectChangesFromAssistantContent(res.answer).catch(() => {});
        } else {
          retryTurnRef.current = { ...turn, sessionId: requestSessionId };
          const errText = res.error || 'Adaptive 에이전트 작업에 실패했습니다.';
          updateLastAssistantMessage(`⚠️ 오류 발생: ${errText}`);
          setStreamError(errText);
        }
      } catch (err: unknown) {
        if (!ownsRun(runIdentity)) return;
        retryTurnRef.current = { ...turn, sessionId: requestSessionId };
        const errText = err instanceof Error ? err.message : 'Adaptive 에이전트 요청 중 통신 오류가 발생했습니다.';
        updateLastAssistantMessage(`⚠️ 통신 오류: ${errText}`);
        setStreamError(errText);
      } finally {
        if (!ownsRun(runIdentity)) return;
        saveToStorage();
        setStreaming(false);
        setStreamStatus(null);
        stopElapsedTimer();
        if (abortRef.current === abortController) abortRef.current = null;
        useActivityStore.getState().setSessionEnded();
        if (!completedSuccessfully) {
          if (queueRef.current.length > 0) {
            syncQueuedMessages();
            addToast(
              '부모 실행이 실패해 후속 대기 메시지를 자동 전송하지 않았습니다. 대기열에서 편집하거나 다시 전송해 주세요.',
              'info',
            );
          }
          return;
        }
        const next = queueRef.current.shift();
        syncQueuedMessages();
        if (next !== undefined) {
          void runRef.current(next);
        }
      }
      return;
    }

    let assistantContent = '';

    // CTX-01: client message array is projection only — server store is authoritative.

    // TS CFA does not track assignments made inside the onError callback across the
    // await boundary (TS#9998), so a bare `= null` initializer narrows this to `null`
    // and the post-await truthy branch collapses to `never`. The assertion keeps the
    // declared string|null type at the read site below.
    let errorMessage: string | null = null as string | null;
    const expectedRevision = useChatStore.getState().conversationRevision ?? 0;
    const conversationId = requestSessionId;
    await streamChatCompletion(
      {
        model,
        // CTX-01: server store is SoT — send new turn + expected revision only
        messages: [{ role: 'user', content: text }],
        new_turn: { role: 'user', content: text },
        conversation_id: conversationId ?? undefined,
        conversation_revision: expectedRevision,
        use_conversation_store: true,
        // ADR-0005: 첨부는 이름·MIME·base64 로 보낸다(서버가 파트로 바꾼다).
        attachments: attachments.length > 0
          ? attachments.map(({ name, mime_type, data_base64 }) => ({ name, mime_type, data_base64 }))
          : undefined,
        stream: true,
        agent_mode: true,
        plan_mode: planMode,
        tdd_mode: tddMode,
        web_search: webSearch,
        code_mode: codeMode,
        mcp_servers: mcpAllowlist,
        // project_id / project_revision also injected by client.streamChatCompletion
        project_id: turn.projectId ?? undefined,
      },
      {
        onChunk: (chunk: string) => {
          if (!ownsRun(runIdentity)) return;
          assistantContent += chunk;
          appendToCurrentAssistantContent(chunk);
          updateLastAssistantMessage(assistantContent);
        },
        onStatus: (status: string) => {
          if (!ownsRun(runIdentity)) return;
          setStreamStatus(status);
        },
        onFinalContent: (content: string) => {
          if (!ownsRun(runIdentity)) return;
          assistantContent = content;
          setCurrentAssistantContent(content);
          updateLastAssistantMessage(content);
          setStreamStatus(null);
        },
        onDone: () => {},
        onError: (err: Error) => {
          if (!ownsRun(runIdentity)) return;
          if (err.name === 'AbortError') return;
          if (err instanceof ConversationRevisionConflictError) {
            errorMessage = `stale_conversation_revision:${err.payload.current_revision}`;
            return;
          }
          errorMessage = err.message;
        },
        onConversationSnapshot: (snapshot) => {
          if (!ownsRun(runIdentity)) return;
          applyServerSnapshot({
            conversation_id: snapshot.conversation_id,
            revision: snapshot.revision,
            summary: snapshot.summary,
            retained_message_ids: snapshot.retained_message_ids,
          });
        },
      },
      abortController.signal,
    );

    // Stale responses from a previous project must not merge into the new UI/store.
    if (!ownsRun(runIdentity)) return;

    updateLastAssistantMessage(assistantContent);
    saveToStorage();

    if (errorMessage) {
      retryTurnRef.current = { ...turn, sessionId: requestSessionId };
      if (errorMessage.includes('revision') || errorMessage.includes('409')) {
        // Best-effort: refresh authoritative projection on conflict.
        try {
          if (conversationId) {
            const history = await fetchConversationHistory(conversationId, turn.projectId);
            if (!ownsRun(runIdentity)) return;
            applyServerSnapshot({
              conversation_id: history.snapshot.conversation_id,
              revision: history.snapshot.revision,
              summary: history.snapshot.summary,
              retained_message_ids: history.snapshot.retained_message_ids,
              messages: history.messages.map((m) => ({
                id: m.id,
                role: m.role === 'tool' ? 'system' : m.role,
                content: m.content,
              })),
            });
            setStreamError(
              `대화 리비전이 충돌했습니다 (서버 r${history.snapshot.revision}). 최신 이력으로 동기화했습니다. 다시 전송해 주세요.`,
            );
          } else {
            setStreamError(errorMessage);
          }
        } catch (error: unknown) {
          if (!ownsRun(runIdentity)) return;
          setStreamError(errorMessage);
        }
      } else {
        setStreamError(errorMessage);
      }
    } else {
      detectChangesFromAssistantContent(assistantContent).catch(() => {});
    }

    if (!ownsRun(runIdentity)) return;
    setStreaming(false);
    setStreamStatus(null);
    stopElapsedTimer();
    if (abortRef.current === abortController) abortRef.current = null;
    useActivityStore.getState().setSessionEnded();
    const approxPromptTokens = Math.ceil(text.length / 4);
    const approxCompletionTokens = Math.ceil(assistantContent.length / 4);
    useActivityStore.getState().recordTokenUsage(approxPromptTokens, approxCompletionTokens);

    if (errorMessage) {
      if (queueRef.current.length > 0) {
        syncQueuedMessages();
        addToast(
          '부모 실행이 실패해 후속 대기 메시지를 자동 전송하지 않았습니다. 대기열에서 편집하거나 다시 전송해 주세요.',
          'info',
        );
      }
      return;
    }

    // Flush queued messages (Codex-style: sends after agent finishes)
    const next = queueRef.current.shift();
    syncQueuedMessages();
    if (next !== undefined) {
      void runRef.current(next);
    }
  }, [
    addMessage, saveToStorage, setStreaming, appendToCurrentAssistantContent,
    updateLastAssistantMessage, startElapsedTimer, stopElapsedTimer,
    webSearch, codeMode, mcpAllowlist, applyServerSnapshot, syncQueuedMessages,
    setCurrentAssistantContent, addToast,
  ]);

  useEffect(() => {
    runRef.current = runCompletion;
  }, [runCompletion]);

  const handleSend = useCallback(async (textToSend?: string) => {
    if (isForking || isCompactingConversation) {
      addToast('대화 분기 또는 압축이 끝난 뒤 전송할 수 있습니다.', 'info');
      return;
    }
    const text = textToSend ?? inputText;
    if (!text.trim()) return;

    const attachments = pendingAttachmentsRef.current;
    if (attachments.length > 0 && isAdaptiveModeRef.current) {
      addToast('첨부는 일반 모드에서만 전송됩니다(Adaptive 모드에서는 지원하지 않음)', 'error');
      return;
    }
    const project = useProjectStore.getState();
    const turn = createQueuedChatTurn({
      text: text.trim(),
      attachments,
      sessionId: useChatStore.getState().activeSessionId,
      projectId: project.activeProjectId,
      projectEpoch: project.switchEpoch,
    });
    pendingAttachmentsRef.current = [];
    setPendingAttachments([]);

    if (useChatStore.getState().isStreaming) {
      queueRef.current = [...queueRef.current, turn];
      syncQueuedMessages();
      setInputText('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      addToast('에이전트 작업이 끝나면 자동으로 전송됩니다.', 'info');
      return;
    }

    setInputText('');
    setActionMenuOpen(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    await runCompletion(turn);
  }, [inputText, runCompletion, addToast, syncQueuedMessages, isForking, isCompactingConversation]);

  const handleSendNow = useCallback((index: number) => {
    if (isForking || isCompactingConversation) return;
    const item = queueRef.current[index];
    if (item === undefined) return;
    queueRef.current = queueRef.current.filter((_, i) => i !== index);
    syncQueuedMessages();
    if (!useChatStore.getState().isStreaming) {
      void runCompletion(item);
    } else {
      queueRef.current = [item, ...queueRef.current];
      syncQueuedMessages();
    }
  }, [runCompletion, syncQueuedMessages, isForking, isCompactingConversation]);

  const handleEditQueued = useCallback((index: number) => {
    const item = queueRef.current[index];
    if (item === undefined) return;
    if (inputText.trim().length > 0 || pendingAttachmentsRef.current.length > 0) {
      addToast('현재 작성 중인 초안을 비운 뒤 대기 메시지를 편집해 주세요.', 'info');
      return;
    }
    queueRef.current = queueRef.current.filter((_, i) => i !== index);
    syncQueuedMessages();
    setInputText(item.text);
    const attachments = item.attachments.map((attachment) => ({ ...attachment }));
    pendingAttachmentsRef.current = attachments;
    setPendingAttachments(attachments);
    textareaRef.current?.focus();
  }, [addToast, inputText, syncQueuedMessages]);

  const handleDeleteQueued = useCallback((index: number) => {
    queueRef.current = queueRef.current.filter((_, i) => i !== index);
    syncQueuedMessages();
  }, [syncQueuedMessages]);

  const handleClearAllQueued = useCallback(() => {
    queueRef.current = [];
    setQueuedMessages([]);
  }, []);

  const handleMoveUpQueued = useCallback((index: number) => {
    if (index <= 0) return;
    const items = [...queueRef.current];
    const temp = items[index];
    items[index] = items[index - 1];
    items[index - 1] = temp;
    queueRef.current = items;
    syncQueuedMessages();
  }, [syncQueuedMessages]);

  const handleMoveDownQueued = useCallback((index: number) => {
    if (index >= queueRef.current.length - 1) return;
    const items = [...queueRef.current];
    const temp = items[index];
    items[index] = items[index + 1];
    items[index + 1] = temp;
    queueRef.current = items;
    syncQueuedMessages();
  }, [syncQueuedMessages]);

  const handleReorderQueued = useCallback((fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) return;
    const items = [...queueRef.current];
    const moved = items[fromIndex];
    if (moved === undefined) return;
    items.splice(fromIndex, 1);
    items.splice(toIndex, 0, moved);
    queueRef.current = items;
    syncQueuedMessages();
  }, [syncQueuedMessages]);

  const handleStop = useCallback(() => {
    const queuedCount = queueRef.current.length;
    invalidateCurrentRun(true);
    addToast(
      queuedCount > 0 ? `생성과 대기 메시지 ${queuedCount}개를 취소했습니다.` : '생성이 중단되었습니다.',
      'info',
    );
  }, [addToast, invalidateCurrentRun]);

  const handleCompactConversation = useCallback(async () => {
    const chat = useChatStore.getState();
    if (chat.isStreaming || isForking || isCompactingConversation) return;
    const conversationId = chat.activeSessionId;
    const projectId = useProjectStore.getState().activeProjectId;
    if (!conversationId || !projectId) {
      const message = '압축할 대화 또는 프로젝트를 찾을 수 없습니다.';
      setCompactionStatus(message);
      addToast(message, 'error');
      return;
    }

    const requestEpoch = useProjectStore.getState().switchEpoch;
    conversationTransitionRef.current += 1;
    const requestTransition = conversationTransitionRef.current;
    const ownsOperation = () => {
      const currentChat = useChatStore.getState();
      const currentProject = useProjectStore.getState();
      return mountedRef.current
        && conversationTransitionRef.current === requestTransition
        && currentChat.activeSessionId === conversationId
        && currentProject.activeProjectId === projectId
        && currentProject.switchEpoch === requestEpoch;
    };
    setIsCompactingConversation(true);
    setCompactionStatus('대화를 압축하고 최신 이력을 동기화하는 중입니다.');
    addToast('대화를 압축하는 중입니다.', 'info');
    try {
      const snapshot = await compactConversation({
        conversation_id: conversationId,
        expected_revision: chat.conversationRevision ?? 0,
        project_id: projectId,
      });
      if (!ownsOperation()) return;
      applyServerSnapshot({
        conversation_id: snapshot.conversation_id,
        revision: snapshot.revision,
        summary: snapshot.summary,
        retained_message_ids: snapshot.retained_message_ids,
      });
      const history = await fetchConversationHistory(conversationId, projectId);
      if (!ownsOperation()) return;
      applyServerSnapshot({
        conversation_id: history.snapshot.conversation_id,
        revision: history.snapshot.revision,
        summary: history.snapshot.summary,
        retained_message_ids: history.snapshot.retained_message_ids,
        messages: history.messages.map((message) => ({
          id: message.id,
          role: message.role === 'tool' ? 'system' : message.role,
          content: message.content,
        })),
      });
      const message = `대화를 압축했습니다. 서버 r${history.snapshot.revision}의 최신 이력을 반영했습니다.`;
      setCompactionStatus(message);
      addToast(message, 'success');
    } catch (error: unknown) {
      if (!ownsOperation()) return;
      if (error instanceof ConversationRevisionConflictError) {
        try {
          const history = await fetchConversationHistory(conversationId, projectId);
          if (!ownsOperation()) return;
          applyServerSnapshot({
            conversation_id: history.snapshot.conversation_id,
            revision: history.snapshot.revision,
            summary: history.snapshot.summary,
            retained_message_ids: history.snapshot.retained_message_ids,
            messages: history.messages.map((message) => ({
              id: message.id,
              role: message.role === 'tool' ? 'system' : message.role,
              content: message.content,
            })),
          });
          const message = `대화 리비전이 충돌했습니다. 서버 r${history.snapshot.revision}의 최신 이력을 반영했습니다. 다시 시도해 주세요.`;
          setCompactionStatus(message);
          addToast(message, 'info');
        } catch (refreshError: unknown) {
          if (!ownsOperation()) return;
          const detail = refreshError instanceof Error ? refreshError.message : '최신 이력을 불러오지 못했습니다.';
          const message = `대화 리비전이 충돌했습니다 (서버 r${error.payload.current_revision}). ${detail}`;
          setCompactionStatus(message);
          addToast(message, 'error');
        }
      } else {
        const detail = error instanceof Error ? error.message : '알 수 없는 오류';
        const message = `대화 압축에 실패했습니다: ${detail}`;
        setCompactionStatus(message);
        addToast(message, 'error');
      }
    } finally {
      if (ownsOperation()) {
        setIsCompactingConversation(false);
      }
    }
  }, [addToast, applyServerSnapshot, isForking, isCompactingConversation]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // 같은 파일을 다시 고를 수 있게 입력값을 비운다(값이 남으면 change 가 안 뜬다).
    e.target.value = '';
    if (!file) return;
    // 빠른 실패 — 서버가 최종 판정하지만, 왕복 전에 이유를 알려 준다.
    if (!ALLOWED_IMAGE_MIME.includes(file.type)) {
      addToast(`지원하지 않는 형식입니다: ${file.type || file.name} (PNG·JPEG·WebP·GIF)`, 'error');
      return;
    }
    if (file.size > MAX_ATTACHMENT_BYTES) {
      addToast(`첨부가 너무 큽니다: ${(file.size / 1024 / 1024).toFixed(1)}MB (상한 5MB)`, 'error');
      return;
    }
    void readAttachmentBase64(file)
      .then((data_base64) => {
        const attachment: ChatAttachment = {
          name: file.name,
          mime_type: file.type,
          data_base64,
          bytes: file.size,
        };
        pendingAttachmentsRef.current = [...pendingAttachmentsRef.current, attachment];
        setPendingAttachments(pendingAttachmentsRef.current);
        // 파일명 표식은 **이력 참조용**으로 남긴다(바이트는 별도 채널로 간다).
        setInputText(prev => prev ? `${prev}\n[첨부 파일: ${file.name}]` : `[첨부 파일: ${file.name}] `);
        addToast(`파일 첨부: ${file.name} — 모델에 이미지로 전달됩니다`, 'info');
      })
      .catch((error: unknown) => {
        addToast(error instanceof Error ? error.message : '파일을 읽지 못했습니다.', 'error');
      });
  };

  const removePendingAttachment = useCallback((name: string, bytes: number) => {
    const next = pendingAttachmentsRef.current.filter(
      (attachment) => !(attachment.name === name && attachment.bytes === bytes),
    );
    pendingAttachmentsRef.current = next;
    setPendingAttachments(next);
  }, []);

  // Close menus on click outside
  useEffect(() => {
    const handleDocumentClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('.model-selector-wrap')) setModelDropdownOpen(false);
      if (!target.closest('.codex-action-plus-wrap')) setActionMenuOpen(false);
      if (!target.closest('.codex-access-pill-wrap')) setAccessDropdownOpen(false);
      if (!target.closest('.agk-mcp-chip-wrap')) setMcpMenuOpen(false);
    };
    document.addEventListener('click', handleDocumentClick);
    return () => document.removeEventListener('click', handleDocumentClick);
  }, []);

  const handleFeedScroll = useCallback(() => {
    const feed = feedRef.current;
    if (!feed) return;
    const nearEnd = feed.scrollHeight - feed.scrollTop - feed.clientHeight <= 80;
    shouldFollowOutputRef.current = nearEnd;
    setShowLatestAction(!nearEnd);
  }, []);

  const handleShowLatestResponse = useCallback(() => {
    const feed = feedRef.current;
    if (!feed) return;
    shouldFollowOutputRef.current = true;
    feed.scrollTop = feed.scrollHeight;
    setShowLatestAction(false);
  }, []);

  const isHero = messages.length === 0;
  const sessionTitle = activeSession?.title || '새 대화';
  const modelLabel = useMemo(() => {
    const foundLocal = localModels.find(m => m.id === selectedModel);
    if (foundLocal) {
      const tag = foundLocal.parameter_count_b > 0
        ? ` (${formatModelAmount(foundLocal.parameter_count_b)}B)`
        : foundLocal.disk_size_gb > 0
          ? ` (${formatModelAmount(foundLocal.disk_size_gb)}GB)`
          : '';
      return `${foundLocal.name || foundLocal.id}${tag}`;
    }
    const foundAvail = availableModels.find(m => m.id === selectedModel);
    if (foundAvail) {
      return foundAvail.description || foundAvail.id;
    }
    if (selectedModel === 'default') {
      return localModels[0]?.name ? `${localModels[0].name} (로컬)` : '로컬 모델 감지 중...';
    }
    return selectedModel;
  }, [selectedModel, localModels, availableModels]);

  const editorContent = previewVisible ? <ArtifactPreview /> : <CodeEditor />;
  const changesContent = (
    <ChangePanel
      visible={true}
      onClose={() => {
        setChangePanelVisible(false);
        setEnvTab('env');
      }}
    />
  );

  const composerCard = (
    <ChatComposer
      inputText={inputText}
      textareaRef={textareaRef}
      attachments={pendingAttachments}
      isStreaming={isStreaming}
      isTransitioning={isForking || isCompactingConversation}
      onChange={(event) => {
        setInputText(event.target.value);
        event.target.style.height = 'auto';
        event.target.style.height = `${Math.min(220, event.target.scrollHeight)}px`;
      }}
      onKeyDown={handleKeyDown}
      onRemoveAttachment={removePendingAttachment}
      onSend={() => void handleSend()}
      onStop={handleStop}
      tools={(
        <ChatComposerTools
          actionMenuOpen={actionMenuOpen}
          accessDropdownOpen={accessDropdownOpen}
          mcpMenuOpen={mcpMenuOpen}
          accessMode={accessMode}
          webSearch={webSearch}
          codeMode={codeMode}
          mcpServers={mcpServerList}
          mcpAllowlist={mcpAllowlist}
          onToggleActionMenu={() => setActionMenuOpen((open) => !open)}
          onAttach={() => { fileInputRef.current?.click(); setActionMenuOpen(false); }}
          onToggleAccessMenu={() => setAccessDropdownOpen((open) => !open)}
          onAccessChoice={(mode) => void handleToggleAccessMode(mode)}
          onToggleSearch={() => setWebSearch((enabled) => !enabled)}
          onToggleCode={() => setCodeMode((enabled) => !enabled)}
          onToggleMcpMenu={() => setMcpMenuOpen((open) => !open)}
          onToggleMcpServer={(name) => {
            const isSelected = mcpAllowlist.includes(name);
            setSelectedMcp((previous) => {
              const base = previous ?? mcpServerList.map((server) => server.name);
              return isSelected ? base.filter((item) => item !== name) : [...base, name];
            });
          }}
        />
      )}
      modelSelector={(
        <ChatModelSelector
          label={modelLabel}
          selectedModel={selectedModel}
          open={modelDropdownOpen}
          scanning={isScanningLocal}
          localModels={localModels}
          availableModels={availableModels}
          onToggle={() => setModelDropdownOpen((open) => !open)}
          onRefresh={() => void loadLocalModels(true)}
          onLocalChoice={handleModelChoice}
          onCloudChoice={(modelId) => { setSelectedModel(modelId); setModelDropdownOpen(false); }}
        />
      )}
    />
  );
  return (
    <div className={`agk-workspace workspace-chat ${isHero ? 'is-empty' : ''}`}>
      {/* ── Main column: topbar + canvas + composer ──────────── */}
      <div className="agk-main-column">
        <header className="agk-topbar workspace-chat-header">
          <div className="agk-breadcrumb">
            <span className="crumb-project" data-testid="active-project-label" data-project-id={activeProjectId ?? ''}>
              {activeProjectName || workspaceContext?.project_name || 'Ssak-Ai'}
            </span>
            <span className="crumb-sep">/</span>
            {isEditingTitle ? (
              <input
                type="text"
                className="crumb-title-input"
                aria-label="대화 제목"
                value={titleInput}
                autoFocus
                onChange={(e) => setTitleInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
                  if (e.key === 'Enter') {
                    if (titleInput.trim() && activeSessionId) {
                      updateSessionTitle(activeSessionId, titleInput.trim());
                      addToast('대화 제목이 변경되었습니다.', 'info');
                    }
                    setIsEditingTitle(false);
                  } else if (e.key === 'Escape') {
                    setIsEditingTitle(false);
                  }
                }}
                onBlur={() => {
                  if (titleInput.trim() && activeSessionId) {
                    updateSessionTitle(activeSessionId, titleInput.trim());
                  }
                  setIsEditingTitle(false);
                }}
              />
            ) : (
              <button
                type="button"
                className="crumb-title editable"
                title="대화 제목 수정"
                aria-label={`대화 제목 수정: ${sessionTitle}`}
                onClick={() => {
                  setIsEditingTitle(true);
                  setTitleInput(sessionTitle);
                }}
              >
                <span className="workspace-conversation-title">{sessionTitle}</span>
                <AppIcon name="edit" size={14} />
              </button>
            )}
          </div>
          <div className="agk-topbar-actions">
            <button
              type="button"
              className={`topbar-tool-btn ${isForking ? 'active' : ''}`}
              aria-label={`대화 분기: ${sessionTitle}`}
              aria-describedby="conversation-compaction-status"
              aria-busy={isForking}
              title={isForking ? '대화 분기 및 동기화 중' : '원본을 보존하고 대화 분기'}
              disabled={isForking || isCompactingConversation || isStreaming || !activeSessionId || !activeProjectId || messages.length === 0}
              onClick={() => void forkActiveConversation()}
            >
              <AppIcon name={isForking ? 'refresh' : 'git'} size={18} />
            </button>
            <button
              type="button"
              className={`topbar-tool-btn ${isCompactingConversation ? 'active' : ''}`}
              aria-label={`대화 압축: ${sessionTitle}`}
              aria-describedby="conversation-compaction-status"
              aria-busy={isCompactingConversation}
              title={isCompactingConversation ? '대화 압축 및 동기화 중' : '현재 대화 압축'}
              disabled={isForking || isCompactingConversation || isStreaming || !activeSessionId || !activeProjectId}
              onClick={() => void handleCompactConversation()}
            >
              <AppIcon name={isCompactingConversation ? 'refresh' : 'layers'} size={18} />
            </button>
            <button
              type="button"
              className="topbar-tool-btn"
              aria-label="명령 팔레트 열기 (Cmd+K)"
              title="명령 팔레트 (Cmd+K)"
              onClick={() => setCommandPaletteVisible(true)}
            >
              <AppIcon name="search" size={18} />
            </button>
            <button
              type="button"
              className="topbar-tool-btn"
              aria-label="대화 기록 열기"
              title="대화 기록"
              onClick={() => setHistoryVisible(true)}
            >
              <AppIcon name="history" size={18} />
            </button>
            <button
              type="button"
              className={`topbar-tool-btn ${envPanelOpen ? 'active' : ''}`}
              onClick={() => setEnvPanelOpen((v) => !v)}
              title="환경 패널 토글"
              aria-label="환경 패널 토글"
              aria-expanded={envPanelOpen}
            >
              <AppIcon name="panelLeft" size={18} />
            </button>
            <button
              type="button"
              className="topbar-tool-btn"
              onClick={() => {
                if (document.fullscreenElement) {
                  document.exitFullscreen().catch(() => {});
                } else {
                  document.documentElement.requestFullscreen().catch(() => {});
                }
              }}
              title="전체화면"
              aria-label="전체화면"
            >
              <AppIcon name="monitor" size={18} />
            </button>
          </div>
        </header>

        <div className="agk-canvas workspace-chat-canvas">
          {!isHero && (
            <div
              className="agk-feed"
              ref={feedRef}
              role="region"
              aria-label="대화 내용"
              tabIndex={0}
              onScroll={handleFeedScroll}
            >
              <div className="agk-feed-inner">
                {messages.map((msg, index) => (
                  <ChatMessage key={msg.id ?? `local:${activeSessionId}:${index}`} message={msg} />
                ))}
                <ActivityTimeline />
                {isStreaming && <WorkingIndicator elapsed={elapsed} status={streamStatus} />}
                {streamError && !isStreaming && (
                  <StreamErrorBanner
                    message={streamError}
                    onRetry={() => {
                      const turn = retryTurnRef.current;
                      if (turn) void runCompletion(turn);
                    }}
                  />
                )}
                {!isStreaming && (
                  <FileEditCard
                    onReview={() => { setEnvPanelOpen(true); setEnvTab('changes'); }}
                    onDiscard={() => {
                      const { rejectAll, clearChanges } = useChangeStore.getState();
                      rejectAll();
                      clearChanges();
                      addToast('편집 변경 사항을 실행 취소했습니다.', 'info');
                    }}
                  />
                )}
                {showLatestAction && (
                  <button type="button" className="workspace-nav-link" onClick={handleShowLatestResponse}>
                    <AppIcon name="chevronDown" size={16} /> 최신 응답 보기
                  </button>
                )}
              </div>
            </div>
          )}

          {isHero && (
            <div className="agk-chat-empty-state">
              <h1 className="hero-headline" data-testid="hero-headline">무엇을 만들어 볼까요?</h1>
              <p className="hero-subline">코드를 살펴보거나, 해결할 문제를 알려 주세요.</p>
              {(activeProjectName || workspaceContext.project_name) && (
                <div className="agk-chat-project-context">
                  <AppIcon name="folder" size={16} />
                  <span>{activeProjectName || workspaceContext.project_name}</span>
                </div>
              )}
            </div>
          )}
        </div>
          <div className={`agk-composer-zone ${isHero ? 'hero' : 'docked'}`}>
            <QueuedMessagesCard
              items={queuedMessages}
              collapsed={queueCollapsed}
              onToggleCollapse={() => setQueueCollapsed((v) => !v)}
              onSendNow={handleSendNow}
              onEdit={handleEditQueued}
              onDelete={handleDeleteQueued}
              onMoveUp={handleMoveUpQueued}
              onMoveDown={handleMoveDownQueued}
              onReorder={handleReorderQueued}
              onClearAll={handleClearAllQueued}
            />
            {composerCard}
            {isHero && (
              <div className="agk-chat-quick-actions" aria-label="작업 시작 제안">
                <button type="button" onClick={() => {
                  setInputText('현재 프로젝트의 구조와 주요 흐름을 설명해 주세요.');
                  textareaRef.current?.focus();
                }}>
                  <AppIcon name="code" size={16} /> 코드 살펴보기
                </button>
                <button type="button" onClick={() => {
                  setInputText('해결할 오류와 관련 코드를 확인해 주세요.\n\n');
                  textareaRef.current?.focus();
                }}>
                  <AppIcon name="activity" size={16} /> 오류 해결하기
                </button>
                <button type="button" onClick={() => {
                  setInputText('현재 프로젝트에서 테스트가 필요한 부분을 찾고 테스트를 작성해 주세요.');
                  textareaRef.current?.focus();
                }}>
                  <AppIcon name="check" size={16} /> 테스트 추가하기
                </button>
              </div>
            )}
            {!isHero && (
              <div className="codex-context-header-bar docked agk-composer-context" aria-label="현재 작업 환경">
                {(activeProjectName || workspaceContext.project_name) && (
                  <div className="context-item">
                    <AppIcon name="folder" size={14} />
                    <span className="item-text">{activeProjectName || workspaceContext.project_name}</span>
                  </div>
                )}
                <div className="context-item">
                  <AppIcon name="monitor" size={14} />
                  <span className="item-text">{workspaceContext.target}</span>
                </div>
                {workspaceContext.branch && (
                  <div className="context-item">
                    <AppIcon name="git" size={14} />
                    <span className="item-text branch" title={`실제 Git 브랜치: ${workspaceContext.branch}`}>{workspaceContext.branch.replace(/^codex\//, 'ssak-ai/')}</span>
                  </div>
                )}
              </div>
            )}
          </div>

        <input
          ref={fileInputRef}
          type="file"
          hidden
          accept="image/png,image/jpeg,image/webp,image/gif"
          onChange={handleFileUpload}
        />
      </div>

      {/* ── Right: Ssak-Ai 환경 rail ──────────────────────── */}
      <EnvironmentPanel
        open={envPanelOpen}
        tab={envTab}
        onTabChange={setEnvTab}
        onClose={() => setEnvPanelOpen(false)}
        branch={workspaceContext.branch}
        workspacePath={workspaceContext.workspace_path}
        mcpServers={mcpServerList}
        editorContent={editorContent}
        changesContent={changesContent}
      />

      <ChatHistory visible={historyVisible} onClose={() => setHistoryVisible(false)} />

      {/* Screen-reader hint for pending review count */}
      <span className="visually-hidden" aria-live="polite">
        {pendingChangeCount > 0 ? `검토 대기 변경 ${pendingChangeCount}건` : ''}
      </span>
      <span id="conversation-compaction-status" className="visually-hidden" role="status">
        {compactionStatus ?? ''}
      </span>
    </div>
  );
};

export default ChatPage;
