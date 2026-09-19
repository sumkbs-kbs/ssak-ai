import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApprovalQueue } from './ApprovalQueue';
import { ApprovalRequestSchema, AlwaysAllowGrantSchema } from './approvalApi';

vi.mock('../../components/Editor/DiffViewer', () => ({
  default: ({ change }: Readonly<{ change: Readonly<{ newContent: string }> }>) => (
    <pre data-testid="approval-diff">{change.newContent}</pre>
  ),
}));

const approval = ApprovalRequestSchema.parse({
  request_id: 'approval-1',
  tool_name: 'apply_patch',
  risk_level: 'high',
  description: '설정 파일 수정',
  diff_preview: '--- a/settings.ts\n+++ b/settings.ts\n@@ -1 +1 @@\n-old\n+new',
  status: 'pending',
  created_at: 1_777_000_000,
  timeout_sec: 120,
  auto_review: {
    decision: 'escalate',
    risk_score: 0.8,
    reason_codes: ['file_change'],
    rationale: '사용자 확인이 필요합니다.',
    reviewer: 'policy-v1',
    reviewed_at: 1_777_000_001,
  },
});

describe('ApprovalQueue', () => {
  it('renders the server approval diff and sends explicit decisions', () => {
    const onResolve = vi.fn();
    render(
      <ApprovalQueue
        approvals={[approval]}
        alwaysAllowed={[]}
        pendingRequestId={null}
        error={null}
        onResolve={onResolve}
        onRevokeAlwaysAllowed={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: '승인 대기열' })).toBeInTheDocument();
    expect(screen.getByTestId('approval-diff')).toHaveTextContent('new');
    expect(screen.getByText('자동 검토 · 사용자 확인 필요')).toBeInTheDocument();
    expect(screen.getByText('80% 위험도')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '설정 파일 수정 승인' }));
    expect(onResolve).toHaveBeenCalledWith('approval-1', 'approve');
    fireEvent.click(screen.getByRole('button', { name: '설정 파일 수정 거절' }));
    expect(onResolve).toHaveBeenCalledWith('approval-1', 'deny');
  });

  it('states that 항상 허용 covers the whole tool, not this one call (F-33)', () => {
    // '항상 허용'은 인자·경로·프로젝트와 무관하게 도구 전체를 덮는다 — 동의 문구가 그 범위를
    // 정확히 말하지 않으면 사용자는 자기가 무엇에 동의했는지 알 수 없다.
    render(
      <ApprovalQueue
        approvals={[approval]}
        alwaysAllowed={[]}
        pendingRequestId={null}
        error={null}
        onResolve={vi.fn()}
        onRevokeAlwaysAllowed={vi.fn()}
      />,
    );

    const control = screen.getByRole('button', { name: /apply_patch 도구를 항상 허용/ });
    expect(control).toHaveAccessibleName('apply_patch 도구를 항상 허용 (이후 모든 호출을 승인 없이 실행)');
    expect(screen.getByText(/도구 전체/)).toBeInTheDocument();
    expect(screen.getByText(/인자·경로·프로젝트와 무관하게/)).toBeInTheDocument();
  });

  it("'항상 허용' 을 서버가 거절하는 도구에는 그 버튼을 주지 않는다 (task 18)", () => {
    // 브라우저 효과는 매 행동에 묶인 승인이 필요하다. 버튼이 있으면 사용자는 눌렀는데 403 을 보고,
    // 화면이 약속한 것과 서버가 하는 일이 갈라진다 — 그래서 화면은 **서버 판정**을 따른다.
    const browserEffect = ApprovalRequestSchema.parse({
      ...approval,
      request_id: 'approval-2',
      tool_name: 'browser_effect',
      description: 'http://127.0.0.1:52370 에서 Send message 을(를) click 합니다',
      diff_preview: '',
      always_allow_allowed: false,
    });

    render(
      <ApprovalQueue
        approvals={[browserEffect]}
        alwaysAllowed={[]}
        pendingRequestId={null}
        error={null}
        onResolve={vi.fn()}
        onRevokeAlwaysAllowed={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: /browser_effect 도구를 항상 허용/ })).toBeNull();
    expect(screen.getByTestId('approval-always-allow-unavailable')).toHaveTextContent(/매 호출/);
    // 승인·거절은 그대로 남는다(막는 것이 아니라 '항상' 만 없앤다).
    expect(screen.getByRole('button', { name: /승인$/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /거절$/ })).toBeInTheDocument();
  });

  it('lists the standing grants with their reason and unconsented run count (F-33)', () => {
    const grant = AlwaysAllowGrantSchema.parse({
      tool_name: 'run_bash_command',
      granted_at: 1_777_000_000,
      granted_for: 'run_bash_command 실행',
      auto_approved_count: 4,
      last_auto_approved_at: 1_777_000_500,
    });

    render(
      <ApprovalQueue
        approvals={[]}
        alwaysAllowed={[grant]}
        pendingRequestId={null}
        error={null}
        onResolve={vi.fn()}
        onRevokeAlwaysAllowed={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: '항상 허용된 도구 1개' })).toBeInTheDocument();
    expect(screen.getByText('run_bash_command')).toBeInTheDocument();
    expect(screen.getByText(/동의 없이 4회 실행/)).toBeInTheDocument();
    expect(screen.getByText(/부여 근거: run_bash_command 실행/)).toBeInTheDocument();
  });

  it('revokes every grant from the queue and disables the control when there are none', () => {
    const onRevokeAlwaysAllowed = vi.fn();
    const grant = AlwaysAllowGrantSchema.parse({
      tool_name: 'run_bash_command',
      granted_at: 1_777_000_000,
      granted_for: 'run_bash_command 실행',
      auto_approved_count: 0,
      last_auto_approved_at: null,
    });

    const { rerender } = render(
      <ApprovalQueue
        approvals={[]}
        alwaysAllowed={[grant]}
        pendingRequestId={null}
        error={null}
        onResolve={vi.fn()}
        onRevokeAlwaysAllowed={onRevokeAlwaysAllowed}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '부여 모두 해제' }));
    expect(onRevokeAlwaysAllowed).toHaveBeenCalledTimes(1);

    rerender(
      <ApprovalQueue
        approvals={[]}
        alwaysAllowed={[]}
        pendingRequestId={null}
        error={null}
        onResolve={vi.fn()}
        onRevokeAlwaysAllowed={onRevokeAlwaysAllowed}
      />,
    );

    expect(screen.getByRole('button', { name: '부여 모두 해제' })).toBeDisabled();
    expect(screen.getByText('상시 자동 승인된 도구가 없습니다.')).toBeInTheDocument();
  });
});
