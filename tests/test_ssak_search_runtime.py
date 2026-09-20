"""관리형 번들 검색 child 수명주기 계약 시험 (task 12).

계약은 **실제 자식 프로세스**에서만 잴 수 있다. 여기서 고정하는 것:

- 상태기계: disabled/stopped/starting/ready/degraded/failed/stopping 이 실측된 전이로 나타난다.
- **동시 첫 호출 10개 → child 1개**(single-flight). child 는 MCP SDK 의 stdio context 가 소유하고,
  이 런타임은 두 번째 `Popen` 을 만들지 않는다.
- **exit 관찰**: 준비된 child 가 조용히 죽으면 bounded 시간 안에 degraded 로 바뀌고 이유가 남는다.
- **crash loop 는 회로를 연다**: 시작 실패는 backoff(1/2/4초) 뒤 최대 3회, 그 뒤 circuit open.
  열린 회로는 즉시 거절하고, cooldown 이 지나면 trial 1회만 허용한다(무한 재spawn 금지).
- **비멱등 작업은 재시도하지 않는다**: `retry_on_transport=True` + `idempotent=False` 는 거절되고
  child 는 **한 번도 호출되지 않는다**(호출 횟수를 fixture 가 기록한다).
- **종료 후 child 0** + 우리가 만든 child 만 정리한다(남의 프로세스는 죽이지 않는다).
- 최소 env allowlist(비밀 미전달) · cwd 불변 · **artifact 불일치 fail-closed**.

fixture child 는 `tests/fixtures/ssak_search_child.py` — 표준 라이브러리만 쓰는 실제 stdio 서버다.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from antigravity_k.tools.mcp_tool_loader import MCPToolLoader
from antigravity_k.tools.mcp_tool_result import MCPToolOutcome
from antigravity_k.tools.ssak_search_runtime import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_ENV_ALLOWLIST,
    SearchRuntimeConfig,
    SearchRuntimeState,
    SsakSearchRuntime,
    get_ssak_search_runtime,
    runtime_config_from_env,
    shutdown_ssak_search_runtime,
    verify_bundled_artifact,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ssak_search_child.py"
HERMETIC_ARGS: tuple[str, ...] = ("-I", "-S")  # 사이트 패키지·환경 개입 없이 순수 stdlib child


# ── 도우미 ────────────────────────────────────────────────────────────────────


def make_config(record: Path, mode: str = "ok", **overrides: object) -> SearchRuntimeConfig:
    """fixture child 를 실행하는 설정(시험은 실제 프로세스를 쓴다)."""
    base: dict[str, object] = {
        "command": sys.executable,
        "args": (*HERMETIC_ARGS, str(FIXTURE), mode),
        "require_manifest": False,
        "extra_env": {"SSAK_CHILD_RECORD": str(record)},
        "monitor_interval_seconds": 0.05,
        "ready_timeout_seconds": 20.0,
        "call_timeout_seconds": 20.0,
        "backoff_seconds": (0.05, 0.05, 0.15),
        "max_start_attempts": 3,
    }
    base.update(overrides)
    return SearchRuntimeConfig(**base)  # type: ignore[arg-type]


@pytest.fixture
def runtimes(tmp_path: Path) -> Iterator[list[SsakSearchRuntime]]:
    """시험이 만든 런타임을 추적하고, 끝나면 **child 0** 을 확인한 뒤 정리한다."""
    created: list[SsakSearchRuntime] = []
    yield created
    for runtime in created:
        status = runtime.shutdown(timeout=20)
        assert status["child_pids"] == [], f"child 가 남았다: {status}"


def start(runtimes: list[SsakSearchRuntime], record: Path, mode: str = "ok", **overrides: object) -> SsakSearchRuntime:
    runtime = SsakSearchRuntime(make_config(record, mode, **overrides))
    runtimes.append(runtime)
    return runtime


def spawn_record(record: Path) -> dict[str, object]:
    return json.loads(record.read_text(encoding="utf-8"))


def recorded_calls(record: Path) -> list[dict[str, object]]:
    path = Path(f"{record}.calls")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def status_of(runtime: SsakSearchRuntime) -> dict[str, Any]:
    """`status()` 는 object 값의 스냅숏이다 — 시험에서는 Any 로 좁혀 읽는다."""
    return cast("dict[str, Any]", runtime.status())


def wait_for(predicate, timeout: float = 10.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ── 상태기계 · 비활성 ─────────────────────────────────────────────────────────


def test_state_machine_is_the_documented_set() -> None:
    assert {state.value for state in SearchRuntimeState} == {
        "disabled",
        "stopped",
        "starting",
        "ready",
        "degraded",
        "failed",
        "stopping",
    }
    assert SearchRuntimeState.READY.serves_tools is True
    assert SearchRuntimeState.DEGRADED.serves_tools is False
    assert SearchRuntimeState.FAILED.terminal is True


def test_disabled_runtime_spawns_nothing_and_fails_typed(runtimes: list[SsakSearchRuntime], tmp_path: Path) -> None:
    runtime = start(runtimes, tmp_path / "off.json", enabled=False)
    assert runtime.state is SearchRuntimeState.DISABLED
    out = runtime.call_tool("ssak_search", {"query": "x"})
    assert out.is_error is True
    assert out.error_code == "RUNTIME_DISABLED"
    assert status_of(runtime)["spawn_attempts"] == 0
    assert runtime.child_pids() == []


def test_runtime_config_reads_the_environment() -> None:
    off = runtime_config_from_env({"AGK_SEARCH_ENABLED": "false"})
    assert off.enabled is False
    on = runtime_config_from_env(
        {"AGK_SEARCH_ENABLED": "1", "AGK_SEARCH_ARTIFACT": "/tmp/a", "AGK_SEARCH_MANIFEST": "/tmp/m"}
    )
    assert (on.enabled, on.artifact_path, on.manifest_path) == (True, "/tmp/a", "/tmp/m")


# ── single-flight: 동시 첫 호출 ────────────────────────────────────────────────


def test_ten_concurrent_first_calls_produce_exactly_one_child(
    runtimes: list[SsakSearchRuntime], tmp_path: Path
) -> None:
    record = tmp_path / "concurrent.json"
    runtime = start(runtimes, record)
    errors: list[bool] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        out = runtime.call_tool("ssak_search", {"query": f"q{index}"})
        with lock:
            errors.append(out.is_error)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    status = status_of(runtime)
    assert errors == [False] * 10, f"동시 첫 호출 중 실패: {errors}"
    assert status["spawn_attempts"] == 1, status
    assert runtime.state is SearchRuntimeState.READY
    # fixture 가 스스로 기록한 PID 와 런타임이 관측한 PID 가 같아야 한다(child 는 하나).
    assert runtime.child_pids() == [spawn_record(record)["pid"]]


# ── 시작 실패: backoff → circuit open ────────────────────────────────────────


def test_start_failure_uses_the_real_backoff_then_opens_the_circuit(
    runtimes: list[SsakSearchRuntime], tmp_path: Path
) -> None:
    """계획의 기본 정책(1/2/4초·최대 3회)을 기본값 그대로 잰다."""
    record = tmp_path / "crash.json"
    runtime = start(
        runtimes,
        record,
        "crash_start",
        backoff_seconds=DEFAULT_BACKOFF_SECONDS,
        max_start_attempts=3,
    )
    started = time.monotonic()
    assert runtime.ensure_ready(timeout=30) is False
    elapsed = time.monotonic() - started

    status = status_of(runtime)
    assert status["state"] == "failed"
    assert status["circuit_open"] is True
    assert status["spawn_attempts"] == 3
    assert status["retry_waits_seconds"] == [1.0, 2.0]  # 3번째 시도 뒤에는 대기 없이 회로를 연다
    assert elapsed >= 3.0, f"backoff 가 실제로 걸리지 않았다: {elapsed:.2f}s"
    assert runtime.child_pids() == []

    # 열린 회로는 새 child 를 만들지 않고 즉시 거절한다.
    refuse_started = time.monotonic()
    assert runtime.ensure_ready(timeout=5) is False
    out = runtime.call_tool("ssak_search", {"query": "x"})
    assert time.monotonic() - refuse_started < 0.5
    assert out.is_error is True and out.error_code == "CIRCUIT_OPEN"
    assert status_of(runtime)["spawn_attempts"] == 3


def test_open_circuit_allows_exactly_one_trial_after_the_cooldown(
    runtimes: list[SsakSearchRuntime], tmp_path: Path
) -> None:
    record = tmp_path / "trial.json"
    runtime = start(runtimes, record, "crash_start", backoff_seconds=(0.02, 0.02, 0.2), max_start_attempts=3)
    assert runtime.ensure_ready(timeout=20) is False
    assert status_of(runtime)["spawn_attempts"] == 3

    # cooldown(마지막 backoff = 0.2s)이 지나면 trial 1회가 허용된다.
    assert wait_for(lambda: status_of(runtime)["spawn_attempts"] > 3, timeout=6.0), status_of(runtime)
    assert wait_for(lambda: runtime.circuit_open is True, timeout=6.0), status_of(runtime)
    assert status_of(runtime)["spawn_attempts"] == 6  # trial episode 도 3회 예산을 쓴다


def test_repeated_child_deaths_open_the_circuit_instead_of_respawning_forever(
    runtimes: list[SsakSearchRuntime], tmp_path: Path
) -> None:
    record = tmp_path / "die0.json"
    runtime = start(
        runtimes,
        record,
        "die_after_ms",
        extra_env={"SSAK_CHILD_RECORD": str(record), "SSAK_CHILD_DIE_MS": "120"},
        health_reset_seconds=60.0,
    )
    assert runtime.ensure_ready(timeout=20) is True
    assert wait_for(lambda: runtime.circuit_open, timeout=15.0), status_of(runtime)
    status = status_of(runtime)
    assert status["state"] == "failed"
    assert status["spawn_attempts"] <= 3, status  # 무한 재spawn 금지
    assert "keeps exiting" in str(status["last_error"])
    assert runtime.child_pids() == []


# ── exit 관찰 ────────────────────────────────────────────────────────────────


def test_idle_child_exit_is_observed_with_a_reason(runtimes: list[SsakSearchRuntime], tmp_path: Path) -> None:
    record = tmp_path / "idle.json"
    runtime = start(
        runtimes,
        record,
        "die_after_ms",
        extra_env={"SSAK_CHILD_RECORD": str(record), "SSAK_CHILD_DIE_MS": "250"},
        monitor_interval_seconds=0.05,
        health_reset_seconds=60.0,
        # 재시작하지 않게 예산을 1로 준다 → 관찰된 첫 죽음이 그대로 "마지막 관찰"로 남는다.
        max_start_attempts=1,
        backoff_seconds=(0.05,),
    )
    assert runtime.ensure_ready(timeout=20) is True
    pid = spawn_record(record)["pid"]

    assert wait_for(lambda: runtime.circuit_open, timeout=8.0), status_of(runtime)
    status = status_of(runtime)
    assert status["state"] == "failed"
    assert status["last_exit"] is not None
    assert "ping failed" in str(status["last_exit"]["reason"]), status["last_exit"]
    assert "keeps exiting" in str(status["last_error"]), status["last_error"]
    assert pid not in runtime.child_pids()


def test_call_racing_with_child_exit_never_hangs_and_never_retries(
    runtimes: list[SsakSearchRuntime], tmp_path: Path
) -> None:
    """child 가 호출 도중 죽는 경우: 응답이 유실될 수 있고, 그래서 **재시도가 금지**된다.

    실측(원시 SDK 로도 재현): child 가 응답을 쓴 직후 `os._exit` 하면 그 응답은 클라이언트에
    전달되지 않고 요청은 `Connection closed` 로 끝난다 — 반면 살아 있는 child 의 지연 응답은
    정상 수신된다. 즉 **응답과 exit 의 경합**이 실재한다. 이 시험이 고정하는 계약은 "응답이 온다"가
    아니라 “멈추지 않는다 · 결과는 반드시 typed 다 · 임의로 재요청하지 않는다”이다.
    """
    record = tmp_path / "probe.json"
    runtime = start(runtimes, record, "die_on_call")
    assert runtime.ensure_ready(timeout=20) is True
    assert runtime.probe().is_error is False
    pid = spawn_record(record)["pid"]

    out = runtime.call_tool("ssak_search", {"query": "x"})
    assert out.is_error in (True, False)  # 멈추지 않았다는 사실 자체가 계약이다
    if out.is_error:
        # 실패는 조용한 빈 결과가 아니라 반드시 typed 여야 한다(호스트가 성공으로 집계하면 안 된다)
        assert out.error_code == "TRANSPORT_LOST"
    assert [call["name"] for call in recorded_calls(record)] == ["ssak_search"], (
        "전송 실패를 런타임이 몸래 재시도했다(비멱등 금지 위반)"
    )

    assert wait_for(lambda: status_of(runtime)["last_exit"] is not None, timeout=8.0), status_of(runtime)
    assert wait_for(lambda: pid not in runtime.child_pids(), timeout=8.0), status_of(runtime)
    reason = str(status_of(runtime)["last_exit"]["reason"])
    assert "call failed" in reason or "ping failed" in reason, reason


# ── 종료: child 0, 그리고 남의 프로세스는 건드리지 않는다 ─────────────────────


def test_teardown_never_crosses_tasks(
    runtimes: list[SsakSearchRuntime], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """task 9 의 결함 재발 방지: 정리는 **세션을 만든 task** 에서 해야 한다.

    SDK 의 stdio context 는 cancel scope 를 만들고, 그것을 다른 task 에서 나가려 하면
    `Attempted to exit cancel scope in a different task` 가 난다. child 사망 → 재시작 → 호스트 종료
    경로를 모두 지나면서 그 문구가 로그에 나타나지 않아야 한다.
    """
    record = tmp_path / "scope.json"
    runtime = start(
        runtimes,
        record,
        "die_after_ms",
        extra_env={"SSAK_CHILD_RECORD": str(record), "SSAK_CHILD_DIE_MS": "200"},
        monitor_interval_seconds=0.05,
    )
    assert runtime.ensure_ready(timeout=20) is True
    assert wait_for(lambda: status_of(runtime)["last_exit"] is not None, timeout=8.0), status_of(runtime)
    status = runtime.shutdown(timeout=20)
    assert status["child_pids"] == []
    assert "different task" not in caplog.text, caplog.text[-800:]


def test_shutdown_leaves_zero_children_and_never_kills_foreign_processes(
    runtimes: list[SsakSearchRuntime], tmp_path: Path
) -> None:
    record = tmp_path / "shutdown.json"
    runtime = start(runtimes, record)
    assert runtime.ensure_ready(timeout=20) is True
    child_pid = spawn_record(record)["pid"]
    assert runtime.child_pids() == [child_pid]

    decoy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])  # noqa: S603 — 우리가 만든 프로세스
    try:
        status = runtime.shutdown(timeout=20)
        assert status["state"] == "stopped"
        assert status["child_pids"] == []
        assert status["shutdown_clean"] is True
        # 우리가 만들지 않은 프로세스는 살아 있어야 한다(이름·pgid 로 죽이지 않는다).
        assert decoy.poll() is None, "남의 프로세스를 죽였다"
    finally:
        decoy.terminate()
        decoy.wait(timeout=10)


def test_shutdown_clean_flag_is_derived_from_the_child_list(
    runtimes: list[SsakSearchRuntime], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`shutdown_clean` 은 **증거 필드**다 — 하드코딩된 True 는 아무것도 증명하지 않는다.

    child 목록을 위조해 "정리했는데도 child 가 남아 있는" 순간을 만들고, 플래그가 그 사실을
    따라가는지 본다(상수로 박아 두면 이 시험이 빨강이 된다).
    """
    record = tmp_path / "derived.json"
    runtime = start(runtimes, record)
    assert runtime.ensure_ready(timeout=20) is True
    monkeypatch.setattr(type(runtime), "child_pids", lambda self: [424242])
    status = runtime.shutdown(timeout=20)
    assert status["shutdown_clean"] is False, "종료 증거가 실제 child 목록에서 계산되지 않는다"
    # 위조한 목록은 이 시험 안에서만 살아야 한다. monkeypatch 해제가 fixture 정리보다 늦으면
    # 정리 단계의 `child_pids == []` 단언이 **영원히** 빨강이 된다(task 24 가 발견: 3회 연속 실패).
    monkeypatch.undo()


