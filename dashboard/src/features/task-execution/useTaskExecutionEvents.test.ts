/**
 * F-39 계약 — **서버를 잃었다가 되찾으면 목록을 다시 읽는다.**
 *
 * 무엇을 재는가
 * -------------
 * `useTaskExecutionEvents` 는 서버의 두 자료를 묶는다: **목록**(한 번 읽은 스냅샷 — 그 안에
 * `status`·`execution_owner`·`resumable` 처럼 시간에 따라 변하는 값이 들어 있다)과 **스트림**(선택한
 * 태스크의 이벤트, 스스로 다시 붙는다). 스트림이 다시 붙어도 목록이 새로워지지 않으면 화면은
 * **낡은 스냅샷을 현재라고 말하면서** 연결됨을 표시한다 — 실물 증인
 * `dashboard/e2e/tests/cr14-crash-restart-surface.spec.ts` 가 그 상태를 쟀다(고침 전: 화면은
 * `running`·재개 없음, 서버는 `dead`·재개 가능, 연결은 `연결됨`).
 *
 * 이 파일은 그 규칙을 **단위로** 고정한다(실 브라우저 증인은 느리고, 이 규칙은 여기서 자란다):
 *   ① 재연결 뒤 목록을 다시 읽는다        — 고침의 본체
 *   ② 스트림이 실패하지 않으면 다시 읽지 않는다 — 거짓 양성 0(불필요한 재조회는 화면을 흔든다)
 *   ③ 다시 읽기가 실패하면 **조용히 넘기지 않는다** — 낡은 목록을 조용히 들고 있으면 그 병이 돌아온다
 *
 * 무엇을 재지 않는가
 * ------------------
 * - **서버의 진실**은 여기서 재지 않는다: 그 값이 무엇이어야 하는지는 실서버 계약(F-36 의
 *   `tests/test_cr14_task_orphan_surface.py`)과 실물 증인이 소유한다. 여기서 재는 것은 **언제
 *   다시 읽는가**이다.
 * - **실제 네트워크·프로세스**는 없다(그것은 e2e 증인의 몫이다).
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { TaskSummarySchema } from './taskExecutionSchema';
import { useProjectStore } from '../../stores/projectStore';

const api = vi.hoisted(() => ({
  fetchTaskList: vi.fn(),
  fetchTaskEvents: vi.fn(),
  streamTaskEvents: vi.fn(),
  submitTask: vi.fn(),
  cancelTask: vi.fn(),
  resumeTask: vi.fn(),
  forkTask: vi.fn(),
  isTaskOperationRetryable: vi.fn(() => true),
}));

vi.mock('./taskExecutionApi', () => api);

const { useTaskExecutionEvents } = await import('./useTaskExecutionEvents');

/** 서버가 주는 모양 그대로 만든다 — 스키마가 소유하는 규칙(브랜드·기본값)을 우회하지 않는다. */
function summary(executionOwner: 'live' | 'dead', resumable: boolean) {
  return TaskSummarySchema.parse({
    task_id: 'task-1',
    prompt: 'cr14-f39-unit-witness',
    status: 'running',
    error: null,
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-01T00:00:00+00:00',
    execution_owner: executionOwner,
    resumable,
  });
}

const LIVE = summary('live', false);
const ORPHANED = summary('dead', true);

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  api.fetchTaskList.mockReset();
  api.fetchTaskEvents.mockReset();
  api.streamTaskEvents.mockReset();
  api.submitTask.mockReset();
  api.cancelTask.mockReset();
  api.resumeTask.mockReset();
  api.forkTask.mockReset();
  api.fetchTaskEvents.mockResolvedValue({ events: [], lastSequence: 0 });
  useProjectStore.setState({
    activeProjectId: 'project-a',
    activeProjectName: 'Project A',
    activeProjectPath: '/tmp/project-a',
    projectRevision: 1,
    switchEpoch: 1,
  });
});

