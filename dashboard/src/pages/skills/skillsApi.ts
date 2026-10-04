import { z } from 'zod';
import { apiRequestPath, isAuthRequiredError } from '../../api/client';

const optionalString = z.string().nullish().transform(value => value ?? undefined);
const SkillSchema = z.object({
  name: optionalString, id: optionalString, description: optionalString,
  source: optionalString, version: optionalString,
});
const MarketSkillSchema = z.object({
  name: z.string(), skill_name: optionalString, version: optionalString,
  is_loaded: z.boolean().optional(), mcp_server_id: optionalString,
});
const SearchSkillSchema = z.object({
  name: z.string(), skill_name: optionalString, version: z.string(),
  description: optionalString, keywords: z.array(z.string()).optional(), publisher: optionalString,
});
const ToolObjectSchema = z.object({
  name: optionalString, function: z.object({ name: optionalString }).optional(),
});
const ToolsSchema = z.union([z.array(z.string()), z.array(ToolObjectSchema)]);
const McpSchema = z.object({
  name: optionalString, server_name: optionalString, description: optionalString,
  status: optionalString, skill_name: optionalString, transport: optionalString,
  tools: ToolsSchema.optional(), available_tools: ToolsSchema.optional(),
});
const EnvelopeSchema = z.object({ ok: z.boolean(), error: z.string().optional() });
const SkillsSchema = z.object({ skills: z.array(SkillSchema) });
const InstalledSchema = z.object({ installed: z.array(MarketSkillSchema) });
const McpListSchema = z.object({ servers: z.array(McpSchema) });
const SearchSchema = z.object({ results: z.array(SearchSkillSchema) });

class SkillsRequestError extends Error {
  readonly name = 'SkillsRequestError';
  constructor() { super('스킬 API가 요청을 완료하지 못했습니다.'); }
}

async function request(path: string, body?: Readonly<Record<string, string>>): Promise<unknown> {
  const raw = await apiRequestPath(path, body ? { method: 'POST', body: JSON.stringify(body) } : {});
  const envelope = EnvelopeSchema.parse(raw);
  if (!envelope.ok) throw new SkillsRequestError();
  return raw;
}

export async function loadSkills() {
  return SkillsSchema.parse(await request('/api/system/skills')).skills;
}

export async function loadInstalledSkills() {
  return InstalledSchema.parse(await request('/api/system/skills/installed')).installed;
}

export async function loadMcpSkills() {
  return McpListSchema.parse(await request('/api/system/skills/mcp')).servers;
}

export async function searchSkills(query: string, limit = 20) {
  return SearchSchema.parse(await request(`/api/system/skills/search?q=${encodeURIComponent(query)}&limit=${limit}`)).results;
}

export async function installSkill(packageName: string): Promise<void> {
  await request('/api/system/skills/install', { package_name: packageName });
}

export async function removeSkill(skillName: string): Promise<void> {
  await request('/api/system/skills/remove', { skill_name: skillName });
}

export function skillsErrorMessage(error: unknown): string {
  if (isAuthRequiredError(error)) return 'PIN 인증이 필요합니다. 잠금을 해제한 뒤 다시 시도하세요.';
  if (error instanceof SkillsRequestError) return error.message;
  if (error instanceof z.ZodError) return '스킬 API 응답 형식을 확인할 수 없습니다. 다시 시도하세요.';
  if (error instanceof Error) return '스킬 요청에 실패했습니다. 연결을 확인한 뒤 다시 시도하세요.';
  return '스킬 요청을 완료하지 못했습니다. 다시 시도하세요.';
}
