import ky, { HTTPError } from 'ky';

import {
  PROJECT_ID_HEADER,
  PROJECT_REVISION_HEADER,
  SESSION_ID_HEADER,
  createProjectIdentityHeaders,
  withProjectIdentityPayload,
} from '../../api/projectIdentity';

import {
  TaskEventSchema,
  TaskActionResponseSchema,
  TaskEventsResponseSchema,
  TaskForkResponseSchema,
  TaskListResponseSchema,
  TaskSubmitResponseSchema,
  TaskStreamEndSchema,
  type TaskEvent,
  type TaskId,
  type TaskSummary,
} from './taskExecutionSchema';
import type { TaskForkOperation, TaskSubmitOperation } from './taskOperation';

export type SseFrame = Readonly<{
  id: string | null;
  event: string | null;
  data: string;
}>;

export type ParsedSseChunk = Readonly<{
  frames: readonly SseFrame[];
  remainder: string;
}>;

export type TaskStreamResult = Readonly<{
  status: string;
  lastSequence: number;
}>;

type TaskStreamHandlers = Readonly<{
  onEvent: (event: TaskEvent) => void;
}>;

export class TaskEventStreamError extends Error {
  readonly code: 'missing-body' | 'invalid-event';

  constructor(code: 'missing-body' | 'invalid-event', message: string) {
    super(message);
    this.name = 'TaskEventStreamError';
    this.code = code;
  }
}

function accessHeaders(accept = 'application/json'): Headers {
  return createProjectIdentityHeaders({ Accept: accept });
}

function operationHeaders(
  operation: TaskSubmitOperation | TaskForkOperation,
  accept = 'application/json',
): Headers {
  const headers = new Headers({ Accept: accept });
  const { authorizationHeader, identity } = operation.scope;
  if (authorizationHeader !== null) headers.set('Authorization', authorizationHeader);
  headers.set(SESSION_ID_HEADER, identity.sessionId);
  if (identity.projectId !== null) headers.set(PROJECT_ID_HEADER, identity.projectId);
  if (identity.projectRevision !== null) headers.set(PROJECT_REVISION_HEADER, String(identity.projectRevision));
  return headers;
}

export function isTaskOperationRetryable(caught: unknown): boolean {
  return !(caught instanceof HTTPError) || caught.response.status >= 500;
}

export function parseSseChunk(input: string): ParsedSseChunk {
  const normalized = input.replaceAll('\r\n', '\n');
  const segments = normalized.split('\n\n');
  const remainder = segments.pop() ?? '';
  const frames: SseFrame[] = [];

  for (const segment of segments) {
    let id: string | null = null;
    let event: string | null = null;
    const data: string[] = [];
    for (const line of segment.split('\n')) {
      if (line.startsWith(':')) continue;
      const separator = line.indexOf(':');
      const field = separator < 0 ? line : line.slice(0, separator);
      const rawValue = separator < 0 ? '' : line.slice(separator + 1);
      const value = rawValue.startsWith(' ') ? rawValue.slice(1) : rawValue;
      if (field === 'id') id = value;
      else if (field === 'event') event = value;
      else if (field === 'data') data.push(value);
    }
    if (data.length > 0) frames.push({ id, event, data: data.join('\n') });
  }

  return { frames, remainder };
}

export async function fetchTaskList(signal: AbortSignal): Promise<readonly TaskSummary[]> {
  const raw: unknown = await ky.get('/api/tasks', {
    headers: accessHeaders(),
    signal,
    retry: 1,
    timeout: 10_000,
  }).json();
  return TaskListResponseSchema.parse(raw).data;
}

export async function submitTask(operation: TaskSubmitOperation): Promise<TaskId> {
  const raw: unknown = await ky.post('/api/tasks/submit', {
    headers: operationHeaders(operation),
    json: withProjectIdentityPayload({ prompt: operation.draft.prompt, idempotency_key: operation.idempotencyKey }, operation.scope.identity),
    retry: 0,
    timeout: 10_000,
  }).json();
  return TaskSubmitResponseSchema.parse(raw).task_id;
}

