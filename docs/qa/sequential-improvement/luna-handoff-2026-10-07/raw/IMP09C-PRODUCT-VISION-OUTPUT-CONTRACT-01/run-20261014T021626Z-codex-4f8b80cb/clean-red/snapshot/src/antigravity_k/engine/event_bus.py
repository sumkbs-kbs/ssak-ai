"""Event Bus module."""

import asyncio
import inspect
import logging
import os
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from pathlib import Path
from typing import Protocol, cast

logger = logging.getLogger(__name__)

# HookEventBus의 hook kind → plain EventBus 이벤트 이름 변환 (브릿지 전용).
# 직접 발행자가 있는 이벤트(ToolExecutionStarted/Finished, FailureDetected 등)는
# 이중 발행을 막기 위해 여기에 넣지 않는다 — 이 목록은 반드시 "직접 발행자가 없는"
# 이벤트만 담아야 한다. 추가/삭제 시 tests/test_event_bus.py의 브릿지 테스트와
# tests/test_events.py의 발행자 문서화 테스트를 함께 갱신할 것.
HOOK_KIND_TO_EVENT_NAME: dict[str, str] = {
    "agent-turn-start": "AgentTurnStarted",
    "agent-turn-end": "AgentTurnEnded",
}


class _SyncCallback(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


class _AsyncCallback(Protocol):
    def __call__(self, **kwargs: object) -> Awaitable[object]: ...


CallbackType = _SyncCallback | _AsyncCallback


def _callback_name(callback: CallbackType) -> str:
    name = getattr(callback, "__name__", "callback")
    return name if isinstance(name, str) else "callback"


class _PersistentAgencyLike(Protocol):
    def record_external_event(
        self,
        project_id: str,
        trajectory_id: str,
        event_name: str,
        payload: Mapping[str, object] | None = None,
    ) -> object: ...


class _HookEventBusLike(Protocol):
    def subscribe_all(self, callback: Callable[[object], object]) -> None: ...

    def emit_event(self, event_name: str, payload: Mapping[str, object]) -> None: ...


class EventBus:
    """비동기/동기 이벤트 버스 (Pub/Sub).

    Ssak-Ai의 단일 동기 루프의 병목을 해소하고,
    다양한 모듈(인지, 로깅, UI)이 이벤트 기반으로 통신할 수 있게 합니다.
    """

    def __init__(self) -> None:
        """Initialize the EventBus."""
        self._subscribers: dict[str, list[CallbackType]] = {}

    def subscribe(self, event_name: str, callback: CallbackType) -> None:
        """특정 이벤트에 콜백을 등록합니다."""
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)
            logger.debug("[EventBus] Subscribed '%s' to '%s'", _callback_name(callback), event_name)

    def unsubscribe(self, event_name: str, callback: CallbackType) -> None:
        """특정 이벤트에서 콜백을 제거합니다."""
        if event_name in self._subscribers and callback in self._subscribers[event_name]:
            self._subscribers[event_name].remove(callback)

    def publish(self, event_name: str, **kwargs: object) -> None:
        """이벤트를 동기적으로 발생시킵니다.

        비동기 콜백은 백그라운드 태스크로 스케줄링됩니다.
        """
        if event_name not in self._subscribers:
            return

        for callback in self._subscribers[event_name]:
            try:
                if inspect.iscoroutinefunction(callback):
                    # 비동기 환경이면 태스크로 실행, 아니면 무시되거나 별도 런루프 필요 (여기선 백그라운드 스케줄 시도)
                    try:
                        loop = asyncio.get_running_loop()
                        _ = loop.create_task(cast(Coroutine[object, object, object], callback(**kwargs)))
                    except RuntimeError:
                        # 실행 중인 루프가 없으면 (순수 동기 환경) 동기적으로 실행
                        _ = asyncio.run(cast(Coroutine[object, object, object], callback(**kwargs)))
                else:
                    _ = callback(**kwargs)
            except Exception as e:
                logger.error(
                    "[EventBus] Error in callback '%s' for event '%s': %s",
                    _callback_name(callback),
                    event_name,
                    e,
                    exc_info=True,
                )

    async def publish_async(self, event_name: str, **kwargs: object) -> None:
        """이벤트를 비동기적으로 발생시킵니다."""
        if event_name not in self._subscribers:
            return

        tasks: list[Coroutine[object, object, object]] = []
        for callback in self._subscribers[event_name]:
            if inspect.iscoroutinefunction(callback):
                tasks.append(cast(Coroutine[object, object, object], callback(**kwargs)))
            else:
                try:
                    _ = callback(**kwargs)
                except Exception as e:
                    logger.error(
                        "[EventBus] Error in sync callback '%s': %s",
                        _callback_name(callback),
                        e,
                        exc_info=True,
                    )

        if tasks:
            _ = await asyncio.gather(*tasks, return_exceptions=True)