describe('useTaskExecutionEvents — idempotent task operation retry', () => {
  it('reuses the original submit operation after an ambiguous response loss and selects the server task', async () => {
    // Given: the server might have committed the first POST, but its response never reaches the browser.
    const committedTask = TaskSummarySchema.parse({
      task_id: 'task-committed-once', prompt: 'compile the project', status: 'pending', error: null,
      created_at: '2026-10-03T00:00:00Z', updated_at: '2026-10-03T00:00:00Z',
    });
    api.fetchTaskList.mockResolvedValueOnce([]).mockResolvedValueOnce([committedTask]);
    api.submitTask
      .mockRejectedValueOnce(new TypeError('network response lost'))
      .mockResolvedValueOnce(committedTask.task_id);

    const { result } = renderHook(() => useTaskExecutionEvents());

    // When: the user submits, then explicitly retries the unresolved operation.
    act(() => result.current.submit({ prompt: 'compile the project', input: 'compile the project', generation: 1 }));
    await waitFor(() => expect(result.current.failedTaskOperation?.kind).toBe('submit'));
    const original = api.submitTask.mock.calls[0]?.[0];
    act(() => result.current.retryTaskOperation());

    // Then: exactly the immutable first request is retried and its authoritative task is selected.
    await waitFor(() => expect(result.current.selectedTaskId).toBe(committedTask.task_id));
    expect(api.submitTask).toHaveBeenCalledTimes(2);
    expect(api.submitTask.mock.calls[1]?.[0]).toBe(original);
    expect(result.current.failedTaskOperation).toBeNull();
    expect(result.current.completedSubmitDraft).toEqual({ prompt: 'compile the project', input: 'compile the project', generation: 1 });
  });

  it('uses a fresh key for a later submit, blocks duplicate pending clicks, and preserves the unresolved first operation', async () => {
    // Given: the first operation has an ambiguous result, then a separate user action starts.
    api.fetchTaskList.mockResolvedValue([]);
    api.submitTask
      .mockRejectedValueOnce(new TypeError('connection reset'))
      .mockRejectedValueOnce(new TypeError('connection reset again'));
    const { result } = renderHook(() => useTaskExecutionEvents());

    // When: a duplicate click occurs while creation is pending, followed by a new prompt after failure.
    act(() => {
      result.current.submit({ prompt: 'first task', input: 'first task', generation: 1 });
      result.current.submit({ prompt: 'first task', input: 'first task', generation: 1 });
    });
    await waitFor(() => expect(result.current.failedTaskOperation?.kind).toBe('submit'));
    const first = api.submitTask.mock.calls[0]?.[0];
    act(() => result.current.submit({ prompt: 'second task', input: 'second task', generation: 2 }));
    await waitFor(() => expect(api.submitTask).toHaveBeenCalledTimes(2));
    const second = api.submitTask.mock.calls[1]?.[0];

    // Then: only one pending click posted, and the later intent has a distinct idempotency key.
    expect(first).toBeDefined();
    expect(second).toBeDefined();
    expect(second.idempotencyKey).not.toBe(first.idempotencyKey);
    expect(second.draft.prompt).toBe('second task');
  });

  it('reuses the original fork operation after an ambiguous response loss', async () => {
    // Given: the fork endpoint committed before its first response was lost.
    const forkedTask = TaskSummarySchema.parse({
      task_id: 'task-forked-once', prompt: 'cr14-f39-unit-witness', status: 'pending', error: null,
      created_at: '2026-10-03T00:00:00Z', updated_at: '2026-10-03T00:00:00Z',
    });
    api.fetchTaskList.mockResolvedValueOnce([LIVE]).mockResolvedValueOnce([LIVE, forkedTask]);
    api.forkTask
      .mockRejectedValueOnce(new TypeError('connection closed'))
      .mockResolvedValueOnce(forkedTask.task_id);
    const { result } = renderHook(() => useTaskExecutionEvents());

    // When: the user forks and explicitly retries the unresolved operation.
    act(() => result.current.fork(LIVE.task_id));
    await waitFor(() => expect(result.current.failedTaskOperation?.kind).toBe('fork'));
    const original = api.forkTask.mock.calls[0]?.[0];
    act(() => result.current.retryTaskOperation());

    // Then: the source and key remain identical, so the server returns the original fork.
    await waitFor(() => expect(result.current.selectedTaskId).toBe(forkedTask.task_id));
    expect(api.forkTask).toHaveBeenCalledTimes(2);
    expect(api.forkTask.mock.calls[1]?.[0]).toBe(original);
    expect(result.current.completedSubmitDraft).toBeNull();
  });

  it('discards an unresolved operation after a project switch instead of retrying it in the new scope', async () => {
    // Given: a submit result is ambiguous in project A.
    api.fetchTaskList.mockResolvedValue([]);
    api.submitTask.mockRejectedValueOnce(new TypeError('network response lost'));
    const { result } = renderHook(() => useTaskExecutionEvents());
    act(() => result.current.submit({ prompt: 'project A task', input: 'project A task', generation: 1 }));
    await waitFor(() => expect(result.current.failedTaskOperation).not.toBeNull());

    // When: the active project changes before the user presses retry.
    useProjectStore.setState({
      activeProjectId: 'project-b', activeProjectName: 'Project B', activeProjectPath: '/tmp/project-b',
      projectRevision: 1, switchEpoch: 2,
    });
    act(() => result.current.retryTaskOperation());

    // Then: no retry crosses project scope, and the stale retry target is removed.
    await waitFor(() => expect(result.current.failedTaskOperation).toBeNull());
    expect(api.submitTask).toHaveBeenCalledTimes(1);
  });

  it('does not post a newly created operation when the project changes during scope capture', async () => {
    api.fetchTaskList.mockResolvedValue([]);
    const { result } = renderHook(() => useTaskExecutionEvents());

    act(() => {
      result.current.submit({ prompt: 'project A task', input: 'project A task', generation: 1 });
      useProjectStore.setState({
        activeProjectId: 'project-b', activeProjectName: 'Project B', activeProjectPath: '/tmp/project-b',
        projectRevision: 1, switchEpoch: 2,
      });
    });

    await waitFor(() => expect(result.current.pendingAction).toBeNull());
    expect(api.submitTask).not.toHaveBeenCalled();
  });

  it('does not post when identity changes while scope verification awaits the owner fingerprint', async () => {
    api.fetchTaskList.mockResolvedValue([]);
    const nativeDigest = crypto.subtle.digest.bind(crypto.subtle);
    let digestCalls = 0;
    let releaseFingerprint: (() => void) | null = null;
    vi.spyOn(crypto.subtle, 'digest').mockImplementation((algorithm, data) => {
      digestCalls += 1;
      const digest = nativeDigest(algorithm, data);
      if (digestCalls === 1) return digest;
      return new Promise<ArrayBuffer>((resolve, reject) => {
        releaseFingerprint = () => { void digest.then(resolve, reject); };
      });
    });
    const { result } = renderHook(() => useTaskExecutionEvents());

    act(() => result.current.submit({ prompt: 'project A task', input: 'project A task', generation: 1 }));
    await waitFor(() => expect(releaseFingerprint).not.toBeNull());
    act(() => {
      useProjectStore.setState({
        activeProjectId: 'project-b', activeProjectName: 'Project B', activeProjectPath: '/tmp/project-b',
        projectRevision: 1, switchEpoch: 2,
      });
      releaseFingerprint?.();
    });

    await waitFor(() => expect(result.current.pendingAction).toBeNull());
    expect(api.submitTask).not.toHaveBeenCalled();
  });

  it('does not post when the authenticated owner changes while scope verification awaits the owner fingerprint', async () => {
    api.fetchTaskList.mockResolvedValue([]);
    window.sessionStorage.setItem('ag_access_token', 'owner-a-token');
    const nativeDigest = crypto.subtle.digest.bind(crypto.subtle);
    let digestCalls = 0;
    let releaseFingerprint: (() => void) | null = null;
    vi.spyOn(crypto.subtle, 'digest').mockImplementation((algorithm, data) => {
      digestCalls += 1;
      const digest = nativeDigest(algorithm, data);
      if (digestCalls === 1) return digest;
      return new Promise<ArrayBuffer>((resolve, reject) => {
        releaseFingerprint = () => { void digest.then(resolve, reject); };
      });
    });
    const { result } = renderHook(() => useTaskExecutionEvents());

    act(() => result.current.submit({ prompt: 'owner task', input: 'owner task', generation: 1 }));
    await waitFor(() => expect(releaseFingerprint).not.toBeNull());
    act(() => {
      window.sessionStorage.setItem('ag_access_token', 'owner-b-token');
      releaseFingerprint?.();
    });

    await waitFor(() => expect(result.current.pendingAction).toBeNull());
    expect(api.submitTask).not.toHaveBeenCalled();
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useTaskExecutionEvents — 재연결 뒤 목록', () => {
  it('스트림이 끊겼다가 다시 붙으면 목록을 다시 읽고 새 사실을 반영한다', async () => {
    api.fetchTaskList.mockResolvedValueOnce([LIVE]).mockResolvedValueOnce([ORPHANED]);
    api.streamTaskEvents
      .mockRejectedValueOnce(new Error('스트림이 끊겼다'))
      .mockResolvedValueOnce({ lastSequence: 0 });

    const { result } = renderHook(() => useTaskExecutionEvents());

    await waitFor(() => expect(result.current.tasks[0]?.execution_owner).toBe('dead'), {
      timeout: 5_000,
      interval: 50,
    });
    expect(api.fetchTaskList).toHaveBeenCalledTimes(2);
    // 목록을 다시 읽는 것은 **스트림을 다시 시작시키지 않는다** — 그렇지 않으면 재시작 루프가 된다.
    expect(api.streamTaskEvents).toHaveBeenCalledTimes(2);
    expect(result.current.tasks[0]?.resumable).toBe(true);
  });

  it('스트림이 끊기지 않으면 목록을 다시 읽지 않는다', async () => {
    api.fetchTaskList.mockResolvedValue([LIVE]);
    api.streamTaskEvents.mockResolvedValue({ lastSequence: 0 });

    const { result } = renderHook(() => useTaskExecutionEvents());
    await waitFor(() => expect(result.current.tasks).toHaveLength(1), { timeout: 5_000 });
    // 재연결 대기(`waitForReconnect`, 1초)보다 **더 오래** 기다린다: 잘못된 재조회가 있다면 그 안에
    // 드러난다. 연결 상태로 기다리지 않는 이유는 이 테스트가 **재조회 여부**를 재기 때문이다
    // (즉시 resolve 하는 mock 에서는 커밋 뒤의 `loading` 타이머가 상태를 덮어쓴다 — 그 타이머는
    // 실제 네트워크 왕복보다 먼저 도는 것이 정상이고, 그래서 이 파일은 상태 대신 **호출 수**를 잰다).
    await new Promise((resolve) => setTimeout(resolve, 1_500));
    expect(api.fetchTaskList).toHaveBeenCalledTimes(1);
    expect(api.streamTaskEvents).toHaveBeenCalledTimes(1);
  });

  it('목록을 다시 읽지 못하면 조용히 넘기지 않고 화면에 말한다', async () => {
    api.fetchTaskList
      .mockResolvedValueOnce([LIVE])
      .mockRejectedValueOnce(new Error('목록을 다시 읽지 못했다'));
    api.streamTaskEvents
      .mockRejectedValueOnce(new Error('스트림이 끊겼다'))
      .mockResolvedValueOnce({ lastSequence: 0 });

    const { result } = renderHook(() => useTaskExecutionEvents());

    await waitFor(() => expect(result.current.error).toBe('목록을 다시 읽지 못했다'), {
      timeout: 5_000,
      interval: 50,
    });
    // 낡은 목록을 조용히 들고 있지 않다 = 그 사실이 화면의 상태로 드러난다.
    expect(result.current.tasks[0]?.execution_owner).toBe('live');
  });
});

/**
 * F-41 계약 — **사용자의 탈출구(`retry`)는 스스로 포기한 화면을 되살린다.**
 *
 * 무엇을 재는가
 * -------------
 * 자동 재연결이 3회를 다 쓰고 포기하면 화면은 `연결 오류` + '다시 연결'을 내놓는다. 그 버튼이 하는
 * 일은 `retry()` 이고, 그 안은 `reloadVersion` 을 올리는 **한 줄**이다 — 그러므로 이 경로의 정직함은
 * `reloadVersion` 이 **목록 이펙트의 의존성이라는 사실**에 얹혀 있다. 그 사실은 지금까지 어떤 계약도
 * 재지 않았다(실 브라우저 증인 `dashboard/e2e/tests/cr14-retry-escape-hatch.spec.ts` 가 그 경로를
 * 제품에서 재지만, 게이트는 그 증인을 돌리지 않는다 — 경계 문서 §2-7).
 *
 *   ① 탈출구는 목록을 **다시 읽는다** — 크래시 전 스냅샷을 현재라고 말하지 않는다
 *   ② 탈출구는 스트림도 **다시 시작한다** — 다시 읽은 목록이 곧 낡아질 수 있으므로 한쪽만 되살리면 안 된다
 *
 * 라벨(`연결 오류` → `연결됨`)은 여기서 재지 않는다: 즉시 resolve 하는 스텁에서는 커밋 뒤의 `loading`
 * 타이머가 정착 상태를 덮어쓴다(같은 파일의 F-39 계약이 그 이유를 적는다). 실서버·실브라우저에서
 * 그 전이를 재는 곳은 `dashboard/e2e/tests/cr14-retry-escape-hatch.spec.ts` 다.
 *
 * 무엇을 재지 않는가
 * ------------------
 * - **실제 네트워크·프로세스·브라우저**는 없다(그것은 e2e 증인의 몫이다).
 * - 자동 재연결의 **횟수 정책**(3회)은 위 F-39 계약이 아니라 제품 코드가 소유한다 — 이 파일은
 *   "포기한 뒤"의 일만 잰다.
 */
describe('useTaskExecutionEvents — 탈출구(retry)', () => {
  it(
    '포기한 화면의 탈출구가 목록을 다시 읽고 스트림도 되살린다',
    async () => {
      // 실물 크래시를 그대로 옮긴다: 서버가 없는 동안 **목록 재조회도 실패**하므로, 화면은 포기할 때
      // **크래시 전 스냅샷**을 들고 있다(그것이 탈출구가 고쳐야 할 대상이다). 탈출구 뒤의 읽기만 성공한다.
      api.fetchTaskList
        .mockResolvedValueOnce([LIVE])
        .mockRejectedValueOnce(new Error('목록을 다시 읽지 못했다'))
        .mockRejectedValueOnce(new Error('목록을 다시 읽지 못했다'))
        .mockResolvedValue([ORPHANED]);
      // 자동 재연결 3회를 모두 실패시켜 **포기** 상태를 만든다(그 뒤의 호출은 성공한다).
      api.streamTaskEvents
        .mockRejectedValueOnce(new Error('서버가 없다'))
        .mockRejectedValueOnce(new Error('서버가 없다'))
        .mockRejectedValueOnce(new Error('서버가 없다'))
        .mockResolvedValue({ lastSequence: 0 });

      const { result } = renderHook(() => useTaskExecutionEvents());

      await waitFor(() => expect(result.current.connectionState).toBe('error'), {
        timeout: 20_000,
        interval: 50,
      });
      const listReadsWhileBroken = api.fetchTaskList.mock.calls.length;
      const streamStartsWhileBroken = api.streamTaskEvents.mock.calls.length;
      // 포기한 시점의 화면은 **크래시 전 스냅샷**이다(그것이 탈출구가 고쳐야 할 대상이다).
      expect(result.current.tasks[0]?.execution_owner).toBe('live');
      expect(result.current.tasks[0]?.resumable).toBe(false);

      act(() => result.current.retry());

      await waitFor(() => expect(result.current.tasks[0]?.execution_owner).toBe('dead'), {
        timeout: 10_000,
        interval: 50,
      });
      expect(result.current.tasks[0]?.resumable).toBe(true);
      expect(api.fetchTaskList.mock.calls.length).toBeGreaterThan(listReadsWhileBroken);
      expect(api.streamTaskEvents.mock.calls.length).toBeGreaterThan(streamStartsWhileBroken);
      // 연결 **라벨**은 여기서 재지 않는다 — 즉시 resolve 하는 스텁에서는 커밋 뒤의 `loading`
      // 타이머가 정착 상태를 덮어쓴다(위 F-39 계약의 두 번째 테스트가 같은 이유를 적는다).
      // 라벨이 실제로 되돌아오는지는 실서버·실브라우저 증인이 잰다: 그것이 이 attempt 의 증인이다.
    },
    30_000,
  );
});
