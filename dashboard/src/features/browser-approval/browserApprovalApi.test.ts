import { beforeEach, describe, expect, it, vi } from 'vitest';

const getMock = vi.hoisted(() => vi.fn());
const postMock = vi.hoisted(() => vi.fn());

vi.mock('ky', () => ({
  default: {
    get: getMock,
    post: postMock,
  },
}));

import {
  BrowserApprovalRequirementSchema,
  BrowserApprovalTicketSchema,
  fetchPendingBrowserApprovals,
  grantBrowserApproval,
  resolveBrowserApproval,
  withdrawBrowserApproval,
} from './browserApprovalApi';

function jsonResponse(body: unknown): Readonly<{ json: () => Promise<unknown> }> {
  return { json: () => Promise.resolve(body) };
}

const binding = {
  owner: '7c67d4ee42d6',
  session_tag: 'edb4a3',
  origin: 'http://127.0.0.1:52370',
  action: 'click',
  ref: 'edb4a3-985a7af8de-b28b-e6',
  payload_hash: '8737da40e12e317a',
  generation: 3,
  effect: 'transmit',
  fingerprint: '4490353cdea6447f',
};

const requirement = {
  schema: 'ssak.browser.approval/1.0',
  request_id: 'breq_1',
  effect: 'transmit',
  risk: 'high',
  reason: '이름/역할이 transmit 를 가리킨다',
  summary: '... Send message ...',
  created_at: 1_777_000_000,
  expires_at: 1_777_000_060,
  binding,
};

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
});

describe('browserApprovalApi', () => {
  it('대기 목록을 전용 경로에서 읽고 서버가 준 위험도를 그대로 쓴다', async () => {
    getMock.mockReturnValue(jsonResponse({ pending: [requirement], count: 1 }));

    const pending = await fetchPendingBrowserApprovals(new AbortController().signal);

    expect(String(getMock.mock.calls[0]?.[0])).toBe('/api/agent/tools/browser/approval/pending');
    expect(pending).toHaveLength(1);
    expect(pending[0]?.risk).toBe('high');
    expect(pending[0]?.binding.generation).toBe(3);
  });

  it('사람의 결정은 승인 API 로 보낸다(발급이 아니다)', async () => {
    postMock.mockReturnValue(jsonResponse({ ok: true, request_id: 'breq_1', status: 'approved' }));

    const status = await resolveBrowserApproval('breq_1', 'approve');

    expect(String(postMock.mock.calls[0]?.[0])).toBe('/api/approval/breq_1/resolve');
    expect(postMock.mock.calls[0]?.[1]).toMatchObject({ json: { decision: 'approve' } });
    expect(status).toBe('approved');
  });

  it('발급은 서버 경로에서만 받고 토큰 없는 응답은 계약 위반으로 거절한다', async () => {
    postMock.mockReturnValue(
      jsonResponse({
        ok: true,
        ticket: {
          schema: 'ssak.browser.approval/1.0',
          ticket_id: 'btk_1',
          request_id: 'breq_1',
          issued_at: 1_777_000_000,
          expires_at: 1_777_000_060,
          ttl_seconds: 60,
          consumed: false,
          approval_token: 'ssak1.server-issued',
          binding,
        },
        summary: '...',
      }),
    );

    const ticket = await grantBrowserApproval('breq_1');
    expect(ticket.approval_token).toBe('ssak1.server-issued');
    expect(ticket.ttl_seconds).toBe(60);

    // 토큰이 빠진 응답은 "발급됐다"는 말로 통과시키지 않는다(서버 계약이 깨진 것이다).
    postMock.mockReturnValue(jsonResponse({ ok: true, ticket: { ...ticket, approval_token: undefined } }));
    await expect(grantBrowserApproval('breq_1')).rejects.toThrow();
  });

  it('거절 뒤에는 대기 목록에서 뺀다(만료까지 다시 권하지 않는다)', async () => {
    postMock.mockReturnValue(jsonResponse({ ok: true, request_id: 'breq_1', withdrawn: true }));

    await withdrawBrowserApproval('breq_1');

    expect(String(postMock.mock.calls[0]?.[0])).toBe('/api/agent/tools/browser/approval/breq_1/withdraw');
  });

  it('요청 ID 를 경로에 그대로 붙이지 않는다', async () => {
    postMock.mockReturnValue(jsonResponse({ ok: true, request_id: 'x', status: 'approved' }));

    await resolveBrowserApproval('../../admin/reset', 'deny');

    expect(String(postMock.mock.calls[0]?.[0])).toBe('/api/approval/..%2F..%2Fadmin%2Freset/resolve');
  });

  it('스키마는 서버가 보낸 위험도 축을 빠뜨린 응답을 거절한다', () => {
    expect(() => BrowserApprovalRequirementSchema.parse({ ...requirement, binding: { origin: 'x' } })).toThrow();
    expect(() =>
      BrowserApprovalTicketSchema.parse({
        schema: 'ssak.browser.approval/1.0',
        ticket_id: 'btk_1',
        request_id: 'breq_1',
        issued_at: 1,
        expires_at: 61,
        ttl_seconds: 60,
        consumed: false,
        approval_token: 'ssak1.x',
      }),
    ).toThrow();
    expect(BrowserApprovalRequirementSchema.parse(requirement).binding.payload_hash).toBe('8737da40e12e317a');
  });
});
