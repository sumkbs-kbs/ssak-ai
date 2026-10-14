"""Plan→Build 자동 전환 파이프라인 (PlanToBuildPipeline).

==========================================================
Phase 1 D4: Plan 아티팩트 완성 → 검증 → QualityGate → ModeManager 전환

사용법:
    pipeline = PlanToBuildPipeline(
        mode_manager=mode_manager,
        artifact_engine=artifact_engine,
        quality_gate=quality_gate,
        kanban_engine=kanban_engine,  # optional
    )
    result = pipeline.run()
    print(result.summary())
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, TypeAlias, TypedDict, final

from antigravity_k.engine.artifact_engine import PlanTask, PlanValidationResult
from antigravity_k.engine.execution_mode import ExecutionMode
from antigravity_k.engine.kanban_engine import KanbanBoard, KanbanTask
from antigravity_k.engine.mode_manager import ModeTransition
from antigravity_k.engine.quality_gate import QualityScore

logger = logging.getLogger(__name__)

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
JsonMap: TypeAlias = Mapping[str, JsonValue]


def _empty_json_map() -> JsonMap:
    return {}


class ValidationPayload(TypedDict):
    success: bool
    score: float
    task_count: int
    message: str
    details: JsonMap
    duration_ms: float


class QualityPayload(TypedDict):
    success: bool
    score: float
    grade: str
    message: str
    details: JsonMap
    warnings: list[str]
    duration_ms: float


class TransitionPayload(TypedDict):
    success: bool
    message: str
    details: JsonMap
    duration_ms: float


class KanbanPayload(TypedDict):
    success: bool
    task_count: int
    message: str
    details: JsonMap
    duration_ms: float


class AutoKanbanResult(TypedDict):
    success: bool
    board: KanbanBoard | None
    task_count: int
    message: str


class ArtifactEnginePort(Protocol):
    artifacts_dir: str

    def read_artifact(self, target_file: str) -> str | None: ...

    def validate_plan_complete(self, target_file: str = "implementation_plan.md") -> PlanValidationResult: ...

    def is_plan_ready_for_build(self, target_file: str = "implementation_plan.md") -> bool: ...

    def extract_plan_tasks(self, target_file: str = "implementation_plan.md") -> list[PlanTask]: ...

    def auto_create_kanban_tasks(self, target_file: str = "implementation_plan.md") -> Mapping[str, object]: ...


class ModeManagerPort(Protocol):
    @property
    def current_mode(self) -> ExecutionMode: ...

    @property
    def plan_artifact_path(self) -> str | None: ...

    @property
    def plan_quality_passed(self) -> bool: ...

    @property
    def can_auto_transition_to_build(self) -> bool: ...

    @property
    def mode_history(self) -> Sequence[ModeTransition]: ...

    def set_plan_artifact(self, path: str) -> None: ...

    def set_plan_quality_passed(self, passed: bool = True) -> None: ...

    def switch_to_build(self, plan_artifact_path: str | None = None, reason: str = "") -> bool: ...


class QualityGatePort(Protocol):
    def evaluate(
        self,
        task_type: str,
        user_request: str,
        agent_output: str,
        execution_mode: str | None = None,
    ) -> QualityScore: ...


class KanbanEnginePort(Protocol):
    def add_task(self, title: str, description: str = "", priority: int = 0) -> KanbanTask: ...


# ─── 데이터 모델 ──────────────────────────────────────────────────────


@final
class TransitionPhase(str):
    """전환 파이프라인의 각 단계."""

    INIT = "init"
    PLAN_VALIDATION = "plan_validation"
    QUALITY_CHECK = "quality_check"
    MODE_TRANSITION = "mode_transition"
    KANBAN_CREATION = "kanban_creation"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class TransitionStep:
    """파이프라인의 개별 단계 결과."""

    phase: str
    success: bool
    message: str = ""
    details: JsonMap = field(default_factory=_empty_json_map)
    duration_ms: float = 0.0


@dataclass
class TransitionResult:
    """전체 전환 파이프라인 결과."""

    success: bool = False
    """전체 파이프라인 성공 여부."""

    plan_file: str = ""
    """검증된 Plan 아티팩트 파일 경로."""

    plan_score: float = 0.0
    """Plan 검증 점수 (0.0~1.0)."""

    task_count: int = 0
    """Plan에서 추출된 태스크 수."""

    kanban_task_count: int = 0
    """Kanban에 등록된 태스크 수."""

    errors: list[str] = field(default_factory=list)
    """오류 메시지 목록."""

    warnings: list[str] = field(default_factory=list)
    """경고 메시지 목록."""

    steps: list[TransitionStep] = field(default_factory=list)
    """각 단계별 결과."""

    started_at: str = ""
    """파이프라인 시작 시간."""

    completed_at: str = ""
    """파이프라인 완료 시간."""

    duration_ms: float = 0.0
    """전체 소요 시간 (ms)."""

    @property
    def has_error(self) -> bool:
        return bool(self.errors) or not self.success

    def add_step(self, step: TransitionStep) -> None:
        """단계 결과를 기록합니다."""
        self.steps.append(step)
        if not step.success and step.phase != TransitionPhase.FAILED:
            self.errors.append(f"[{step.phase}] {step.message}")

    def summary(self) -> str:
        """사용자 친화적인 결과 요약 문자열."""
        if not self.success:
            parts = ["❌ **Plan→Build 전환 실패**"]
            if self.errors:
                for err in self.errors[:3]:
                    parts.append(f"  - {err}")
            return "\n".join(parts)

        parts = [
            "✅ **Plan→Build 자동 전환 완료**",
            "",
            f"  📄 Plan: `{self.plan_file}`",
            f"  📊 검증 점수: `{self.plan_score:.0%}`",
            f"  📋 태스크: {self.task_count}개 추출",
        ]

        if self.kanban_task_count > 0:
            parts.append(f"  🗂️ Kanban: {self.kanban_task_count}개 등록")

        if self.warnings:
            for w in self.warnings[:2]:
                parts.append(f"  ⚠️  {w}")

        parts.append(f"  ⏱️  {self.duration_ms:.0f}ms 소요")
        return "\n".join(parts)


# ─── 메인 파이프라인 ──────────────────────────────────────────────────


@final
class PlanToBuildPipeline:
    """Plan→Build 자동 전환 파이프라인.

    파이프라인 순서:
      1. Plan 아티팩트 존재 확인
      2. validate_plan_complete() → 완전성 검증
      3. QualityGate 평가 (task_type="plan")
      4. ModeManager 상태 설정 (set_plan_artifact + set_plan_quality_passed)
      5. switch_to_build() 실행
      6. (선택) Kanban 태스크 자동 생성

    각 단계는 독립적이며, 실패 시 나머지 단계를 건너뛰고
    명확한 오류 메시지를 반환합니다.
    """

    # 기본 Plan 아티팩트 파일명
    DEFAULT_PLAN_FILE: str = "implementation_plan.md"

    # Plan 검증 최소 점수 임계값
    DEFAULT_MIN_SCORE: float = 0.6

    def __init__(
        self,
        mode_manager: ModeManagerPort | None = None,
        artifact_engine: ArtifactEnginePort | None = None,
        quality_gate: QualityGatePort | None = None,
        kanban_engine: KanbanEnginePort | None = None,
        min_plan_score: float = DEFAULT_MIN_SCORE,
    ):
        """Initialize the PlanToBuildPipeline.

        Args:
            mode_manager: ModeManager 인스턴스 (필수)
            artifact_engine: ArtifactEngine 인스턴스 (필수)
            quality_gate: QualityGate 인스턴스 (선택 — 없으면 mode_manager 자체 검증 사용)
            kanban_engine: KanbanEngine 인스턴스 (선택 — Plan 태스크 자동 등록용)
            min_plan_score: Plan 검증 최소 점수 (기본: 0.6)
        """
        self.mode_manager = mode_manager
        self.artifact_engine = artifact_engine
        self.quality_gate = quality_gate
        self.kanban_engine = kanban_engine
        self.min_plan_score = min_plan_score

    # ─── 메인 진입점 ────────────────────────────────────────────────

    def run(
        self,
        plan_file: str = DEFAULT_PLAN_FILE,
        auto_transition: bool = True,
        create_kanban: bool = True,
    ) -> TransitionResult:
        """Plan→Build 자동 전환 파이프라인을 실행합니다.

        Args:
            plan_file: 검증할 Plan 아티팩트 파일명
            auto_transition: True면 검증 통과 후 자동 Build 전환
            create_kanban: True면 Plan 태스크를 Kanban에 등록

        Returns:
            TransitionResult
        """
        result = TransitionResult(
            plan_file=plan_file,
            started_at=datetime.now().isoformat(),
        )
        start_time = datetime.now()

        logger.info(
            "[PlanToBuild] Pipeline started (plan=%s, auto=%s, kanban=%s)",
            plan_file,
            auto_transition,
            create_kanban,
        )

        # --- Pre-check: 필수 의존성 ---
        if not self.mode_manager:
            result.errors.append("ModeManager가 설정되지 않았습니다")
            result.completed_at = datetime.now().isoformat()
            result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            return result

        if not self.artifact_engine:
            result.errors.append("ArtifactEngine이 설정되지 않았습니다")
            result.completed_at = datetime.now().isoformat()
            result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            return result

        # --- Step 1: Plan 검증 ---
        logger.info("[PlanToBuild] Step 1/4: Validating plan '%s'...", plan_file)
        validation = self._validate_plan(plan_file)
        step1 = TransitionStep(
            phase=TransitionPhase.PLAN_VALIDATION,
            success=validation["success"],
            message=validation.get("message", ""),
            details=validation.get("details", {}),
            duration_ms=validation.get("duration_ms", 0),
        )
        result.add_step(step1)
        result.plan_score = validation.get("score", 0.0)
        result.task_count = validation.get("task_count", 0)

        if not step1.success:
            result.completed_at = datetime.now().isoformat()
            result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            return result

        # --- Step 2: QualityGate 평가 ---
        if self.quality_gate:
            logger.info("[PlanToBuild] Step 2/4: Running QualityGate...")
            quality = self._check_quality(plan_file, validation)
            step2 = TransitionStep(
                phase=TransitionPhase.QUALITY_CHECK,
                success=quality["success"],
                message=quality.get("message", ""),
                details=quality.get("details", {}),
                duration_ms=quality.get("duration_ms", 0),
            )
            result.add_step(step2)

            if not step2.success:
                result.completed_at = datetime.now().isoformat()
                result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                return result

            # QualityGate 경고 전달
            if quality.get("warnings"):
                result.warnings.extend(quality["warnings"])
        else:
            logger.info("[PlanToBuild] Step 2/4: QualityGate not configured — skipped")

        # --- Step 3: Build 모드 전환 ---
        if auto_transition:
            logger.info("[PlanToBuild] Step 3/4: Transitioning to BUILD mode...")
            transition = self._execute_transition(plan_file)
            step3 = TransitionStep(
                phase=TransitionPhase.MODE_TRANSITION,
                success=transition["success"],
                message=transition.get("message", ""),
                details=transition.get("details", {}),
                duration_ms=transition.get("duration_ms", 0),
            )
            result.add_step(step3)

            if not step3.success:
                result.completed_at = datetime.now().isoformat()
                result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                return result
        else:
            logger.info("[PlanToBuild] Step 3/4: Auto-transition disabled — skipped")

        # --- Step 4: Kanban 태스크 자동 생성 ---
        if create_kanban and validation.get("task_count", 0) > 0:
            logger.info(
                "[PlanToBuild] Step 4/4: Creating Kanban tasks (%d tasks)...",
                validation["task_count"],
            )
            kanban = self._create_kanban_tasks(plan_file)
            step4 = TransitionStep(
                phase=TransitionPhase.KANBAN_CREATION,
                success=kanban["success"],
                message=kanban.get("message", ""),
                details=kanban.get("details", {}),
                duration_ms=kanban.get("duration_ms", 0),
            )
            result.add_step(step4)
            result.kanban_task_count = kanban.get("task_count", 0)

            if not step4.success:
                result.warnings.append(step4.message)
        else:
            logger.info("[PlanToBuild] Step 4/4: Kanban creation skipped")

        # --- 완료 ---
        result.success = True
        result.completed_at = datetime.now().isoformat()
        result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        logger.info(
            "[PlanToBuild] Pipeline completed (success=%s, score=%.2f, tasks=%d, duration=%.0fms)",
            result.success,
            result.plan_score,
            result.task_count,
            result.duration_ms,
        )

        return result

    # ─── 서브스텝 ───────────────────────────────────────────────────

    def _validate_plan(self, plan_file: str) -> ValidationPayload:
        """Step 1: Plan 아티팩트 완전성을 검증합니다.

        1. Plan 파일 존재 여부 확인
        2. ArtifactEngine.validate_plan_complete() 실행
        3. 점수/누락 섹션/이슈 수집

        Args:
            plan_file: Plan 파일명

        Returns:
            검증 결과 딕셔너리
        """
        start = datetime.now()

        if not self.artifact_engine:
            return {
                "success": False,
                "score": 0.0,
                "task_count": 0,
                "message": "ArtifactEngine이 설정되지 않았습니다",
                "details": {},
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

        try:
            # 1-a. 파일 존재 확인
            content = self.artifact_engine.read_artifact(plan_file)
            if not content:
                return {
                    "success": False,
                    "score": 0.0,
                    "task_count": 0,
                    "message": (
                        f"Plan 아티팩트 '{plan_file}'를 찾을 수 없습니다. artifacts/{plan_file} 경로를 확인하세요."
                    ),
                    "details": {"missing_file": True},
                    "duration_ms": (datetime.now() - start).total_seconds() * 1000,
                }

            # 1-b. 완전성 검증
            validation = self.artifact_engine.validate_plan_complete(plan_file)
            score = validation.score
            missing = validation.missing_sections
            issues = validation.issues
            task_count = validation.task_count

            # 1-c. 최소 점수 확인
            if score < self.min_plan_score:
                message_parts = [f"Plan 점수 {score:.0%}가 최소 기준 {self.min_plan_score:.0%} 미만"]
                if missing:
                    message_parts.append(f"누락 섹션: {', '.join(missing)}")
                if issues:
                    message_parts.append(f"이슈: {'; '.join(issues[:3])}")

                return {
                    "success": False,
                    "score": score,
                    "task_count": task_count,
                    "message": ". ".join(message_parts),
                    "details": {
                        "score": score,
                        "missing_sections": missing,
                        "issues": issues,
                        "task_count": task_count,
                    },
                    "duration_ms": (datetime.now() - start).total_seconds() * 1000,
                }

            # 성공
            return {
                "success": True,
                "score": score,
                "task_count": task_count,
                "message": f"Plan 검증 통과 (점수: {score:.0%}, 태스크: {task_count}개)",
                "details": {
                    "score": score,
                    "missing_sections": missing,
                    "issues": issues,
                    "task_count": task_count,
                    "has_tasks": task_count > 0,
                },
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

        except Exception as e:
            logger.exception("[PlanToBuild] Plan validation failed")
            return {
                "success": False,
                "score": 0.0,
                "task_count": 0,
                "message": f"Plan 검증 중 오류: {e}",
                "details": {"error": str(e)},
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

    def _check_quality(self, plan_file: str, _validation: ValidationPayload) -> QualityPayload:
        """Step 2: QualityGate로 Plan 품질을 평가합니다.

        ArtifactEngine의 validate_plan_complete() 결과를
        QualityGate 형식에 맞춰 평가합니다.

        Args:
            plan_file: Plan 파일명
            validation: _validate_plan()의 반환값

        Returns:
            품질 평가 결과 딕셔너리
        """
        start = datetime.now()

        if not self.artifact_engine:
            return {
                "success": True,
                "score": 0.5,
                "grade": "unknown",
                "message": "ArtifactEngine 미설치 — 품질 검사 생략",
                "details": {},
                "warnings": ["ArtifactEngine 미설치"],
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }
        if not self.quality_gate:
            return {
                "success": True,
                "score": 0.5,
                "grade": "unknown",
                "message": "QualityGate 미설치 — 품질 검사 생략",
                "details": {},
                "warnings": ["QualityGate 미설치"],
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

        try:
            content = self.artifact_engine.read_artifact(plan_file) or ""

            # QualityGate 평가 (task_type="plan")
            quality = self.quality_gate.evaluate(
                task_type="plan",
                user_request="Create implementation plan",
                agent_output=content,
                execution_mode="plan",
            )

            warnings: list[str] = []
            if quality.issues:
                warnings = [str(i) for i in quality.issues[:3]]

            passed = quality.grade.value in ("excellent", "good")

            return {
                "success": passed,
                "score": quality.score,
                "grade": quality.grade.value,
                "message": (
                    f"QualityGate: {quality.grade.value} ({quality.score:.0%})"
                    if passed
                    else f"QualityGate 미통과: {quality.grade.value} ({quality.score:.0%}) — {quality.feedback[:100]}"
                ),
                "details": {
                    "grade": quality.grade.value,
                    "score": quality.score,
                    "issues": quality.issues,
                    "should_retry": quality.should_retry,
                },
                "warnings": warnings,
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

        except Exception as e:
            logger.exception("[PlanToBuild] Quality check failed")
            return {
                "success": True,  # QualityGate 실패는 치명적이지 않음
                "score": 0.5,
                "grade": "unknown",
                "message": f"QualityGate 평가 생략 (오류: {e})",
                "details": {"error": str(e)},
                "warnings": [f"QualityGate 평가 실패: {e}"],
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

    def _execute_transition(self, plan_file: str) -> TransitionPayload:
        """Step 3: ModeManager를 통해 Plan→Build 전환을 실행합니다.

        1. set_plan_artifact(plan_file) — Plan 아티팩트 경로 설정
        2. set_plan_quality_passed(True) — 품질 검증 통과 표시
        3. switch_to_build(plan_file) — Build 모드 전환

        Args:
            plan_file: Plan 파일명

        Returns:
            전환 결과 딕셔너리
        """
        start = datetime.now()

        if not self.mode_manager:
            return {
                "success": False,
                "message": "ModeManager가 설정되지 않았습니다",
                "details": {},
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }
        if not self.artifact_engine:
            return {
                "success": False,
                "message": "ArtifactEngine이 설정되지 않았습니다",
                "details": {},
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

        try:
            plan_path = ""
            if hasattr(self.artifact_engine, "artifacts_dir"):
                plan_path = f"{self.artifact_engine.artifacts_dir}/{plan_file}"

            # 1. Plan 아티팩트 경로 설정
            self.mode_manager.set_plan_artifact(plan_path)

            # 2. 품질 검증 통과 표시
            self.mode_manager.set_plan_quality_passed(True)

            # 3. Build 모드 전환
            switch_ok = self.mode_manager.switch_to_build(
                plan_artifact_path=plan_path,
                reason=f"Plan 검증 완료 (파일: {plan_file})",
            )

            if not switch_ok:
                return {
                    "success": False,
                    "message": "Build 모드 전환 실패 — 자동 전환이 비활성화되었거나 검증 조건 미충족",
                    "details": {
                        "plan_path": plan_path,
                        "auto_transition_enabled": self.mode_manager.can_auto_transition_to_build,
                        "plan_quality_passed": self.mode_manager.plan_quality_passed,
                    },
                    "duration_ms": (datetime.now() - start).total_seconds() * 1000,
                }

            logger.info("[PlanToBuild] Build mode transition successful (path=%s)", plan_path)
            return {
                "success": True,
                "message": "BUILD 모드 전환 완료",
                "details": {
                    "plan_path": plan_path,
                    "current_mode": str(self.mode_manager.current_mode.value)
                    if hasattr(self.mode_manager, "current_mode")
                    else "build",
                    "mode_history_count": len(self.mode_manager.mode_history),
                },
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

        except Exception as e:
            logger.exception("[PlanToBuild] Mode transition failed")
            return {
                "success": False,
                "message": f"모드 전환 중 오류: {e}",
                "details": {"error": str(e)},
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

    def _create_kanban_tasks(self, plan_file: str) -> KanbanPayload:
        """Step 4: Plan에서 태스크를 추출하여 Kanban에 등록합니다.

        KanbanEngine이 없으면 ArtifactEngine.auto_create_kanban_tasks()에 위임합니다.

        Args:
            plan_file: Plan 파일명

        Returns:
            Kanban 생성 결과
        """
        start = datetime.now()

        if not self.artifact_engine:
            return {
                "success": True,
                "task_count": 0,
                "message": "ArtifactEngine 미설치 — Kanban 태스크 등록 생략",
                "details": {"skipped": True},
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

        try:
            # 우선 ArtifactEngine의 auto_create_kanban_tasks 사용
            if hasattr(self.artifact_engine, "auto_create_kanban_tasks"):
                kanban_result = self.artifact_engine.auto_create_kanban_tasks(plan_file)

                if kanban_result.get("success"):
                    task_count_value = kanban_result.get("task_count", 0)
                    task_count = task_count_value if isinstance(task_count_value, int) else 0
                    return {
                        "success": True,
                        "task_count": task_count,
                        "message": f"Kanban에 {task_count}개 태스크 등록",
                        "details": {
                            "task_count": task_count,
                            "board_name": f"Plan: {plan_file}",
                        },
                        "duration_ms": (datetime.now() - start).total_seconds() * 1000,
                    }
                else:
                    message_value = kanban_result.get("message", "Kanban 태스크 생성 실패")
                    message = message_value if isinstance(message_value, str) else "Kanban 태스크 생성 실패"
                    return {
                        "success": False,
                        "task_count": 0,
                        "message": message,
                        "details": {},
                        "duration_ms": (datetime.now() - start).total_seconds() * 1000,
                    }

            # ArtifactEngine에 메서드가 없으면 KanbanEngine 직접 사용
            if self.kanban_engine:
                tasks = self.artifact_engine.extract_plan_tasks(plan_file)
                if not tasks:
                    return {
                        "success": False,
                        "task_count": 0,
                        "message": "Plan에서 추출할 태스크가 없습니다",
                        "details": {},
                        "duration_ms": (datetime.now() - start).total_seconds() * 1000,
                    }

                todo_tasks = [t for t in tasks if t.status == "todo"]
                registered = 0
                for task in todo_tasks:
                    try:
                        _ = self.kanban_engine.add_task(
                            title=task.title,
                            description=task.description,
                            priority=task.priority,
                        )
                        registered += 1
                    except Exception:
                        continue

                return {
                    "success": True,
                    "task_count": registered,
                    "message": f"Kanban에 {registered}개 태스크 등록",
                    "details": {
                        "task_count": registered,
                        "total_extracted": len(tasks),
                    },
                    "duration_ms": (datetime.now() - start).total_seconds() * 1000,
                }

            # KanbanEngine도 없으면 스킵
            return {
                "success": True,
                "task_count": 0,
                "message": "Kanban 엔진 미설치 — 태스크 등록 생략",
                "details": {"skipped": True},
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

        except Exception as e:
            logger.exception("[PlanToBuild] Kanban task creation failed")
            return {
                "success": False,
                "task_count": 0,
                "message": f"Kanban 태스크 생성 중 오류: {e}",
                "details": {"error": str(e)},
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
            }

    # ─── 유틸리티 ───────────────────────────────────────────────────

    def quick_check(self, plan_file: str = DEFAULT_PLAN_FILE) -> bool:
        """Plan→Build 전환이 가능한지 빠르게 확인합니다.

        ArtifactEngine 검증만 수행하고, 실제 전환은 하지 않습니다.

        Args:
            plan_file: Plan 파일명

        Returns:
            전환 가능 여부
        """
        if not self.artifact_engine:
            return False

        try:
            return self.artifact_engine.is_plan_ready_for_build(plan_file)
        except Exception:
            return False

    def format_status(self) -> str:
        """현재 파이프라인 상태를 포맷팅된 문자열로 반환합니다."""
        lines = [
            "## 🔄 Plan→Build Pipeline Status",
            "",
        ]

        if self.mode_manager:
            mode = self.mode_manager.current_mode.value if hasattr(self.mode_manager, "current_mode") else "unknown"
            lines.append(f"**Current Mode:** {mode.upper()}")

            if hasattr(self.mode_manager, "can_auto_transition_to_build"):
                can_transition = self.mode_manager.can_auto_transition_to_build
                lines.append(f"**Auto-transition Ready:** {'✅' if can_transition else '❌'}")

            if hasattr(self.mode_manager, "plan_artifact_path"):
                plan_path = self.mode_manager.plan_artifact_path
                if plan_path:
                    lines.append(f"**Plan Artifact:** `{plan_path}`")

            quality_pass = self.mode_manager.plan_quality_passed
            lines.append(f"**Quality Passed:** {'✅' if quality_pass else '❌'}")

            if hasattr(self.mode_manager, "mode_history") and self.mode_manager.mode_history:
                lines.append("")
                lines.append("**Transition History:**")
                for h in self.mode_manager.mode_history[-3:]:
                    lines.append(f"  - {h.from_mode} → {h.to_mode}: {h.reason}")

        else:
            lines.append("*Pipeline not initialized (no ModeManager)*")

        return "\n".join(lines)
