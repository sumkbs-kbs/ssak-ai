import { z } from 'zod';

export const TaskIdSchema = z.string().min(1).brand<'TaskId'>();
export const AgentIdSchema = z.string().min(1).brand<'AgentId'>();
export const StepIdSchema = z.string().min(1).brand<'StepId'>();
export const ToolCallIdSchema = z.string().min(1).brand<'ToolCallId'>();
export const TaskStatusSchema = z.enum([
  'pending',
  'running',
  'resuming',
  'done',
  'failed',
  'paused',
  'cancelled',
]);

export const TaskSequenceScopeSchema = z.enum(['task', 'global']);
export type TaskSequenceScope = z.infer<typeof TaskSequenceScopeSchema>;

export const TaskEventSchema = z.object({
  sequence_scope: TaskSequenceScopeSchema.optional(),
  sequence: z.number().int().nonnegative(),
  schema_version: z.number().int().positive(),
  task_id: TaskIdSchema,
  step_id: StepIdSchema.nullable(),
  agent_id: AgentIdSchema.nullable(),
  parent_id: AgentIdSchema.nullable(),
  tool_call_id: ToolCallIdSchema.nullable(),
  approval_id: z.string().min(1).nullable(),
  resource_job_id: z.string().min(1).nullable(),
  correlation_id: z.string().min(1).nullable(),
  event_type: z.string().min(1),
  payload: z.json(),
  created_at: z.string().min(1),
}).readonly();

export const TaskEventsResponseSchema = z.object({
  sequence_scope: TaskSequenceScopeSchema.optional(),
  task_id: TaskIdSchema,
  events: z.array(TaskEventSchema).readonly(),
  last_sequence: z.number().int().nonnegative(),
  has_more: z.boolean(),
}).readonly();

/**
 * 소유 사실 — F-36: `running` 행의 **실행 주인이 지금 살아 있는가**.
 *
 * `live` 는 그 프로세스가 실행 중이라는 뜻이고, `dead` 는 크래시·재시작으로 주인이 사라졌다는
 * 뜻이다(행은 여전히 `running` 이다 — 저장된 상태는 정책이라 바꾸지 않는다). 서버가 보내지
 * 않으면 `undefined` 이며, 그때는 예전 상태 규칙으로 되돌아간다(`taskLifecycleActions`).
 */
export const ExecutionOwnerSchema = z.enum(['live', 'dead', 'none']);

export const TaskSummarySchema = z.object({
  task_id: TaskIdSchema,
  prompt: z.string(),
  status: TaskStatusSchema,
  output: z.string().optional().default(''),
  error: z.string().nullable(),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  completed_at: z.string().nullable().optional().default(null),
  execution_owner: ExecutionOwnerSchema.optional(),
  resumable: z.boolean().optional(),
}).readonly();

export const TaskListResponseSchema = z.object({
  status: z.literal('ok'),
  data: z.array(TaskSummarySchema).readonly(),
}).readonly();

export const TaskStreamEndSchema = z.object({
  sequence_scope: TaskSequenceScopeSchema.optional(),
  task_id: TaskIdSchema,
  last_sequence: z.number().int().nonnegative(),
  status: z.string().min(1),
}).readonly();

export const TaskSubmitResponseSchema = z.object({
  status: z.literal('submitted'),
  task_id: TaskIdSchema,
}).readonly();

export const TaskForkResponseSchema = z.object({
  status: z.literal('forked'),
  task_id: TaskIdSchema,
  source_task_id: TaskIdSchema,
}).readonly();

export const TaskActionResponseSchema = z.object({
  status: z.enum(['cancelled', 'resumed']),
  task_id: TaskIdSchema,
}).readonly();

export type TaskId = z.infer<typeof TaskIdSchema>;
export type AgentId = z.infer<typeof AgentIdSchema>;
export type StepId = z.infer<typeof StepIdSchema>;
export type TaskEvent = z.infer<typeof TaskEventSchema>;
export type TaskSummary = z.infer<typeof TaskSummarySchema>;
export type TaskStatus = z.infer<typeof TaskStatusSchema>;
export type JsonValue = z.infer<ReturnType<typeof z.json>>;
