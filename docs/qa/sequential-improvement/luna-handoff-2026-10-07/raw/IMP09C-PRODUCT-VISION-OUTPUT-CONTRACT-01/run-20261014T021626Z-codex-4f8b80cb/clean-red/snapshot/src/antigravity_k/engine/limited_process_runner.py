from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import BinaryIO, final

from antigravity_k.engine.task_execution_context import current_task_execution_context
from antigravity_k.engine.task_process_supervisor import task_process_supervisor


@dataclass(frozen=True, slots=True)
class LimitedProcessResult:
    return_code: int
    stdout: str
    stderr: str
    output_truncated: bool


@final
class LimitedProcessRunner:
    def __init__(self, max_output_bytes: int) -> None:
        self._max_output_bytes = max(1, max_output_bytes)

    def run(
        self,
        args: list[str] | str,
        *,
        shell: bool,
        timeout: int,
        env: Mapping[str, str] | None,
        cwd: str,
    ) -> LimitedProcessResult:
        # `shell` is an explicit execution mode selected only by SandboxRunner;
        # command authorization and OS isolation are enforced at that boundary.
        process = subprocess.Popen(  # nosec B602
            args,
            shell=shell,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            env=dict(env) if env is not None else os.environ.copy(),
            cwd=cwd,
            start_new_session=os.name == "posix",
        )
        context = current_task_execution_context()
        registration = task_process_supervisor.register(
            context.task_id if context is not None else None,
            process,
            process.pid if os.name == "posix" else None,
        )
        stdout_buffer = bytearray()
        stderr_buffer = bytearray()
        truncated = [False, False]
        threads = (
            threading.Thread(
                target=self._drain,
                args=(process.stdout, stdout_buffer, truncated, 0),
                name=f"process-{process.pid}-stdout",
            ),
            threading.Thread(
                target=self._drain,
                args=(process.stderr, stderr_buffer, truncated, 1),
                name=f"process-{process.pid}-stderr",
            ),
        )
        for thread in threads:
            thread.start()

        timed_out = False
        try:
            _ = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            task_process_supervisor.terminate(registration)
            task_process_supervisor.unregister(registration)
            for thread in threads:
                thread.join(timeout=1)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            for thread in threads:
                thread.join(timeout=1)

        stdout = bytes(stdout_buffer).decode("utf-8", errors="replace")
        stderr = bytes(stderr_buffer).decode("utf-8", errors="replace")
        if timed_out:
            raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr)
        return LimitedProcessResult(
            return_code=process.returncode or 0,
            stdout=stdout,
            stderr=stderr,
            output_truncated=any(truncated),
        )

    def _drain(
        self,
        stream: BinaryIO | None,
        buffer: bytearray,
        truncated: list[bool],
        index: int,
    ) -> None:
        if stream is None:
            return
        while chunk := stream.read(8192):
            remaining = self._max_output_bytes - len(buffer)
            if remaining > 0:
                buffer.extend(chunk[:remaining])
            if len(chunk) > max(remaining, 0):
                truncated[index] = True


__all__ = ["LimitedProcessResult", "LimitedProcessRunner"]
