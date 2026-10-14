import { describe, expect, it } from 'vitest';

import {
  compactTaskEventReplica,
  mergeTaskEventReplica,
  readTaskEventReplicaCache,
  replaceTaskEventReplica,
  TaskEventReplicaConflictError,
  writeTaskEventReplicaCache,
} from './taskEventReplica';
import { TaskEventSchema, TaskIdSchema, type TaskEvent } from './taskExecutionSchema';

const taskId = TaskIdSchema.parse('task-replica');

function event(sequence: number, payload: string = `event-${sequence}`): TaskEvent {
  return TaskEventSchema.parse({
    sequence,
    schema_version: 2,
    task_id: taskId,
    step_id: null,
    agent_id: null,
    parent_id: null,
    tool_call_id: null,
    approval_id: null,
    resource_job_id: null,
    correlation_id: null,
    event_type: 'task.progress',
    payload: { payload },
    created_at: '2026-09-01T00:00:00Z',
  });
}

describe('task event replica', () => {
  it('advances a task-filtered global cursor across other tasks without a false gap', () => {
    const globalEvent = (sequence: number): TaskEvent => TaskEventSchema.parse({
      ...event(sequence), sequence_scope: 'global',
    });
    const initial = replaceTaskEventReplica(taskId, [globalEvent(24), globalEvent(27)], 27, 'global');
    const result = mergeTaskEventReplica(initial, [globalEvent(35)]);
    expect(result.contiguousSequence).toBe(35);
    expect(result.gap).toBeNull();
    expect(result.events.map((item) => item.sequence)).toEqual([24, 27, 35]);
  });

  it('keeps an unseen global terminal cursor incomplete until replay supplies it', () => {
    const initial = replaceTaskEventReplica(taskId, [event(24)], 35, 'global');
    expect(initial.contiguousSequence).toBe(24);
    expect(initial.gap).toEqual({ from: 25, to: 35 });
    const result = mergeTaskEventReplica(initial, [event(35)]);
    expect(result.gap).toBeNull();
  });

  it('preserves global scope when cached and still rejects conflicting event payloads', () => {
    const initial = replaceTaskEventReplica(taskId, [event(24), event(35)], 35, 'global');
    writeTaskEventReplicaCache(initial);
    const restored = readTaskEventReplicaCache(taskId);
    expect(restored?.contiguousSequence).toBe(35);
    expect(restored?.sequenceScope).toBe('global');
    expect(() => mergeTaskEventReplica(initial, [event(35, 'conflict')])).toThrow(TaskEventReplicaConflictError);
  });

  it('deduplicates replay overlap without changing event order', () => {
    // Given: the replica has the first two authoritative events.
    const initial = replaceTaskEventReplica(taskId, [event(1), event(2)], 2);

    // When: a replay page overlaps sequence 2 and adds sequence 3.
    const result = mergeTaskEventReplica(initial, [event(2), event(3)]);

    // Then: each sequence appears once and the contiguous cursor advances.
    expect(result.events.map((item) => item.sequence)).toEqual([1, 2, 3]);
    expect(result.contiguousSequence).toBe(3);
    expect(result.gap).toBeNull();
  });

  it('records a gap and clears it when the missing replay arrives', () => {
    // Given: the live stream delivered sequence 3 after sequence 1.
    const initial = replaceTaskEventReplica(taskId, [event(1)], 1);
    const withGap = mergeTaskEventReplica(initial, [event(3)]);

    // When: the authoritative replay supplies the missing sequence 2.
    const recovered = mergeTaskEventReplica(withGap, [event(2)]);

    // Then: the replica exposes the gap first, then recovers a contiguous cursor.
    expect(withGap.contiguousSequence).toBe(1);
    expect(withGap.gap).toEqual({ from: 2, to: 3 });
    expect(recovered.contiguousSequence).toBe(3);
    expect(recovered.gap).toBeNull();
  });

  it('rejects conflicting payloads for the same sequence', () => {
    // Given: an existing event at sequence 4.
    const initial = replaceTaskEventReplica(taskId, [event(4)], 4);

    // When: a different event attempts to reuse sequence 4.
    const conflicting = event(4, 'different-payload');

    // Then: the conflict is surfaced as a typed replica error.
    expect(() => mergeTaskEventReplica(initial, [conflicting])).toThrow(TaskEventReplicaConflictError);
  });

  it('compacts old events behind a generated snapshot boundary', () => {
    // Given: the replica has five retained events.
    const initial = replaceTaskEventReplica(taskId, [1, 2, 3, 4, 5].map((sequence) => event(sequence)), 5);

    // When: local cache compaction keeps only the newest three events.
    const result = compactTaskEventReplica(initial, 3);

    // Then: the snapshot boundary covers discarded history without a false gap.
    expect(result.events.map((item) => item.sequence)).toEqual([3, 4, 5]);
    expect(result.snapshotSequence).toBe(2);
    expect(result.contiguousSequence).toBe(5);
    expect(result.gap).toBeNull();
  });

  it('round-trips a compacted snapshot through local cache storage', () => {
    // Given: a compacted replica and an isolated browser storage namespace.
    const storage = window.localStorage;
    storage.clear();
    const initial = compactTaskEventReplica(
      replaceTaskEventReplica(taskId, [1, 2, 3].map((sequence) => event(sequence)), 3),
      2,
    );

    // When: the snapshot is written and read from localStorage.
    writeTaskEventReplicaCache(initial, storage);
    const result = readTaskEventReplicaCache(taskId, storage);

    // Then: the typed cache preserves the bounded timeline and cursors.
    expect(result?.events.map((item) => item.sequence)).toEqual([2, 3]);
    expect(result?.snapshotSequence).toBe(1);
    expect(result?.contiguousSequence).toBe(3);
  });
});
