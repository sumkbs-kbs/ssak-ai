"""soak 통제 도구(`soak_control.sh`)의 계약 시험 — 예약·실행·**회수**를 다루는 도구를 게이트가 지킨다.

왜 승격하는가: 이 스크립트는 프로세스를 **죽이고**(`cancel`) 예약을 **걸고**(`arm`) 8시간 실행을
**띄운다**(`run`). `docs/` 안에 있는 동안에는 어떤 게이트도 그 판단을 보지 않았다 — 실제로 오늘
“취소했다고 기록한 예약 3건이 살아 있었다”를 사람이 `pgrep` 으로 발견했고, 그 뒤 이 도구의 자기시험
(77~79개 검사)이 그 부류를 잡도록 만들어졌다. 이 파일은 그 자기시험이 **게이트 안에서 매번 돌게** 한다.

이 시험이 고정하는 것:

  1. 스크립트가 문법적으로 살아 있다(`bash -n`) — 스크립트가 깨지면 예약·회수가 통째로 멈춘다.
  2. **자기시험 77/77**(깨끗한 트리) — 수명주기(arm/cancel/orphans/preflight/run/harvest)를 임시 루트에서 돈다.
     진짜 soak 이 도는 동안에도 통과해야 의미가 있으므로, 시험 환경의 하네스 이름을 도구가 통제한다.
     커밋되지 않은 파일이 있는 **더러운 트리**(승격 리허설·편집 중)에서는 “현재 트리 == HEAD”(후보 귀속)가
     설계상 거짓이므로, 자기시험이 그 항목만 생략하고 **생략했다고 문장으로 밝힌다** — 그 문장을 확인하는
     검사가 하나 늘어 79/79 가 된다. 생략은 조용하지 않고, 깨끗한 트리에서는 종전대로 검사한다.
     (2026-09-17 리허설이 이 전제를 잡아냈다 — `GATE_LEDGER` §23 · §25-7. 그래서 수는 77 또는 79 이고 하한은 60 이다.
     수가 올라간 이유: 셸 오탐 이빨(⑧b) 2건 + 더러운 트리 전용 생략 확인 1건.)
  3. 잘못된 부속 명령은 **거부**된다(exit 2, 사용법 출력) — 오타가 조용히 다른 일을 하지 않는다.
  4. 예약이 없을 때 `status` 는 거짓 초록을 내지 않는다(exit 1 · `ATTENTION`).
  5. `harvest --no-wait` 는 **도는 실행을 판정하지 않는다**(exit 4) — 러너는 종료 시에만 `end_*`·`exit`
     를 쓰므로 지금 읽으면 옛 값을 판정하게 된다. 그리고 아무것도 쓰지 않는다.

`arm`·`run` 은 시험에서 **일부러 부르지 않는다**(둘 다 실제 예약/실행을 만든다). 그 경로는 자기시험의
임시 루트 픽스처가 검증한다 — 시험 환경을 오염시키지 않는 방식으로 같은 계약을 지킨다.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


def _repo_root() -> Path:
    """루트를 **걸어 올라가며** 찾는다 — 스테이징(`docs/…/promote3/`)과 승격 위치(`tests/`) 둘 다에서 산다."""
    override = os.environ.get("AGK_REPO_ROOT")
    if override:
        return Path(override).resolve()
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "antigravity_k").is_dir():
            return candidate
    raise RuntimeError("저장소 루트를 찾지 못했다 — AGK_REPO_ROOT 로 지정한다")


REPO_ROOT = _repo_root()
_NX10 = REPO_ROOT / "docs" / "qa" / "2026-09-16-followup" / "nx10"
CONTROL_CANDIDATES = (REPO_ROOT / "scripts" / "soak_control.sh", _NX10 / "soak_control.sh")

# 자기시험 검사 수의 하한 — 검사를 지우면 “passed” 가 아니라 여기서 걸리게 한다.
MIN_SELFTEST_CHECKS = 60
# 회수해야 할 실행이 없을 때의 exit(그리고 도는 실행이 있으면 4 로 **거부**해야 한다).
NO_RUN_TO_HARVEST = 3
RUN_STILL_LIVE = 4


def _control_path() -> Path:
    for candidate in CONTROL_CANDIDATES:
        if candidate.is_file():
            return candidate
    pytest.fail(
        "soak 통제 도구(soak_control.sh)를 찾지 못했다 — 승격 위치/스테이징 어디에도 없다: "
        + ", ".join(str(path) for path in CONTROL_CANDIDATES)
    )


def _run_ctl(*args: str, out_dir: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["NX10_REPO"] = str(REPO_ROOT)
    env.setdefault("NX10_PYTHON", sys.executable)
    if out_dir is not None:
        env["NX10_OUT"] = str(out_dir)
    env.setdefault("NX10_PREFLIGHT_SKIP_THROUGHPUT", "1")
    return subprocess.run(
        ["bash", str(_control_path()), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def _soak_pids() -> list[str]:
    """도는 soak 을 **도구와 같은 이름 규칙**으로 찾는다.

    도구(`soak_control.sh`)는 `NX10_SOAK_PROC_PATTERN`(기본 `val02_staging.py`)으로 대상을 지목한다.
    이 시험이 그 이름을 보지 않고 하드코딩하면, 이름을 바꿔 도는 환경(승격 뒤 순서의 리허설처럼 미러에서
    진짜 soak 을 피해가는 경우)에서 **시험과 도구가 다른 세계를 본다** — 실측 2026-09-17: 시험은 “도는
    실행 있음”(4를 기대)이라 했고 도구는 “없음”(3을 반환)이라 해서 계약 시험이 거짓으로 빨개졌다.
    """
    if shutil.which("pgrep") is None:
        return []
    pattern = os.environ.get("NX10_SOAK_PROC_PATTERN", "val02_staging.py")
    result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, check=False)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def test_script_parses():
    """스크립트가 문법적으로 살아 있는가 — 깨진 스크립트는 예약도 회수도 못 한다."""
    result = subprocess.run(["bash", "-n", str(_control_path())], capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"bash -n 실패:\n{result.stderr[-800:]}"


def test_selftest_covers_the_lifecycle(tmp_path: Path, monkeypatch):
    """자기시험이 실제로 수명주기를 돌리고 초록인가(진짜 soak 이 도는 중에도 통과해야 한다)."""
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "soak-exit.txt"
    sentinel.write_text("outside sentinel\n")
    monkeypatch.setenv("NX10_SOAK_OUT_DIR", str(outside))
    result = _run_ctl("selftest", timeout=600)
    assert sentinel.read_text() == "outside sentinel\n"
    assert sorted(path.name for path in outside.iterdir()) == ["soak-exit.txt"]
    match = re.search(r"SOAK_CONTROL_SELFTEST: (\d+)/(\d+) passed", result.stdout)
    assert result.returncode == 0, f"자기시험 실패(exit {result.returncode}):\n{result.stdout[-1500:]}"
    assert match is not None, f"자기시험 요약줄이 없다:\n{result.stdout[-800:]}"
    passed, total = int(match.group(1)), int(match.group(2))
    assert total >= MIN_SELFTEST_CHECKS, f"검사가 {total}개뿐이다(하한 {MIN_SELFTEST_CHECKS})"
    assert passed == total, f"{passed}/{total} — 실패가 있다:\n{result.stdout[-1500:]}"
    assert "[FAIL]" not in result.stdout, "실패 표시가 있는데 요약은 통과라고 말한다"


def test_an_immediate_run_records_what_it_means_to_measure():
    """즉시 실행은 예약 블록을 남기지 않았다 → 판정기가 **낡은 예약**을 기대값으로 집었다(2026-09-17 실측).

    그 실행은 지표 all_pass · 러너 exit 0 · 8h00m04s · 시작==종료==현재 트리였는데도 FAIL 로 판정됐다.
    처방은 “이 실행의 기대값을 이 실행이 적는다”이므로, `cmd_run` 이 그 기록을 부르는지 본다(배선 이빨).
    기록 자체의 동작은 자기시험 ⑬ 이 임시 루트에서 실제로 돌린다.
    """
    text = _control_path().read_text(encoding="utf-8")
    run_body = text.split("cmd_run() {", 1)[1].split("\n}", 1)[0]
    assert "_record_run_expectation" in run_body, "즉시 실행이 기대 지문을 기록하지 않는다"
    helper = text.split("_record_run_expectation() {", 1)[1].split("\n}", 1)[0]
    assert "expected_fingerprint:" in helper, "기록에 기대 지문이 없다 — 판정기가 쓸 값이 없다"
    assert "aborted" not in helper, "살아 있는 실행의 기록에 중단 표시가 섞이면 판정기가 그 블록을 건너뛴다"


def test_unknown_subcommand_is_rejected():
    """오타 난 부속 명령은 **거부**된다 — 조용히 다른 일을 하지 않는다."""
    result = _run_ctl("definitely-not-a-command")
    combined = result.stdout + result.stderr
    assert result.returncode == 2, f"기대 2, 받은 {result.returncode}:\n{combined[-500:]}"
    assert "사용:" in combined, f"사용법을 보여 주지 않았다:\n{combined[-500:]}"


def test_status_without_a_schedule_is_not_a_false_green(tmp_path: Path):
    """예약도 실행도 없으면 `status` 는 초록이 아니다(exit 1 + ATTENTION) — 거짓 초록은 판정을 망친다."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = _run_ctl("status", out_dir=out_dir)
    assert result.returncode == 1, f"기대 1, 받은 {result.returncode}:\n{result.stdout[-600:]}"
    assert "살아 있는 예약: 0건" in result.stdout, result.stdout[-600:]
    assert "ATTENTION" in result.stdout, result.stdout[-600:]
    assert sorted(path.name for path in out_dir.iterdir()) == [], "status 가 상태 파일을 만들었다"


