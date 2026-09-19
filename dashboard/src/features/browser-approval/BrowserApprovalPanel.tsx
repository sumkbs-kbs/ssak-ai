/**
 * BrowserApprovalPanel — 브라우저 효과 승인 (task 18)
 * ==================================================
 * 에이전트가 페이지에서 **효과를 일으키려 할 때** 사람에게 묻는 표면이다. 이 화면이 지키는 것:
 *
 * 1. **서버가 판정한 것을 그대로 보여준다.** 무엇을(행동), 어디서(origin), 무슨 뜻인지(effect),
 *    얼마나 위험한지(risk), 왜 그렇게 봤는지(reason)를 서버 문자열 그대로 그린다. 화면이
 *    위험도를 다시 계산하지 않는다 — 두 곳에서 판단하면 사용자가 보는 것과 서버가 막는 것이
 *    갈라진다.
 * 2. **승인이 무엇에 묶였는지 보여준다.** origin·generation·ref·payload 지문을 같이 보여 주므로,
 *    "내가 승인한 뒤에 페이지가 바뀌었다"는 사실을 사용자가 화면에서 알 수 있다. 승인은 그 순간의
 *    그 행동에만 유효하고 한 번만 쓰인다 — 만료까지 남은 시간도 초로 센다.
 * 3. **'항상 허용' 이 없다는 사실을 말한다.** 다른 도구에는 '항상 허용' 이 있지만 브라우저
 *    효과에는 없다(매번 그 행동 하나에 대한 승인이다). 그 정책을 화면이 숨기면 사용자는
 *    왜 매번 묻는지 모른 채 클릭만 반복한다.
 *
 * 비밀 위생: 이 화면은 **발급하지 않는다**. 승인은 사람의 결정이고 일회용 토큰 발급은 요청한
 * 클라이언트의 몫이다 — 화면이 발급까지 하면 토큰이 브라우저에 남고 정작 실행할 주체는 토큰을
 * 받지 못한다. 그래서 토큰은 DOM 에도, 이 컴포넌트의 props 에도 등장하지 않는다.
 */

import React, { useEffect, useMemo, useState } from 'react';

import type { BrowserApprovalDecision, BrowserApprovalRequirement } from './browserApprovalApi';

/** 서버가 준 effect 코드를 사람 말로 옮기는 **표시용** 사전(판정은 서버가 한다). */
const EFFECT_LABEL: Record<string, string> = {
  read: '읽기',
  navigate: '페이지 이동',
  input: '입력',
  download: '다운로드',
  settings: '설정 변경',
  transmit: '전송·게시',
  upload: '업로드',
  auth: '로그인·인증',
  permission: '권한 부여',
  delete: '삭제',
  financial: '결제·송금',
  unknown: '판정 불가',
};

const RISK_LABEL: Record<string, string> = {
  safe: '안전',
  low: '낮음',
  medium: '보통',
  high: '높음',
  critical: '치명적',
};

export function effectLabel(effect: string): string {
  return EFFECT_LABEL[effect] ?? effect;
}

export function riskLabel(risk: string): string {
  return RISK_LABEL[risk] ?? risk;
}

/** 남은 초. 만료된 승인은 0 이다(음수를 보여 주면 남은 것처럼 보인다). */
export function secondsLeft(expiresAt: number, now: number): number {
  return Math.max(0, Math.ceil(expiresAt - now));
}

export type BrowserApprovalPanelProps = Readonly<{
  requirements: readonly BrowserApprovalRequirement[];
  decisions: Readonly<Record<string, BrowserApprovalDecision>>;
  pendingRequestId: string | null;
  error: string | null;
  /** 시험·스냅숏을 위해 주입 가능 — 서버의 `expires_at` 과 **같은 단위**(Unix 초)다. */
  now?: number;
  onDecide: (requestId: string, decision: BrowserApprovalDecision) => void;
}>;

