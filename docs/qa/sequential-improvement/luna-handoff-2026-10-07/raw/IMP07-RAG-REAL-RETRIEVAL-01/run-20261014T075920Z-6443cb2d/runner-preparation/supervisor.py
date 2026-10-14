from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .control import Phase, load_freeze, save, sha, verify_manifest


def group_members(group: int, timeout: float) -> list[dict[str, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,pgid=,stat="],
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )
    return [
        dict(zip(("pid", "ppid", "pgid", "stat"), fields, strict=True))
        for line in result.stdout.splitlines()
        if len(fields := line.split()) == 4 and int(fields[2]) == group
    ]


class OwnedProcess(Protocol):
    @property
    def pid(self) -> int: ...

    def wait(self, timeout: float) -> int: ...


@dataclass
class Cleanup:
    reaped: bool = False
    exit_code: int | None = None
    remaining: list[dict[str, str]] | None = None
    signals: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0
    graceful_wait_timed_out: bool = False

    def record(self) -> dict[str, object]:
        return {
            "reaped": self.reaped,
            "exit_code": self.exit_code,
            "remaining_owned_processes": self.remaining,
            "remaining_count": len(self.remaining) if self.remaining is not None else None,
            "signals": self.signals,
            "cleanup_errors": self.errors,
            "cleanup_seconds_actual": self.elapsed_seconds,
            "graceful_wait_timed_out": self.graceful_wait_timed_out,
        }


def cleanup_owned(
    process: OwnedProcess,
    *,
    outer_deadline: float,
    clock: Callable[[], float] = time.monotonic,
    signal_group: Callable[[int, int], None] = os.killpg,
    inventory: Callable[[int, float], list[dict[str, str]]] = group_members,
) -> Cleanup:
    started = clock()
    deadline = min(started + 10.0, outer_deadline)
    result = Cleanup()

    def remaining() -> float:
        return max(0.0, deadline - clock())

    def send(sig: signal.Signals) -> None:
        try:
            signal_group(process.pid, sig)
            result.signals.append(sig.name)
        except ProcessLookupError:
            pass
        except Exception as exc:
            result.errors.append(f"{sig.name}: {type(exc).__name__}: {exc}")

    try:
        send(signal.SIGTERM)
        try:
            result.exit_code = process.wait(timeout=min(1.0, remaining()))
            result.reaped = True
        except subprocess.TimeoutExpired:
            result.graceful_wait_timed_out = True
        except Exception as exc:
            result.errors.append(f"graceful wait: {type(exc).__name__}: {exc}")
        send(signal.SIGKILL)
        if not result.reaped:
            try:
                result.exit_code = process.wait(timeout=remaining())
                result.reaped = True
            except Exception as exc:
                result.errors.append(f"kill wait: {type(exc).__name__}: {exc}")
        if remaining() > 0:
            try:
                result.remaining = inventory(process.pid, remaining())
            except Exception as exc:
                result.errors.append(f"terminal inventory: {type(exc).__name__}: {exc}")
        else:
            result.errors.append("Shared cleanup deadline exhausted before terminal inventory")
    finally:
        result.elapsed_seconds = clock() - started
    return result


def runner_argv(python: Path, out: Path) -> list[str]:
    return [
        str(python.absolute()),
        "-B",
        "-m",
        "runner-preparation.runner",
        "--execution",
        str(out),
        "--freeze",
        str(out / "approved-freeze.json"),
    ]


class Arguments(argparse.Namespace):
    freeze: Path = Path()
    python: Path = Path()
    go: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Only run after root approval of the exact source freeze.")
    _ = parser.add_argument("--freeze", required=True, type=Path)
    _ = parser.add_argument("--go", required=True, choices=["ROOT_GO"])
    _ = parser.add_argument("--python", required=True, type=Path)
    args = Arguments()
    _ = parser.parse_args(namespace=args)
    prep = Path(__file__).resolve().parent
    fixture = prep.parent
    freeze = load_freeze(args.freeze, fixture)
    _ = verify_manifest(fixture, "fixture-manifest.sha256")
    out = fixture / ("execution-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    out.mkdir()
    save(out / "approved-freeze.json", freeze.model_dump(mode="json"))
    owned_env = {
        "PYTHONPATH": os.pathsep.join((str(freeze.source_root / "src"), str(fixture))),
        "PYTHONDONTWRITEBYTECODE": "1",
        "AGK_STATE_DIR": str(out / "state"),
        "AGK_USER_BRAIN_ROOT": str(out / "user-brain"),
        "AGK_DATABASE_PATH": str(out / "state/qa.db"),
        "AGK_CONFIG_FILE": str(out / "owned-model-profile.json"),
        "ANONYMIZED_TELEMETRY": "False",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "XDG_CACHE_HOME": str(out / "cache"),
        "HF_HOME": str(out / "cache/huggingface"),
    }
    env = dict(os.environ, **owned_env)
    argv = runner_argv(args.python, out)
    receipt: dict[str, object] = {
        "argv": argv,
        "cwd": str(freeze.source_root),
        "owned_environment": owned_env,
        "supervisor_pid": os.getpid(),
        "started": datetime.now(UTC).isoformat(),
        "hard_seconds": 230,
        "semantic_seconds": 180,
        "peer_seconds": 30,
        "cleanup_seconds": 10,
        "timed_out": False,
        "freeze_sha256": sha(args.freeze),
        "execution": str(out),
    }
    save(out / "invocation.json", receipt)
    began = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    cleanup = Cleanup()
    try:
        with (out / "stdout.log").open("xb") as stdout, (out / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(
                argv, cwd=str(freeze.source_root), env=env, stdout=stdout, stderr=stderr, start_new_session=True
            )
            receipt["child_pid"] = process.pid
            save(out / "invocation.json", receipt)
            while process.poll() is None:
                elapsed = time.monotonic() - began
                phase_file = out / "phase.json"
                phase = Phase.model_validate_json(phase_file.read_bytes()) if phase_file.exists() else None
                phase_limit = 30 if phase is not None and phase.name == "peer" else 180
                phase_started = phase.started_monotonic if phase is not None else began
                if elapsed >= 220 or time.monotonic() - phase_started >= phase_limit:
                    receipt["timed_out"] = True
                    break
                time.sleep(min(0.1, max(0, 220 - elapsed)))
    except Exception as exc:
        receipt["supervisor_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if process is not None:
            cleanup = cleanup_owned(process, outer_deadline=began + 230)
        receipt.update(cleanup.record())
        receipt.update(elapsed_seconds=time.monotonic() - began, ended=datetime.now(UTC).isoformat())
        try:
            source_after = {path: sha(Path(path)) for path in freeze.sources}
            receipt["source_unchanged"] = source_after == freeze.sources
            save(out / "supervisor-source-after.json", source_after)
            _ = verify_manifest(fixture, "fixture-manifest.sha256")
        except Exception as exc:
            receipt["verification_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            save(out / "invocation.json", receipt)
    print(
        json.dumps(
            {
                "execution": str(out),
                "exit_code": cleanup.exit_code,
                "timed_out": receipt["timed_out"],
                "remaining_count": len(cleanup.remaining) if cleanup.remaining is not None else None,
            }
        )
    )
    return (
        0
        if cleanup.reaped
        and cleanup.exit_code == 0
        and cleanup.remaining == []
        and not cleanup.errors
        and not receipt["timed_out"]
        and receipt.get("source_unchanged") is True
        and "supervisor_error" not in receipt
        and "verification_error" not in receipt
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
