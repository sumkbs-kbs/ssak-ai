import { beforeEach, describe, expect, it, vi } from 'vitest';

const getMock = vi.hoisted(() => vi.fn());

vi.mock('ky', () => ({
  default: {
    get: getMock,
  },
}));

import { fetchTaskEvents, parseSseChunk } from './taskExecutionApi';
import { TaskIdSchema } from './taskExecutionSchema';

const taskId = TaskIdSchema.parse('task-paged');

function event(sequence: number): Readonly<Record<string, unknown>> {
  return {
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
    payload: { sequence },
    created_at: '2026-09-01T00:00:00Z',
  };
}

beforeEach(() => {
  getMock.mockReset();
});

describe('parseSseChunk', () => {
  it('parses complete frames, ignores keep-alives, and retains an incomplete frame', () => {
    const result = parseSseChunk(
      ': keep-alive\n\n' +
        'id: 7\nevent: tool.completed\ndata: {"sequence":7}\n\n' +
        'id: 8\nevent: task.completed\ndata: {"sequence":8',
    );

    expect(result.frames).toEqual([
      { id: '7', event: 'tool.completed', data: '{"sequence":7}' },
    ]);
    expect(result.remainder).toBe('id: 8\nevent: task.completed\ndata: {"sequence":8');
  });

  it('joins multi-line data fields according to the event-stream format', () => {
    const result = parseSseChunk('event: task.event\ndata: first\ndata: second\n\n');

    expect(result.frames[0]?.data).toBe('first\nsecond');
    expect(result.remainder).toBe('');
  });
});

describe('fetchTaskEvents', () => {
  it('retains the declared global cursor scope on a sparse authoritative replay', async () => {
    getMock.mockReturnValueOnce({ json: async () => ({
      task_id: taskId, sequence_scope: 'global', events: [event(24), event(35)],
      last_sequence: 35, has_more: false,
    }) });
    const result = await fetchTaskEvents(taskId, 0, new AbortController().signal);
    expect(result.sequenceScope).toBe('global');
    expect(result.events.map((item) => item.sequence)).toEqual([24, 35]);
  });

  it('fetches every authoritative replay page before returning events', async () => {
    // Given: the server reports that the first replay page has more events.
    getMock
      .mockReturnValueOnce({
        json: async () => ({
          task_id: taskId,
          events: [event(501)],
          last_sequence: 501,
          has_more: true,
        }),
      })
      .mockReturnValueOnce({
        json: async () => ({
          task_id: taskId,
          events: [event(502)],
          last_sequence: 502,
          has_more: false,
        }),
      });

    // When: the dashboard catches up from the previous sequence.
    const result = await fetchTaskEvents(taskId, 500, new AbortController().signal);

    // Then: it returns both pages and advances the cursor for the second request.
    expect(result.events.map((item) => item.sequence)).toEqual([501, 502]);
    expect(result.lastSequence).toBe(502);
    expect(getMock).toHaveBeenCalledTimes(2);
    expect(getMock).toHaveBeenNthCalledWith(
      2,
      '/api/tasks/task-paged/events',
      expect.objectContaining({ searchParams: { after_sequence: 501, limit: 500 } }),
    );
  });
});
