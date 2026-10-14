"""Computer Use Tool — 데스크탑 자동화 도구.

==========================================
os-ai-computer-use 프레임워크의 핵심 패턴을 Ssak-Ai의 BaseTool 인터페이스에
맞춰 이식한 도구입니다.

에이전트가 이 도구를 호출하면 실제 마우스/키보드/스크린샷 명령이 실행됩니다.

보안:
  - ActionGuard를 통한 사전 검증
  - 위험 영역 클릭 자동 차단
  - HITL(Human-In-The-Loop) 게이트 지원
"""

import logging
from collections.abc import Mapping
from typing import final, override

from ..security.computer_use_guard import ActionGuard
from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from .os_drivers import DriverSet, get_driver_set

logger = logging.getLogger(__name__)

type ActionValue = str | int | float | bool | None
type ActionResultValue = str | int | float | dict[str, int]
type ActionResult = dict[str, ActionResultValue]
type SchemaValue = str | int | bool | list[str] | Mapping[str, "SchemaValue"]


def _int_arg(args: dict[str, ActionValue], key: str, default: int = 0) -> int:
    value = args.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _float_arg(args: dict[str, ActionValue], key: str, default: float) -> float:
    value = args.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _str_arg(args: dict[str, ActionValue], key: str, default: str = "") -> str:
    value = args.get(key)
    return value if isinstance(value, str) else default


def _action_params(kwargs: Mapping[str, object]) -> dict[str, ActionValue]:
    return {key: value for key, value in kwargs.items() if value is None or isinstance(value, (str, int, float, bool))}