def test_runtime_can_be_restarted_after_shutdown(runtimes: list[SsakSearchRuntime], tmp_path: Path) -> None:
    record = tmp_path / "restart.json"
    runtime = start(runtimes, record)
    assert runtime.ensure_ready(timeout=20) is True
    assert runtime.shutdown(timeout=20)["child_pids"] == []

    out = runtime.call_tool("ssak_search", {"query": "again"})
    assert out.is_error is False
    assert runtime.state is SearchRuntimeState.READY
    assert status_of(runtime)["spawn_attempts"] == 2


def test_host_singleton_shutdown_closes_the_child(tmp_path: Path) -> None:
    record = tmp_path / "singleton.json"
    runtime = get_ssak_search_runtime(make_config(record))
    try:
        # "한 host instance = 한 런타임" 은 동일성으로만 잴 수 있다. 두 번째 호출이 새 런타임을
        # 만들면 child 가 둘이 되고 stdout 을 나눠 읽는다(이 시험이 그걸 잡는다).
        assert get_ssak_search_runtime(make_config(record)) is runtime
        assert runtime.ensure_ready(timeout=20) is True
        status = shutdown_ssak_search_runtime(timeout=20)
        assert status is not None
        assert status["child_pids"] == []
        assert shutdown_ssak_search_runtime() is None  # 두 번 불러도 새 child 를 만들지 않는다
    finally:
        runtime.shutdown(timeout=20)


