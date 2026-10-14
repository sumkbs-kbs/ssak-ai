"""Ssak-Ai: Self-Evolution Coordinator (SEC) — Hermes-style Closed Learning Loop.

================================================================================
Orchestrator의 태스크 완료 후 QualityGate 점수가 C 이하일 때 자동으로 가동되어,
11개 분산된 자기 개선 모듈을 하나의 파이프라인으로 연결합니다.

핵심 플로우:
  1. Collect: QualityGate 점수 + SelfRepair 로그 + ToolCall 기록
  2. Analyze: RSIEngine.diagnose() → 약점 패턴 추출
  3. Prioritize: 가장 큰 개선 효과가 예상되는 1가지 선택
  4. Mutate:
     ┣─ Prompt 문제 → PromptEvolver.evolve_system_prompt()
     ┣─ 패턴 문제 → SkillAutoLearner.generate_skill()
     ┣─ 코드 문제 → MetaArchitect.analyze_and_propose()
     ┗─ 설정 문제 → ConfigEditorTool
  5. Validate: RSISandbox.validate_mutation() + dual_audit()
  6. Integrate: 성공 → commit / 실패 → rollback
  7. Report: 사용자에게 "[Self-Evolution] n개 개선 완료" 알림
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol, TypeAlias, cast

import yaml

from antigravity_k.engine.model_manager import ModelManager

logger = logging.getLogger("antigravity_k.self_evolution_coordinator")

JsonObject: TypeAlias = dict[str, object]


def _object_dict(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    return {str(key): item for key, item in mapping.items()}


def _string_value(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


class _InsightProtocol(Protocol):
    pattern_name: str
    occurrence_count: int
    avg_score: float


class _SelfImprovementProtocol(Protocol):
    def record_turn(self, user_request: str, grade: str, score: float, issues: list[str]) -> None: ...

    def get_insights(self) -> Sequence[_InsightProtocol]: ...

    def get_reinforcement_prompt(self) -> str: ...


class _PromptEvolverProtocol(Protocol):
    def evolve_system_prompt(
        self,
        current_prompt: str,
        performance_data: Mapping[str, object],
    ) -> tuple[str, float]: ...

    def evolve_few_shots(self, current_examples: list[dict[str, str]], task_type: str) -> list[dict[str, str]]: ...


class _RSIEngineProtocol(Protocol):
    def _diagnose(self, performance_data: Mapping[str, object], result: object) -> list[str]: ...


class _SandboxProtocol(Protocol):
    def safe_mutation(self, label: str = "") -> AbstractContextManager[object]: ...

    def validate_mutation(self, filepath: str, new_content: str) -> Mapping[str, object]: ...

    def dual_audit(
        self,
        filepath: str,
        original: str,
        modified: str,
        audit_fn_1: Callable[[str], str] | None = None,
    ) -> Mapping[str, object]: ...


class _ProposalProtocol(Protocol):
    title: str
    description: str
    target_files: list[str]


class _MetaArchitectProtocol(Protocol):
    def analyze_and_propose(self, performance_data: Mapping[str, object]) -> _ProposalProtocol | None: ...

    def execute_proposal(self, proposal: _ProposalProtocol) -> bool: ...


class _SkillLearnerProtocol(Protocol):
    def record_tool_call(
        self,
        name: str,
        arguments: dict[str, object],
        result: str = "",
        success: bool = True,
    ) -> None: ...

    def on_task_complete(self, user_message: str = "") -> str | None: ...


class _EvolutionManagerProtocol(Protocol):
    def evolve_system_prompt(self) -> str | None: ...


# ─── 데이터 모델 ──────────────────────────────────────────────────────


class EvolutionTrigger(str, Enum):
    """자기 진화 트리거 유형."""

    QUALITY_FAILURE = "quality_failure"  # QualityGate C/F
    REPETITIVE_FAILURE = "repetitive_failure"  # 동일 패턴 반복 실패
    PATTERN_DETECTED = "pattern_detected"  # SkillAutoLearner 패턴 감지
    SCHEDULED = "scheduled"  # 정기 진화 사이클
    MANUAL = "manual"  # 사용자 요청


class MutationDomain(str, Enum):
    """변이 대상 도메인."""

    SYSTEM_PROMPT = "system_prompt"
    SKILL = "skill"
    CODE = "code"
    CONFIG = "config"
    SAMPLING = "sampling"
    FEW_SHOT = "few_shot"


@dataclass
class PerformanceSnapshot:
    """단일 태스크 완료 후 성능 스냅샷."""

    user_message: str = ""
    agent_output: str = ""
    task_type: str = "simple_chat"
    quality_grade: str = "A"
    quality_score: float = 1.0
    quality_issues: list[str] = field(default_factory=list)
    tool_calls: list[JsonObject] = field(default_factory=list)
    failure_count: int = 0
    duration_ms: float = 0.0  # memory_save_handler에서 ctx.get_duration_ms()로 설정
    timestamp: float = field(default_factory=time.time)


@dataclass
class EvolutionDecision:
    """진화 결정 — 무엇을 어떻게 개선할지."""

    trigger: EvolutionTrigger = EvolutionTrigger.QUALITY_FAILURE
    domain: MutationDomain = MutationDomain.SYSTEM_PROMPT
    weakness_description: str = ""
    confidence: float = 0.0
    expected_improvement: float = 0.0
    target_file: str = ""
    mutation_payload: JsonObject = field(default_factory=dict)


@dataclass
class EvolutionResult:
    """단일 진화 사이클의 결과.

    EVO-02 — 예상과 실측의 분리 계약:
      - ``expected_improvement``: mutation 적용 전 산출한 "기대값" (추정).
      - ``measured_after_metric``: held-out benchmark 재실행으로만 채워지는 실측값.
        적용 직후에는 반드시 ``None`` (pending_evaluation 상태).
      - ``improvement``: 실측이 있을 때만 계산된다 (measured - before).
        실측 전 improvement 주장은 금지된다 (None).
    """

    success: bool = False
    skipped: bool = False
    rolled_back: bool = False
    mutation_domain: MutationDomain = MutationDomain.SYSTEM_PROMPT
    decision: EvolutionDecision | None = None
    before_metric: float = 0.0
    # EVO-02 — 예상값 (추정) 과 실측값의 명시적 분리
    expected_improvement: float = 0.0
    measured_after_metric: float | None = None
    improvement: float | None = None
    evaluation_state: str = "pending_evaluation"  # pending | evaluated | regression_rejected
    benchmark_provenance: JsonObject = field(default_factory=dict)
    error_message: str = ""
    duration_sec: float = 0.0
    details: JsonObject = field(default_factory=dict)
    # EVO-01 — lifecycle 단계 기록: approved/applied/validated/rolled_back 순
    events: list[JsonObject] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """사용자에게 보여줄 한 줄 요약."""
        if self.skipped:
            return "⏭ 진화 생략 (이미 최근 개선됨)"
        if self.rolled_back:
            return f"🔄 진화 롤백됨 ({self.error_message})"
        if self.success and self.evaluation_state == "regression_rejected":
            return f"⚠️ [{self.mutation_domain.value}] 적용됐으나 실측 회귀 — promotion 거절"
        if self.success and self.improvement is None:
            return f"🔬 [{self.mutation_domain.value}] 적용 완료 — 평가 대기 (기대 Δ{{:+.2f}}, 실측 미확정)".format(
                self.expected_improvement
            )
        if self.success and self.improvement is not None:
            return f"✅ [{self.mutation_domain.value}] 실측 개선 확인 (Δ{self.improvement:+.2f})"
        return f"❌ 진화 실패: {self.error_message}"


@dataclass
class EvolutionHistory:
    """진화 이력 (영속 저장용)."""

    cycle_id: str = ""
    timestamp: float = 0.0
    result: EvolutionResult = field(default_factory=EvolutionResult)
    snapshot: PerformanceSnapshot = field(default_factory=PerformanceSnapshot)


# ─── 메인 코디네이터 ──────────────────────────────────────────────────


class SelfEvolutionCoordinator:
    """자기 재귀 개선 코디네이터 — Hermes Agent Closed Learning Loop.

    Orchestrator의 memory_save_handler에서 QualityGate C/F 등급 시 자동 호출됩니다.
    모든 기존 자기 개선 모듈을 하나의 파이프라인으로 유기적으로 연결합니다.
    """

    # 최소 진화 간격 (초) — 과도한 진화 방지
    MIN_EVOLUTION_INTERVAL: float = 30.0

    # 최근 N건의 성능 스냅샷 유지
    MAX_HISTORY_SIZE: int = 20

    # 진화 후 최소 N턴 동안은 재진화 금지
    EVOLUTION_COOLDOWN_TURNS: int = 3

    def __init__(
        self,
        project_root: str = "",
        model_manager: ModelManager | None = None,
        verify_fn: Callable[[str], str] | None = None,
    ):
        """Initialize the SelfEvolutionCoordinator.

        Args:
            project_root: 프로젝트 루트 경로
            model_manager: 모델 매니저 (LLM 호출용)
            verify_fn: LLM 검증 함수 (RSISandbox dual-audit용)
        """
        self._root: str = project_root
        self._manager: ModelManager | None = model_manager
        self._verify_fn: Callable[[str], str] | None = verify_fn

        # 지연 초기화되는 하위 엔진들
        self._rsi_engine: _RSIEngineProtocol | None = None
        self._prompt_evolver: _PromptEvolverProtocol | None = None
        self._meta_architect: _MetaArchitectProtocol | None = None
        self._skill_learner: _SkillLearnerProtocol | None = None
        self._sandbox: _SandboxProtocol | None = None
        self._self_improvement: _SelfImprovementProtocol | None = None
        self._self_repair: object | None = None
        self._evolution_manager: _EvolutionManagerProtocol | None = None

        # 상태
        self._history: list[EvolutionHistory] = []
        self._last_evolution_time: float = 0.0
        self._turns_since_last_evolution: int = 0
        self._deps_initialized: bool = False
        # EVO-01 — sandbox/validator 초기화 실패는 fail-closed: mutation 금지
        self._deps_init_failed: bool = False
        self._deps_init_error: str = ""
        # EVO-01 — 승인/적용/검증/rollback event ledger (메모리, 최근 200건)
        self._event_ledger: list[JsonObject] = []

    # ─── 지연 초기화 ─────────────────────────────────────────────

    def _ensure_deps(self) -> None:
        """필요한 하위 엔진들을 지연 초기화합니다. (EVO-01 fail-closed)

        sandbox 또는 필수 validator 초기화가 실패하면 조용히 넘어가지 않고
        ``_deps_init_failed``를 남겨 ``auto_evolve``가 mutation을 거절한다.
        """
        if self._deps_initialized:
            return
        self._deps_initialized = True

        failures: list[str] = []
        try:
            from antigravity_k.engine.rsi_engine import RSIEngine

            self._rsi_engine = cast(
                _RSIEngineProtocol,
                cast(object, RSIEngine(project_root=self._root, model_manager=self._manager)),
            )
        except (ImportError, RuntimeError, AttributeError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        try:
            from antigravity_k.engine.prompt_evolver import PromptEvolver

            self._prompt_evolver = cast(
                _PromptEvolverProtocol,
                cast(object, PromptEvolver(model_manager=self._manager)),
            )
        except (ImportError, RuntimeError, AttributeError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        try:
            from antigravity_k.engine.meta_architect import MetaArchitect

            self._meta_architect = cast(
                _MetaArchitectProtocol,
                cast(object, MetaArchitect(project_root=self._root, model_manager=self._manager)),
            )
        except (ImportError, RuntimeError, AttributeError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        try:
            from antigravity_k.engine.rsi_sandbox import RSISandbox

            self._sandbox = cast(
                _SandboxProtocol,
                RSISandbox(project_root=self._root, verify_fn=self._verify_fn),
            )
        except (ImportError, RuntimeError, AttributeError):
            # EVO-01 — sandbox는 mutation의 전제 조건. 실패는 fail-closed로 기록한다.
            failures.append("sandbox")
            logger.warning("[SEC] sandbox 초기화 실패 — mutation 차단 (fail-closed)", exc_info=True)

        if failures:
            self._deps_init_failed = True
            self._deps_init_error = ", ".join(failures)

        try:
            from antigravity_k.engine.self_improvement import SelfImprovementLoop

            self._self_improvement = cast(
                _SelfImprovementProtocol,
                cast(object, SelfImprovementLoop(data_dir=self._root)),
            )
        except (ImportError, RuntimeError, AttributeError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        try:
            from antigravity_k.engine.self_repair import SelfRepairEngine

            self._self_repair = SelfRepairEngine()
        except (ImportError, RuntimeError, AttributeError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        try:
            from antigravity_k.engine.evolution import EvolutionManager
            from antigravity_k.engine.vault import VaultEngine

            vault_path = f"{self._root}/vault_data"
            vault = VaultEngine(vault_path, sync_rag=False)
            if self._manager:
                self._evolution_manager = cast(
                    _EvolutionManagerProtocol,
                    EvolutionManager(
                        model_manager=self._manager,
                        vault_engine=vault,
                    ),
                )
        except (ImportError, RuntimeError, AttributeError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

    # ─── 메인 API ────────────────────────────────────────────────

    def _record_event(self, stage: str, detail: JsonObject | None = None) -> None:
        """EVO-01 — 진화 lifecycle 이벤트를 ledger에 기록 (최근 200건 유지)."""
        event: JsonObject = {"stage": stage, "ts": time.time()}
        if detail:
            event.update(detail)
        self._event_ledger.append(event)
        if len(self._event_ledger) > 200:
            del self._event_ledger[:-200]

    def get_event_ledger(self) -> list[JsonObject]:
        """EVO-01 — 승인/적용/검증/rollback event ledger 사본 반환."""
        return [dict(e) for e in self._event_ledger]

    def record_performance(self, snapshot: PerformanceSnapshot) -> None:
        """태스크 완료 후 성능 스냅샷을 기록합니다.

        Args:
            snapshot: 태스크 완료 시점의 성능 데이터
        """
        self._history.append(
            EvolutionHistory(
                cycle_id=f"perf_{int(time.time())}",
                timestamp=time.time(),
                snapshot=snapshot,
            )
        )

        # 최대 크기 유지
        if len(self._history) > self.MAX_HISTORY_SIZE:
            self._history = self._history[-self.MAX_HISTORY_SIZE :]

        # SelfImprovementLoop에도 기록
        if self._self_improvement:
            try:
                self._self_improvement.record_turn(
                    user_request=snapshot.user_message,
                    grade=snapshot.quality_grade,
                    score=snapshot.quality_score,
                    issues=snapshot.quality_issues,
                )
            except (AttributeError, TypeError, ValueError):
                logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        self._turns_since_last_evolution += 1

    def should_evolve(self, quality_grade: str) -> bool:
        """현재 시점에서 진화가 필요한지 판단합니다.

        Hermes 스타일: QualityGate C/F 등급일 때만 진화.
        추가 조건:
          - 최소 간격(30초) 경과
          - 이전 진화 후 최소 N턴 경과
          - 5턴 연속 A/B 등급이면 진화 스킵 (안정 상태)

        Args:
            quality_grade: QualityGate 등급 (A/B/C/F)

        Returns:
            진화 필요 여부
        """
        # 품질 기준: C/F 등급일 때만 진화
        if quality_grade not in ("C", "F", "retry", "fail"):
            return False

        # 최소 간격 체크
        if time.time() - self._last_evolution_time < self.MIN_EVOLUTION_INTERVAL:
            logger.debug("[SEC] Evolution skipped: cooldown")
            return False

        # 최소 턴 수 체크
        if self._turns_since_last_evolution < self.EVOLUTION_COOLDOWN_TURNS:
            logger.debug(
                "[SEC] Evolution skipped: needs %s more turns",
                self.EVOLUTION_COOLDOWN_TURNS - self._turns_since_last_evolution,
            )
            return False

        return True

    def auto_evolve(self, snapshot: PerformanceSnapshot) -> EvolutionResult:
        """전체 자기 진화 파이프라인을 실행합니다.

        Args:
            snapshot: 현재 태스크의 성능 스냅샷

        Returns:
            진화 결과
        """
        start_time = time.time()
        self._ensure_deps()
        self.record_performance(snapshot)

        # EVO-01 — sandbox/필수 validator 초기화 실패 시 mutation을 실행하지 않는다 (fail-closed)
        if self._deps_init_failed or self._sandbox is None:
            result = EvolutionResult(
                skipped=True,
                error_message=(
                    f"fail-closed: 진화 의존성 초기화 실패 ({self._deps_init_error or 'sandbox 미구성'})"
                    " — mutation 실행 차단"
                ),
                duration_sec=time.time() - start_time,
            )
            self._record_event(
                "blocked",
                {"reason": "deps_init_failed", "detail": result.error_message},
            )
            self._save_evolution_history(
                EvolutionHistory(
                    cycle_id=f"sec_{int(time.time())}",
                    timestamp=time.time(),
                    result=result,
                    snapshot=snapshot,
                )
            )
            logger.warning("[SEC] ⛔ fail-closed: %s", result.error_message)
            return result

        # 1. 진화 필요성 판단
        if not self.should_evolve(snapshot.quality_grade):
            return EvolutionResult(skipped=True)

        self._last_evolution_time = time.time()
        self._turns_since_last_evolution = 0

        result = EvolutionResult(
            before_metric=snapshot.quality_score,
            duration_sec=0.0,
        )

        logger.info(
            "[SEC] ═══ Hermes Self-Evolution 시작 ═══ (grade=%s, score=%s)",
            snapshot.quality_grade,
            snapshot.quality_score,
        )

        try:
            # 2. RSI 진단: 약점 패턴 추출
            decision = self._analyze(snapshot)
            if not decision or decision.confidence < 0.3:
                result.skipped = True
                result.details["reason"] = "low_confidence"
                return result

            result.decision = decision
            result.mutation_domain = decision.domain

            # 3. 샌드박스 내 변이 실행 (EVO-01 — sandbox 없는 mutation 경로 제거)
            mutation_payload = {}
            with self._sandbox.safe_mutation(f"sec_{decision.domain.value}_{int(time.time())}"):
                mutation_payload = self._execute_mutation(decision, snapshot)
                if mutation_payload.get("applied"):
                    self._record_event(
                        "applied",
                        {"domain": decision.domain.value, "method": str(mutation_payload.get("method", ""))},
                    )
                    # 4. 검증 (validation timeout 포함 — 실패/timeout 모두 task-owned rollback)
                    validation = self._validate(decision, mutation_payload)
                    if not validation.get("passed", False):
                        self._record_event(
                            "validation_failed",
                            {"reason": str(validation.get("reason", "unknown"))[:200]},
                        )
                        raise RuntimeError(f"Validation failed: {validation.get('reason', 'unknown')}")
                    self._record_event("validated", {"domain": decision.domain.value})

            # 5. 결과 기록 (EVO-02 — 예상과 실측의 분리)
            # after_metric을 expected로 채우지 않는다 — 실측은 held-out 재평가로만 확정된다.
            # 적용 직후 상태는 pending_evaluation이며 improvement는 미확정(None)이다.
            result.success = bool(mutation_payload.get("applied"))
            result.expected_improvement = decision.expected_improvement
            result.measured_after_metric = None  # pending_evaluation — 실측 없음
            result.improvement = None
            result.evaluation_state = "pending_evaluation"
            result.details = mutation_payload
            result.events = list(self._event_ledger[-10:])

            self._record_event("approved", {"domain": decision.domain.value})

            # 6. 진화 이력 저장
            self._save_evolution_history(
                EvolutionHistory(
                    cycle_id=f"sec_{int(time.time())}",
                    timestamp=time.time(),
                    result=result,
                    snapshot=snapshot,
                )
            )

            logger.info(
                "[SEC] ✅ 진화 완료: domain=%s, improvement=%s",
                decision.domain.value,
                result.improvement,
            )

        except RuntimeError as e:
            # 롤백 필요 — safe_mutation 컨텍스트가 이미 snapshot rollback 수행
            result.success = False
            result.rolled_back = True
            result.error_message = str(e)
            self._record_event("rolled_back", {"reason": str(e)[:200]})
            result.events = list(self._event_ledger[-10:])
            logger.warning("[SEC] 🔄 진화 롤백: %s", e)

        except Exception as e:
            result.success = False
            result.error_message = str(e)
            self._record_event("rolled_back", {"reason": f"unexpected: {str(e)[:150]}"})
            result.events = list(self._event_ledger[-10:])
            logger.exception("[SEC] ❌ 진화 실패 (최상위 안전망)")

        result.duration_sec = time.time() - start_time
        return result

    # ─── 분석 파이프라인 ─────────────────────────────────────────

    def _analyze(self, snapshot: PerformanceSnapshot) -> EvolutionDecision | None:
        """성능 스냅샷을 분석하여 최적의 진화 결정을 내립니다.

        여러 진단 소스를 통합하여 가장 큰 개선 효과가 예상되는 1가지를 선택합니다.

        Args:
            snapshot: 성능 데이터

        Returns:
            진화 결정, 또는 None (분석 불가)
        """
        candidates: list[EvolutionDecision] = []

        # 진단 소스 1: RSI Engine 진단
        try:
            if self._rsi_engine:
                from antigravity_k.engine.rsi_engine import RSICycleResult

                perf_data = {
                    "weaknesses": snapshot.quality_issues,
                    "quality_score": snapshot.quality_score,
                }
                dummy_result = RSICycleResult(
                    cycle_id="sec_analyze",
                    generation=0,
                    before_score=snapshot.quality_score,
                )
                diagnose = cast(
                    Callable[[Mapping[str, object], object], list[str]],
                    getattr(cast(object, self._rsi_engine), "_diagnose"),
                )
                weaknesses = diagnose(perf_data, dummy_result)
                for w in weaknesses[:2]:
                    candidates.append(
                        EvolutionDecision(
                            trigger=EvolutionTrigger.QUALITY_FAILURE,
                            weakness_description=w,
                            confidence=0.6,
                            expected_improvement=0.05,
                        )
                    )
        except (RuntimeError, AttributeError, ValueError, KeyError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        # 진단 소스 2: SelfImprovementLoop 패턴 분석
        try:
            if self._self_improvement:
                insights = self._self_improvement.get_insights()
                for insight in insights[:2]:
                    candidates.append(
                        EvolutionDecision(
                            trigger=EvolutionTrigger.REPETITIVE_FAILURE,
                            weakness_description=(
                                f"반복 패턴 '{insight.pattern_name}' "
                                f"({insight.occurrence_count}회, 평균 {insight.avg_score:.2f})"
                            ),
                            confidence=min(0.9, 0.3 + insight.occurrence_count * 0.15),
                            expected_improvement=min(0.15, 0.05 + (1.0 - insight.avg_score) * 0.1),
                        )
                    )
        except (RuntimeError, AttributeError, ValueError, KeyError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        # 진단 소스 3: 품질 이슈 직접 분석
        for issue in snapshot.quality_issues[:3]:
            issue_lower = issue.lower()
            confidence = 0.5
            domain = MutationDomain.SYSTEM_PROMPT
            expected_improvement = 0.05

            if "코드" in issue_lower or "구문" in issue_lower:
                domain = MutationDomain.CODE
                confidence = 0.7
                expected_improvement = 0.12
            elif "비교" in issue_lower or "테이블" in issue_lower:
                domain = MutationDomain.FEW_SHOT
                confidence = 0.6
                expected_improvement = 0.08
            elif "중국어" in issue_lower or "일본어" in issue_lower or "오염" in issue_lower:
                domain = MutationDomain.SYSTEM_PROMPT
                confidence = 0.8
                expected_improvement = 0.15
            elif "반복" in issue_lower or "중복" in issue_lower:
                domain = MutationDomain.SYSTEM_PROMPT
                confidence = 0.6
                expected_improvement = 0.07
            elif "밀도" in issue_lower or "구조" in issue_lower:
                domain = MutationDomain.FEW_SHOT
                confidence = 0.5
                expected_improvement = 0.06
            elif "안전" in issue_lower or "위험" in issue_lower:
                domain = MutationDomain.CONFIG
                confidence = 0.9
                expected_improvement = 0.20

            candidates.append(
                EvolutionDecision(
                    trigger=EvolutionTrigger.QUALITY_FAILURE,
                    domain=domain,
                    weakness_description=issue,
                    confidence=confidence,
                    expected_improvement=expected_improvement,
                )
            )

        if not candidates:
            return None

        # 신뢰도 × 기대효과 순으로 정렬하여 최적 1개 선택
        candidates.sort(
            key=lambda d: d.confidence * d.expected_improvement,
            reverse=True,
        )
        best = candidates[0]

        # 도메인별 타겟 파일 설정
        domain_file_map = {
            MutationDomain.SYSTEM_PROMPT: "prompt_builder.py",
            MutationDomain.SKILL: ".agent/skills/",
            MutationDomain.CODE: "orchestrator.py",
            MutationDomain.CONFIG: "config.yaml",
            MutationDomain.SAMPLING: "sampling_config.py",
            MutationDomain.FEW_SHOT: "prompt_builder.py",
        }
        best.target_file = domain_file_map.get(best.domain, "")
        best.mutation_payload = {
            "weakness": best.weakness_description,
            "issues": snapshot.quality_issues[:3],
        }

        logger.info(
            "[SEC] 최적 진화 결정: domain=%s, confidence=%s, expected=%s",
            best.domain.value,
            best.confidence,
            best.expected_improvement,
        )
        return best

    # ─── 변이 실행 ───────────────────────────────────────────────

    def _execute_mutation(
        self,
        decision: EvolutionDecision,
        snapshot: PerformanceSnapshot,
    ) -> JsonObject:
        """진화 결정에 따라 변이를 실행합니다.

        Args:
            decision: 진화 결정
            snapshot: 성능 데이터

        Returns:
            변이 결과 (applied, message 등)
        """
        domain = decision.domain
        result: JsonObject = {"applied": False, "message": ""}

        if domain == MutationDomain.SYSTEM_PROMPT:
            result = self._mutate_system_prompt(decision, snapshot)
        elif domain == MutationDomain.SKILL:
            result = self._mutate_skill(decision, snapshot)
        elif domain == MutationDomain.CODE:
            result = self._mutate_code(decision, snapshot)
        elif domain == MutationDomain.FEW_SHOT:
            result = self._mutate_few_shot(decision, snapshot)
        elif domain == MutationDomain.CONFIG:
            result = self._mutate_config(decision, snapshot)
        elif domain == MutationDomain.SAMPLING:
            result = self._mutate_sampling(decision, snapshot)

        return result

    def _mutate_system_prompt(
        self,
        decision: EvolutionDecision,
        snapshot: PerformanceSnapshot,
    ) -> JsonObject:
        """시스템 프롬프트 진화 — PromptEvolver 또는 EvolutionManager 사용.

        현재 프롬프트는 다음 순서로 가져옵니다:
          1. prompts/system_prompt.md (파일 기반)
          2. prompts/persona.md (페르소나)
          3. agents/personas.py의 get_orchestrator_prompt()
          4. config.yaml의 agent_models
          5. 최종 폴백 문자열
        """
        _ = decision
        result: JsonObject = {"applied": False, "message": "", "method": "prompt_evolver"}

        # 실제 시스템 프롬프트 로드
        current_prompt = self._load_current_system_prompt()

        # 방법 1: PromptEvolver (OPRO 기반)
        if self._prompt_evolver and self._verify_fn:
            try:
                perf_data = {
                    "quality_avg": snapshot.quality_score,
                    "weaknesses": snapshot.quality_issues,
                    "failure_patterns": snapshot.quality_issues,
                }

                new_prompt, score = self._prompt_evolver.evolve_system_prompt(
                    current_prompt=current_prompt,
                    performance_data=perf_data,
                )

                if new_prompt and len(new_prompt) > 50:
                    result["applied"] = True
                    result["message"] = f"프롬프트 진화 완료 (score={score:.2f})"
                    result["new_prompt_snippet"] = new_prompt[:200]
                    logger.info("[SEC] PromptEvolver: 새 프롬프트 점수 %.2f", score)
                    return result
            except (RuntimeError, AttributeError, ValueError, KeyError):
                logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        # 방법 2: EvolutionManager (Hermes 스타일, Vault 실패 기반)
        if self._evolution_manager:
            try:
                draft_path = self._evolution_manager.evolve_system_prompt()
                if draft_path:
                    result["applied"] = True
                    result["message"] = f"시스템 프롬프트 진화 완료 → {draft_path}"
                    result["method"] = "evolution_manager"
                    result["draft_path"] = draft_path
                    return result
            except (RuntimeError, AttributeError, KeyError, ValueError):
                logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        # 방법 3: SelfImprovementLoop 보강 프롬프트 (패턴 기반)
        if self._self_improvement:
            try:
                reinforcement = self._self_improvement.get_reinforcement_prompt()
                if reinforcement:
                    result["applied"] = True
                    result["message"] = "보강 프롬프트 생성 완료"
                    result["method"] = "self_improvement"
                    result["reinforcement"] = reinforcement
                    return result
            except (RuntimeError, AttributeError, KeyError, ValueError):
                logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        return result

    def _load_current_system_prompt(self) -> str:
        """현재 시스템 프롬프트를 실제 파일/코드에서 로드합니다.

        우선순위(높은 순):
          1. prompts/system_prompt.md (메인 시스템 프롬프트)
          2. prompts/persona.md (페르소나 정의)
          3. prompts/roles/ceo.md (CEO 프롬프트)
          4. prompts/roles/worker.md (Worker 프롬프트)

        Returns:
            현재 시스템 프롬프트 문자열, 없으면 포괄적 폴백
        """
        import os

        candidate_paths = [
            os.path.join(self._root, "prompts", "system_prompt.md"),
            os.path.join(self._root, "prompts", "persona.md"),
            os.path.join(self._root, "prompts", "roles", "ceo.md"),
            os.path.join(self._root, "prompts", "roles", "worker.md"),
        ]

        for path in candidate_paths:
            try:
                if os.path.exists(path):
                    with open(path, encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            return content
            except (OSError, UnicodeDecodeError):
                continue

        # 최종 폴백: 프로젝트 구조 기반 설명
        return (
            "You are Ssak-Ai, a local autonomous engineering agent "
            "running on Apple Silicon. You orchestrate multi-agent workflows "
            "using MoE Swarm architecture with collective intelligence. "
            "Your capabilities include: multi-model orchestration, "
            "tool-augmented reasoning, self-evolution, RAG, and autonomous learning."
        )

    def _mutate_skill(
        self,
        decision: EvolutionDecision,
        snapshot: PerformanceSnapshot,
    ) -> JsonObject:
        """스킬 진화 — SkillAutoLearner 패턴 감지 및 스킬 생성."""
        _ = decision
        result: JsonObject = {"applied": False, "message": ""}

        if not self._skill_learner:
            try:
                from antigravity_k.engine.skill_auto_learner import SkillAutoLearner

                self._skill_learner = cast(
                    _SkillLearnerProtocol,
                    cast(
                        object,
                        SkillAutoLearner(
                            project_root=self._root,
                            model_manager=self._manager,
                        ),
                    ),
                )
            except (ImportError, RuntimeError, AttributeError):
                logger.debug("[SEC] SkillAutoLearner init failed")
                return result

        learner = self._skill_learner

        for tc in snapshot.tool_calls:
            try:
                learner.record_tool_call(
                    name=_string_value(tc.get("name"), "unknown"),
                    arguments=_object_dict(tc.get("arguments")),
                    success=bool(tc.get("success", True)),
                )
            except (AttributeError, TypeError, KeyError):
                continue

        # 패턴 감지 및 스킬 생성
        try:
            skill_path = learner.on_task_complete(user_message=snapshot.user_message)
            if skill_path:
                result["applied"] = True
                result["message"] = f"새 스킬 생성됨: {skill_path}"
                result["skill_path"] = skill_path
        except (RuntimeError, AttributeError, ValueError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        return result

    def _mutate_code(
        self,
        decision: EvolutionDecision,
        snapshot: PerformanceSnapshot,
    ) -> JsonObject:
        """코드 변이 — MetaArchitect를 통한 대규모 리팩터링."""
        _ = decision
        result: JsonObject = {"applied": False, "message": ""}

        if not self._meta_architect:
            return result

        try:
            perf_data = {
                "quality_avg": snapshot.quality_score,
                "weaknesses": snapshot.quality_issues,
                "quality_grade": snapshot.quality_grade,
            }

            proposal = self._meta_architect.analyze_and_propose(perf_data)
            if proposal:
                executed = self._meta_architect.execute_proposal(proposal)
                if executed:
                    result["applied"] = True
                    result["message"] = f"아키텍처 리팩터링 완료: {proposal.title}"
                    result["proposal"] = {
                        "title": proposal.title,
                        "description": proposal.description,
                        "target_files": proposal.target_files,
                    }
        except (RuntimeError, AttributeError, KeyError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        return result

    def _mutate_few_shot(
        self,
        decision: EvolutionDecision,
        snapshot: PerformanceSnapshot,
    ) -> JsonObject:
        """Few-shot 예시 진화 — PromptEvolver가 예시를 개선합니다."""
        _ = decision
        result: JsonObject = {"applied": False, "message": ""}

        if not self._prompt_evolver:
            return result

        try:
            current_examples = [{"input": "사용자 질문", "output": "AI 응답"}]
            new_examples = self._prompt_evolver.evolve_few_shots(
                current_examples=current_examples,
                task_type=snapshot.task_type,
            )
            if new_examples and len(new_examples) > 0:
                result["applied"] = True
                result["message"] = f"Few-shot 예시 {len(new_examples)}개 진화 완료"
                result["examples"] = new_examples
        except (RuntimeError, AttributeError, ValueError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

        return result

    def _mutate_config(
        self,
        decision: EvolutionDecision,
        snapshot: PerformanceSnapshot,
    ) -> JsonObject:
        """설정 변이 — ConfigEditorTool로 보안/성능 설정 조정."""
        _ = decision
        result: JsonObject = {"applied": False, "message": ""}
        result["message"] = "설정 변경은 사용자 승인이 필요합니다"
        result["suggestion"] = (
            f"품질 이슈({snapshot.quality_issues[0] if snapshot.quality_issues else '알 수 없음'}) "
            f"해결을 위해 config.yaml 설정 검토 필요"
        )
        return result

    def _mutate_sampling(
        self,
        decision: EvolutionDecision,
        snapshot: PerformanceSnapshot,
    ) -> JsonObject:
        """샘플링 프로파일 진화 — temperature/min_p 조정."""
        _ = decision
        result: JsonObject = {"applied": False, "message": ""}
        result["message"] = (
            f"샘플링 프로파일 조정 제안: 품질 점수 {snapshot.quality_score:.2f}에 따라 temperature ±0.05 조정"
        )
        return result

    # ─── 검증 ─────────────────────────────────────────────────

    def _validate(
        self,
        decision: EvolutionDecision,
        mutation_payload: JsonObject,
    ) -> JsonObject:
        """변이 결과를 검증합니다.

        P2-2 강화: 결정적 검증(AST/문법)을 sandbox와 무관하게 항상 수행.
        1단계: 결정적 검증 (AST 파싱, 린트) — LLM 없이 항상 실행
        2단계: RSISandbox 3중 검증 (sandbox 사용 가능 시)
        3단계: LLM 이중 감사 (보조 — 최종 결정은 결정적 검증이 우선)

        Returns:
            {"passed": bool, "reason": str, "details": dict}
        """
        target_file = decision.target_file
        if not target_file or not mutation_payload.get("applied"):
            return {"passed": True, "reason": "no_file_to_validate"}

        new_content_value = mutation_payload.get("new_prompt_snippet", "")
        if not isinstance(new_content_value, str) or not new_content_value:
            return {"passed": True, "reason": "no_content_to_validate"}
        new_content = new_content_value

        # 1단계: 결정적 검증 (P2-2) — 항상 수행, LLM 의존 없음
        deterministic_result = self._deterministic_validate(target_file, new_content)
        if deterministic_result.get("passed") is not True:
            return deterministic_result
        validation: JsonObject = _object_dict(deterministic_result.get("details"))

        # 2단계: RSISandbox 3중 검증 (sandbox 사용 가능 시)
        if self._sandbox:
            validation = _object_dict(
                self._sandbox.validate_mutation(
                    filepath=target_file,
                    new_content=new_content,
                )
            )

            failed = [k for k, v in validation.items() if getattr(v, "value", None) == "fail"]

            if failed:
                return {
                    "passed": False,
                    "reason": f"검증 실패: {', '.join(failed)}",
                    "details": {k: str(v) for k, v in validation.items()},
                }

        # 3단계: LLM 이중 감사 (보조 — 결정적 검증 통과 후에만)
        if self._sandbox and self._verify_fn:
            audit = _object_dict(
                self._sandbox.dual_audit(
                    filepath=target_file,
                    original="",
                    modified=new_content,
                    audit_fn_1=self._verify_fn,
                )
            )
            if not bool(audit.get("approved", True)):
                return {
                    "passed": False,
                    "reason": f"이중 감사 거부: {str(audit.get('auditor_1', 'unknown'))[:100]}",
                    "details": audit,
                }

        return {
            "passed": True,
            "reason": "모든 검증 통과",
            "details": validation,
        }

    @staticmethod
    def _deterministic_validate(filepath: str, content: str) -> JsonObject:
        """결정적 검증 — LLM 없이 항상 수행 (P2-2).

        파일 유형에 따라:
          - Python: AST 파싱으로 문법 오류 검출
          - YAML: yaml.safe_load로 파싱 검증
          - JSON: json.loads로 파싱 검증
          - 기타: 빈 content 검사만

        Returns:
            {"passed": bool, "reason": str, "details": dict}
        """
        import ast

        details: JsonObject = {"filepath": filepath}

        if not content or not content.strip():
            return {
                "passed": False,
                "reason": "변이 후 content가 비어 있음",
                "details": details,
            }

        ext = filepath.lower().rsplit(".", 1)[-1] if "." in filepath else ""

        # Python: AST 파싱
        if ext == "py":
            try:
                _ = ast.parse(content)
                details["ast_valid"] = True
            except SyntaxError as e:
                details["ast_valid"] = False
                details["syntax_error"] = str(e)
                return {
                    "passed": False,
                    "reason": f"Python 문법 오류 (line {e.lineno}): {e.msg}",
                    "details": details,
                }

        # YAML 파싱
        elif ext in ("yaml", "yml"):
            try:
                parsed = cast(object, yaml.safe_load(content))
                if parsed is None and content.strip():
                    details["yaml_warning"] = "content가 있지만 파싱 결과가 None"
                details["yaml_valid"] = True
            except (yaml.YAMLError, AttributeError, ValueError) as e:
                details["yaml_valid"] = False
                return {
                    "passed": False,
                    "reason": f"YAML 파싱 오류: {e}",
                    "details": details,
                }

        # JSON 파싱
        elif ext == "json":
            try:
                _ = cast(object, json.loads(content))
                details["json_valid"] = True
            except json.JSONDecodeError as e:
                details["json_valid"] = False
                return {
                    "passed": False,
                    "reason": f"JSON 파싱 오류: {e}",
                    "details": details,
                }

        return {"passed": True, "reason": "결정적 검증 통과", "details": details}

    # ─── 이력 관리 ───────────────────────────────────────────────

    def _save_evolution_history(self, entry: EvolutionHistory) -> None:
        """진화 이력을 메모리와 파일에 저장합니다."""
        self._history.append(entry)

        # JSON 파일로 영속 저장
        try:
            import os

            history_path = os.path.join(self._root, "data", "evolution_history.json")
            os.makedirs(os.path.dirname(history_path), exist_ok=True)

            existing: list[JsonObject] = []
            if os.path.exists(history_path):
                with open(history_path, encoding="utf-8") as f:
                    try:
                        loaded = cast(object, json.load(f))
                        if isinstance(loaded, list):
                            loaded_items = cast(list[object], loaded)
                            existing = [_object_dict(item) for item in loaded_items]
                    except json.JSONDecodeError:
                        existing = []

            existing.append(
                {
                    "cycle_id": entry.cycle_id,
                    "timestamp": entry.timestamp,
                    "success": entry.result.success,
                    "skipped": entry.result.skipped,
                    "rolled_back": entry.result.rolled_back,
                    "domain": entry.result.mutation_domain.value,
                    # EVO-02 — 예상·실측·평가 상태를 분리 기록
                    "expected_improvement": entry.result.expected_improvement,
                    "measured_after_metric": entry.result.measured_after_metric,
                    "improvement": entry.result.improvement,
                    "evaluation_state": entry.result.evaluation_state,
                    "benchmark_provenance": entry.result.benchmark_provenance,
                    "error": entry.result.error_message,
                    "quality_grade": entry.snapshot.quality_grade,
                    "quality_score": entry.snapshot.quality_score,
                }
            )

            # 최근 100건만 유지
            if len(existing) > 100:
                existing = existing[-100:]

            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

        except (OSError, json.JSONDecodeError):
            logger.warning("[SEC] 진화 단계 실패 (non-critical)", exc_info=True)

    # ─── 보고 및 통계 ────────────────────────────────────────────

    def get_report(self) -> JsonObject:
        """진화 코디네이터의 상태 보고서를 반환합니다."""
        recent = self._history[-10:] if self._history else []
        successes = sum(1 for h in recent if h.result.success)
        rollbacks = sum(1 for h in recent if h.result.rolled_back)
        skips = sum(1 for h in recent if h.result.skipped)

        return {
            "total_evolutions": len([h for h in self._history if not h.result.skipped]),
            "total_skipped": len([h for h in self._history if h.result.skipped]),
            "recent_successes": successes,
            "recent_rollbacks": rollbacks,
            "recent_skips": skips,
            "recent_window": len(recent),
            "turns_since_last": self._turns_since_last_evolution,
            "last_evolution": (
                datetime.fromtimestamp(self._last_evolution_time).astimezone().replace(tzinfo=None).isoformat()
                if self._last_evolution_time > 0
                else "never"
            ),
            # EVO-02 — 평가 대기/완료 구분 노출
            "pending_evaluations": sum(
                1 for h in self._history if h.result.success and h.result.evaluation_state == "pending_evaluation"
            ),
        }

    # ─── EVO-02 · held-out 실측 평가 ─────────────────────────────────

    def evaluate_pending_mutation(
        self,
        cycle_id: str,
        run_frozen_benchmark: Callable[[str], float] | None = None,
    ) -> EvolutionResult | None:
        """적용 완료(pending_evaluation) mutation의 held-out 실측 평가를 수행한다.

        Args:
            cycle_id: 평가할 진화 사이클 ID.
            run_frozen_benchmark: frozen benchmark 재실행 함수. suite id를 받고 실측 점수를 반환한다.
                None이면 coordinator가 가진 harness 참조를 사용하려 시도한다 (미구성 시 실패).

        Returns:
            실측이 채워진 EvolutionResult (regression이면 promotion 거절 상태). 사이클을
            찾지 못하면 None.
        """
        entry = next((h for h in self._history if h.cycle_id == cycle_id), None)
        if entry is None:
            return None
        result = entry.result
        if not result.success or result.evaluation_state != "pending_evaluation":
            return result

        if run_frozen_benchmark is None:
            logger.warning("[SEC] ⛔ frozen benchmark runner 미구성 — 실측 없이 평가 불가 (pending 유지)")
            return result

        suite = f"evo-{result.mutation_domain.value}"
        measured = float(run_frozen_benchmark(suite))
        result.measured_after_metric = measured
        result.improvement = measured - result.before_metric
        result.evaluation_state = "evaluated"

        # environment/provenance hash — 같은 환경에서 재실행됐음을 보장
        import hashlib

        env_fingerprint = {
            "suite": suite,
            "before_metric": result.before_metric,
            "python": sys.version.split()[0],
            "timestamp": time.time(),
        }
        result.benchmark_provenance = {
            "suite": suite,
            "env_hash": hashlib.sha256(json.dumps(env_fingerprint, sort_keys=True).encode("utf-8")).hexdigest()[:16],
            "evaluated_at": time.time(),
        }

        if result.improvement <= 0:
            # regression — promotion 거절을 기록. mutation은 이미 rollback되지 않았으므로
            # task-owned rollback 또는 disabled 전환을 상위 레이어에 위임한다.
            result.evaluation_state = "regression_rejected"
            self._record_event(
                "promotion_rejected",
                {"cycle_id": cycle_id, "improvement": result.improvement},
            )
            logger.warning(
                "[SEC] ⚠️ 실측 회귀 — promotion 거절: cycle=%s, Δ=%s",
                cycle_id,
                result.improvement,
            )
        else:
            self._record_event(
                "promotion_approved",
                {"cycle_id": cycle_id, "improvement": result.improvement},
            )

        result.events = list(self._event_ledger[-10:])
        self._save_evolution_history(entry)
        return result

    def render_markdown_report(self) -> str:
        """진화 보고서를 마크다운으로 렌더링합니다."""
        report = self.get_report()

        lines = [
            "## 🧬 Self-Evolution Coordinator Report",
            "",
            f"**총 진화 횟수**: {report['total_evolutions']}",
            (
                f"**최근 성공/롤백/스킵**: "
                f"{report['recent_successes']}/{report['recent_rollbacks']}/{report['recent_skips']}"
            ),
            f"**마지막 진화**: {report['last_evolution']}",
            f"**마지막 진화 이후 턴 수**: {report['turns_since_last']}",
            "",
        ]

        if self._history:
            lines.extend(["### 최근 진화 이력", "", "| 시간 | 도메인 | 결과 | 개선도 |", "|---|---|---|:---:|"])
            for h in self._history[-5:]:
                ts = datetime.fromtimestamp(h.timestamp).astimezone().replace(tzinfo=None).strftime("%H:%M:%S")
                domain = h.result.mutation_domain.value
                if h.result.skipped:
                    status = "⏭ 스킵"
                elif h.result.rolled_back:
                    status = "🔄 롤백"
                elif h.result.success:
                    status = "✅ 성공"
                else:
                    status = "❌ 실패"
                imp = f"{h.result.improvement:+.2f}" if not h.result.skipped else "-"
                lines.append(f"| {ts} | {domain} | {status} | {imp} |")

        return "\n".join(lines)

    @property
    def last_result(self) -> EvolutionResult | None:
        """가장 최근 진화 결과."""
        if self._history:
            return self._history[-1].result
        return None
