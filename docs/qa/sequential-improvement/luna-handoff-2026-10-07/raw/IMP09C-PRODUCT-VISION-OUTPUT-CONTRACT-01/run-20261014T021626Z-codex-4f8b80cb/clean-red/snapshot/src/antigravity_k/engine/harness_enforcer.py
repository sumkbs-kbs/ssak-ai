"""Harness Enforcer module."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, NotRequired, TypedDict

from pydantic import TypeAdapter, ValidationError

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]
type JsonMap = dict[str, JsonValue]


class BoundaryResult(TypedDict):
    allowed: bool
    reason: str
    stall: NotRequired[bool]


_GUIDELINES_ADAPTER: TypeAdapter[JsonMap] = TypeAdapter(JsonMap)


@dataclass(frozen=True, slots=True)
class HarnessFeedbackAction:
    """Harnessfeedbackaction."""

    action_type: str = "continue"
    reason: str = ""


def load_longrun_harness_prompt(project_root: str = ".") -> str:
    """장기 자율 실행 하네스 프롬프트(prompts/harness_longrun_v1.md)를 로드한다.

    파일이 없거나 읽지 못하면 빈 문자열 — 호출자는 빈 값일 때 주입을 생략한다.
    """
    path = Path(project_root) / "prompts" / "harness_longrun_v1.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class HarnessEnforcer:
    """Small runtime boundary checker for tool calls inside the agent loop."""

    _BLOCKED_TOOLS: ClassVar[set[str]] = {"terminal_ws"}
    _DESTRUCTIVE_PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(r"\brm\s+-rf\s+/(?:\s|$)", re.IGNORECASE),
        re.compile(r"\b(format|mkfs|diskutil\s+erase|wipe)\b", re.IGNORECASE),
    )

    # AVO 스타일 스톨 감지: 동일 (tool, args-hash) 반복 임계. 2회째 시도는
    # 이미 반복이므로 차단하고 전략수정 프롬프트를 되돌려준다.
    STALL_REPEAT_THRESHOLD: ClassVar[int] = 2
    # 유사한 오류 메시지가 이 횟수만큼 모이면 같은 원인의 정체로 판정한다.
    STALL_ERROR_CLUSTER_THRESHOLD: ClassVar[int] = 3
    # 연속 실패(무진행) 행동이 이 개수를 채우면 목표 재분해를 요구한다.
    STALL_NO_PROGRESS_WINDOW: ClassVar[int] = 5

    def __init__(
        self,
        project_root: str = ".",
        strict_mode: bool = False,
        *,
        no_progress_window: int | None = None,
        error_cluster_threshold: int | None = None,
    ):
        """Initialize the HarnessEnforcer.

        Args:
            project_root (str): str project root.
            strict_mode (bool): bool strict mode.
            no_progress_window: 무진행 윈도우 임계값 오버라이드 (기본 클래스 상수).
                짧은 재시도 예산의 루프에서 감독축을 발화시키기 위한 보정용.
            error_cluster_threshold: 유사 오류 클러스터 임계값 오버라이드.

        """
        self.project_root: str = str(Path(project_root).resolve())
        self.strict_mode: bool = strict_mode
        self.no_progress_window: int = int(no_progress_window or self.STALL_NO_PROGRESS_WINDOW)
        self.error_cluster_threshold: int = int(error_cluster_threshold or self.STALL_ERROR_CLUSTER_THRESHOLD)
        self.guidelines: JsonMap = {}
        self._call_counts: dict[str, int] = {}
        self._error_clusters: dict[str, int] = {}
        self._outcome_window: list[bool] = []
        self._pending_intervention: str = ""

    def load_guidelines(self) -> None:
        """Load optional harness guidance when present."""
        candidates = [
            Path(self.project_root) / "harness.json",
            Path(self.project_root) / ".agent" / "harness.json",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                self.guidelines = _GUIDELINES_ADAPTER.validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError, json.JSONDecodeError):
                self.guidelines = {}
            return

    def reset_stall_tracking(self) -> None:
        """스톨 카운터를 초기화한다 (새 목표/세션 시작 시 호출)."""
        self._call_counts.clear()
        self._error_clusters.clear()
        self._outcome_window.clear()
        self._pending_intervention = ""

    @staticmethod
    def build_stall_message(tool_name: str) -> str:
        """스톨 차단 시 모델에 되돌려줄 전략수정 지시문."""
        return (
            f"[STALL DETECTED] 동일 도구·동일 인자 {HarnessEnforcer.STALL_REPEAT_THRESHOLD}회 반복\n"
            f"[폐기] {tool_name} 동일 인자 재시도\n"
            "[대안 가설] 같은 방식의 재시도는 금지다. 원인 분류 후 구조적으로 다른 "
            "접근 1개를 가설로 세우고 즉시 실행하라."
        )

    @staticmethod
    def _error_fingerprint(error_text: str) -> str:
        """오류 표면을 정규화해 동일 원인 판정용 지문을 뽑는다.

        숫자·따옴표 문자열·경로는 표면 차이일 뿐이므로 치환해 버린다.
        """
        lines = [line.strip() for line in (error_text or "").splitlines() if line.strip()]
        if not lines:
            return ""
        signature = lines[-1]
        signature = re.sub(r"\d+", "<N>", signature)
        signature = re.sub(r"[\"'][^\"']{4,}[\"']", "<Q>", signature)
        signature = re.sub(r"[\w./\\-]*[/\\][\w./\\-]+", "<P>", signature)
        return signature.lower()[:160]

    def record_outcome(self, failed: bool, error_text: str = "") -> None:
        """도구 실행 결과를 감독기에 적재한다 (check_after에서 호출).

        유사 오류 클러스터와 무진행 윈도우를 갱신하고, 임계 도달 시 1회용
        개입(STALL 지시문)을 예약한다 — 다음 허용 경계 검사에서 한 번만
        차단해 강제로 전략수정 한 턴을 벌린다.
        """
        self._outcome_window.append(bool(failed))
        if len(self._outcome_window) > self.no_progress_window:
            _ = self._outcome_window.pop(0)

        if not self._pending_intervention:
            if len(self._outcome_window) >= self.no_progress_window and all(self._outcome_window):
                self._pending_intervention = (
                    f"[STALL DETECTED] 진척 없는 행동 {self.no_progress_window}개 연속\n"
                    "[폐기] 현재 접근 방식 자체\n"
                    "[대안 가설] 목표를 서브골로 분해하고, 가장 작은 검증 가능한 단위부터 다시 실행하라."
                )
                return

            fingerprint = self._error_fingerprint(error_text)
            if fingerprint:
                count = self._error_clusters.get(fingerprint, 0) + 1
                self._error_clusters[fingerprint] = count
                if len(self._error_clusters) > 64:
                    self._error_clusters.clear()
                if count >= self.error_cluster_threshold:
                    self._error_clusters[fingerprint] = 0
                    self._pending_intervention = (
                        f"[STALL DETECTED] 유사한 오류 {self.error_cluster_threshold}회 반복\n"
                        f"[오류 지문] {fingerprint}\n"
                        "[폐기] 같은 원인을 건드리지 않는 표면적 수정\n"
                        "[대안 가설] 오류의 근본 원인을 한 문장으로 분류한 뒤, 그 원인을 직접 제거하는 접근으로 전환하라."
                    )

    def _consume_intervention_if_due(self) -> BoundaryResult | None:
        """예약된 개입이 있으면 한 번 반환하고 소비한다."""
        if self._pending_intervention:
            message = self._pending_intervention
            self._pending_intervention = ""
            return {"allowed": False, "reason": message, "stall": True}
        return None

    def consume_pending_intervention(self) -> BoundaryResult | None:
        """예약된 1회용 개입(STALL 지시문)을 반환하고 소비한다 (공개 API).

        미션 루프 밖의 재시도 루프(벤치마크 AVO 모드 등)에서도 동일한
        감독축(무진행 윈도우·유사 오류 클러스터)을 재사용하기 위한 창구다.
        """
        return self._consume_intervention_if_due()

    def check_tool_boundary(
        self,
        tool_name: str,
        tool_args: Mapping[str, JsonValue] | None = None,
    ) -> BoundaryResult:
        """Check Tool Boundary.

        Args:
            tool_name (str): str tool name.
            tool_args (dict | None): dict | None tool args.

        Returns:
            dict: The dict result. 스톨 감지 시 allowed=False + STALL 지시문.

        """
        args: Mapping[str, JsonValue] = tool_args or {}
        if tool_name in self._BLOCKED_TOOLS:
            return {"allowed": False, "reason": f"{tool_name} is not an agent tool"}

        command = str(args.get("command", ""))
        if any(pattern.search(command) for pattern in self._DESTRUCTIVE_PATTERNS):
            return {"allowed": False, "reason": "destructive shell command blocked"}

        path_value = args.get("path") or args.get("file_path") or args.get("target")
        if path_value and not self._path_allowed(str(path_value)):
            return {"allowed": False, "reason": "path is outside project boundary"}

        intervention = self._consume_intervention_if_due()
        if intervention is not None:
            return intervention

        if self._is_stalled(tool_name, args):
            return {
                "allowed": False,
                "reason": self.build_stall_message(tool_name),
                "stall": True,
            }

        return {"allowed": True, "reason": ""}

    def _is_stalled(self, tool_name: str, args: Mapping[str, JsonValue]) -> bool:
        """동일 (tool, args) 호출 횟수 기반 스톨 판정. 허용 경로만 카운트된다."""
        try:
            payload = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            payload = repr(args)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        key = f"{tool_name}:{digest}"
        count = self._call_counts.get(key, 0) + 1
        self._call_counts[key] = count
        return count >= self.STALL_REPEAT_THRESHOLD

    def feedback_loop(self, tool_result: str) -> HarnessFeedbackAction:
        """Feedback Loop.

        Args:
            tool_result (str): str tool result.

        Returns:
            HarnessFeedbackAction: The harnessfeedbackaction result.

        """
        lowered = (tool_result or "").lower()
        error_markers = ("traceback", "permission denied", "no such file", "error")
        if sum(marker in lowered for marker in error_markers) >= 2:
            return HarnessFeedbackAction("escalate", "repeated tool failure markers")
        return HarnessFeedbackAction()

    def _path_allowed(self, raw_path: str) -> bool:
        if not self.strict_mode:
            return True
        target = Path(raw_path)
        if not target.is_absolute():
            target = Path(self.project_root) / target
        try:
            _ = os.path.commonpath([self.project_root, str(target.resolve())])
        except ValueError:
            return False
        return os.path.commonpath([self.project_root, str(target.resolve())]) == self.project_root