# ── 환경·cwd 위생 ─────────────────────────────────────────────────────────────


def test_minimal_env_allowlist_and_unchanged_cwd(
    runtimes: list[SsakSearchRuntime], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGK_SEARCH_TEST_SECRET", "do-not-leak-9f3a")
    record = tmp_path / "env.json"
    runtime = start(runtimes, record, extra_env={"SSAK_CHILD_RECORD": str(record), "SSAK_CHILD_EXTRA": "forwarded"})
    assert runtime.ensure_ready(timeout=20) is True

    seen = spawn_record(record)
    env = seen["env"]
    assert isinstance(env, dict)
    assert "AGK_SEARCH_TEST_SECRET" not in env, "호스트 비밀이 child 로 전달됐다"
    assert env["PATH"], "PATH 는 allowlist 로 넘어가야 한다"
    assert env["SSAK_CHILD_EXTRA"] == "forwarded", "명시적 extra_env 는 전달된다"
    # allowlist 밖 변수는 넘기지 않는다(예: 이 시험 프로세스에만 있는 표식).
    assert "PYTEST_CURRENT_TEST" not in env
    assert DEFAULT_ENV_ALLOWLIST[0] == "PATH"
    assert seen["cwd"] == os.getcwd(), "cwd 는 호스트 것을 그대로 물려받아야 한다"


# ── 재시도 금지(비멱등) ───────────────────────────────────────────────────────


def test_non_idempotent_tool_is_never_retried(runtimes: list[SsakSearchRuntime], tmp_path: Path) -> None:
    record = tmp_path / "idempotent.json"
    runtime = start(runtimes, record)
    assert runtime.ensure_ready(timeout=20) is True

    refused = runtime.call_tool("mutating_write", {}, retry_on_transport=True, idempotent=False)
    assert refused.is_error is True
    assert refused.error_code == "NON_IDEMPOTENT_NOT_RETRIED"
    assert recorded_calls(record) == [], "거절한 호출이 child 에 도달했다"

    allowed = runtime.call_tool("mutating_write", {}, retry_on_transport=True, idempotent=True)
    assert allowed.is_error is False
    assert [call["name"] for call in recorded_calls(record)] == ["mutating_write"]


def test_call_timeout_fails_the_call_without_killing_the_session(
    runtimes: list[SsakSearchRuntime], tmp_path: Path
) -> None:
    record = tmp_path / "slow.json"
    runtime = start(
        runtimes,
        record,
        "slow",
        extra_env={"SSAK_CHILD_RECORD": str(record), "SSAK_CHILD_SLOW_MS": "700"},
    )
    assert runtime.ensure_ready(timeout=20) is True

    pid_before = runtime.child_pids()
    assert pid_before, "손잡기 전에 child pid 를 못 잡았다"
    slow = runtime.call_tool("ssak_search", {"query": "slow"}, timeout=0.25)
    assert slow.is_error is True and slow.error_code == "TIMEOUT"

    fast = runtime.call_tool("ssak_search", {"query": "after"}, timeout=20)
    assert fast.is_error is False, "타임아웃이 세션을 죽였다"
    assert runtime.state is SearchRuntimeState.READY
    # 손잡기 **전에** 잡은 pid·spawn 수가 그대로여야 한다: 타임아웃을 child 죽음으로 오판하면
    # 세션이 갈리고 새 pid 가 나온다(느린 정상 검색이 child 를 잃는 그 실패 모드다).
    assert runtime.child_pids() == pid_before, "타임아웃이 child 를 갈아치웠다"
    assert status_of(runtime)["spawn_attempts"] == 1


# ── artifact fail-closed ─────────────────────────────────────────────────────


def _write_artifact(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_artifact_hash_mismatch_fails_closed_before_spawning(runtimes: list[SsakSearchRuntime], tmp_path: Path) -> None:
    artifact = _write_artifact(tmp_path / "ssak-mcp", "#!/bin/sh\nexit 0\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"artifact": {"path": "ssak-mcp", "sha256": "0" * 64, "platform": "darwin", "arch": "arm64"}}),
        encoding="utf-8",
    )
    runtime = SsakSearchRuntime(
        SearchRuntimeConfig(artifact_path=str(artifact), manifest_path=str(manifest), require_manifest=True)
    )
    runtimes.append(runtime)

    assert runtime.ensure_ready(timeout=10) is False
    status = status_of(runtime)
    assert status["state"] == "failed"
    assert status["spawn_attempts"] == 0, "불일치 artifact 를 실행해 버렸다"
    assert "does not match the manifest" in str(status["last_error"])
    assert runtime.child_pids() == []


def test_artifact_verification_units(tmp_path: Path) -> None:
    missing = verify_bundled_artifact(tmp_path / "nope", None)
    assert missing.ok is False and "not found" in missing.detail

    plain = tmp_path / "plain"
    plain.write_text("x", encoding="utf-8")
    not_exec = verify_bundled_artifact(plain, None)
    assert not_exec.ok is False and "not executable" in not_exec.detail

    executable = _write_artifact(tmp_path / "run", "#!/bin/sh\n")
    unpinned = verify_bundled_artifact(executable, None)
    assert unpinned.ok is False and "cannot be pinned" in unpinned.detail
    opted_out = verify_bundled_artifact(executable, None, require_manifest=False)
    assert opted_out.ok is True and "opted out" in opted_out.detail

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"artifact": {"path": "run", "sha256": unpinned.sha256}}), encoding="utf-8")
    ok = verify_bundled_artifact(executable, manifest)
    assert ok.ok is True and ok.detail.startswith("artifact matches")

    manifest.write_text(json.dumps({"artifact": {"sha256": "f" * 64}}), encoding="utf-8")
    mismatched = verify_bundled_artifact(executable, manifest)
    assert mismatched.ok is False
    assert "refusing to run different bytes" in mismatched.detail


