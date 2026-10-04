import { useEffect, useState, type FormEvent } from 'react';

import type { TaskId, TaskSummary } from './taskExecutionSchema';
import { canCancelTask, canResumeTask, taskStateLabel } from './taskLifecycleActions';
import type { TaskOperation, TaskSubmitDraft } from './taskOperation';

export type PendingTaskAction =
  | Readonly<{ kind: 'submit' }>
  | Readonly<{ taskId: TaskId; kind: 'cancel' | 'resume' | 'fork' }>;

type TaskQueuePanelProps = Readonly<{
  tasks: readonly TaskSummary[];
  selectedTaskId: TaskId | null;
  pendingAction: PendingTaskAction | null;
  failedTaskOperation: TaskOperation | null;
  completedSubmitDraft: TaskSubmitDraft | null;
  onSelectTask: (taskId: TaskId) => void;
  onSubmit: (draft: TaskSubmitDraft) => void;
  onCancel: (taskId: TaskId) => void;
  onResume: (taskId: TaskId) => void;
  onFork: (taskId: TaskId) => void;
  onRetryTaskOperation: () => void;
}>;

function taskTitle(task: TaskSummary): string {
  const prompt = task.prompt.trim();
  return prompt.length > 0 ? prompt : task.task_id;
}

export function TaskQueuePanel({
  tasks,
  selectedTaskId,
  pendingAction,
  failedTaskOperation,
  completedSubmitDraft,
  onSelectTask,
  onSubmit,
  onCancel,
  onResume,
  onFork,
  onRetryTaskOperation,
}: TaskQueuePanelProps) {
  const [prompt, setPrompt] = useState('');
  const [draftGeneration, setDraftGeneration] = useState(0);
  useEffect(() => {
    if (
      completedSubmitDraft !== null
      && completedSubmitDraft.input === prompt
      && completedSubmitDraft.generation === draftGeneration
    ) {
      setPrompt('');
      setDraftGeneration((generation) => generation + 1);
    }
  }, [completedSubmitDraft, draftGeneration, prompt]);
  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const normalized = prompt.trim();
    if (normalized.length === 0) return;
    onSubmit({ prompt: normalized, input: prompt, generation: draftGeneration });
  };
  const operationPending = pendingAction?.kind === 'submit' || pendingAction?.kind === 'fork';

  return (
    <section className="task-queue" aria-labelledby="task-queue-title">
      <header>
        <div>
          <h4 id="task-queue-title">Task Queue</h4>
          <span>{tasks.length}개 실행</span>
        </div>
      </header>
      <form className="task-submit-form" onSubmit={handleSubmit}>
        <label htmlFor="task-submit-prompt">새 작업 지시</label>
        <div>
          <input
            id="task-submit-prompt"
            value={prompt}
            onChange={(event) => {
              setPrompt(event.currentTarget.value);
              setDraftGeneration((generation) => generation + 1);
            }}
            placeholder="실행할 작업을 입력하세요"
            disabled={operationPending}
          />
          <button type="submit" disabled={prompt.trim().length === 0 || operationPending}>
            {pendingAction?.kind === 'submit' ? '제출 중' : '작업 제출'}
          </button>
        </div>
      </form>
      {failedTaskOperation !== null && (
        <div className="task-execution-error task-operation-retry" role="status" aria-live="polite">
          <span>{failedTaskOperation.kind === 'submit' ? '작업 제출 응답을 확인하지 못했습니다.' : '작업 분기 응답을 확인하지 못했습니다.'}</span>
          <button type="button" onClick={onRetryTaskOperation} disabled={pendingAction !== null}>
            같은 작업 다시 시도
          </button>
        </div>
      )}
      <div className="task-history-heading">
        <h5>세션 히스토리</h5>
        <span>{tasks.length}개 세션</span>
      </div>
      <ul className="task-queue-list">
        {tasks.map((task) => {
          const title = taskTitle(task);
          const stateLabel = taskStateLabel(task);
          const isPending = pendingAction !== null
            && 'taskId' in pendingAction
            && pendingAction.taskId === task.task_id;
          return (
            <li key={task.task_id} className={task.task_id === selectedTaskId ? 'is-selected' : undefined}>
              <button
                className="task-queue-select"
                type="button"
                onClick={() => onSelectTask(task.task_id)}
                aria-label={`${title}, 상태 ${stateLabel}`}
              >
                <strong>{title}</strong>
                <span>{stateLabel}</span>
              </button>
              <div className="task-queue-actions">
                {canCancelTask(task) && (
                  <button type="button" disabled={isPending || operationPending} onClick={() => onCancel(task.task_id)} aria-label={`${title} 취소`}>
                    취소
                  </button>
                )}
                {canResumeTask(task) && (
                  <button type="button" disabled={isPending || operationPending} onClick={() => onResume(task.task_id)} aria-label={`${title} 재개`}>
                    재개
                  </button>
                )}
                <button type="button" disabled={isPending || operationPending} onClick={() => onFork(task.task_id)} aria-label={`${title} 분기`}>
                  {pendingAction?.kind === 'fork' && isPending ? '분기 중' : '분기'}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
