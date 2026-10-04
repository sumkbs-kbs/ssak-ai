import { useCallback, useEffect, useRef, useState } from 'react';

import {
  cancelTask,
  fetchTaskEvents,
  fetchTaskList,
  forkTask,
  isTaskOperationRetryable,
  resumeTask,
  streamTaskEvents,
  submitTask,
} from './taskExecutionApi';
import {
  compactTaskEventReplica,
  createTaskEventReplica,
  mergeTaskEventReplica,
  readTaskEventReplicaCache,
  replaceTaskEventReplica,
  writeTaskEventReplicaCache,
  type TaskEventReplicaState,
} from './taskEventReplica';
import type { PendingTaskAction } from './TaskQueuePanel';
import {
  createTaskForkOperation,
  createTaskSubmitOperation,
  isTaskOperationScopeCurrent,
  type TaskOperation,
  type TaskSubmitDraft,
} from './taskOperation';
import type { TaskEvent, TaskId, TaskSummary } from './taskExecutionSchema';

export type TaskConnectionState = 'idle' | 'loading' | 'connected' | 'reconnecting' | 'complete' | 'error';

export type TaskExecutionState = Readonly<{
  tasks: readonly TaskSummary[];
  selectedTaskId: TaskId | null;
  events: readonly TaskEvent[];
  connectionState: TaskConnectionState;
  error: string | null;
  pendingAction: PendingTaskAction | null;
  failedTaskOperation: TaskOperation | null;
  completedSubmitDraft: TaskSubmitDraft | null;
  selectTask: (taskId: TaskId) => void;
  submit: (draft: TaskSubmitDraft) => void;
  cancel: (taskId: TaskId) => void;
  resume: (taskId: TaskId) => void;
  fork: (taskId: TaskId) => void;
  retryTaskOperation: () => void;
  retry: () => void;
}>;

function waitForReconnect(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, 1_000));
}

/**
 * Task 화면의 두 자료 — **목록**(스냅샷)과 **이벤트 스트림**(선택한 태스크) — 을 한 곳에서 묶는다.
 *
 * F-39: 목록은 **서버에 물어본 순간의 사실**이고 그 안에는 시간에 따라 변하는 값이 섞여 있다
 * (`status` · `execution_owner` · `resumable`). 스트림은 스스로 다시 붙지만, 다시 붙었다고 목록이
 * 새로워지지는 않았다 — 그래서 크래시·재기동을 넘긴 화면은 **낡은 스냅샷을 현재라고 말하면서**
 * 연결됨을 표시했고, 복구 가능한 태스크에 재개 대신 취소만 제안했다(막다른 길).
 *
 * 규칙: **서버를 잃었다가 되찾은 순간에는 목록을 다시 읽는다**(`refreshTaskList`).
 * 목록을 다시 읽는 것은 `reloadVersion` 이 아니라 **별도 경로**여야 한다 — `reloadVersion` 은
 * 스트림 이펙트까지 다시 시작시키므로, 스트림이 스스로 부르면 재시작 루프가 된다.
 */