# ── 로더 배선 ────────────────────────────────────────────────────────────────


def test_loader_registers_managed_tools_and_routes_calls_through_the_runtime(
    runtimes: list[SsakSearchRuntime], tmp_path: Path
) -> None:
    record = tmp_path / "loader.json"
    runtime = start(runtimes, record)
    loader = MCPToolLoader(config_path=None, include_system_tools=False, load_skill_servers=False)

    tools = loader.load_bundled_search_tools(runtime)
    names = sorted(tool.name for tool in tools)
    assert names == ["count_calls", "mutating_write", "ssak_search"], names
    assert loader.schema_errors == []

    tool = next(tool for tool in tools if tool.name == "ssak_search")
    outcome = cast("MCPToolOutcome", tool.execute(query="managed"))
    assert outcome.is_error is False
    assert "managed" in str(outcome)
    assert [call["name"] for call in recorded_calls(record)] == ["ssak_search"]
    metadata = tool.to_metadata()
    assert metadata["mcp"]["managed_runtime"] is not None
    assert metadata["mcp"]["transport"] == "bundled_stdio"

    # child 가 하나도 광고하지 못하면 등록하지 않고 이유를 남긴다(조용한 성공 금지).
    dead = SsakSearchRuntime(make_config(tmp_path / "dead.json", enabled=False))
    runtimes.append(dead)
    assert loader.load_bundled_search_tools(dead) == []
    assert loader.schema_errors[-1]["reason"].startswith("child advertised no tools")


