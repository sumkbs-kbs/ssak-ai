import { z } from 'zod';
import { ApiHttpError, apiRequestPath, isAuthRequiredError } from '../../api/client';
import type { LocalSkill, PublishResult } from './types';

const LocalSkillSchema = z.object({
  name: z.string(), path: z.string(), source: z.enum(['market', 'local']),
  valid: z.boolean(), has_skill_md: z.boolean(), has_readme: z.boolean(),
  version: z.string(), tool_count: z.number().int().nonnegative(), warnings: z.array(z.string()),
});

const LocalSkillsResponseSchema = z.object({
  ok: z.boolean(), skills: z.array(LocalSkillSchema), error: z.string().optional(),
});

const OptionalPublishTextSchema = z.string().nullish().transform(value => value ?? undefined);
const PublishResultSchema = z.object({
  success: z.boolean(),
  action: z.enum(['npm_publish', 'github_pr', '']),
  skill_name: z.string(),
  package_name: OptionalPublishTextSchema, version: OptionalPublishTextSchema,
  npm_url: OptionalPublishTextSchema, pr_url: OptionalPublishTextSchema,
  errors: z.array(z.string()), warnings: z.array(z.string()), summary: z.string(),
});

const PublishResponseSchema = z.union([
  z.object({ ok: z.boolean(), publish_result: PublishResultSchema }),
  z.object({ ok: z.literal(false), error: z.string() }),
]);

const PUBLISH_ENDPOINTS = {
  npm: '/api/system/skills/publish-npm',
  github: '/api/system/skills/publish-github',
} as const;

type PublishSubmission = Readonly<{ skill_name: string; dry_run: boolean }> & (
  | Readonly<{ mode: 'npm'; tag: string }>
  | Readonly<{ mode: 'github'; repo: string; draft: boolean }>
);

class PublishResponseError extends Error {
  readonly name = 'PublishResponseError';
}

export async function fetchPublishableSkills(): Promise<LocalSkill[]> {
  const raw = await apiRequestPath('/api/system/skills/local', { suppressLog: true });
  const response = LocalSkillsResponseSchema.parse(raw);
  if (!response.ok) throw new PublishResponseError(response.error ?? '로컬 스킬 목록 요청이 실패했습니다.');
  return response.skills;
}

export async function submitSkillPublication(submission: PublishSubmission): Promise<PublishResult> {
  const { mode, ...body } = submission;
  const raw = await apiRequestPath(PUBLISH_ENDPOINTS[mode], {
    method: 'POST', body: JSON.stringify(body), suppressLog: true,
  });
  const response = PublishResponseSchema.parse(raw);
  if ('publish_result' in response) return response.publish_result;
  throw new PublishResponseError(response.error);
}

export function publishRequestErrorMessage(error: unknown): string {
  if (isAuthRequiredError(error)) return 'PIN 인증이 필요합니다. PIN 로그인 후 다시 시도하세요.';
  if (error instanceof ApiHttpError) return `스킬 요청이 실패했습니다 (HTTP ${error.status}). 다시 시도하세요.`;
  if (error instanceof z.ZodError || error instanceof SyntaxError) return '스킬 응답을 읽을 수 없습니다. 다시 시도하세요.';
  if (error instanceof PublishResponseError) return error.message;
  if (error instanceof Error) return '스킬 요청에 연결할 수 없습니다. 연결을 확인하고 다시 시도하세요.';
  return '스킬 요청이 실패했습니다. 다시 시도하세요.';
}
