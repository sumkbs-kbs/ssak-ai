import { useMemo, useState } from 'react';

import DiffViewer from '../../components/Editor/DiffViewer';
import type { ProposedChange } from '../../stores/changeStore';
import type {
  AlwaysAllowGrant,
  ApprovalDecision,
  ApprovalRequest,
  ApprovalReview,
} from './approvalApi';

type ApprovalQueueProps = Readonly<{
  approvals: readonly ApprovalRequest[];
  alwaysAllowed: readonly AlwaysAllowGrant[];
  pendingRequestId: string | null;
  error: string | null;
  onResolve: (requestId: string, decision: ApprovalDecision) => void;
  onRevokeAlwaysAllowed: () => void;
}>;

function diffPath(lines: readonly string[]): string {
  const header = lines.find((line) => line.startsWith('+++ '));
  if (header === undefined) return 'proposed-change.diff';
  return header.slice(4).replace(/^b\//, '').replace(/ \(after\)$/, '') || 'proposed-change.diff';
}

function reviewLabel(review: ApprovalReview): string {
  if (review.decision === 'approve') return '승인 후보';
  if (review.decision === 'deny') return '거부 권고';
  return '사용자 확인 필요';
}

function grantedAtLabel(grantedAt: number): string {
  return new Date(grantedAt * 1_000).toLocaleString();
}

export function approvalDiffChange(approval: ApprovalRequest): ProposedChange {
  const lines = approval.diff_preview.split('\n');
  const original: string[] = [];
  const modified: string[] = [];
  let additions = 0;
  let deletions = 0;

  for (const line of lines) {
    if (line.startsWith('--- ') || line.startsWith('+++ ') || line.startsWith('@@')) continue;
    if (line.startsWith('-')) {
      original.push(line.slice(1));
      deletions += 1;
    } else if (line.startsWith('+')) {
      modified.push(line.slice(1));
      additions += 1;
    } else {
      const content = line.startsWith(' ') ? line.slice(1) : line;
      original.push(content);
      modified.push(content);
    }
  }

  const filePath = diffPath(lines);
  return {
    id: approval.request_id,
    filePath,
    fileName: filePath.split('/').at(-1) ?? filePath,
    originalContent: original.join('\n'),
    newContent: modified.join('\n'),
    status: 'pending',
    diffStats: { additions, deletions },
    createdAt: approval.created_at * 1_000,
    description: approval.description,
  };
}

export function ApprovalQueue({
  approvals,
  alwaysAllowed,
  pendingRequestId,
  error,
  onResolve,
  onRevokeAlwaysAllowed,
}: ApprovalQueueProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = approvals.find((approval) => approval.request_id === selectedId) ?? approvals[0] ?? null;
  const change = useMemo(() => selected === null ? null : approvalDiffChange(selected), [selected]);

  return (
    <section className="approval-queue" aria-labelledby="approval-queue-title">
      <header>
        <div>
          <h4 id="approval-queue-title">승인 대기열</h4>
          <span>{approvals.length}건 대기</span>
        </div>
      </header>
      {error !== null && <p className="approval-queue-error" role="alert">{error}</p>}
      <section className="approval-grants" aria-labelledby="approval-grants-title">
        <header>
          <h5 id="approval-grants-title">항상 허용된 도구 {alwaysAllowed.length}개</h5>
          <button type="button" disabled={alwaysAllowed.length === 0} onClick={onRevokeAlwaysAllowed}>
            부여 모두 해제
          </button>
        </header>
        {alwaysAllowed.length === 0 ? (
          <p className="approval-queue-empty">상시 자동 승인된 도구가 없습니다.</p>
        ) : (
          <ul className="approval-grants-list">
            {alwaysAllowed.map((grant) => (
              <li key={grant.tool_name}>
                <strong>{grant.tool_name}</strong>
                <span>
                  {grantedAtLabel(grant.granted_at)} 부여 · 동의 없이 {grant.auto_approved_count}회 실행
                </span>
                <small>부여 근거: {grant.granted_for || '(기록 없음)'}</small>
              </li>
            ))}
          </ul>
        )}
      </section>
      {approvals.length === 0 ? (
        <p className="approval-queue-empty">대기 중인 승인 요청이 없습니다.</p>
      ) : (
        <div className="approval-queue-layout">
          <ul className="approval-queue-list">
            {approvals.map((approval) => (
              <li key={approval.request_id}>
                <button
                  type="button"
                  className={approval.request_id === selected?.request_id ? 'is-selected' : undefined}
                  onClick={() => setSelectedId(approval.request_id)}
                >
                  <strong>{approval.description}</strong>
                  <span>{approval.tool_name} · {approval.risk_level}</span>
                </button>
              </li>
            ))}
          </ul>
          {selected !== null && change !== null && (
            <div className="approval-queue-detail">
              {selected.diff_preview.length > 0 ? (
                <DiffViewer change={change} showActions={false} height={280} />
              ) : (
                <p className="approval-queue-empty">이 요청에는 파일 변경 미리보기가 없습니다.</p>
              )}
              {selected.auto_review !== null && (
                <aside className={`approval-review approval-review-${selected.auto_review.decision}`} aria-label="자동 검토 결과">
                  <div className="approval-review-heading">
                    <strong>자동 검토 · {reviewLabel(selected.auto_review)}</strong>
                    <span>{Math.round(selected.auto_review.risk_score * 100)}% 위험도</span>
                  </div>
                  <p>{selected.auto_review.rationale}</p>
                  <small>{selected.auto_review.reviewer} · 사용자 결정은 별도로 필요합니다.</small>
                </aside>
              )}
              <div className="approval-queue-actions">
                <button
                  type="button"
                  disabled={pendingRequestId === selected.request_id}
                  onClick={() => onResolve(selected.request_id, 'deny')}
                  aria-label={`${selected.description} 거절`}
                >
                  거절
                </button>
                {/* '항상 허용' 을 서버가 거절하는 도구(브라우저 효과)에는 버튼을 주지 않는다.
                    버튼이 있으면 사용자는 눌렀는데 403 을 보게 된다 — 화면은 서버 판정을 따른다. */}
                {selected.always_allow_allowed !== false && (
                  <button
                    type="button"
                    disabled={pendingRequestId === selected.request_id}
                    onClick={() => onResolve(selected.request_id, 'always_allow')}
                    aria-label={`${selected.tool_name} 도구를 항상 허용 (이후 모든 호출을 승인 없이 실행)`}
                  >
                    항상 허용
                  </button>
                )}
                <button
                  type="button"
                  className="is-primary"
                  disabled={pendingRequestId === selected.request_id}
                  onClick={() => onResolve(selected.request_id, 'approve')}
                  aria-label={`${selected.description} 승인`}
                >
                  승인
                </button>
              </div>
              {selected.always_allow_allowed === false ? (
                <p className="approval-queue-note" data-testid="approval-always-allow-unavailable">
                  이 도구에는 &lsquo;항상 허용&rsquo; 을 줄 수 없습니다 — <strong>{selected.tool_name}</strong> 의
                  매 호출은 그 대상·내용·페이지 상태에 묶인 승인이 따로 필요합니다.
                </p>
              ) : (
                <p className="approval-queue-note">
                  &lsquo;항상 허용&rsquo;은 이 요청이 아니라 <strong>{selected.tool_name} 도구 전체</strong>를 덮습니다 —
                  이후 그 도구의 모든 호출이 인자·경로·프로젝트와 무관하게 승인 없이 실행되고,
                  서버를 다시 시작하거나 위 목록에서 해제할 때까지 유지됩니다.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