# ── 실제 번들(제공됐을 때만) ──────────────────────────────────────────────────


@pytest.mark.skipif(
    not (os.environ.get("SSAK_SEARCH_ARTIFACT") and os.environ.get("SSAK_SEARCH_MANIFEST")),
    reason="SSAK_SEARCH_ARTIFACT/SSAK_SEARCH_MANIFEST 를 주면 실제 번들로도 잰다",
)
def test_real_bundled_artifact_handshakes_and_shuts_down_cleanly(tmp_path: Path) -> None:
    artifact = os.environ["SSAK_SEARCH_ARTIFACT"]
    manifest = os.environ["SSAK_SEARCH_MANIFEST"]
    verdict = verify_bundled_artifact(artifact, manifest)
    assert verdict.ok is True, verdict.detail

    runtime = SsakSearchRuntime(
        SearchRuntimeConfig(artifact_path=artifact, manifest_path=manifest, call_timeout_seconds=60.0)
    )
    try:
        assert runtime.ensure_ready(timeout=60) is True, status_of(runtime)
        assert runtime.probe().is_error is False
        tools = runtime.list_tools()
        assert any(tool["name"] == "ssak_search" for tool in tools), tools
    finally:
        status = runtime.shutdown(timeout=30)
    assert status["child_pids"] == []