export const BrowserApprovalPanel: React.FC<BrowserApprovalPanelProps> = ({
  requirements,
  decisions,
  pendingRequestId,
  error,
  now,
  onDecide,
}) => {
  // 서버의 `expires_at` 은 **Unix 초**다. ms 와 섞으면 남은 시간이 만 배로 어긋나 만료된 승인이
  // 살아 있는 것처럼 보인다(혹은 그 반대) — 그래서 한 단위로만 센다.
  const [tick, setTick] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (requirements.length === 0) return;
    const interval = window.setInterval(() => setTick(Date.now() / 1000), 1_000);
    return () => window.clearInterval(interval);
  }, [requirements.length]);
  const clock = now ?? tick;

  const ordered = useMemo(
    () => [...requirements].sort((a, b) => a.created_at - b.created_at),
    [requirements],
  );

  return (
    <section className="glass-panel browser-approval-panel" aria-labelledby="browser-approval-heading">
      <header className="browser-approval-header">
        <h3 id="browser-approval-heading">브라우저 효과 승인</h3>
        <p className="browser-approval-note">
          에이전트가 페이지에서 무언가를 실행하려 할 때 서버가 <strong>동작의 의미</strong>로 위험도를
          판정합니다. 승인은 그 순간의 <strong>주소·요소·내용·DOM 세대</strong>에 묶이고
          <strong> 한 번만</strong> 쓰입니다. 브라우저 효과에는 &lsquo;항상 허용&rsquo;이 없습니다.
        </p>
      </header>

      {error !== null ? (
        <div className="browser-approval-error" role="alert">
          {error}
        </div>
      ) : null}

      {ordered.length === 0 ? (
        <p className="browser-approval-empty" data-testid="browser-approval-empty">
          대기 중인 브라우저 승인이 없습니다.
        </p>
      ) : (
        <ul className="browser-approval-list">
          {ordered.map(item => {
            const decision = decisions[item.request_id];
            const busy = pendingRequestId === item.request_id;
            const left = secondsLeft(item.expires_at, clock);
            return (
              <li key={item.request_id} data-testid="browser-approval-item" className="browser-approval-item">
                <div className="browser-approval-summary">{item.summary}</div>
                <div className="browser-approval-meta">
                  <span className={`status-badge ${item.risk === 'critical' ? 'danger' : 'pending'}`}>
                    {effectLabel(item.effect)} · {riskLabel(item.risk)}
                  </span>
                  <span className="browser-approval-axis">
                    주소 <code>{item.binding.origin || '(없음)'}</code>
                  </span>
                  <span className="browser-approval-axis">
                    동작 <code>{item.binding.action}</code> · DOM 세대 <code>{item.binding.generation}</code>
                  </span>
                  <span className="browser-approval-axis" data-testid="browser-approval-ttl">
                    만료까지 {left}초
                  </span>
                </div>
                <div className="browser-approval-reason">판정 근거: {item.reason}</div>
                <div className="browser-approval-fingerprint">
                  요소 <code>{item.binding.ref || '(없음)'}</code> · 내용 지문{' '}
                  <code>{item.binding.payload_hash || '(없음)'}</code>
                </div>
                {decision === 'approve' ? (
                  <p className="browser-approval-granted" data-testid="browser-approval-granted">
                    승인됨 · 요청한 클라이언트가 이어서 실행합니다. 그 실행은 <strong>한 번만</strong> 유효하고,
                    페이지·주소·내용이 바뀌면 이 승인은 무효가 됩니다(다시 물어봅니다).
                  </p>
                ) : decision === 'deny' ? (
                  <p className="browser-approval-granted" data-testid="browser-approval-denied">
                    거절됨 · 이 효과는 실행되지 않습니다.
                  </p>
                ) : (
                  <div className="browser-approval-actions">
                    <button
                      type="button"
                      data-testid="browser-approval-approve"
                      disabled={busy || left === 0}
                      onClick={() => onDecide(item.request_id, 'approve')}
                    >
                      승인
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      data-testid="browser-approval-deny"
                      disabled={busy}
                      onClick={() => onDecide(item.request_id, 'deny')}
                    >
                      거절
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};
