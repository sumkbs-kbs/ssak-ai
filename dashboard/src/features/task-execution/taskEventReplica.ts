import { z } from 'zod';

import { TaskEventSchema, TaskIdSchema, TaskSequenceScopeSchema, type TaskEvent, type TaskId, type TaskSequenceScope } from './taskExecutionSchema';

export const TASK_EVENT_REPLICA_DEFAULT_LIMIT = 1_000;

export type TaskEventGap = Readonly<{
  from: number;
  to: number;
}>;

export type TaskEventReplicaState = Readonly<{
  sequenceScope: TaskSequenceScope;
  taskId: TaskId;
  events: readonly TaskEvent[];
  lastSequence: number;
  contiguousSequence: number;
  snapshotSequence: number;
  gap: TaskEventGap | null;
}>;

export class TaskEventReplicaConflictError extends Error {
  readonly name = 'TaskEventReplicaConflictError';

  constructor(readonly taskId: TaskId, readonly sequence: number) {
    super(`Conflicting task event at sequence ${sequence} for ${taskId}.`);
  }
}

export class TaskEventReplicaTaskMismatchError extends Error {
  readonly name = 'TaskEventReplicaTaskMismatchError';

  constructor(readonly expectedTaskId: TaskId, readonly actualTaskId: TaskId) {
    super(`Task event belongs to ${actualTaskId}, expected ${expectedTaskId}.`);
  }
}

const PersistedReplicaSchema = z.object({
  sequence_scope: TaskSequenceScopeSchema.optional().default('task'),
  task_id: TaskIdSchema,
  events: z.array(TaskEventSchema).readonly(),
  last_sequence: z.number().int().nonnegative(),
  contiguous_sequence: z.number().int().nonnegative(),
  snapshot_sequence: z.number().int().nonnegative(),
}).readonly();

function eventsEqual(left: TaskEvent, right: TaskEvent): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function normalizeEvents(taskId: TaskId, input: readonly TaskEvent[]): readonly TaskEvent[] {
  const bySequence = new Map<number, TaskEvent>();
  for (const event of input) {
    if (event.task_id !== taskId) throw new TaskEventReplicaTaskMismatchError(taskId, event.task_id);
    const previous = bySequence.get(event.sequence);
    if (previous !== undefined && !eventsEqual(previous, event)) {
      throw new TaskEventReplicaConflictError(taskId, event.sequence);
    }
    bySequence.set(event.sequence, event);
  }
  return [...bySequence.values()].sort((left, right) => left.sequence - right.sequence);
}

function contiguousSequence(events: readonly TaskEvent[], snapshotSequence: number): number {
  let contiguous = snapshotSequence;
  for (const event of events) {
    if (event.sequence <= contiguous) continue;
    if (event.sequence !== contiguous + 1) break;
    contiguous = event.sequence;
  }
  return contiguous;
}

function gapFor(lastSequence: number, contiguous: number): TaskEventGap | null {
  return lastSequence > contiguous ? { from: contiguous + 1, to: lastSequence } : null;
}

function stateFrom(
  taskId: TaskId,
  events: readonly TaskEvent[],
  lastSequence: number,
  snapshotSequence: number,
  sequenceScope: TaskSequenceScope,
): TaskEventReplicaState {
  const normalized = normalizeEvents(taskId, events);
  const effectiveLast = Math.max(lastSequence, normalized.at(-1)?.sequence ?? 0);
  const effectiveSnapshot = Math.min(snapshotSequence, effectiveLast);
  const contiguous = sequenceScope === 'global'
    ? Math.max(effectiveSnapshot, normalized.at(-1)?.sequence ?? 0)
    : contiguousSequence(normalized, effectiveSnapshot);
  return {
    sequenceScope,
    taskId,
    events: normalized,
    lastSequence: effectiveLast,
    contiguousSequence: contiguous,
    snapshotSequence: effectiveSnapshot,
    gap: gapFor(effectiveLast, contiguous),
  };
}

export function createTaskEventReplica(taskId: TaskId, snapshotSequence = 0): TaskEventReplicaState {
  return stateFrom(taskId, [], snapshotSequence, snapshotSequence, 'task');
}

export function replaceTaskEventReplica(
  taskId: TaskId,
  events: readonly TaskEvent[],
  lastSequence: number,
  sequenceScope: TaskSequenceScope = 'task',
): TaskEventReplicaState {
  const normalized = normalizeEvents(taskId, events);
  const effectiveLast = Math.max(lastSequence, normalized.at(-1)?.sequence ?? 0);
  const snapshotSequence = normalized.length === 0 ? effectiveLast : 0;
  return stateFrom(taskId, normalized, effectiveLast, snapshotSequence, sequenceScope);
}

export function mergeTaskEventReplica(
  current: TaskEventReplicaState,
  incoming: readonly TaskEvent[],
  lastSequence = current.lastSequence,
  sequenceScope = current.sequenceScope,
): TaskEventReplicaState {
  const merged = [...current.events, ...incoming];
  return stateFrom(current.taskId, merged, lastSequence, current.snapshotSequence, sequenceScope);
}

export function compactTaskEventReplica(
  current: TaskEventReplicaState,
  maxEvents = TASK_EVENT_REPLICA_DEFAULT_LIMIT,
): TaskEventReplicaState {
  if (!Number.isInteger(maxEvents) || maxEvents < 1) {
    throw new RangeError('Task event replica limit must be a positive integer.');
  }
  if (current.events.length <= maxEvents) return current;
  const retained = current.events.slice(-maxEvents);
  const firstRetained = retained[0];
  if (firstRetained === undefined) return current;
  const snapshotSequence = Math.max(current.snapshotSequence, firstRetained.sequence - 1);
  return stateFrom(current.taskId, retained, current.lastSequence, snapshotSequence, current.sequenceScope);
}

function cacheKey(taskId: TaskId): string {
  return `agk:task-event-replica:${encodeURIComponent(taskId)}`;
}

export function writeTaskEventReplicaCache(
  replica: TaskEventReplicaState,
  storage: Storage = window.localStorage,
): void {
  storage.setItem(cacheKey(replica.taskId), JSON.stringify({
    sequence_scope: replica.sequenceScope,
    task_id: replica.taskId,
    events: replica.events,
    last_sequence: replica.lastSequence,
    contiguous_sequence: replica.contiguousSequence,
    snapshot_sequence: replica.snapshotSequence,
  }));
}

export function readTaskEventReplicaCache(
  taskId: TaskId,
  storage: Storage = window.localStorage,
): TaskEventReplicaState | null {
  const raw = storage.getItem(cacheKey(taskId));
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    const persisted = PersistedReplicaSchema.safeParse(parsed);
    if (!persisted.success || persisted.data.task_id !== taskId) return null;
    return stateFrom(
      taskId,
      persisted.data.events,
      persisted.data.last_sequence,
      persisted.data.snapshot_sequence,
      persisted.data.sequence_scope,
    );
  } catch (error: unknown) {
    if (error instanceof SyntaxError) return null;
    throw error;
  }
}

export function clearTaskEventReplicaCache(
  taskId: TaskId,
  storage: Storage = window.localStorage,
): void {
  storage.removeItem(cacheKey(taskId));
}