# ── 호스트 종료 배선 ─────────────────────────────────────────────────────────
# 런타임 단위 시험은 "닫으면 child 가 0개가 된다"를 재지만, **호스트가 그 함수를 부르는지**는
# 재지 않는다 — 배선을 지우면 아무 시험도 빨강이 되지 않고 child 가 조용히 남는다.
# 전체 lifespan 을 띄우는 것은 IDE 서버·RAG 색인까지 켜므로, 종료 구간의 배선만 소스로 고정한다.


def _lifespan_body() -> str:
    server = Path(__file__).resolve().parents[1] / "src" / "antigravity_k" / "api" / "server.py"
    source = server.read_text(encoding="utf-8")
    start = source.index("async def lifespan")
    rest = source[start + 1 :]
    end = rest.find("\ndef ")  # 다음 최상위 정의까지가 lifespan 본문이다
    return rest[:end] if end != -1 else rest


def test_host_lifespan_wires_the_bundled_search_shutdown() -> None:
    body = _lifespan_body()
    assert "from antigravity_k.tools.ssak_search_runtime import shutdown_ssak_search_runtime" in body
    assert "shutdown_ssak_search_runtime()" in body, "lifespan 이 번들 검색 child 를 닫지 않는다"
    # 훅이 실패해도 호스트 종료가 멈추면 안 된다(뒤의 정리 단계가 굶는다).
    call_index = body.index("shutdown_ssak_search_runtime()")
    assert "except Exception" in body[call_index:], "종료 훅 실패가 호스트 종료를 막는다"
    # 인자를 넘겨 남의 타임아웃을 흉내내지 않는다(기본값이 계약이다).
    assert "shutdown_ssak_search_runtime(timeout=" not in body


