import { beforeEach, describe, expect, it, vi } from 'vitest';

const postMock = vi.hoisted(() => vi.fn());

vi.mock('ky', () => {
  class HTTPError extends Error {
    response: Response;

    constructor(response: Response) {
      super(`Request failed with status code ${response.status}`);
      this.name = 'HTTPError';
      this.response = response;
    }
  }

  return { default: { post: postMock }, HTTPError };
});

import { useProjectStore } from '../../stores/projectStore';
import { cancelTask, forkTask, isTaskOperationRetryable, resumeTask, submitTask } from './taskExecutionApi';
import { TaskIdSchema } from './taskExecutionSchema';
import { createTaskForkOperation, createTaskSubmitOperation } from './taskOperation';

const taskId = TaskIdSchema.parse('task-owned-elsewhere');

// 모킹된 모듈의 HTTPError 로 실패를 만든다 — 제품 코드는 `instanceof HTTPError` 로 분기한다.
const mockedKy = (await import('ky')) as unknown as {
  HTTPError: new (response: Response) => Error;
};

function httpFailure(status: number, body: unknown): Error {
  return new mockedKy.HTTPError(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    }),
  );
}

/** 제품 코드는 `ky.post(...).json()` 을 부른다 — 모의도 **그 형태**를 돌려줘야 한다. */
function postResult(json: () => Promise<unknown>): { json: () => Promise<unknown> } {
  return { json };
}

beforeEach(() => {
  postMock.mockReset();
  useProjectStore.setState({
    activeProjectId: 'project-a',
    activeProjectName: 'Project A',
    activeProjectPath: '/tmp/project-a',
    projectRevision: 7,
    switchEpoch: 7,
  });
});

describe('cancelTask failure reporting (F-35)', () => {
  it('resolves when the server cancels the task', async () => {
    postMock.mockReturnValue(postResult(() => Promise.resolve({ status: 'cancelled', task_id: taskId })));

    await expect(cancelTask(taskId)).resolves.toBeUndefined();
  });

  it("surfaces the server's reason when another live process owns the task", async () => {
    const detail = "Another live process owns this task's execution — cancel it there";
    postMock.mockReturnValue(postResult(() => Promise.reject(httpFailure(409, { detail }))));

    // 화면이 "HTTP 409" 가 아니라 **사유**를 말해야 사용자가 다음 행동을 알 수 있다.
    await expect(cancelTask(taskId)).rejects.toThrow(detail);
  });

  it('keeps the original failure when the server gives no reason', async () => {
    postMock.mockReturnValue(postResult(() => Promise.reject(httpFailure(500, {}))));

    await expect(cancelTask(taskId)).rejects.toThrow(/status code 500/);
  });

  it('keeps non-HTTP failures untouched', async () => {
    postMock.mockReturnValue(postResult(() => Promise.reject(new Error('network down'))));

    await expect(resumeTask(taskId)).rejects.toThrow('network down');
  });

  it('reuses an operation key and captured identity for a submit after the active project changes', async () => {
    postMock.mockReturnValue(postResult(() => Promise.resolve({ status: 'submitted', task_id: taskId })));
    window.sessionStorage.setItem('ag_access_token', 'owner-a-token');
    const operation = await createTaskSubmitOperation({ prompt: 'retain this exact request', input: 'retain this exact request', generation: 1 });
    window.sessionStorage.setItem('ag_access_token', 'owner-b-token');
    useProjectStore.setState({
      activeProjectId: 'project-b',
      activeProjectName: 'Project B',
      activeProjectPath: '/tmp/project-b',
      projectRevision: 8,
      switchEpoch: 8,
    });

    await expect(submitTask(operation)).resolves.toBe(taskId);

    expect(postMock).toHaveBeenCalledWith('/api/tasks/submit', expect.objectContaining({
      headers: expect.objectContaining({
        get: expect.any(Function),
      }),
      json: expect.objectContaining({
        prompt: 'retain this exact request',
        idempotency_key: operation.idempotencyKey,
        project_id: 'project-a',
        project_revision: 7,
      }),
    }));
    const options = postMock.mock.calls[0]?.[1];
    expect(options?.headers.get('X-AGK-Project-Id')).toBe('project-a');
    expect(options?.headers.get('X-AGK-Project-Revision')).toBe('7');
    expect(options?.headers.get('Authorization')).toBe('Bearer owner-a-token');
  });

  it('sends the same fork key with its immutable source task', async () => {
    postMock.mockReturnValue(postResult(() => Promise.resolve({ status: 'forked', task_id: taskId, source_task_id: taskId })));
    const operation = await createTaskForkOperation(taskId);

    await expect(forkTask(operation)).resolves.toBe(taskId);

    expect(postMock).toHaveBeenCalledWith(`/api/tasks/${taskId}/fork`, expect.objectContaining({
      json: { idempotency_key: operation.idempotencyKey },
    }));
  });

  it('does not offer retry for a server-confirmed API failure', () => {
    expect(isTaskOperationRetryable(httpFailure(422, { detail: 'invalid prompt' }))).toBe(false);
    expect(isTaskOperationRetryable(httpFailure(503, { detail: 'temporary outage' }))).toBe(true);
    expect(isTaskOperationRetryable(new TypeError('response lost'))).toBe(true);
  });
});
