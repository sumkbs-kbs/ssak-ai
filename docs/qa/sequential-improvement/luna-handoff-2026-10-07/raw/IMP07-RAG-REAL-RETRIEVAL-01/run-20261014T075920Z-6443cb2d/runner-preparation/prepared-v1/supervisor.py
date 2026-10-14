from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from control import Phase, load_freeze, save, sha, verify_manifest


def group_members(group: int) -> list[dict[str, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,pgid=,stat="],
        capture_output=True,
        text=True,
        check=True,
        timeout=3,
    )
    return [
        dict(zip(("pid", "ppid", "pgid", "stat"), fields, strict=True))
        for line in result.stdout.splitlines()
        if len(fields := line.split()) == 4 and int(fields[2]) == group
    ]


class Arguments(argparse.Namespace):
    freeze: Path = Path()
    python: Path = Path()
    go: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Only run after root approval of the exact source freeze."
    )
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--go", required=True, choices=["ROOT_GO"])
    parser.add_argument("--python", required=True, type=Path)
    args = Arguments()
    _ = parser.parse_args(namespace=args)
    prep = Path(__file__).resolve().parent
    fixture = prep.parent
    freeze = load_freeze(args.freeze, fixture)
    verify_manifest(fixture, "fixture-manifest.sha256")
    out = fixture / (
        "execution-"
        + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    out.mkdir()
    save(out / "approved-freeze.json", freeze.model_dump(mode="json"))
    owned_env = {
        "PYTHONPATH": str(Path(str(freeze.source_root)) / "src"),
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
    argv = [
        str(args.python.absolute()),
        "-B",
        str(prep / "runner.py"),
        "--execution",
        str(out),
        "--freeze",
        str(out / "approved-freeze.json"),
    ]
    signals: list[str] = []
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
        "signals": signals,
        "timed_out": False,
        "freeze_sha256": sha(args.freeze),
        "execution": str(out),
    }
    save(out / "invocation.json", receipt)
    began = time.monotonic()
    with (
        (out / "stdout.log").open("xb") as stdout,
        (out / "stderr.log").open("xb") as stderr,
    ):
        process = subprocess.Popen(
            argv,
            cwd=str(freeze.source_root),
            env=env,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        receipt["child_pid"] = process.pid
        save(out / "invocation.json", receipt)
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - began
                phase_file = out / "phase.json"
                phase = (
                    Phase.model_validate_json(phase_file.read_bytes())
                    if phase_file.exists()
                    else None
                )
                phase_limit = 30 if phase is not None and phase.name == "peer" else 180
                phase_started = phase.started_monotonic if phase is not None else began
                if elapsed >= 220 or time.monotonic() - phase_started >= phase_limit:
                    receipt["timed_out"] = True
                    break
                time.sleep(0.1)
        except Exception as exc:
            receipt["supervisor_error"] = f"{type(exc).__name__}: {exc}"
        cleanup_start = time.monotonic()
        members_before = group_members(process.pid)
        if members_before:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                signals.append("SIGTERM")
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            if group_members(process.pid):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    signals.append("SIGKILL")
                except ProcessLookupError:
                    pass
        exit_code = process.wait(timeout=3)
        remaining = group_members(process.pid)
        while remaining and time.monotonic() - cleanup_start < 8:
            time.sleep(0.1)
            remaining = group_members(process.pid)
    receipt.update(
        exit_code=exit_code,
        reaped=True,
        cleanup_before=members_before,
        remaining_owned_processes=remaining,
        remaining_count=len(remaining),
        cleanup_seconds_actual=time.monotonic() - cleanup_start,
        elapsed_seconds=time.monotonic() - began,
        ended=datetime.now(UTC).isoformat(),
    )
    source_after = {path: sha(Path(path)) for path in freeze.sources}
    receipt["source_unchanged"] = source_after == freeze.sources
    save(out / "supervisor-source-after.json", source_after)
    verify_manifest(fixture, "fixture-manifest.sha256")
    save(out / "invocation.json", receipt)
    print(
        json.dumps(
            {
                "execution": str(out),
                "exit_code": exit_code,
                "timed_out": receipt["timed_out"],
                "remaining_count": len(remaining),
            }
        )
    )
    return (
        0
        if exit_code == 0
        and not remaining
        and not receipt["timed_out"]
        and receipt["source_unchanged"]
        and "supervisor_error" not in receipt
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