def test_lifespan_gate_is_looking_at_a_real_function_body() -> None:
    """시험 자체의 이빨: 위 게이트가 빈 문자열이나 엉뚱한 구간을 보고 있지 않은가."""
    body = _lifespan_body()
    assert len(body) > 500
    assert "yield" in body, "lifespan 본문에 yield 가 없다 — 잘못된 구간을 읽고 있다"


# ── 실패한 이빨이 지목한 계약 2개 ────────────────────────────────────────────
# 두 변이(R10·R16)가 초록이었다: 계약이 시험으로 고정되지 않았다는 뜻이다. 그 자리를 채운다.


def test_queued_call_is_failed_when_the_runtime_stops(runtimes: list[SsakSearchRuntime], tmp_path: Path) -> None:
    """호스트가 멈추면 **아직 돌지 않은 요청**은 매달리지 않고 typed 오류로 끝난다.

    child 를 붙잡아 두는 호출(느린 검색) 하나가 진행 중일 때 두 번째 요청을 큐에 넣고 런타임을
    닫는다. 두 번째 요청은 서비스되지 않으므로, 그것을 실패시키는 코드가 없으면 호출자는
    자기 타임아웃까지 매달린다 — 그게 이 계약이 막는 실패다.
    """
    record = tmp_path / "pending.json"
    runtime = start(
        runtimes,
        record,
        "slow",
        extra_env={"SSAK_CHILD_RECORD": str(record), "SSAK_CHILD_SLOW_MS": "2500"},
    )
    assert runtime.ensure_ready(timeout=20) is True

    results: dict[str, MCPToolOutcome] = {}

    def call(name: str) -> None:
        outcome = runtime.call_tool("ssak_search", {"query": name}, timeout=30)
        results[name] = outcome

    in_flight = threading.Thread(target=call, args=("in-flight",), daemon=True)
    queued = threading.Thread(target=call, args=("queued",), daemon=True)
    in_flight.start()
    time.sleep(0.3)  # 첫 요청이 child 에 들어가 큐를 비우게 한다
    queued.start()
    time.sleep(0.3)  # 두 번째 요청이 큐에 남아 있게 한다

    status = runtime.shutdown(timeout=25)
    assert status["child_pids"] == []
    assert wait_for(lambda: "queued" in results, timeout=15.0), "큐에 남은 요청이 끝나지 않았다(호출자가 매달린다)"
    assert results["queued"].is_error is True
    assert results["queued"].error_code == "RUNTIME_STOPPED", str(results["queued"])
    assert "was not run" in str(results["queued"])


