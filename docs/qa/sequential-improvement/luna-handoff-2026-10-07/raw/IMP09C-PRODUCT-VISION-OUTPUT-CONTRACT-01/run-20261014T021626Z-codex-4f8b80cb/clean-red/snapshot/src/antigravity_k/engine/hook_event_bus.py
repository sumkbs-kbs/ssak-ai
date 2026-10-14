"""HookEventBus — 파일 기반 실시간 이벤트 IPC.

==============================================
Sidabari의 hooks_bus.rs + HookBridge.tsx 패턴을 Python으로 이식.

JSONL 파일(events.jsonl)을 통한 프로세스 간 실시간 이벤트 전달.
watchdog 라이브러리로 파일 변경을 감지하고, 새 라인만 파싱하여
기존 인메모리 EventBus에 브릿지합니다.

디렉토리 구조 (init에서 생성):
  vault_data/hooks/
    events.jsonl           (append-only, tail 대상)
    req-<uuid>.json        (gate 요청, 임시)
    resp-<uuid>.json       (gate 응답, 임시)

보안:
  - 디렉토리 권한 0700 (Unix)
  - events.jsonl에는 도구 호출 데이터가 포함될 수 있으므로 외부 노출 금지
  - resp 작성 권한이 곧 gate 결정 권한 — 다른 사용자 위장 불가
"""

from __future__ import annotations

import json
import logging
import os
import platform
import stat
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast, final

logger = logging.getLogger("antigravity_k.engine.hook_event_bus")

HOOKS_SUBDIR = "hooks"
EVENTS_FILE = "events.jsonl"

# 이벤트 분류 매핑 (Sidabari의 classify_event 패턴)
EVENT_KIND_MAP = {
    "Stop": "stop",
    "PreToolUse": "pretool",
    "PostToolUse": "posttool",
    "Notification": "notification",
    "SessionStart": "session-start",
    "SubagentStop": "subagent-stop",
    "UserPromptSubmit": "user-prompt",
    "ToolExecutionStarted": "tool-exec-start",
    "ToolExecutionFinished": "tool-exec-finish",
    "AgentTurnStarted": "agent-turn-start",
    "AgentTurnEnded": "agent-turn-end",
    "QualityCheckPassed": "quality-pass",
    "QualityCheckFailed": "quality-fail",
    "FailureDetected": "failure-detected",
    "FailureRecovered": "failure-recovered",
}


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def _as_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _parse_json(value: str) -> object:
    return cast(object, json.loads(value))


def classify_event(payload: Mapping[str, object]) -> str:
    """이벤트 페이로드에서 종류를 분류합니다 (Sidabari classify_event 이식)."""
    # _antigravity 메타데이터에서 먼저 확인
    meta = _as_mapping(payload.get("_antigravity"))
    raw = _as_str(meta.get("hook_event_name_arg"))
    if not raw:
        raw = _as_str(payload.get("hook_event_name"))
    if not raw:
        raw = _as_str(payload.get("event"))
    if not raw:
        return "unknown"
    return EVENT_KIND_MAP.get(raw, f"other:{raw}")


