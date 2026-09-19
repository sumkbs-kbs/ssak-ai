import ky from 'ky';
import { z } from 'zod';

import { createAccessPinHeaders } from '../../utils/accessPinCredential';

export const ApprovalDecisionSchema = z.enum(['approve', 'deny', 'always_allow']);
export const ApprovalReviewSchema = z.object({
  decision: z.enum(['approve', 'deny', 'escalate']),
  risk_score: z.number().min(0).max(1),
  reason_codes: z.array(z.string()).readonly(),
  rationale: z.string(),
  reviewer: z.string().min(1),
  reviewed_at: z.number().nonnegative(),
}).readonly();
export const ApprovalRequestSchema = z.object({
  request_id: z.string().min(1),
  tool_name: z.string().min(1),
  risk_level: z.string().min(1),
  description: z.string(),
  diff_preview: z.string(),
  status: z.literal('pending'),
  created_at: z.number().nonnegative(),
  timeout_sec: z.number().int().positive(),
  auto_review: ApprovalReviewSchema.nullable(),
  // 서버 판정: 이 도구에 '항상 허용' 을 줄 수 있는가(task 18 — 브라우저 효과는 없다).
  // 옵션인 이유는 구버전 서버·기존 fixture 와의 호환이다(없으면 허용으로 본다).
  always_allow_allowed: z.boolean().optional(),
}).readonly();

const ApprovalListResponseSchema = z.object({
  pending: z.array(ApprovalRequestSchema).readonly(),
  count: z.number().int().nonnegative(),
}).readonly();

const ApprovalResolveResponseSchema = z.object({
  ok: z.literal(true),
  request_id: z.string().min(1),
  status: z.string().min(1),
}).readonly();

// '항상 허용' 부여 — 도구 단위이며 프로세스 수명 동안 유지된다. 읽고 되돌릴 수 있어야 한다(F-33).
export const AlwaysAllowGrantSchema = z.object({
  tool_name: z.string().min(1),
  granted_at: z.number().nonnegative(),
  granted_for: z.string(),
  auto_approved_count: z.number().int().nonnegative(),
  last_auto_approved_at: z.number().nonnegative().nullable(),
}).readonly();

const AlwaysAllowListResponseSchema = z.object({
  grants: z.array(AlwaysAllowGrantSchema).readonly(),
  count: z.number().int().nonnegative(),
}).readonly();

const ResetAlwaysAllowedResponseSchema = z.object({
  ok: z.literal(true),
  revoked: z.array(z.string()).readonly(),
  message: z.string(),
}).readonly();

export type ApprovalDecision = z.infer<typeof ApprovalDecisionSchema>;
export type ApprovalReview = z.infer<typeof ApprovalReviewSchema>;
export type ApprovalRequest = z.infer<typeof ApprovalRequestSchema>;
export type AlwaysAllowGrant = z.infer<typeof AlwaysAllowGrantSchema>;

function accessHeaders(): Headers {
  return createAccessPinHeaders({ Accept: 'application/json' });
}

export async function fetchPendingApprovals(signal: AbortSignal): Promise<readonly ApprovalRequest[]> {
  const raw: unknown = await ky.get('/api/approval/pending', {
    headers: accessHeaders(),
    signal,
    retry: 1,
    timeout: 10_000,
  }).json();
  return ApprovalListResponseSchema.parse(raw).pending;
}

export async function resolveApproval(requestId: string, decision: ApprovalDecision): Promise<void> {
  const raw: unknown = await ky.post(`/api/approval/${encodeURIComponent(requestId)}/resolve`, {
    headers: accessHeaders(),
    json: { decision },
    retry: 0,
    timeout: 10_000,
  }).json();
  ApprovalResolveResponseSchema.parse(raw);
}

export async function fetchAlwaysAllowedGrants(signal: AbortSignal): Promise<readonly AlwaysAllowGrant[]> {
  const raw: unknown = await ky.get('/api/approval/always-allowed', {
    headers: accessHeaders(),
    signal,
    retry: 1,
    timeout: 10_000,
  }).json();
  return AlwaysAllowListResponseSchema.parse(raw).grants;
}

export async function resetAlwaysAllowed(): Promise<readonly string[]> {
  const raw: unknown = await ky.post('/api/approval/reset-always-allowed', {
    headers: accessHeaders(),
    retry: 0,
    timeout: 10_000,
  }).json();
  return ResetAlwaysAllowedResponseSchema.parse(raw).revoked;
}