def test_a_successful_call_resets_the_episode_budget(runtimes: list[SsakSearchRuntime], tmp_path: Path) -> None:
    """성공한 호출은 \"이 child 는 일하고 있다\"는 증거다 — 예산을 되돌리지 않으면 정상 동작이 회로를 연다.

    예산(`start_attempts_in_episode`)은 첫 연결이 이미 1을 쓴 상태로 시작한다. 성공한 호출이
    되돌리면 0으로 돌아가고, 되돌리지 않으면 1로 남아 다음 상실이 곧바르 회로를 연다.
    (child 를 실제로 죽여 관측하는 방식은 회로가 열리기 전에 재연결이 끼어들어 흔들린다 —
    이 계약은 부기(bookkeeping) 규칙이므로 상태 스냅숏으로 직접 잰다.)
    """
    record = tmp_path / "episode.json"
    runtime = start(runtimes, record)
    assert runtime.ensure_ready(timeout=20) is True
    assert status_of(runtime)["start_attempts_in_episode"] == 1, status_of(runtime)

    outcome = runtime.call_tool("ssak_search", {"query": "proves the child works"}, timeout=20)
    assert outcome.is_error is False, outcome
    assert status_of(runtime)["start_attempts_in_episode"] == 0, "성공한 호출이 예산을 되돌리지 않았다"