export function useTaskExecutionEvents(): TaskExecutionState {
  const [tasks, setTasks] = useState<readonly TaskSummary[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<TaskId | null>(null);
  const [events, setEvents] = useState<readonly TaskEvent[]>([]);
  const [connectionState, setConnectionState] = useState<TaskConnectionState>('loading');
  const [error, setError] = useState<string | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [pendingAction, setPendingAction] = useState<PendingTaskAction | null>(null);
  const [failedTaskOperation, setFailedTaskOperation] = useState<TaskOperation | null>(null);
  const [completedSubmitDraft, setCompletedSubmitDraft] = useState<TaskSubmitDraft | null>(null);
  const replicaRef = useRef<TaskEventReplicaState | null>(null);
  const taskOperationPendingRef = useRef(false);

  /** 서버가 준 목록을 화면 상태로 옮기는 **한 곳** — 선택 유지 규칙도 여기가 소유한다. */
  const applyTaskList = useCallback((nextTasks: readonly TaskSummary[]): void => {
    setTasks(nextTasks);
    setSelectedTaskId((current) => {
      if (current !== null && nextTasks.some((task) => task.task_id === current)) return current;
      return nextTasks[0]?.task_id ?? null;
    });
    if (nextTasks.length === 0) setConnectionState('idle');
  }, []);

  /**
   * 목록만 다시 읽는다(스트림은 건드리지 않는다 — 스트림이 이 함수를 부르기 때문이다).
   *
   * 실패는 **조용히 넘기지 않는다**: 낡은 목록을 조용히 들고 있으면 이 자리의 병(화면이 현재
   * 사실을 모르는 채 현재라고 말한다)이 그대로 돌아온다. 다만 연결 상태는 스트림이 소유하므로
   * 여기서 뒤집지 않고, 사용자가 고칠 수 있는 형태(메시지 + 다시 연결)로 남긴다.
   */
  const refreshTaskList = useCallback(async (signal: AbortSignal): Promise<void> => {
    try {
      const nextTasks = await fetchTaskList(signal);
      if (signal.aborted) return;
      applyTaskList(nextTasks);
    } catch (caught: unknown) {
      if (signal.aborted) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [applyTaskList]);

  useEffect(() => {
    const controller = new AbortController();
    const resetTimer = window.setTimeout(() => {
      setConnectionState('loading');
      if (!taskOperationPendingRef.current) setError(null);
    }, 0);

    void fetchTaskList(controller.signal)
      .then((nextTasks) => {
        if (controller.signal.aborted) return;
        applyTaskList(nextTasks);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        if (!(caught instanceof Error)) throw caught;
        setError(caught.message);
        setConnectionState('error');
      });

    return () => {
      window.clearTimeout(resetTimer);
      controller.abort();
    };
  }, [reloadVersion, applyTaskList]);

  useEffect(() => {
    if (selectedTaskId === null) {
      replicaRef.current = null;
      const clearTimer = window.setTimeout(() => setEvents([]), 0);
      return () => window.clearTimeout(clearTimer);
    }

    const controller = new AbortController();
    const cachedReplica = readTaskEventReplicaCache(selectedTaskId);
    let replica = cachedReplica ?? createTaskEventReplica(selectedTaskId);
    replicaRef.current = replica;
    const resetTimer = window.setTimeout(() => {
      setEvents(replica.events);
      setError(null);
      setConnectionState('loading');
    }, 0);

    const run = async (): Promise<void> => {
      const replayCursor = cachedReplica?.contiguousSequence ?? 0;
      const replay = await fetchTaskEvents(selectedTaskId, replayCursor, controller.signal);
      if (controller.signal.aborted) return;
      replica = cachedReplica === null
        ? replaceTaskEventReplica(selectedTaskId, replay.events, replay.lastSequence)
        : mergeTaskEventReplica(replica, replay.events, replay.lastSequence);
      replica = compactTaskEventReplica(replica);
      replicaRef.current = replica;
      writeTaskEventReplicaCache(replica);
      let sequence = replica.contiguousSequence;
      setEvents(replica.events);
      setConnectionState('connected');
      let gapRecovery: Promise<void> | null = null;
      /**
       * 서버를 잃었다가 되찾았는가 — 그 순간 목록은 **낡은 스냅샷**이 된다(F-39).
       *
       * 실패할 때마다 `true` 로 세우고 회복에 성공한 뒤 한 번만 다시 읽는다: 한 번만 읽고 마는
       * 것이 아니라 **재연결마다** 다시 읽어야 두 번째 크래시에도 같은 정직함이 유지된다.
       */
      let listIsStale = false;

      const recoverGap = async (afterSequence: number): Promise<void> => {
        const missed = await fetchTaskEvents(selectedTaskId, afterSequence, controller.signal);
        if (controller.signal.aborted) return;
        replica = compactTaskEventReplica(mergeTaskEventReplica(replica, missed.events, missed.lastSequence));
        replicaRef.current = replica;
        sequence = replica.contiguousSequence;
        writeTaskEventReplicaCache(replica);
        setEvents(replica.events);
        setConnectionState(replica.gap === null ? 'connected' : 'reconnecting');
      };

      for (let attempt = 0; attempt < 3 && !controller.signal.aborted; attempt += 1) {
        try {
          const end = await streamTaskEvents(selectedTaskId, sequence, controller.signal, {
            onEvent: (event) => {
              const next = compactTaskEventReplica(mergeTaskEventReplica(replica, [event]));
              replica = next;
              replicaRef.current = next;
              sequence = next.contiguousSequence;
              writeTaskEventReplicaCache(next);
              setEvents(next.events);
              setConnectionState(next.gap === null ? 'connected' : 'reconnecting');
              if (next.gap !== null && gapRecovery === null) {
                gapRecovery = recoverGap(next.contiguousSequence).finally(() => {
                  gapRecovery = null;
                });
              }
            },
          });
          if (controller.signal.aborted) return;
          const pendingGapRecovery = gapRecovery;
          if (pendingGapRecovery !== null) await pendingGapRecovery;
          if (end.lastSequence > replica.contiguousSequence) {
            setConnectionState('reconnecting');
            await recoverGap(replica.contiguousSequence);
          }
          if (replica.gap !== null || replica.contiguousSequence < end.lastSequence) {
            setError(`Task event replay is incomplete at sequence ${replica.contiguousSequence}.`);
            setConnectionState('error');
            return;
          }
          setConnectionState('complete');
          sequence = Math.max(sequence, end.lastSequence);
          return;
        } catch (caught: unknown) {
          if (controller.signal.aborted) return;
          if (!(caught instanceof Error)) throw caught;
          if (attempt === 2) {
            setError(caught.message);
            setConnectionState('error');
            return;
          }
          setConnectionState('reconnecting');
          listIsStale = true;
          await waitForReconnect();
          await recoverGap(sequence);
          if (listIsStale && !controller.signal.aborted) {
            listIsStale = false;
            await refreshTaskList(controller.signal);
          }
        }
      }
    };

    void run().catch((caught: unknown) => {
      if (controller.signal.aborted) return;
      if (!(caught instanceof Error)) throw caught;
      setError(caught.message);
      setConnectionState('error');
    });

    return () => {
      window.clearTimeout(resetTimer);
      controller.abort();
    };
  }, [selectedTaskId, reloadVersion, refreshTaskList]);

  const selectTask = useCallback((taskId: TaskId) => setSelectedTaskId(taskId), []);
  const retry = useCallback(() => setReloadVersion((current) => current + 1), []);

  const executeTaskOperation = useCallback((operation: TaskOperation): void => {
    const request = operation.kind === 'submit' ? submitTask(operation) : forkTask(operation);
    void request
      .then(async (taskId) => {
        if (!(await isTaskOperationScopeCurrent(operation))) return;
        setFailedTaskOperation(null);
        if (operation.kind === 'submit') setCompletedSubmitDraft(operation.draft);
        setSelectedTaskId(taskId);
        setReloadVersion((current) => current + 1);
      })
      .catch((caught: unknown) => {
        if (!(caught instanceof Error)) throw caught;
        setError(caught.message);
        setFailedTaskOperation(isTaskOperationRetryable(caught) ? operation : null);
      })
      .finally(() => {
        taskOperationPendingRef.current = false;
        setPendingAction(null);
      });
  }, []);

  const startTaskOperation = useCallback((createOperation: () => Promise<TaskOperation>, action: PendingTaskAction): void => {
    if (taskOperationPendingRef.current) return;
    taskOperationPendingRef.current = true;
    setPendingAction(action);
    setError(null);
    setFailedTaskOperation(null);
    void createOperation()
      .then(async (operation) => {
        if (!(await isTaskOperationScopeCurrent(operation))) {
          setError('프로젝트 또는 사용자 범위가 바뀌어 작업을 제출할 수 없습니다.');
          taskOperationPendingRef.current = false;
          setPendingAction(null);
          return;
        }
        executeTaskOperation(operation);
      })
      .catch((caught: unknown) => {
        if (!(caught instanceof Error)) throw caught;
        setError(caught.message);
        taskOperationPendingRef.current = false;
        setPendingAction(null);
      });
  }, [executeTaskOperation]);

  const submit = useCallback((draft: TaskSubmitDraft): void => {
    startTaskOperation(() => createTaskSubmitOperation(draft), { kind: 'submit' });
  }, [startTaskOperation]);

  const cancel = useCallback((taskId: TaskId): void => {
    setPendingAction({ kind: 'cancel', taskId });
    setError(null);
    void cancelTask(taskId)
      .then(() => setReloadVersion((current) => current + 1))
      .catch((caught: unknown) => {
        if (!(caught instanceof Error)) throw caught;
        setError(caught.message);
      })
      .finally(() => setPendingAction(null));
  }, []);

  const resume = useCallback((taskId: TaskId): void => {
    setPendingAction({ kind: 'resume', taskId });
    setError(null);
    void resumeTask(taskId)
      .then(() => setReloadVersion((current) => current + 1))
      .catch((caught: unknown) => {
        if (!(caught instanceof Error)) throw caught;
        setError(caught.message);
      })
      .finally(() => setPendingAction(null));
  }, []);

  const fork = useCallback((taskId: TaskId): void => {
    startTaskOperation(() => createTaskForkOperation(taskId), { kind: 'fork', taskId });
  }, [startTaskOperation]);

  const retryTaskOperation = useCallback((): void => {
    const operation = failedTaskOperation;
    if (operation === null || taskOperationPendingRef.current) return;
    taskOperationPendingRef.current = true;
    void isTaskOperationScopeCurrent(operation).then((isCurrent) => {
      if (!isCurrent) {
        setFailedTaskOperation(null);
        setError('프로젝트 또는 사용자 범위가 바뀌어 이전 작업을 다시 시도할 수 없습니다.');
        taskOperationPendingRef.current = false;
        return;
      }
      setPendingAction(operation.kind === 'submit' ? { kind: 'submit' } : { kind: 'fork', taskId: operation.sourceTaskId });
      setError(null);
      executeTaskOperation(operation);
    });
  }, [executeTaskOperation, failedTaskOperation]);

  return {
    tasks,
    selectedTaskId,
    events,
    connectionState,
    error,
    pendingAction,
    failedTaskOperation,
    completedSubmitDraft,
    selectTask,
    submit,
    cancel,
    resume,
    fork,
    retryTaskOperation,
    retry,
  };
}
