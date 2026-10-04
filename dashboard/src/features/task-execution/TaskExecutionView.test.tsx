import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TaskExecutionView } from './TaskExecutionView';
import { TaskEventSchema, TaskIdSchema, TaskSummarySchema } from './taskExecutionSchema';

const taskId = TaskIdSchema.parse('task-live');
const task = TaskSummarySchema.parse({
  task_id: 'task-live',
  prompt: 'Repository tests and repair',
  status: 'running',
  output: '',
  error: null,
  created_at: '2026-08-20T09:00:00Z',
  updated_at: '2026-08-20T09:00:01Z',
  completed_at: null,
});
const leadEvent = TaskEventSchema.parse({
  sequence: 1,
  schema_version: 1,
  task_id: 'task-live',
  step_id: 'plan',
  agent_id: 'lead-agent',
  parent_id: null,
  tool_call_id: null,
  approval_id: null,
  resource_job_id: null,
  correlation_id: 'run-live',
  event_type: 'agent.started',
  payload: {
    agent_name: 'Lead agent',
    title: 'Plan verification',
  },
  created_at: '2026-08-20T09:00:01Z',
});
const event = TaskEventSchema.parse({
  sequence: 2,
  schema_version: 1,
  task_id: 'task-live',
  step_id: 'verify',
  agent_id: 'qa-agent',
  parent_id: 'lead-agent',
  tool_call_id: 'tool-qa',
  approval_id: null,
  resource_job_id: null,
  correlation_id: 'run-live',
  event_type: 'tool.running',
  payload: {
    agent_name: 'QA agent',
    title: 'Run verification',
    tool_name: 'terminal',
    command: 'npm run build',
    stdout: 'building dashboard',
  },
  created_at: '2026-08-20T09:00:02Z',
});

describe('TaskExecutionView', () => {
  it('renders a clear empty state when no task runs exist', () => {
    render(
      <TaskExecutionView
        tasks={[]}
        selectedTaskId={null}
        events={[]}
        connectionState="idle"
        error={null}
        pendingAction={null}
        failedTaskOperation={null}
        completedSubmitDraft={null}
        approvals={[]}
        alwaysAllowed={[]}
        pendingApprovalId={null}
        approvalError={null}
        onSelectTask={vi.fn()}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onResume={vi.fn()}
        onFork={vi.fn()}
        onRetryTaskOperation={vi.fn()}
        onResolveApproval={vi.fn()}
        onRevokeAlwaysAllowed={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: '실행 추적' })).toBeInTheDocument();
    expect(screen.getByText('표시할 task 실행 기록이 없습니다.')).toBeInTheDocument();
  });

  it('renders agent, checklist, and terminal evidence from the selected task', () => {
    render(
      <TaskExecutionView
        tasks={[task]}
        selectedTaskId={taskId}
        events={[leadEvent, event]}
        connectionState="connected"
        error={null}
        pendingAction={null}
        failedTaskOperation={null}
        completedSubmitDraft={null}
        approvals={[]}
        alwaysAllowed={[]}
        pendingApprovalId={null}
        approvalError={null}
        onSelectTask={vi.fn()}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onResume={vi.fn()}
        onFork={vi.fn()}
        onRetryTaskOperation={vi.fn()}
        onResolveApproval={vi.fn()}
        onRevokeAlwaysAllowed={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Repository tests and repair, 상태 running' })).toBeInTheDocument();
    expect(screen.getByText('QA agent')).toBeInTheDocument();
    expect(screen.getByText('Run verification')).toBeInTheDocument();
    expect(screen.getByText('npm run build')).toBeInTheDocument();
    expect(screen.getByText('building dashboard')).toBeInTheDocument();
    expect(screen.getByText('연결됨')).toBeInTheDocument();

    const leadNode = screen.getByText('Lead agent').closest('li');
    expect(leadNode).not.toBeNull();
    if (leadNode !== null) {
      expect(within(leadNode).getByText('QA agent')).toBeInTheDocument();
    }
  });

  it('DAT-01 F1: wires store cancelled status so late direct_completed stays cancelled', () => {
    const cancelledTask = TaskSummarySchema.parse({
      task_id: 'task-live',
      prompt: 'Cancel vs late complete',
      status: 'cancelled',
      output: '',
      error: 'user-cancel',
      created_at: '2026-08-20T09:00:00Z',
      updated_at: '2026-08-20T09:00:03Z',
      completed_at: '2026-08-20T09:00:03Z',
    });
    const cancelEvent = TaskEventSchema.parse({
      sequence: 1,
      schema_version: 2,
      task_id: 'task-live',
      step_id: 'run',
      agent_id: 'lead-agent',
      parent_id: null,
      tool_call_id: null,
      approval_id: null,
      resource_job_id: null,
      correlation_id: 'run-live',
      event_type: 'task.status',
      payload: { from_status: 'running', to_status: 'cancelled', terminal: true },
      created_at: '2026-08-20T09:00:02Z',
    });
    const lateComplete = TaskEventSchema.parse({
      sequence: 2,
      schema_version: 2,
      task_id: 'task-live',
      step_id: 'run',
      agent_id: 'lead-agent',
      parent_id: null,
      tool_call_id: null,
      approval_id: null,
      resource_job_id: null,
      correlation_id: 'run-live',
      event_type: 'direct_completed',
      payload: { output_length: 12 },
      created_at: '2026-08-20T09:00:03Z',
    });

    render(
      <TaskExecutionView
        tasks={[cancelledTask]}
        selectedTaskId={taskId}
        events={[cancelEvent, lateComplete]}
        connectionState="connected"
        error={null}
        pendingAction={null}
        failedTaskOperation={null}
        completedSubmitDraft={null}
        approvals={[]}
        alwaysAllowed={[]}
        pendingApprovalId={null}
        approvalError={null}
        onSelectTask={vi.fn()}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onResume={vi.fn()}
        onFork={vi.fn()}
        onRetryTaskOperation={vi.fn()}
        onResolveApproval={vi.fn()}
        onRevokeAlwaysAllowed={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    // Queue panel uses store status; execution blocks must also stay cancelled (not completed).
    expect(screen.getByRole('button', { name: 'Cancel vs late complete, 상태 cancelled' })).toBeInTheDocument();
    expect(screen.getAllByText('취소됨').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('완료')).not.toBeInTheDocument();
    expect(document.querySelector('.task-execution-status-completed')).toBeNull();
  });

});
