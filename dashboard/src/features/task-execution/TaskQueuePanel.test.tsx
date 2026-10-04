import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TaskQueuePanel } from './TaskQueuePanel';
import { TaskIdSchema, TaskSummarySchema } from './taskExecutionSchema';
import { createTaskSubmitOperation } from './taskOperation';

const runningTask = TaskSummarySchema.parse({
  task_id: 'task-running',
  prompt: '검증 작업 실행',
  status: 'running',
  error: null,
  created_at: '2026-08-22T09:00:00Z',
  updated_at: '2026-08-22T09:00:01Z',
});
const failedTask = TaskSummarySchema.parse({
  task_id: 'task-failed',
  prompt: '중단 지점부터 복구',
  status: 'failed',
  error: 'interrupted',
  created_at: '2026-08-22T08:00:00Z',
  updated_at: '2026-08-22T08:00:01Z',
});

describe('TaskQueuePanel', () => {
  it('submits trimmed prompts and exposes only valid lifecycle actions', () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();
    const onResume = vi.fn();
    const onFork = vi.fn();

    const { rerender } = render(
      <TaskQueuePanel
        tasks={[runningTask, failedTask]}
        selectedTaskId={TaskIdSchema.parse('task-running')}
        pendingAction={null}
        failedTaskOperation={null}
        completedSubmitDraft={null}
        onSelectTask={vi.fn()}
        onSubmit={onSubmit}
        onCancel={onCancel}
        onResume={onResume}
        onFork={onFork}
        onRetryTaskOperation={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('새 작업 지시'), { target: { value: '  테스트를 실행해줘  ' } });
    fireEvent.click(screen.getByRole('button', { name: '작업 제출' }));
    const submittedDraft = onSubmit.mock.calls[0]?.[0];
    expect(submittedDraft).toEqual({ prompt: '테스트를 실행해줘', input: '  테스트를 실행해줘  ', generation: 1 });
    expect(screen.getByLabelText('새 작업 지시')).toHaveValue('  테스트를 실행해줘  ');

    rerender(
      <TaskQueuePanel
        tasks={[runningTask, failedTask]}
        selectedTaskId={TaskIdSchema.parse('task-running')}
        pendingAction={null}
        failedTaskOperation={null}
        completedSubmitDraft={submittedDraft}
        onSelectTask={vi.fn()}
        onSubmit={onSubmit}
        onCancel={onCancel}
        onResume={onResume}
        onFork={onFork}
        onRetryTaskOperation={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('새 작업 지시')).toHaveValue('');

    fireEvent.click(screen.getByRole('button', { name: '검증 작업 실행 취소' }));
    expect(onCancel).toHaveBeenCalledWith(TaskIdSchema.parse('task-running'));
    expect(screen.queryByRole('button', { name: '검증 작업 실행 재개' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '중단 지점부터 복구 재개' }));
    expect(onResume).toHaveBeenCalledWith(TaskIdSchema.parse('task-failed'));
    expect(screen.queryByRole('button', { name: '중단 지점부터 복구 취소' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '중단 지점부터 복구 분기' }));
    expect(onFork).toHaveBeenCalledWith(TaskIdSchema.parse('task-failed'));
    expect(screen.getByRole('heading', { name: '세션 히스토리' })).toBeInTheDocument();
  });

  it('offers resume for a run whose owning process died (F-36)', () => {
    // 크래시 뒤 재시작한 서버의 응답: 상태는 `running` 그대로이고 소유자는 죽었다.
    const orphaned = TaskSummarySchema.parse({
      task_id: 'task-orphaned',
      prompt: '크래시 뒤 복구할 작업',
      status: 'running',
      error: null,
      created_at: '2026-09-14T00:00:00Z',
      updated_at: '2026-09-14T00:00:01Z',
      execution_owner: 'dead',
      resumable: true,
    });
    const onResume = vi.fn();
    const onCancel = vi.fn();

    render(
      <TaskQueuePanel
        tasks={[orphaned]}
        selectedTaskId={null}
        pendingAction={null}
        failedTaskOperation={null}
        completedSubmitDraft={null}
        onSelectTask={vi.fn()}
        onSubmit={vi.fn()}
        onCancel={onCancel}
        onResume={onResume}
        onFork={vi.fn()}
        onRetryTaskOperation={vi.fn()}
      />,
    );

    // 화면이 "실행 중"이라고 말하지 않는다 — 주인이 죽었다는 사실을 말한다.
    expect(screen.queryByText('running')).not.toBeInTheDocument();
    expect(screen.getByText('실행 중단(소유 프로세스 종료) — 재개 가능')).toBeInTheDocument();

    // 복구 버튼이 보인다(예전 규칙은 `running` 에게 취소만 보여 줬다).
    fireEvent.click(
      screen.getByRole('button', { name: '크래시 뒤 복구할 작업 재개' }),
    );
    expect(onResume).toHaveBeenCalledWith(TaskIdSchema.parse('task-orphaned'));
    fireEvent.click(
      screen.getByRole('button', { name: '크래시 뒤 복구할 작업 취소' }),
    );
    expect(onCancel).toHaveBeenCalledWith(TaskIdSchema.parse('task-orphaned'));
  });

  it('offers a named retry for an unresolved submit without discarding its form input', async () => {
    const onRetryTaskOperation = vi.fn();
    const failedTaskOperation = await createTaskSubmitOperation({ prompt: 'retry this exact task', input: 'retry this exact task', generation: 1 });

    render(
      <TaskQueuePanel
        tasks={[]}
        selectedTaskId={null}
        pendingAction={null}
        failedTaskOperation={failedTaskOperation}
        completedSubmitDraft={null}
        onSelectTask={vi.fn()}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onResume={vi.fn()}
        onFork={vi.fn()}
        onRetryTaskOperation={onRetryTaskOperation}
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('작업 제출 응답을 확인하지 못했습니다.');
    fireEvent.click(screen.getByRole('button', { name: '같은 작업 다시 시도' }));
    expect(onRetryTaskOperation).toHaveBeenCalledTimes(1);
  });

  it('clears a retry completion only when its submitted draft remains unchanged', () => {
    const onSubmit = vi.fn();
    const { rerender } = render(
      <TaskQueuePanel
        tasks={[]}
        selectedTaskId={null}
        pendingAction={null}
        failedTaskOperation={null}
        completedSubmitDraft={null}
        onSelectTask={vi.fn()}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        onResume={vi.fn()}
        onFork={vi.fn()}
        onRetryTaskOperation={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('새 작업 지시'), { target: { value: 'same task' } });
    fireEvent.click(screen.getByRole('button', { name: '작업 제출' }));
    const submittedDraft = onSubmit.mock.calls[0]?.[0];
    fireEvent.change(screen.getByLabelText('새 작업 지시'), { target: { value: 'newer edit' } });
    fireEvent.change(screen.getByLabelText('새 작업 지시'), { target: { value: 'same task' } });

    rerender(
      <TaskQueuePanel
        tasks={[]}
        selectedTaskId={null}
        pendingAction={null}
        failedTaskOperation={null}
        completedSubmitDraft={submittedDraft}
        onSelectTask={vi.fn()}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        onResume={vi.fn()}
        onFork={vi.fn()}
        onRetryTaskOperation={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('새 작업 지시')).toHaveValue('same task');
  });

  it('clears an unchanged draft after a retry completion', async () => {
    const onRetryTaskOperation = vi.fn();
    const completedSubmitDraft = { prompt: 'retry task', input: 'retry task', generation: 1 };
    const failedTaskOperation = await createTaskSubmitOperation(completedSubmitDraft);
    const { rerender } = render(
      <TaskQueuePanel
        tasks={[]}
        selectedTaskId={null}
        pendingAction={null}
        failedTaskOperation={failedTaskOperation}
        completedSubmitDraft={null}
        onSelectTask={vi.fn()}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onResume={vi.fn()}
        onFork={vi.fn()}
        onRetryTaskOperation={onRetryTaskOperation}
      />,
    );

    fireEvent.change(screen.getByLabelText('새 작업 지시'), { target: { value: 'retry task' } });
    fireEvent.click(screen.getByRole('button', { name: '같은 작업 다시 시도' }));
    rerender(
      <TaskQueuePanel
        tasks={[]}
        selectedTaskId={null}
        pendingAction={null}
        failedTaskOperation={null}
        completedSubmitDraft={completedSubmitDraft}
        onSelectTask={vi.fn()}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onResume={vi.fn()}
        onFork={vi.fn()}
        onRetryTaskOperation={onRetryTaskOperation}
      />,
    );

    expect(onRetryTaskOperation).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('새 작업 지시')).toHaveValue('');
  });
});
