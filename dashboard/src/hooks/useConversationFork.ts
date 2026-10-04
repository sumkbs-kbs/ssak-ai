import { useCallback, useEffect, useRef, useState } from 'react';

import {
  ConversationRevisionConflictError,
  fetchConversationHistory,
  forkConversation,
} from '../api/client';
import type { ConversationHistoryWire } from '../api/client';
import type { ChatMessage } from '../stores/chatStore';
import { useChatStore } from '../stores/chatStore';
import { useProjectStore } from '../stores/projectStore';

export type ConversationForkStatus =
  | Readonly<{ kind: 'idle' }>
  | Readonly<{ kind: 'pending'; message: string }>
  | Readonly<{ kind: 'success'; message: string }>
  | Readonly<{ kind: 'error'; message: string }>;

export type UseConversationForkOptions = Readonly<{
  isCompacting: boolean;
  onStatus?: (status: ConversationForkStatus) => void;
}>;

export type UseConversationForkResult = Readonly<{
  forkActiveConversation: () => Promise<void>;
  isForking: boolean;
  status: ConversationForkStatus;
}>;

type CapturedForkContext = Readonly<{
  sourceConversationId: string;
  projectId: string;
  projectEpoch: number;
  expectedRevision: number;
}>;

const IDLE_STATUS: ConversationForkStatus = { kind: 'idle' };

function mapHistoryMessages(history: ConversationHistoryWire): ChatMessage[] {
  return history.messages.map((message) => ({
    id: message.id,
    role: message.role === 'tool' ? 'system' : message.role,
    content: message.content,
  }));
}

function failureDetail(error: unknown): string {
  return error instanceof Error ? error.message : '알 수 없는 오류';
}

