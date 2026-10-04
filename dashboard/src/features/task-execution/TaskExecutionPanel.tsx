import { useApprovalQueue } from './useApprovalQueue';
import { TaskExecutionView } from './TaskExecutionView';
import { useTaskExecutionEvents } from './useTaskExecutionEvents';

export function TaskExecutionPanel() {
  const state = useTaskExecutionEvents();
  const approvals = useApprovalQueue();
  return (
    <TaskExecutionView
      tasks={state.tasks}
      selectedTaskId={state.selectedTaskId}
      events={state.events}
      connectionState={state.connectionState}
      error={state.error}
      pendingAction={state.pendingAction}
      failedTaskOperation={state.failedTaskOperation}
      completedSubmitDraft={state.completedSubmitDraft}
      approvals={approvals.approvals}
      alwaysAllowed={approvals.alwaysAllowed}
      pendingApprovalId={approvals.pendingRequestId}
      approvalError={approvals.error}
      onSelectTask={state.selectTask}
      onSubmit={state.submit}
      onCancel={state.cancel}
      onResume={state.resume}
      onFork={state.fork}
      onRetryTaskOperation={state.retryTaskOperation}
      onResolveApproval={approvals.resolve}
      onRevokeAlwaysAllowed={approvals.revokeAlwaysAllowed}
      onRetry={state.retry}
    />
  );
}