@final
class ComputerUseTool(BaseTool):
    """AI 에이전트가 사용자의 데스크탑을 조작할 수 있는 도구.

    지원 액션:
      - screenshot: 화면 캡처 (base64 PNG 반환)
      - mouse_move: 마우스 이동
      - left_click / right_click / double_click: 클릭
      - type: 텍스트 타이핑
      - key: 키 입력 (단일 또는 조합)
      - scroll: 스크롤
    """

    # tiptap-vuetify 메타데이터 패턴 적용
    category = ToolCategory.COMPUTER_USE
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.CRITICAL
    icon = "🖥️"
    tags = ["desktop", "automation", "gui", "mouse", "keyboard"]

    def __init__(
        self,
        driver_set: DriverSet | None = None,
        guard: ActionGuard | None = None,
        force_stub: bool = False,
    ):
        """Initialize the ComputerUseTool.

        Args:
            driver_set (DriverSet): DriverSet driver set.
            guard (ActionGuard): ActionGuard guard.
            force_stub (bool): bool force stub.

        """
        super().__init__()
        self._name = "computer_use"
        self._description = (
            "Control the user's desktop: take screenshots, move/click mouse, "
            "type text, press keys, and scroll. Use this when you need to interact "
            "with GUI applications on the user's computer."
        )
        self._schema: dict[str, SchemaValue] = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "screenshot",
                        "mouse_move",
                        "left_click",
                        "right_click",
                        "double_click",
                        "left_click_drag",
                        "type",
                        "key",
                        "hold_key",
                        "scroll",
                    ],
                    "description": "The desktop action to perform.",
                },
                "x": {"type": "integer", "description": "X coordinate (for mouse actions)."},
                "y": {"type": "integer", "description": "Y coordinate (for mouse actions)."},
                "end_x": {"type": "integer", "description": "End X coordinate (for drag action)."},
                "end_y": {"type": "integer", "description": "End Y coordinate (for drag action)."},
                "text": {"type": "string", "description": "Text to type (for 'type' action)."},
                "key_combo": {
                    "type": "string",
                    "description": "Key or key combo (for 'key' action, e.g. 'ctrl+c').",
                },
                "duration": {
                    "type": "number",
                    "description": "Duration in seconds (for drag or hold_key actions).",
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Scroll direction.",
                },
                "amount": {"type": "integer", "description": "Scroll amount (default 3)."},
            },
            "required": ["action"],
        }

        # 드라이버 셋 (OS 추상화 계층) — 첫 실행까지 프로브를 미룬다 (CLI 시작 잡음 제거)
        self._driver_set_override = driver_set
        self._force_stub = force_stub
        self._resolved_drivers: DriverSet | None = None

        # 보안 게이트
        self._guard = guard or ActionGuard()

    @property
    def _drivers(self) -> DriverSet:
        if self._resolved_drivers is None:
            self._resolved_drivers = self._driver_set_override or get_driver_set(force_stub=self._force_stub)
        return self._resolved_drivers

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return self._name

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return self._description

    @property
    @override
    def parameters_schema(self) -> dict[str, SchemaValue]:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> ActionResult:
        """액션을 실행합니다."""
        params = _action_params(kwargs)
        action_value = params.get("action")
        if not action_value:
            return {"error": "No action specified."}
        if not isinstance(action_value, str):
            return {"error": f"Unknown action: {action_value}"}
        action = action_value

        # 해상도 주입 (위험 영역 검사용)
        try:
            screen_w, screen_h = self._drivers.screen.get_screen_size()
            params["screen_width"] = screen_w
            params["screen_height"] = screen_h
        except Exception:
            logger.exception("Could not get screen size for validation")

        # ── 보안 검증 ──
        validation = self._guard.validate_action(action, params)
        if not validation["allowed"]:
            return {"error": f"Action blocked: {validation['reason']}"}

        if validation.get("requires_hitl"):
            logger.warning("[HITL] Action '%s' requires human approval.", action)
            # 비대화형 환경에서는 자동 차단
            return {"error": f"Action '{action}' requires human approval (HITL)."}

        # ── 액션 디스패치 ──
        try:
            handlers = {
                "screenshot": self._action_screenshot,
                "mouse_move": self._action_mouse_move,
                "left_click": self._action_left_click,
                "right_click": self._action_right_click,
                "double_click": self._action_double_click,
                "left_click_drag": self._action_left_click_drag,
                "type": self._action_type,
                "key": self._action_key,
                "hold_key": self._action_hold_key,
                "scroll": self._action_scroll,
            }
            handler = handlers.get(action)
            if handler is None:
                return {"error": f"Unknown action: {action}"}
            return handler(**params)
        except Exception as e:
            logger.error("Computer use error [%s]: %s", action, e, exc_info=True)
            return {"error": f"Failed to execute '{action}': {str(e)}"}

    # ────────────────── 개별 액션 핸들러 ──────────────────

    def _action_screenshot(self, **kwargs: ActionValue) -> ActionResult:
        """화면을 캡처합니다."""
        _ = kwargs
        base64_png = self._drivers.screen.screenshot()
        width, height = self._drivers.screen.get_screen_size()
        return {
            "type": "screenshot",
            "image_base64": base64_png,
            "screen_size": {"width": width, "height": height},
        }

    def _action_mouse_move(self, **kwargs: ActionValue) -> ActionResult:
        """마우스를 이동합니다."""
        x, y = _int_arg(kwargs, "x"), _int_arg(kwargs, "y")
        self._drivers.mouse.move(x, y)
        return {"status": "ok", "action": "mouse_move", "position": {"x": x, "y": y}}

    def _action_left_click(self, **kwargs: ActionValue) -> ActionResult:
        """왼쪽 클릭합니다."""
        x, y = _int_arg(kwargs, "x"), _int_arg(kwargs, "y")
        self._drivers.mouse.click(x, y, button="left")
        return {"status": "ok", "action": "left_click", "position": {"x": x, "y": y}}

    def _action_right_click(self, **kwargs: ActionValue) -> ActionResult:
        """오른쪽 클릭합니다."""
        x, y = _int_arg(kwargs, "x"), _int_arg(kwargs, "y")
        self._drivers.mouse.click(x, y, button="right")
        return {"status": "ok", "action": "right_click", "position": {"x": x, "y": y}}

    def _action_double_click(self, **kwargs: ActionValue) -> ActionResult:
        """더블 클릭합니다."""
        x, y = _int_arg(kwargs, "x"), _int_arg(kwargs, "y")
        self._drivers.mouse.double_click(x, y)
        return {"status": "ok", "action": "double_click", "position": {"x": x, "y": y}}

    def _action_left_click_drag(self, **kwargs: ActionValue) -> ActionResult:
        """드래그합니다."""
        start_x, start_y = _int_arg(kwargs, "x"), _int_arg(kwargs, "y")
        end_x, end_y = _int_arg(kwargs, "end_x"), _int_arg(kwargs, "end_y")
        duration = _float_arg(kwargs, "duration", 0.5)
        self._drivers.mouse.drag(start_x, start_y, end_x, end_y, duration=duration)
        return {
            "status": "ok",
            "action": "left_click_drag",
            "start": {"x": start_x, "y": start_y},
            "end": {"x": end_x, "y": end_y},
        }

    def _action_type(self, **kwargs: ActionValue) -> ActionResult:
        """텍스트를 타이핑합니다."""
        text = _str_arg(kwargs, "text")
        if not text:
            return {"error": "No text provided for 'type' action."}
        self._drivers.keyboard.type_text(text)
        return {"status": "ok", "action": "type", "text_length": len(text)}

    def _action_key(self, **kwargs: ActionValue) -> ActionResult:
        """키를 입력합니다."""
        key_combo = _str_arg(kwargs, "key_combo")
        if not key_combo:
            return {"error": "No key_combo provided for 'key' action."}

        # 조합 키 (예: 'ctrl+c') 처리
        keys = [k.strip() for k in key_combo.split("+")]
        if len(keys) > 1:
            self._drivers.keyboard.hotkey(*keys)
        else:
            self._drivers.keyboard.press_key(keys[0])

        return {"status": "ok", "action": "key", "key_combo": key_combo}

    def _action_hold_key(self, **kwargs: ActionValue) -> ActionResult:
        """키를 홀드합니다."""
        key_combo = _str_arg(kwargs, "key_combo")
        duration = _float_arg(kwargs, "duration", 1.0)
        if not key_combo:
            return {"error": "No key_combo provided for 'hold_key' action."}

        keys = [k.strip() for k in key_combo.split("+")]
        self._drivers.keyboard.hold_key(keys[0], duration=duration)
        return {"status": "ok", "action": "hold_key", "key": keys[0], "duration": duration}

    def _action_scroll(self, **kwargs: ActionValue) -> ActionResult:
        """스크롤합니다."""
        x, y = _int_arg(kwargs, "x"), _int_arg(kwargs, "y")
        direction = _str_arg(kwargs, "direction", "down")
        amount = _int_arg(kwargs, "amount", 3)
        self._drivers.mouse.scroll(x, y, direction=direction, amount=amount)
        return {
            "status": "ok",
            "action": "scroll",
            "position": {"x": x, "y": y},
            "direction": direction,
            "amount": amount,
        }
