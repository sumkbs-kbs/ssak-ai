import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BrowserApprovalPanel, effectLabel, riskLabel, secondsLeft } from './BrowserApprovalPanel';
import { BrowserApprovalRequirementSchema } from './browserApprovalApi';

const NOW = 1_777_000_000; // 서버와 같은 단위 — Unix **초**

function requirement(overrides: Partial<Record<string, unknown>> = {}) {
  return BrowserApprovalRequirementSchema.parse({
    schema: 'ssak.browser.approval/1.0',
    request_id: 'breq_1',
    effect: 'financial',
    risk: 'critical',
    reason: '이름/역할이 financial 를 가리킨다',
    summary: 'http://127.0.0.1:52370 에서 Pay now — transfer 100 을(를) click 합니다 — 결제·송금',
    created_at: NOW - 5,
    expires_at: NOW + 55,
    binding: {
      owner: '7c67d4ee42d6',
      session_tag: 'edb4a3',
      origin: 'http://127.0.0.1:52370',
      action: 'click',
      ref: 'edb4a3-985a7af8de-b28b-e6',
      payload_hash: '8737da40e12e317a',
      generation: 3,
      effect: 'financial',
      fingerprint: '4490353cdea6447f',
    },
    ...overrides,
  });
}

describe('BrowserApprovalPanel', () => {
  it('그린다: 서버가 준 의미·주소·세대·지문과 남은 시간', () => {
    render(
      <BrowserApprovalPanel
        requirements={[requirement()]}
        decisions={{}}
        pendingRequestId={null}
        error={null}
        now={NOW}
        onDecide={vi.fn()}
      />,
    );

    expect(screen.getByText(/결제·송금 · 치명적/)).toBeTruthy();
    expect(screen.getByText('http://127.0.0.1:52370')).toBeTruthy();
    expect(screen.getByText('edb4a3-985a7af8de-b28b-e6')).toBeTruthy();
    expect(screen.getByText('8737da40e12e317a')).toBeTruthy();
    expect(screen.getByTestId('browser-approval-ttl').textContent).toContain('55초');
    // '항상 허용' 이 없다는 사실을 화면이 말한다(정책을 숨기지 않는다).
    expect(screen.getByText(/항상 허용/)).toBeTruthy();
  });

  it('승인·거절을 각각의 결정으로 보낸다', () => {
    const onDecide = vi.fn();
    render(
      <BrowserApprovalPanel
        requirements={[requirement()]}
        decisions={{}}
        pendingRequestId={null}
        error={null}
        now={NOW}
        onDecide={onDecide}
      />,
    );

    fireEvent.click(screen.getByTestId('browser-approval-approve'));
    expect(onDecide).toHaveBeenCalledWith('breq_1', 'approve');

    fireEvent.click(screen.getByTestId('browser-approval-deny'));
    expect(onDecide).toHaveBeenCalledWith('breq_1', 'deny');
  });

  it('승인 뒤에는 실행 주체를 밝히고 승인 버튼을 다시 주지 않는다(토큰은 화면에 없다)', () => {
    render(
      <BrowserApprovalPanel
        requirements={[requirement()]}
        decisions={{ breq_1: 'approve' }}
        pendingRequestId={null}
        error={null}
        now={NOW}
        onDecide={vi.fn()}
      />,
    );

    const granted = screen.getByTestId('browser-approval-granted').textContent ?? '';
    expect(granted).toContain('요청한 클라이언트가 이어서 실행');
    expect(granted).toContain('한 번만');
    // 화면은 발급하지 않는다 — 토큰이 DOM 에 실리면 페이지 안의 무엇이든 읽을 수 있다.
    expect(document.body.textContent ?? '').not.toMatch(/ssak1\./);
    expect(screen.queryByTestId('browser-approval-approve')).toBeNull();
  });

  it('거절하면 실행되지 않는다는 사실을 그린다', () => {
    render(
      <BrowserApprovalPanel
        requirements={[requirement()]}
        decisions={{ breq_1: 'deny' }}
        pendingRequestId={null}
        error={null}
        now={NOW}
        onDecide={vi.fn()}
      />,
    );

    expect(screen.getByTestId('browser-approval-denied').textContent).toContain('실행되지 않습니다');
    expect(screen.queryByTestId('browser-approval-deny')).toBeNull();
  });

  it('만료된 승인은 승인할 수 없다', () => {
    render(
      <BrowserApprovalPanel
        requirements={[requirement({ expires_at: NOW - 1 })]}
        decisions={{}}
        pendingRequestId={null}
        error={null}
        now={NOW}
        onDecide={vi.fn()}
      />,
    );

    expect(screen.getByTestId('browser-approval-ttl').textContent).toContain('0초');
    expect(screen.getByTestId<HTMLButtonElement>('browser-approval-approve').disabled).toBe(true);
  });

  it('오래 기다린 승인부터 그린다(먼저 만료되는 것부터 사람이 본다)', () => {
    render(
      <BrowserApprovalPanel
        requirements={[
          requirement({ request_id: 'breq_new', created_at: NOW - 1, summary: '나중에 온 요청' }),
          requirement({ request_id: 'breq_old', created_at: NOW - 50, summary: '먼저 온 요청' }),
        ]}
        decisions={{}}
        pendingRequestId={null}
        error={null}
        now={NOW}
        onDecide={vi.fn()}
      />,
    );

    const items = screen.getAllByTestId('browser-approval-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('먼저 온 요청');
    expect(items[1].textContent).toContain('나중에 온 요청');
  });

  it('빈 목록과 오류를 상태로 그린다', () => {
    const { unmount } = render(
      <BrowserApprovalPanel
        requirements={[]}
        decisions={{}}
        pendingRequestId={null}
        error={null}
        now={NOW}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.getByTestId('browser-approval-empty')).toBeTruthy();
    unmount();

    render(
      <BrowserApprovalPanel
        requirements={[requirement()]}
        decisions={{}}
        pendingRequestId="breq_1"
        error="POST /api/approval/breq_1/resolve: 409"
        now={NOW}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.getByRole('alert').textContent).toContain('409');
    expect(screen.getByTestId<HTMLButtonElement>('browser-approval-approve').disabled).toBe(true);
  });

  it('라벨·남은 초 계산은 경계에서 음수를 만들지 않는다', () => {
    expect(effectLabel('transmit')).toBe('전송·게시');
    expect(effectLabel('mystery')).toBe('mystery'); // 모르는 코드를 감추지 않는다
    expect(riskLabel('critical')).toBe('치명적');
    expect(secondsLeft(NOW - 10, NOW)).toBe(0);
    expect(secondsLeft(NOW + 4.2, NOW)).toBe(5);
  });
});
