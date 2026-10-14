"""Message Bus module."""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

logger = logging.getLogger(__name__)

type MessageValue = str | int | float | bool | None | list[MessageValue] | dict[str, MessageValue]
type MessageRecord = dict[str, MessageValue]


class _AgentSubscriber(Protocol):
    name: str

    def add_message(self, role: str, content: str) -> None: ...


class MessageBus:
    """에이전트 간의 통신(Message Passing)을 담당하는 클래스.

    Claude Agent Teams 아키텍처에서 에이전트들이 서로 피드백을 주고받거나
    작업 상태를 업데이트할 때 사용됩니다.
    """

    def __init__(self) -> None:
        """Initialize the MessageBus."""
        self.channels: dict[str, list[MessageRecord]] = {
            "general": [],  # 기본 채널
        }
        self.subscribers: dict[str, list[_AgentSubscriber]] = {"general": []}
        self.callbacks: dict[str, list[Callable[[MessageRecord], None]]] = {"general": []}

    def create_channel(self, channel_name: str) -> None:
        """Create channel.

        Args:
            channel_name (str): str channel name.

        """
        if channel_name not in self.channels:
            self.channels[channel_name] = []
            self.subscribers[channel_name] = []
            self.callbacks[channel_name] = []
            logger.info("Message channel '%s' created.", channel_name)

    def subscribe(self, channel_name: str, agent: _AgentSubscriber) -> None:
        """Subscribe.

        Args:
            channel_name (str): str channel name.
            agent: agent.

        """
        if channel_name not in self.subscribers:
            self.create_channel(channel_name)
        if agent not in self.subscribers[channel_name]:
            self.subscribers[channel_name].append(agent)
            logger.info("Agent '%s' subscribed to '%s'.", agent.name, channel_name)

    def subscribe_callback(self, channel_name: str, callback: Callable[[MessageRecord], None]) -> None:
        """특정 채널에 콜백 함수를 등록하여 이벤트 기반 처리를 지원합니다."""
        if channel_name not in self.callbacks:
            self.create_channel(channel_name)
        if callback not in self.callbacks[channel_name]:
            self.callbacks[channel_name].append(callback)
            logger.info("Callback registered for channel '%s'.", channel_name)

    def publish(
        self,
        channel_name: str,
        sender: str,
        message: str,
        meta: dict[str, MessageValue] | None = None,
    ) -> None:
        """특정 채널에 메시지를 발행합니다."""
        if channel_name not in self.channels:
            logger.warning("Channel '%s' does not exist.", channel_name)
            return

        msg_obj: MessageRecord = {
            "timestamp": datetime.now().isoformat(),
            "sender": sender,
            "message": message,
            "meta": meta or {},
        }
        self.channels[channel_name].append(msg_obj)
        logger.debug("[%s] %s: %s", channel_name, sender, message)

        # 1. 일반 구독자(에이전트)들에게 메시지 전달
        for agent in self.subscribers[channel_name]:
            # 에이전트의 내부 컨텍스트에 추가
            agent.add_message("user", f"[{sender} via {channel_name}]: {message}")

        # 2. 콜백 구독자들에게 이벤트 전달 (Pub-Sub 콜백 실행)
        for cb in self.callbacks[channel_name]:
            try:
                cb(msg_obj)
            except Exception:
                logger.exception("Error executing callback on channel '%s'", channel_name)

    def get_history(self, channel_name: str) -> list[MessageRecord]:
        """Retrieve history.

        Args:
            channel_name (str): str channel name.

        Returns:
            list[dict[str, Any]]: The list[dict[str, any]] result.

        """
        return self.channels.get(channel_name, [])
