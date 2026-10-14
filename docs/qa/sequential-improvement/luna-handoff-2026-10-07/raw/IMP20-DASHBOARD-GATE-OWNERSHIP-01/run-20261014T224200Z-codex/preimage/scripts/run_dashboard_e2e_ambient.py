#!/usr/bin/env python3
"""CR-14 F-46 / F-47 — ambient 백엔드가 필요한 Playwright 스펙을 required 게이트로 돌린다.

게이트 명령이 **서버를 세운 뒤** 명명된 스펙을 돌리고, 끝나면 프로세스 그룹째 정리한다.
서버 없이 같은 스펙만 돌리면 실패해야 한다 — 그 이빨은
``tests/test_cr14_ambient_backend_gate_contract.py`` 가 소유한다.

attempt-035 (F-47 일부 폐쇄):
  ``capture-disclosure-*`` 는 Vite :5173 하드코드가 아니라 **시드된 hermetic 서버**
  (``AGK_SEED_LEVEL=healthy|exhausted``) 로 소유한다. healthy/exhausted 는 시드가
  프로세스에 고정되므로 **각자 서버를 따로** 띄운다.

attempt-039 (F-47 EXTERNAL_HUB 폐쇄):
  ``capture-real-local-models`` 는 실 unsloth/GPU 없이 ``AGK_SEED_LOCAL_HUB=1``
  hermetic 픽스처로 ModelHub ``실행 중`` 배지를 소유한다(``HUB_SPEC_FILES``).
  생산 경로에는 시드 플래그가 없다 — EX-01 실 프로바이더 증명이 아니다.

격리 (F-44 · F-45):
  AGK_PATH_DATA_DIR / AGK_PATH_LOGS_DIR / AGK_HOOK_VAULT_DIR / AGK_CORS_ORIGINS
  + 격리 cwd + start_new_session=True + /health 폴링 + 그룹 신호 종료.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "dashboard"

# 이 게이트가 소유하는 파일 — 계약이 같은 목록을 읽는다(복제 금지: 게이트 스크립트가 원본).
AMBIENT_SPEC_FILES: tuple[str, ...] = (
    "e2e/tests/task-execution.spec.ts",
    "e2e/tests/ws-contract-e2e.spec.ts",
    "e2e/tests/file-explorer.spec.ts",
    "e2e/tests/capture-desktop-layout.spec.ts",
    "e2e/tests/capture-model-selection.spec.ts",
)

# attempt-035: disclosure 는 시드별 서버로 소유한다(목록 원본 = 이 튜플).
DISCLOSURE_SPEC_FILES: tuple[tuple[str, str], ...] = (
    ("healthy", "e2e/tests/capture-disclosure-healthy.spec.ts"),
    ("exhausted", "e2e/tests/capture-disclosure-exhausted.spec.ts"),
)

# 서버를 세워도 실패하는 **제품/환경** 테스트 제목 — ambient 부재가 아니다(F-47 leftover).
# 이 목록은 ``tests/test_cr14_f47_leftover_inventory_contract.py`` 가 센다(침묵 금지).
GREP_INVERT: str = ""  # PRODUCT_FLAKE invert 없음(attempt-038). 주석에 따옴표 금지 — 계약이 괄호 안 문자열을 모은다.

# attempt-039: 허브 스펙은 AGK_SEED_LOCAL_HUB 시드 서버로 소유한다(목록 원본 = 이 튜플).
HUB_SPEC_FILES: tuple[tuple[str, str], ...] = (("hub", "e2e/tests/capture-real-local-models.spec.ts"),)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(
    port: int, state: Path, *, seed_level: str | None = None, seed_local_hub: bool = False
) -> subprocess.Popen[bytes]:
    (state / "token_secret").write_text("ambient-gate-secret-" + "x" * 16, encoding="utf-8")
    (state / "isolated.env").write_text("# ambient gate isolated env\n", encoding="utf-8")
    hook_vault = state / "vault_data"
    data_dir = state / "data"
    logs_dir = state / "logs"
    hook_vault.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    origin = f"http://127.0.0.1:{port}"
    cors = ",".join(
        [
            origin,
            f"http://localhost:{port}",
            "http://127.0.0.1:8012",
            "http://localhost:8012",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ]
    )
    env = {
        **os.environ,
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        "PYTHONPATH": str(REPO / "src"),
        "AGK_ENV": "development",
        "AGK_ENV_FILE": str(state / "isolated.env"),
        "AGK_SEC_ACCESS_PIN": "",
        "AGK_ACCESS_PIN": "",
        "AGK_SEC_PIN_HASH_FILE": str(state / "pin_hash"),
        "AGK_SEC_TOKEN_SECRET_FILE": str(state / "token_secret"),
        "AGK_SEC_DEV_NO_PIN_ALLOW": "1",
        "AGK_HOOK_VAULT_DIR": str(hook_vault),
        "AGK_PATH_DATA_DIR": str(data_dir),
        "AGK_PATH_LOGS_DIR": str(logs_dir),
        "AGK_CORS_ORIGINS": cors,
        "AGK_DAILY_BUDGET_USD": "50.0",
        "AGK_HOURLY_ACTION_LIMIT": "100",
    }
    if seed_level:
        env["AGK_SEED_LEVEL"] = seed_level
    if seed_local_hub:
        env["AGK_SEED_LOCAL_HUB"] = "1"
    proc = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "antigravity_k.api.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(state),  # F-44: 격리 cwd — 저장소에 런타임 상태 쓰지 않음
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                return proc
        except (urllib.error.URLError, TimeoutError, OSError):
            if proc.poll() is not None:
                break
            time.sleep(0.2)
    _stop(proc)
    raise RuntimeError(f"ambient backend failed to become healthy on :{port}")


def _stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(50):
        if proc.poll() is not None:
            return
        time.sleep(0.1)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_playwright(base_url: str, specs: list[str], *, grep_invert: str | None, label: str) -> int:
    env = {
        **os.environ,
        "AGK_BACKEND_URL": base_url,
    }
    cmd = [
        "pnpm",
        "exec",
        "playwright",
        "test",
        *specs,
        "--project=chromium",
        "--reporter=list",
    ]
    if grep_invert:
        cmd.insert(-2, f"--grep-invert={grep_invert}")
    print(f"[dashboard-e2e-ambient] {label} base_url={base_url} specs={len(specs)}", flush=True)
    completed = subprocess.run(cmd, cwd=str(DASHBOARD), env=env, check=False)  # noqa: S603
    return int(completed.returncode)


def _run_main_suite(base_url: str) -> int:
    return run_playwright(
        base_url,
        list(AMBIENT_SPEC_FILES),
        grep_invert=GREP_INVERT,
        label="main",
    )


def _run_disclosure_seeded() -> int:
    """healthy / exhausted 는 CostGuard 시드가 프로세스에 고정되므로 서버를 나눈다."""
    for seed_level, rel in DISCLOSURE_SPEC_FILES:
        port = _free_port()
        with tempfile.TemporaryDirectory(prefix=f"agk-ambient-disclosure-{seed_level}-") as tmp:
            state = Path(tmp)
            proc = start_server(port, state, seed_level=seed_level)
            try:
                rc = run_playwright(
                    f"http://127.0.0.1:{port}",
                    [rel],
                    grep_invert=None,
                    label=f"disclosure-{seed_level}",
                )
            finally:
                _stop(proc)
        if rc != 0:
            return rc
    return 0


def _run_hub_seeded() -> int:
    """AGK_SEED_LOCAL_HUB 픽스처 서버로 capture-real-local-models 를 소유한다."""
    for _seed_label, rel in HUB_SPEC_FILES:
        port = _free_port()
        with tempfile.TemporaryDirectory(prefix="agk-ambient-hub-") as tmp:
            state = Path(tmp)
            proc = start_server(port, state, seed_local_hub=True)
            try:
                rc = run_playwright(
                    f"http://127.0.0.1:{port}",
                    [rel],
                    grep_invert=None,
                    label="hub-seed",
                )
            finally:
                _stop(proc)
        if rc != 0:
            return rc
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-server",
        action="store_true",
        help="서버를 세우지 않는다(계약 이빨 — 이 모드에서는 스펙이 실패해야 한다).",
    )
    args = parser.parse_args(argv)
    if args.skip_server:
        # 닫힌 포트 — Chromium 이 UNSAFE 로 거절하는 :1 대신 연결 거부되는 고번호.
        # disclosure·hub 도 상대경로라 같은 닫힌 포트에서 실패해야 한다(이빨).
        closed = "http://127.0.0.1:59999"
        rc_main = _run_main_suite(closed)
        rc_disc = run_playwright(
            closed,
            [rel for _, rel in DISCLOSURE_SPEC_FILES],
            grep_invert=None,
            label="disclosure-skip-server",
        )
        rc_hub = run_playwright(
            closed,
            [rel for _, rel in HUB_SPEC_FILES],
            grep_invert=None,
            label="hub-skip-server",
        )
        all_green = rc_main == 0 and rc_disc == 0 and rc_hub == 0
        return 1 if all_green else (rc_main or rc_disc or rc_hub or 1)

    port = _free_port()
    with tempfile.TemporaryDirectory(prefix="agk-ambient-gate-") as tmp:
        state = Path(tmp)
        proc = start_server(port, state)
        try:
            rc = _run_main_suite(f"http://127.0.0.1:{port}")
        finally:
            _stop(proc)
    if rc != 0:
        return rc
    rc_disc = _run_disclosure_seeded()
    if rc_disc != 0:
        return rc_disc
    return _run_hub_seeded()


if __name__ == "__main__":
    raise SystemExit(main())
