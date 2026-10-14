"""Ambient Watchdog module."""

import logging
import subprocess
import threading
import time
from pathlib import Path

from .heartbeat import HeartbeatMonitor, HeartbeatResult
from .model_manager import ModelManager
from .operational_alert_store import AlertSeverity, OperationalAlertStore, OperationalAlertStoreError
from .vault import VaultEngine

logger = logging.getLogger(__name__)


class AmbientWatchdog:
    """Phase 3: Ambient Partner (자율적 개입 데몬).

    사용자가 명시적으로 명령하지 않아도, 백그라운드에서 파일 변경(git diff)을 감시하다가
    에러나 개선점을 발견하면 스스로 분석하고 제안을 준비합니다.
    """

    def __init__(
        self,
        project_root: str,
        model_manager: ModelManager,
        vault_engine: VaultEngine | None,
        heartbeat: HeartbeatMonitor | None = None,
        alert_store_path: str | Path | None = None,
    ):
        """Initialize the AmbientWatchdog.

        Args:
            project_root (str): str project root.
            model_manager (ModelManager): ModelManager model manager.
            vault_engine (VaultEngine | None): VaultEngine | None vault engine.
            heartbeat (HeartbeatMonitor | None): HeartbeatMonitor | None heartbeat.

        """
        self.project_root: str = project_root
        self.model_manager: ModelManager = model_manager
        self.vault_engine: VaultEngine | None = vault_engine
        self.heartbeat: HeartbeatMonitor = heartbeat or HeartbeatMonitor(project_root=project_root)
        self._alert_store: OperationalAlertStore = OperationalAlertStore(
            alert_store_path or Path(project_root) / ".antigravity" / "operational_alerts.json",
        )

        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._poll_interval: float = 5.0
        self._debounce_time: float = 10.0

        self._last_diff_hash: str = ""
        self._last_change_time: float = 0.0
        self._analyzing: bool = False
        self._heartbeat_counter: int = 0  # IronClaw heartbeat cycle counter

        # 콜백 큐 (오케스트레이터로 메시지 전달용)
        self.notification_queue: list[str] = []

    def _queue_notification(
        self,
        message: str,
        *,
        source: str,
        severity: AlertSeverity = "warning",
    ) -> None:
        try:
            _ = self._alert_store.record(source, message, severity=severity)
        except OperationalAlertStoreError:
            logger.exception("Operational alert persistence failed")
        self.notification_queue.append(message)

    def start(self):
        """Start the ambient watchdog background monitor."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="AmbientWatchdog",
        )
        self._thread.start()
        logger.info("Ambient Watchdog daemon started. Watching for background changes...")

    def stop(self):
        """Stop the ambient watchdog and clean up resources."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _get_current_diff(self) -> str:
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout
        except Exception:
            logger.exception("Unhandled exception")
            return ""

    def _watch_loop(self):
        while self._running:
            try:
                time.sleep(self._poll_interval)
                if self._analyzing:
                    continue

                current_diff = self._get_current_diff()

                if not current_diff:
                    self._last_diff_hash = ""
                    # IronClaw Heartbeat: diff가 없을 때도 하트비트 체크
                    self._maybe_run_heartbeat()
                    continue

                current_hash = str(hash(current_diff))

                if current_hash != self._last_diff_hash:
                    # 변경 발생
                    self._last_diff_hash = current_hash
                    self._last_change_time = time.time()
                else:
                    # 변경이 멈추고 디바운스 시간이 지났는가?
                    if time.time() - self._last_change_time > self._debounce_time and self._last_change_time > 0:
                        self._analyzing = True
                        self._analyze_proactively(current_diff)
                        self._last_change_time = 0.0  # 초기화
                        self._analyzing = False

            except Exception:
                logger.exception("Watchdog error")

    def _maybe_run_heartbeat(self):
        """IronClaw Heartbeat: watchdog loop 60 cycle (5s x 60 = 5min) heartbeat check."""
        self._heartbeat_counter += 1
        if self._heartbeat_counter < 60:
            return
        self._heartbeat_counter = 0

        try:
            results: list[HeartbeatResult] = self.heartbeat.execute_due_tasks()
            for result in results:
                if not result.success:
                    self._queue_notification(
                        f"\u26a0\ufe0f [Heartbeat] {result.task_title}: {result.message}",
                        source="heartbeat",
                    )
        except Exception:
            logger.exception("Heartbeat execution error")

    def _analyze_proactively(self, diff_content: str):
        """사용자가 코드를 저장하고 잠깐 쉴 때(Debounce) 백그라운드에서 코드를 분석합니다."""
        # 아주 큰 diff는 무시 (CPU 보호)
        if len(diff_content) > 10000:
            return

        logger.info("Ambient Watchdog proactively analyzing recent changes...")

        prompt = f"""You are the Proactive Ambient Watchdog.

The user just saved some changes to the codebase, but hasn't asked you anything yet.
Look at this git diff and silently check for obvious syntax errors, logic bugs, or severe code smells.

DIFF:
{diff_content}

If the code looks fine, output exactly: 'OK'
If you spot a critical bug or an obvious typo that will crash, generate a proactive
notification message that we will subtly show to the user.
Format your warning starting with '⚠️ [Proactive Notice] ...'
Keep it very brief, like a friend tapping them on the shoulder.
"""
        try:
            response = self.model_manager.generate(
                prompt,
                target="reasoning-balanced",
                model_id="default",
            )
            response = response.strip()

            if response != "OK" and response.startswith("⚠️"):
                # 알림 큐에 삽입
                self._queue_notification(response, source="watchdog")
                logger.info("Proactive Watchdog queued a notification.")
        except Exception:
            logger.exception("Proactive analysis failed")

    def pop_notifications(self) -> list[str]:
        """오케스트레이터가 주기적으로 호출하여 알림을 가져갑니다."""
        try:
            pending = self._alert_store.pending()
        except OperationalAlertStoreError:
            logger.exception("Operational alert read failed")
            pending = ()
        if not self.notification_queue and not pending:
            return []
        notifs = list(self.notification_queue)
        self.notification_queue.clear()
        pending_ids: list[str] = []
        known_messages = set(notifs)
        for alert in pending:
            pending_ids.append(alert.alert_id)
            if alert.message not in known_messages:
                notifs.append(alert.message)
                known_messages.add(alert.message)
        try:
            self._alert_store.acknowledge(pending_ids)
        except OperationalAlertStoreError:
            logger.exception("Operational alert acknowledgement failed")
        return notifs