# 전역 싱글톤 인스턴스
global_event_bus = EventBus()


def attach_persistent_agency(
    controller: object,
    project_id: str,
    trajectory_id: str = "hooks",
    hook_bus: object | None = None,
) -> Callable[[object], None] | None:
    """Attach a durable observation sink to a HookEventBus instance."""
    bus = hook_bus
    if bus is None:
        from antigravity_k.engine.hook_event_bus import get_hook_event_bus

        bus = get_hook_event_bus()
    bus_like = cast(_HookEventBusLike, bus)
    default_bindings: set[tuple[int, str, str]] = set()
    bindings = cast(
        set[tuple[int, str, str]],
        getattr(bus, "_persistent_agency_bindings", default_bindings),
    )
    key = (id(controller), project_id, trajectory_id)
    if key in bindings:
        return None

    def on_hook_event(event: object) -> None:
        try:
            agency = cast(_PersistentAgencyLike, controller)
            payload_value = getattr(event, "payload", {})
            payload: Mapping[str, object] = (
                cast(Mapping[str, object], payload_value) if isinstance(payload_value, Mapping) else {}
            )
            _ = agency.record_external_event(
                project_id,
                trajectory_id,
                str(getattr(event, "kind", "unknown")),
                payload,
            )
        except Exception:
            logger.exception("[EventBus] persistent agency event record failed")

    bus_like.subscribe_all(on_hook_event)
    bindings.add(key)
    setattr(bus, "_persistent_agency_bindings", bindings)
    return on_hook_event


def bridge_to_hook_event_bus(
    project_root: str | None = None,
    persistent_agency: object | None = None,
) -> None:
    """HookEventBus와 글로벌 EventBus를 양방향 브릿지합니다.

    - EventBus.publish() → HookEventBus JSONL 파일에도 기록 (듀얼 싱크)
    - HookEventBus 이벤트 → EventBus 구독자에게도 전달
    """
    try:
        from antigravity_k.engine.hook_event_bus import get_hook_event_bus

        hook_bus = cast(_HookEventBusLike, get_hook_event_bus())

        if persistent_agency is None and project_root:
            from antigravity_k.engine.persistent_agency import PersistentAgencyController

            persistent_agency = PersistentAgencyController(project_root)
        if persistent_agency is not None:
            root = str(Path(project_root or os.getcwd()).resolve())
            _ = attach_persistent_agency(persistent_agency, root, hook_bus=hook_bus)

        # EventBus → HookEventBus 듀얼 싱크
        original_publish = global_event_bus.publish

        def dual_publish(event_name: str, **kwargs: object) -> None:
            _ = original_publish(event_name, **kwargs)
            # 파일 기반 영구 기록 (초기화된 경우에만)
            if bool(getattr(hook_bus, "_initialized", False)):
                hook_bus.emit_event(event_name, kwargs)

        setattr(global_event_bus, "publish", dual_publish)

        # HookEventBus → EventBus 브릿지
        def on_hook_event(event: object) -> None:
            kind = str(getattr(event, "kind", "unknown"))
            payload_value = getattr(event, "payload", {})
            payload: Mapping[str, object] = (
                cast(Mapping[str, object], payload_value) if isinstance(payload_value, Mapping) else {}
            )
            _ = original_publish(f"Hook:{kind}", **payload)
            # 직접 발행자가 없는 hook kind는 plain 이벤트 이름으로도 발행한다
            # (예: AgentTurnStarted/Ended → kanban_api 구독자 연동).
            plain_name = HOOK_KIND_TO_EVENT_NAME.get(kind)
            if plain_name is not None:
                _ = original_publish(plain_name, **payload)

        hook_bus.subscribe_all(on_hook_event)

        logger.info("[EventBus] HookEventBus 듀얼 싱크 브릿지 설정 완료")
    except ImportError:
        logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
    except Exception:
        logger.exception("[EventBus] HookEventBus 브릿지 설정 실패")
