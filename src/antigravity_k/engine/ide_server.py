"""Ide Server module."""

import logging
import os
import shutil
import socket
import subprocess
import threading
from typing import Final, final

logger = logging.getLogger(__name__)

IDE_AUTOSTART_ENV: Final = "AGK_IDE_SERVER_AUTOSTART"


def ide_autostart_requested() -> bool:
    """Dev default keeps autostart on; only an explicit off value (the DMG launcher sets 0) disables it."""
    return os.environ.get(IDE_AUTOSTART_ENV, "").strip().lower() not in {"0", "false", "no", "off"}


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


@final
class IDEServer:
    """Manages the lifecycle of the code-server daemon to provide a Web IDE."""

    def __init__(self, port: int = 8080, workspace_dir: str = "."):
        """Initialize the IDEServer.

        Args:
            port (int): int port.
            workspace_dir (str): str workspace dir.

        """
        self.port: Final = port
        self.workspace_dir: Final = workspace_dir
        self.process: subprocess.Popen[bytes] | None = None
        self._lock: Final = threading.Lock()
        self.status: str = "not_started"

    def start(self) -> None:
        """Start the embedded code-server (IDE) process."""
        with self._lock:
            if self.process and self.process.poll() is None:
                logger.info("IDE Server is already running on port %s.", self.port)
                return

            # Note: auth=none is used because we assume the dashboard handles authentication,
            # and the code-server is only bound to localhost for proxying.
            cmd = [
                "code-server",
                "--bind-addr",
                f"127.0.0.1:{self.port}",
                "--auth",
                "none",
                self.workspace_dir,
            ]

            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=os.environ.copy(),
                )
                logger.info(
                    "Started IDE (code-server) on port %s for %s",
                    self.port,
                    self.workspace_dir,
                )
            except FileNotFoundError:
                logger.info("Optional IDE unavailable: code-server executable not found in PATH.")
                # We do not raise here to prevent crashing the main orchestrator if code-server is missing
                self.process = None

    def start_if_available(self) -> str:
        """Start code-server only after preflight checks; never touch an occupied port.

        Returns:
            str: "running", "not_installed", "port_in_use" or "failed".

        """
        if shutil.which("code-server") is None:
            self.status = "not_installed"
            logger.info("Optional IDE unavailable: code-server is not installed.")
        elif _port_in_use(self.port):
            self.status = "port_in_use"
            logger.warning("Optional IDE not started: port %s is already in use by another service.", self.port)
        else:
            self.start()
            self.status = "running" if self.is_running() else "failed"
        return self.status

    def stop(self) -> None:
        """Stop the embedded code-server and release resources."""
        with self._lock:
            if self.process and self.process.poll() is None:
                logger.info("Stopping IDE Server...")
                self.process.terminate()
                try:
                    _ = self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                self.process = None
                logger.info("IDE Server stopped.")

    def is_running(self) -> bool:
        """Check if running.

        Returns:
            bool: The bool result.

        """
        with self._lock:
            return self.process is not None and self.process.poll() is None