@final
class HookEventEmit:
    """프론트엔드/대시보드로 방출할 훅 이벤트 구조체."""

    __slots__: tuple[str, ...] = ("kind", "payload", "timestamp")
    kind: str
    payload: Mapping[str, object]
    timestamp: float

    def __init__(self, kind: str, payload: Mapping[str, object]):
        """Initialize the HookEventEmit.

        Args:
            kind (str): str kind.
            payload (dict[str, Any]): dict[str, Any] payload.

        """
        self.kind = kind
        self.payload = payload
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, object]:
        """To Dict.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "kind": self.kind,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


@final
class GateRequest:
    """양방향 IPC Gate 요청 (Sidabari의 req-/resp- 파일 패턴)."""

    __slots__: tuple[str, ...] = ("hook_event_name", "panel_id", "payload", "request_id")
    hook_event_name: str
    panel_id: str | None
    payload: Mapping[str, object]
    request_id: str

    def __init__(
        self,
        request_id: str,
        panel_id: str | None,
        hook_event_name: str,
        payload: Mapping[str, object],
    ):
        """Initialize the GateRequest.

        Args:
            request_id (str): str request id.
            panel_id (str | None): str | None panel id.
            hook_event_name (str): str hook event name.
            payload (dict[str, Any]): dict[str, Any] payload.

        """
        self.request_id = request_id
        self.panel_id = panel_id
        self.hook_event_name = hook_event_name
        self.payload = payload


class HookEventBus:
    """파일 기반 실시간 이벤트 IPC 버스.

    Sidabari hooks_bus.rs의 Python 이식.
    JSONL 파일을 통한 프로세스 간 이벤트 전달 + 인메모리 EventBus 브릿지.
    """

    def __init__(self, base_dir: str | None = None):
        """Initialize the HookEventBus.

        Args:
            base_dir (str | None): str | None base dir.

        """
        self._base_dir: Path | None = Path(base_dir) if base_dir else None
        self._events_path: Path | None = None
        self._offset: int = 0
        self._subscribers: dict[str, list[Callable[[HookEventEmit], object]]] = {}
        self._watcher_thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self._lock: threading.Lock = threading.Lock()
        self._initialized: bool = False

    def init(self, vault_data_dir: str | None = None) -> HookEventBus:
        """이벤트 버스를 초기화합니다.

        디렉토리 생성, 권한 설정, 잔여 파일 sweep, watcher 시작.
        """
        if self._initialized:
            return self

        if vault_data_dir:
            self._base_dir = Path(vault_data_dir) / HOOKS_SUBDIR
        elif self._base_dir is None:
            try:
                from antigravity_k.config import config

                self._base_dir = config.paths.data_dir / "vault_data" / HOOKS_SUBDIR
            except Exception:
                project_root = Path(__file__).resolve().parent.parent.parent.parent
                self._base_dir = project_root / "vault_data" / HOOKS_SUBDIR

        # 디렉토리 생성 및 권한 확인 (읽기 전용 환경 폴백)
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            test_file = self._base_dir / f".agk_write_test_{os.getpid()}"
            test_file.touch()
            test_file.unlink()
        except OSError:
            self._base_dir = Path.home() / ".antigravity-k" / "vault_data" / HOOKS_SUBDIR
            self._base_dir.mkdir(parents=True, exist_ok=True)

        # Unix 권한 설정 (0700)
        if platform.system() != "Windows":
            try:
                os.chmod(self._base_dir, stat.S_IRWXU)
            except OSError as e:
                logger.warning("[HookEventBus] 디렉토리 권한 설정 실패: %s", e)

        # events.jsonl 생성/확인
        self._events_path = self._base_dir / EVENTS_FILE
        if not self._events_path.exists():
            _ = self._events_path.write_text("", encoding="utf-8")

        # 시작 시점의 파일 끝을 기준 offset으로 (과거 이벤트 무시)
        self._offset = self._events_path.stat().st_size

        # 잔여 req-/resp- 파일 sweep
        self._sweep_stale()

        # Watcher 스레드 시작
        self._stop_event.clear()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="hook-event-watcher",
        )
        self._watcher_thread.start()
        self._initialized = True

        logger.info(
            "[HookEventBus] Initialized at %s, start_offset=%s",
            self._base_dir,
            self._offset,
        )
        return self

    def shutdown(self) -> None:
        """Watcher를 종료합니다."""
        self._stop_event.set()
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=3.0)
        self._initialized = False
        logger.info("[HookEventBus] Shut down")

    # ── 이벤트 발행 ──

    def emit_event(
        self,
        event_name: str,
        payload: Mapping[str, object] | None = None,
        *,
        panel_id: str | None = None,
    ) -> None:
        """이벤트를 JSONL 파일에 기록합니다.

        기록 후 watcher가 자동으로 파싱하여 구독자에게 전달합니다.
        """
        if not self._initialized or not self._events_path:
            logger.warning("[HookEventBus] Not initialized, cannot emit")
            return

        event_data: dict[str, object] = {
            "hook_event_name": event_name,
            "timestamp": time.time(),
            **(payload or {}),
        }
        if panel_id:
            metadata = _as_mapping(event_data.get("_antigravity"))
            metadata_dict = dict(metadata)
            metadata_dict["panel_id"] = panel_id
            event_data["_antigravity"] = metadata_dict

        try:
            line = json.dumps(event_data, ensure_ascii=False, default=str) + "\n"
            with open(self._events_path, "a", encoding="utf-8") as f:
                _ = f.write(line)
        except Exception:
            logger.exception("[HookEventBus] 이벤트 기록 실패")

    def emit(self, event: HookEventEmit) -> None:
        self._dispatch(event)

    # ── 이벤트 구독 ──

    def subscribe(self, kind: str, callback: Callable[[HookEventEmit], object]) -> None:
        """특정 종류의 이벤트에 콜백을 등록합니다."""
        with self._lock:
            if kind not in self._subscribers:
                self._subscribers[kind] = []
            if callback not in self._subscribers[kind]:
                self._subscribers[kind].append(callback)

    def subscribe_all(self, callback: Callable[[HookEventEmit], object]) -> None:
        """모든 이벤트에 콜백을 등록합니다."""
        self.subscribe("*", callback)

    def unsubscribe(self, kind: str, callback: Callable[[HookEventEmit], object]) -> None:
        """이벤트 구독을 해제합니다."""
        with self._lock:
            if kind in self._subscribers and callback in self._subscribers[kind]:
                self._subscribers[kind].remove(callback)

    # ── Gate 메커니즘 (양방향 IPC) ──

    def send_gate_request(
        self,
        hook_event_name: str,
        payload: Mapping[str, object],
        *,
        panel_id: str | None = None,
        timeout: float = 30.0,
    ) -> dict[str, object] | None:
        """Gate 요청을 보내고 응답을 대기합니다.

        req-<uuid>.json 작성 후 resp-<uuid>.json이 나타날 때까지 대기.
        """
        if not self._base_dir:
            return None

        request_id = str(uuid.uuid4())
        req_path = self._base_dir / f"req-{request_id}.json"
        resp_path = self._base_dir / f"resp-{request_id}.json"

        req_data = {
            "request_id": request_id,
            "hook_event_name_arg": hook_event_name,
            "panel_id": panel_id,
            **payload,
        }

        try:
            # Atomic write via tmp file
            tmp_path = req_path.with_suffix(".json.tmp")
            _ = tmp_path.write_text(json.dumps(req_data, ensure_ascii=False), encoding="utf-8")
            _ = tmp_path.rename(req_path)
        except Exception:
            logger.exception("[HookEventBus] Gate 요청 작성 실패")
            return None

        # 응답 대기 (polling)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if resp_path.exists():
                try:
                    parsed_response = _parse_json(resp_path.read_text(encoding="utf-8"))
                    resp_data = _as_object(parsed_response)
                    # Cleanup
                    req_path.unlink(missing_ok=True)
                    resp_path.unlink(missing_ok=True)
                    return resp_data
                except Exception:
                    logger.exception("[HookEventBus] Gate 응답 읽기 실패")
                    return None
            time.sleep(0.1)

        # Timeout — cleanup
        req_path.unlink(missing_ok=True)
        logger.warning("[HookEventBus] Gate 응답 타임아웃: %s", request_id)
        return None

    def respond_gate(
        self,
        request_id: str,
        decision: str,
        reason: str = "",
    ) -> bool:
        """Gate 요청에 응답합니다.

        외부 프로세스나 대시보드가 호출합니다.
        """
        if not self._base_dir or not request_id.strip():
            return False

        valid_decisions = {"allow", "deny", "ask", "defer"}
        if decision not in valid_decisions:
            logger.error("[HookEventBus] 유효하지 않은 decision: %s", decision)
            return False

        resp_path = self._base_dir / f"resp-{request_id}.json"
        tmp_path = self._base_dir / f"resp-{request_id}.json.tmp"

        body = {
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }

        try:
            _ = tmp_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            _ = tmp_path.rename(resp_path)
            return True
        except Exception:
            logger.exception("[HookEventBus] Gate 응답 작성 실패")
            return False

    # ── 내부 Watcher ──

    def _watch_loop(self) -> None:
        """JSONL 파일과 req- 파일을 폴링으로 감시합니다.

        watchdog가 설치되어 있으면 이벤트 기반, 아니면 폴링 폴백.
        """
        poll_interval = 0.3  # seconds

        while not self._stop_event.is_set():
            try:
                self._tail_events()
                self._check_req_files()
            except Exception:
                logger.exception("[HookEventBus] Watch loop error")

            _ = self._stop_event.wait(poll_interval)

    def _tail_events(self) -> None:
        """events.jsonl의 새로운 라인을 읽어 구독자에게 전달합니다."""
        if not self._events_path or not self._events_path.exists():
            return

        try:
            current_size = self._events_path.stat().st_size
        except OSError:
            return

        # truncate/rotate 감지
        if current_size < self._offset:
            self._offset = 0

        if current_size == self._offset:
            return

        try:
            with open(self._events_path, encoding="utf-8") as f:
                _ = f.seek(self._offset)
                new_offset = self._offset

                for line in f:
                    new_offset += len(line.encode("utf-8"))
                    trimmed = line.strip()
                    if not trimmed:
                        continue

                    try:
                        parsed_payload = _parse_json(trimmed)
                        payload = _as_object(parsed_payload)
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "[HookEventBus] JSON 파싱 실패: %s (line %s bytes)",
                            e,
                            len(trimmed),
                        )
                        continue

                    kind = classify_event(payload)
                    event = HookEventEmit(kind=kind, payload=payload)
                    self._dispatch(event)

                self._offset = new_offset
        except Exception:
            logger.exception("[HookEventBus] tail 실패")

    def _check_req_files(self) -> None:
        """req-*.json 파일을 확인하여 gate 요청 이벤트를 발생시킵니다."""
        if not self._base_dir:
            return

        try:
            for entry in self._base_dir.iterdir():
                name = entry.name
                if name.startswith("req-") and name.endswith(".json"):
                    self._handle_req_file(entry)
        except Exception:
            logger.exception("[HookEventBus] req 파일 확인 실패")

    def _handle_req_file(self, path: Path) -> None:
        """Req 파일을 읽어 gate-request 이벤트를 발생시킵니다."""
        try:
            parsed_data = _parse_json(path.read_text(encoding="utf-8"))
            data = _as_object(parsed_data)
        except (OSError, ValueError):
            # Windows: atomic rename 직후 읽기 실패 → 짧은 재시도
            time.sleep(0.05)
            try:
                parsed_data = _parse_json(path.read_text(encoding="utf-8"))
                data = _as_object(parsed_data)
            except (OSError, ValueError):
                logger.exception("[HookEventBus] req 읽기 실패 (%s)", path)
                return

        request = GateRequest(
            request_id=_as_str(data.get("request_id")),
            panel_id=_as_optional_str(data.get("panel_id")),
            hook_event_name=_as_str(data.get("hook_event_name_arg")),
            payload=data,
        )
        gate_event = HookEventEmit(
            kind="gate-request",
            payload={
                "request_id": request.request_id,
                "panel_id": request.panel_id,
                "hook_event_name": request.hook_event_name,
                "data": request.payload,
            },
        )
        self._dispatch(gate_event)

    def _dispatch(self, event: HookEventEmit) -> None:
        """구독자에게 이벤트를 전달합니다."""
        with self._lock:
            # kind 별 구독자
            for callback in self._subscribers.get(event.kind, []):
                try:
                    _ = callback(event)
                except Exception:
                    logger.exception("[HookEventBus] 콜백 실행 오류 (%s)", event.kind)
            # 와일드카드 구독자
            for callback in self._subscribers.get("*", []):
                try:
                    _ = callback(event)
                except Exception:
                    logger.exception("[HookEventBus] 와일드카드 콜백 오류 (%s)", event.kind)

    def _sweep_stale(self) -> None:
        """시작 시 잔여 req-/resp- 파일을 제거합니다."""
        if not self._base_dir:
            return

        try:
            for entry in self._base_dir.iterdir():
                name = entry.name
                if name.startswith(("req-", "resp-")) and name.endswith((".json", ".tmp")):
                    try:
                        entry.unlink()
                    except OSError:
                        logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
        except Exception:
            logger.exception("Unhandled exception")

    @property
    def base_dir(self) -> Path | None:
        """Base Dir.

        Returns:
            Path | None: The path | none result.

        """
        return self._base_dir

    @property
    def events_path(self) -> Path | None:
        """Events Path.

        Returns:
            Path | None: The path | none result.

        """
        return self._events_path


# ── 글로벌 싱글톤 ──

_global_hook_bus: HookEventBus | None = None
_global_lock = threading.Lock()


def get_hook_event_bus() -> HookEventBus:
    """글로벌 HookEventBus 인스턴스를 반환합니다."""
    global _global_hook_bus
    if _global_hook_bus is None:
        with _global_lock:
            if _global_hook_bus is None:
                _global_hook_bus = HookEventBus()
    return _global_hook_bus


def init_hook_event_bus(vault_data_dir: str | None = None) -> HookEventBus:
    """글로벌 HookEventBus를 초기화합니다."""
    bus = get_hook_event_bus()
    _ = bus.init(vault_data_dir)
    return bus
