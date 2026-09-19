import { useCallback, useEffect, useState } from 'react';

import {
  fetchPendingBrowserApprovals,
  resolveBrowserApproval,
  withdrawBrowserApproval,
  type BrowserApprovalDecision,
  type BrowserApprovalRequirement,
} from './browserApprovalApi';

export type BrowserApprovalState = Readonly<{
  requirements: readonly BrowserApprovalRequirement[];
  /** 이 화면이 내린 결정(표시용). 실제 실행은 **요청한 클라이언트**가 이어받는다. */
  decisions: Readonly<Record<string, BrowserApprovalDecision>>;
  pendingRequestId: string | null;
  error: string | null;
  decide: (requestId: string, decision: BrowserApprovalDecision) => void;
}>;

/**
 * 대기 중인 브라우저 효과 승인을 폴링하고, 사람의 결정을 서버에 보낸다.
 *
 * **이 화면은 발급하지 않는다.** 승인은 사람의 결정이고, 일회용 토큰 발급은 **요청한 클라이언트**의
 * 몫이다(에이전트가 자기 실행 직전에 받아 쓴다). 화면이 발급까지 하면 토큰이 브라우저 메모리에
 * 남고, 정작 실행할 주체는 쓸 토큰을 받지 못한다 — 그래서 여기서는 `resolve` 만 부르고
 * `grant` 는 부르지 않는다.
 *
 * 거절은 서버 기록(F-33)에 남기고 대기 목록에서도 뺀다(withdraw) — 안 빼면 만료(60초)까지
 * 화면이 이미 거절한 승인을 다시 권한다.
 */
export function useBrowserApprovals(): BrowserApprovalState {
  const [requirements, setRequirements] = useState<readonly BrowserApprovalRequirement[]>([]);
  const [decisions, setDecisions] = useState<Readonly<Record<string, BrowserApprovalDecision>>>({});
  const [pendingRequestId, setPendingRequestId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const refresh = async (): Promise<void> => {
      try {
        const pending = await fetchPendingBrowserApprovals(controller.signal);
        if (controller.signal.aborted) return;
        setRequirements(pending);
        setError(null);
        // 클라이언트가 발급해 실행까지 마친 요청은 목록에서 사라진다 — 그 결정 표시도 함께 지운다.
        const live = new Set(pending.map(item => item.request_id));
        setDecisions(current => {
          const next: Record<string, BrowserApprovalDecision> = {};
          for (const [id, decision] of Object.entries(current)) {
            if (live.has(id)) next[id] = decision;
          }
          return next;
        });
      } catch (caught: unknown) {
        if (controller.signal.aborted) return;
        if (!(caught instanceof Error)) throw caught;
        setError(caught.message);
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 3_000);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, []);

  const decide = useCallback((requestId: string, decision: BrowserApprovalDecision): void => {
    setPendingRequestId(requestId);
    setError(null);
    void resolveBrowserApproval(requestId, decision)
      .then(async () => {
        setDecisions(current => ({ ...current, [requestId]: decision }));
        if (decision === 'deny') {
          await withdrawBrowserApproval(requestId);
          setRequirements(current => current.filter(item => item.request_id !== requestId));
        }
      })
      .catch((caught: unknown) => {
        if (!(caught instanceof Error)) throw caught;
        setError(caught.message);
      })
      .finally(() => setPendingRequestId(null));
  }, []);

  return { requirements, decisions, pendingRequestId, error, decide };
}