export function useConversationFork(options: UseConversationForkOptions): UseConversationForkResult {
  const [isForking, setIsForking] = useState(false);
  const [status, setStatus] = useState<ConversationForkStatus>(IDLE_STATUS);
  const mountedRef = useRef(true);
  const pendingRef = useRef(false);
  const invalidatedRef = useRef(false);
  const isCompactingRef = useRef(options.isCompacting);
  const onStatusRef = useRef(options.onStatus);
  isCompactingRef.current = options.isCompacting;
  onStatusRef.current = options.onStatus;

  useEffect(() => {
    mountedRef.current = true;
    const unsubscribeChat = useChatStore.subscribe((state, previous) => {
      if (!pendingRef.current) return;
      if (
        state.activeSessionId !== previous.activeSessionId
        || state.isStreaming !== previous.isStreaming
        || state.conversationRevision !== previous.conversationRevision
      ) {
        invalidatedRef.current = true;
      }
    });
    const unsubscribeProject = useProjectStore.subscribe((state, previous) => {
      if (pendingRef.current && state.switchEpoch !== previous.switchEpoch) {
        invalidatedRef.current = true;
      }
    });
    return () => {
      unsubscribeChat();
      unsubscribeProject();
      mountedRef.current = false;
      invalidatedRef.current = true;
    };
  }, []);

  useEffect(() => {
    if (pendingRef.current && options.isCompacting) invalidatedRef.current = true;
  }, [options.isCompacting]);

  const publishStatus = useCallback((next: ConversationForkStatus): void => {
    if (!mountedRef.current) return;
    setStatus(next);
    onStatusRef.current?.(next);
  }, []);

  const isCapturedContextCurrent = useCallback((captured: CapturedForkContext): boolean => {
    const project = useProjectStore.getState();
    const chat = useChatStore.getState();
    const source = chat.sessions.find((session) => session.id === captured.sourceConversationId);
    return mountedRef.current
      && !invalidatedRef.current
      && !isCompactingRef.current
      && project.activeProjectId === captured.projectId
      && project.switchEpoch === captured.projectEpoch
      && chat.activeSessionId === captured.sourceConversationId
      && chat.activeSession?.id === captured.sourceConversationId
      && source?.conversationRevision === captured.expectedRevision
      && chat.conversationRevision === captured.expectedRevision
      && !chat.isStreaming;
  }, []);

  const forkActiveConversation = useCallback(async (): Promise<void> => {
    if (pendingRef.current) return;

    const chat = useChatStore.getState();
    const project = useProjectStore.getState();
    const sourceConversationId = chat.activeSessionId;
    const source = sourceConversationId
      ? chat.sessions.find((session) => session.id === sourceConversationId)
      : undefined;
    if (!sourceConversationId || !source || !project.activeProjectId) {
      publishStatus({ kind: 'error', message: '분기할 대화 또는 프로젝트를 찾을 수 없습니다.' });
      return;
    }
    if (chat.isStreaming || isCompactingRef.current) {
      publishStatus({ kind: 'error', message: '응답 생성 또는 대화 압축이 끝난 뒤 분기할 수 있습니다.' });
      return;
    }

    const captured: CapturedForkContext = {
      sourceConversationId,
      projectId: project.activeProjectId,
      projectEpoch: project.switchEpoch,
      expectedRevision: source.conversationRevision,
    };
    pendingRef.current = true;
    invalidatedRef.current = false;
    setIsForking(true);
    publishStatus({ kind: 'pending', message: '대화를 분기하고 최신 이력을 불러오는 중입니다.' });

    let staleCompletion = false;
    try {
      const snapshot = await forkConversation({
        conversation_id: captured.sourceConversationId,
        expected_revision: captured.expectedRevision,
        project_id: captured.projectId,
      });
      if (!isCapturedContextCurrent(captured)) {
        staleCompletion = true;
        return;
      }
      const history = await fetchConversationHistory(snapshot.conversation_id, captured.projectId);
      if (!isCapturedContextCurrent(captured)) {
        staleCompletion = true;
        return;
      }
      const adopted = useChatStore.getState().adoptForkedSession({
        sourceConversationId: captured.sourceConversationId,
        conversationId: snapshot.conversation_id,
        revision: history.snapshot.revision,
        messages: mapHistoryMessages(history),
      });
      if (!adopted) {
        staleCompletion = true;
        return;
      }
      publishStatus({ kind: 'success', message: '대화를 분기하고 새 대화로 전환했습니다.' });
    } catch (error: unknown) {
      if (!isCapturedContextCurrent(captured)) {
        staleCompletion = true;
        return;
      }
      if (error instanceof ConversationRevisionConflictError) {
        try {
          const history = await fetchConversationHistory(captured.sourceConversationId, captured.projectId);
          if (!isCapturedContextCurrent(captured)) {
            staleCompletion = true;
            return;
          }
          useChatStore.getState().applyServerSnapshot({
            conversation_id: history.snapshot.conversation_id,
            revision: history.snapshot.revision,
            summary: history.snapshot.summary,
            retained_message_ids: history.snapshot.retained_message_ids,
            messages: mapHistoryMessages(history),
          });
          publishStatus({
            kind: 'error',
            message: `대화 리비전이 충돌했습니다. 서버 r${history.snapshot.revision}의 최신 이력을 반영했습니다. 다시 시도해 주세요.`,
          });
        } catch (refreshError: unknown) {
          if (!isCapturedContextCurrent(captured)) {
            staleCompletion = true;
            return;
          }
          publishStatus({
            kind: 'error',
            message: `대화 리비전이 충돌했습니다 (서버 r${error.payload.current_revision}). ${failureDetail(refreshError)}`,
          });
        }
        return;
      }
      publishStatus({ kind: 'error', message: `대화 분기에 실패했습니다: ${failureDetail(error)}` });
    } finally {
      pendingRef.current = false;
      if (mountedRef.current) {
        setIsForking(false);
        if (staleCompletion) setStatus(IDLE_STATUS);
      }
    }
  }, [isCapturedContextCurrent, publishStatus]);

  return { forkActiveConversation, isForking, status };
}
