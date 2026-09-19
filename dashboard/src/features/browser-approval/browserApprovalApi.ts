/**
 * 브라우저 효과 승인 API (task 18)
 * ================================
 * 서버가 판정한 **효과·위험도·바인딩**을 그대로 읽고, 사람의 결정을 보내고, **서버가 발급한**
 * 일회용 토큰을 받아 온다.
 *
 * 화면이 위험도를 계산하지 않는 것이 이 모듈의 요점이다 — 클라이언트가 `risk` 를 판단하기
 * 시작하면 그 판정이 두 곳으로 갈라지고, 사용자가 보는 위험도와 서버가 막는 위험도가 달라진다.
 * 여기서는 서버가 준 문자열을 그대로 zod 로 검증해 그린다.
 */

import ky from 'ky';
import { z } from 'zod';

import { createAccessPinHeaders } from '../../utils/accessPinCredential';

export const BrowserEffectSchema = z
  .object({
    effect: z.string().min(1),
    risk: z.string().min(1),
    requires_approval: z.boolean(),
    reason: z.string(),
    matched: z.string().optional(),
  })
  .readonly();

/** 승인이 묶인 좌표. 하나라도 달라지면 서버가 발급을 거절한다(재승인). */
export const BrowserApprovalBindingSchema = z
  .object({
    owner: z.string(),
    session_tag: z.string(),
    origin: z.string(),
    action: z.string().min(1),
    ref: z.string(),
    payload_hash: z.string(),
    generation: z.number().int().nonnegative(),
    effect: z.string().min(1),
    fingerprint: z.string(),
  })
  .readonly();

export const BrowserApprovalRequirementSchema = z
  .object({
    schema: z.string().min(1),
    request_id: z.string().min(1),
    effect: z.string().min(1),
    risk: z.string().min(1),
    reason: z.string(),
    summary: z.string(),
    created_at: z.number().nonnegative(),
    expires_at: z.number().nonnegative(),
    binding: BrowserApprovalBindingSchema,
  })
  .readonly();

const PendingBrowserApprovalsSchema = z
  .object({
    pending: z.array(BrowserApprovalRequirementSchema).readonly(),
    count: z.number().int().nonnegative(),
  })
  .readonly();

export const BrowserApprovalTicketSchema = z
  .object({
    schema: z.string().min(1),
    ticket_id: z.string().min(1),
    request_id: z.string().min(1),
    issued_at: z.number().nonnegative(),
    expires_at: z.number().nonnegative(),
    ttl_seconds: z.number().nonnegative(),
    consumed: z.boolean(),
    approval_token: z.string().min(1),
    binding: BrowserApprovalBindingSchema,
  })
  .readonly();

const BrowserApprovalGrantSchema = z
  .object({
    ok: z.literal(true),
    ticket: BrowserApprovalTicketSchema,
    summary: z.string(),
  })
  .readonly();

const BrowserApprovalResolveSchema = z
  .object({
    ok: z.literal(true),
    request_id: z.string().min(1),
    status: z.string().min(1),
  })
  .readonly();

export type BrowserEffect = z.infer<typeof BrowserEffectSchema>;
export type BrowserApprovalBinding = z.infer<typeof BrowserApprovalBindingSchema>;
export type BrowserApprovalRequirement = z.infer<typeof BrowserApprovalRequirementSchema>;
export type BrowserApprovalTicket = z.infer<typeof BrowserApprovalTicketSchema>;
export type BrowserApprovalDecision = 'approve' | 'deny';

function accessHeaders(): Headers {
  return createAccessPinHeaders({ Accept: 'application/json' });
}

export async function fetchPendingBrowserApprovals(
  signal: AbortSignal,
): Promise<readonly BrowserApprovalRequirement[]> {
  const raw: unknown = await ky
    .get('/api/agent/tools/browser/approval/pending', { headers: accessHeaders(), signal })
    .json();
  return PendingBrowserApprovalsSchema.parse(raw).pending;
}

/** 사람의 결정. 이 경로가 승인 상태를 바꾸고, 토큰은 **그 다음** 발급 경로에서만 나온다. */
export async function resolveBrowserApproval(
  requestId: string,
  decision: BrowserApprovalDecision,
): Promise<string> {
  const raw: unknown = await ky
    .post(`/api/approval/${encodeURIComponent(requestId)}/resolve`, {
      json: { decision },
      headers: accessHeaders(),
    })
    .json();
  return BrowserApprovalResolveSchema.parse(raw).status;
}

/** 서버 발급 경로. 승인되지 않은 요청에는 아무것도 나오지 않는다(409/403). */
export async function grantBrowserApproval(requestId: string): Promise<BrowserApprovalTicket> {
  const raw: unknown = await ky
    .post(`/api/agent/tools/browser/approval/${encodeURIComponent(requestId)}/grant`, {
      json: {},
      headers: accessHeaders(),
    })
    .json();
  return BrowserApprovalGrantSchema.parse(raw).ticket;
}

/** 거절된 요청을 대기 목록에서 뺀다 — 안 빼면 만료(60초)까지 화면이 거절한 승인을 다시 권한다. */
export async function withdrawBrowserApproval(requestId: string): Promise<void> {
  await ky.post(`/api/agent/tools/browser/approval/${encodeURIComponent(requestId)}/withdraw`, {
    json: {},
    headers: accessHeaders(),
  });
}