def test_harvest_refuses_to_judge_a_live_run(tmp_path: Path):
    """`harvest --no-wait` 는 도는 실행을 판정하지 않는다 — 러너는 종료 시에만 `end_*`·`exit` 를 쓴다.

    도는 실행이 없으면 “회수할 실행 없음”(exit 3)이다. 어느 쪽이든 **아무것도 쓰지 않아야** 한다
    (판정 JSON 을 쓰면 회수 기록이 오염된다).
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    live = _soak_pids()
    result = _run_ctl("harvest", "--no-wait", out_dir=out_dir)
    expected = RUN_STILL_LIVE if live else NO_RUN_TO_HARVEST
    assert result.returncode == expected, (
        f"기대 {expected}(도는 실행 {len(live)}건), 받은 {result.returncode}:\n{result.stdout[-800:]}"
    )
    leftovers = sorted(path.name for path in out_dir.iterdir())
    assert leftovers == [], f"판정하지 않고 물러나면서 파일을 남겼다: {leftovers}"


def test_run_refuses_when_a_soak_is_already_live(tmp_path: Path):
    """**동결 가드** — 이미 soak 이 돌고 있으면 `run` 은 두 번째를 띄우지 않는다(exit 2).

    왜 이 시험이 중요한가: 두 번째가 뜨면 같은 리포트·작업디렉터리를 다투고 시작/종료 지문이 엉킨다.
    시험은 **가짜 soak**(고유 argv 를 가진 프로세스)으로 그 상황을 만들고, 도구가 하네스 이름을
    환경변수(`NX10_SOAK_PROC_PATTERN`)로 통제한다는 점을 쓴다 — 진짜 soak 을 띄우지 않는다.
    """
    decoy_marker = "nx10-contract-decoy"
    decoy = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)", decoy_marker],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    env = dict(os.environ)
    env.update(
        NX10_REPO=str(REPO_ROOT),
        NX10_OUT=str(tmp_path),
        NX10_SOAK_PROC_PATTERN=decoy_marker,
        NX10_PREFLIGHT_SKIP_THROUGHPUT="1",
    )
    try:
        result = subprocess.run(
            ["bash", str(_control_path()), "run"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            check=False,
        )
    finally:
        decoy.terminate()
        decoy.wait(timeout=10)
    combined = result.stdout + result.stderr
    assert result.returncode == 2, (
        f"이미 soak(pid {decoy.pid})이 도는데 run 이 거절하지 않았다(exit {result.returncode}):\n{combined[-800:]}"
    )
    # 거절 사유가 **점검 항목 이름과 pid** 로 남아야 한다(사람이 원인을 바로 안다).
    assert "다른 soak 실행 없음" in combined and str(decoy.pid) in combined, combined[-800:]
    assert "거부" in combined, combined[-500:]
    assert not (tmp_path / ".soak-run.lock").exists(), "거절했는데 실행 잠금을 잡았다"


def test_no_wait_returns_without_waiting_for_incomplete_run(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "NX10_REPO": str(REPO_ROOT),
        "NX10_OUT": str(tmp_path / "out"),
        "NX10_SOAK_OUT_DIR": str(tmp_path / "out"),
        "NX10_PYTHON": sys.executable,
        "NX10_SOAK_PROC_PATTERN": "no-live-soak-" + uuid.uuid4().hex,
        "NX10_HARVEST_SETTLE": "3600",
    }
    process = subprocess.Popen(
        ["bash", str(_control_path()), "harvest", "--no-wait"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        _, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=5)
        pytest.fail("--no-wait waited for an incomplete run")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    assert process.returncode == NO_RUN_TO_HARVEST, stderr
    assert not (tmp_path / "out").exists()