export async function forkTask(operation: TaskForkOperation): Promise<TaskId> {
  const raw: unknown = await ky.post(`/api/tasks/${encodeURIComponent(operation.sourceTaskId)}/fork`, {
    headers: operationHeaders(operation),
    json: { idempotency_key: operation.idempotencyKey },
    retry: 0,
    timeout: 10_000,
  }).json();
  return TaskForkResponseSchema.parse(raw).task_id;
}

/**
 * 거부된 취소/재개의 **이유**는 서버가 안다 — 화면이 "HTTP 409" 를 말하면 안 된다.
 *
 * F-35: 서버는 이제 소유자 없는 태스크와 **다른 살아 있는 프로세스가 실행 중인** 태스크를
 * 다른 응답으로 구분한다(404 대 409). 그 구분이 화면까지 오지 않으면 사용자는 "실패했다"만
 * 보고 무엇을 해야 하는지 모른다 — 그래서 서버의 `detail` 을 오류 메시지로 올린다.
 */
async function describeActionFailure(caught: unknown): Promise<unknown> {
  if (!(caught instanceof HTTPError)) return caught;
  const body = (await caught.response.json().catch(() => null)) as { detail?: unknown } | null;
  const detail = typeof body?.detail === 'string' ? body.detail.trim() : '';
  if (!detail) return caught;
  const error = new Error(detail);
  error.name = caught.name;
  return error;
}

async function performTaskAction(taskId: TaskId, action: 'cancel' | 'resume'): Promise<void> {
  try {
    const raw: unknown = await ky.post(`/api/tasks/${encodeURIComponent(taskId)}/${action}`, {
      headers: accessHeaders(),
      retry: 0,
      timeout: 10_000,
    }).json();
    TaskActionResponseSchema.parse(raw);
  } catch (caught: unknown) {
    throw await describeActionFailure(caught);
  }
}

export async function cancelTask(taskId: TaskId): Promise<void> {
  await performTaskAction(taskId, 'cancel');
}

export async function resumeTask(taskId: TaskId): Promise<void> {
  await performTaskAction(taskId, 'resume');
}

export async function fetchTaskEvents(
  taskId: TaskId,
  afterSequence: number,
  signal: AbortSignal,
): Promise<Readonly<{ events: readonly TaskEvent[]; lastSequence: number }>> {
  const events: TaskEvent[] = [];
  let sequence = afterSequence;

  while (true) {
    const raw: unknown = await ky.get(`/api/tasks/${encodeURIComponent(taskId)}/events`, {
      headers: accessHeaders(),
      searchParams: { after_sequence: sequence, limit: 500 },
      signal,
      retry: 1,
      timeout: 10_000,
    }).json();
    const response = TaskEventsResponseSchema.parse(raw);
    events.push(...response.events);
    if (!response.has_more) {
      return { events, lastSequence: response.last_sequence };
    }
    if (response.last_sequence <= sequence) {
      throw new TaskEventStreamError('invalid-event', 'Task event replay cursor did not advance.');
    }
    sequence = response.last_sequence;
  }
}

function frameResult(frame: SseFrame): TaskStreamResult | TaskEvent {
  const raw: unknown = JSON.parse(frame.data);
  if (frame.event === 'stream.end') {
    const end = TaskStreamEndSchema.parse(raw);
    return { status: end.status, lastSequence: end.last_sequence };
  }
  return TaskEventSchema.parse(raw);
}

export async function streamTaskEvents(
  taskId: TaskId,
  afterSequence: number,
  signal: AbortSignal,
  handlers: TaskStreamHandlers,
): Promise<TaskStreamResult> {
  const response = await ky.get(`/api/tasks/${encodeURIComponent(taskId)}/events/stream`, {
    headers: accessHeaders('text/event-stream'),
    searchParams: { after_sequence: afterSequence },
    signal,
    retry: 0,
    timeout: false,
  });
  if (response.body === null) {
    throw new TaskEventStreamError('missing-body', 'Task event stream returned no response body.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const parsed = parseSseChunk(buffer);
    buffer = parsed.remainder;
    for (const frame of parsed.frames) {
      const item = frameResult(frame);
      if ('status' in item && 'lastSequence' in item) return item;
      handlers.onEvent(item);
    }
  }

  throw new TaskEventStreamError('invalid-event', 'Task event stream ended without a terminal frame.');
}
