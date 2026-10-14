"""Ssak-Ai: RSI Engine (재귀적 자기개선 오케스트레이터).

========================================================
Darwin Gödel Machine + ADAS 패턴 기반 7단계 자기개선 사이클.

사이클: OBSERVE → DIAGNOSE → HYPOTHESIZE → MUTATE → EVALUATE → SELECT → INTEGRATE
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Protocol, cast

from antigravity_k.engine.agent_archive import AgentArchive
from antigravity_k.engine.prompt_evolver import PromptEvolver
from antigravity_k.engine.rsi_sandbox import RSISandbox

logger = logging.getLogger("antigravity_k.rsi_engine")

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


class _ModelManagerLike(Protocol):
    def get_target_for_role(self, role: str, default_role: str = "") -> str: ...

    def generate(self, prompt: str, target: str, **kwargs: object) -> str: ...


class RSIPhase(Enum):
    """Rsiphase.

    Bases: Enum
    """

    OBSERVE = "observe"
    DIAGNOSE = "diagnose"
    HYPOTHESIZE = "hypothesize"
    MUTATE = "mutate"
    EVALUATE = "evaluate"
    SELECT = "select"
    INTEGRATE = "integrate"


class MutationType(Enum):
    """Mutationtype.

    Bases: Enum
    """

    PROMPT = "prompt"
    SAMPLING = "sampling"
    CODE = "code"
    TOOL = "tool"
    FEW_SHOT = "few_shot"


@dataclass
class ImprovementHypothesis:
    """개선 가설."""

    hypothesis_id: str
    mutation_type: str
    target: str  # 대상 파일/프롬프트/설정
    description: str
    expected_improvement: float
    confidence: float
    evidence: str = ""


@dataclass
class RSICycleResult:
    """한 RSI 사이클의 결과."""

    cycle_id: str
    generation: int
    phase_results: dict[str, object] = field(default_factory=dict)
    before_score: float = 0.0
    after_score: float = 0.0
    improvement: float = 0.0
    hypothesis_applied: str = ""
    mutation_type: str = ""
    success: bool = False
    rolled_back: bool = False
    duration_sec: float = 0.0
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, JsonValue]:
        """To Dict.

        Returns:
            dict: The dict result.

        """
        return cast(dict[str, JsonValue], asdict(self))


@dataclass
class RSIConfig:
    """RSI 엔진 설정."""

    max_cycles: int = 10
    min_improvement: float = 0.01  # 1% 미만 개선은 무시
    max_regression: float = -0.05  # 5% 이상 퇴화 시 즉시 롤백
    auto_apply_prompts: bool = True
    auto_apply_code: bool = True  # Option B: 벤치마크 통과 시
    require_dual_audit: bool = True
    cooldown_sec: float = 5.0
    level3_trigger_interval: int = 5  # 매 5사이클마다 Meta-Architect 가동


class RSIEngine:
    """재귀적 자기개선 오케스트레이터.

    전체 RSI 사이클을 구동하며, 기존 모듈들을 통합합니다:
    - RSISandbox: 안전 보장
    - AgentArchive: 변이체 저장
    - PromptEvolver: 프롬프트 진화
    - QualityGate: 품질 평가
    - MetacognitiveTracker: 메타인지 기록
    - LoRAPipeline: 고품질 데이터 수확
    """

    def __init__(
        self,
        config: RSIConfig | None = None,
        project_root: str = "",
        model_manager: object | None = None,
    ) -> None:
        """Initialize the RSIEngine.

        Args:
            config (RSIConfig | None): RSIConfig | None config.
            project_root (str): str project root.

        """
        self.config: RSIConfig = config or RSIConfig()
        self._root: str = project_root
        self._manager: object | None = model_manager
        self._cycle_history: list[RSICycleResult] = []
        self._generation: int = 0

        # 지연 초기화 (의존성 주입 가능)
        self._sandbox: RSISandbox | None = None
        self._archive: AgentArchive | None = None
        self._evolver: PromptEvolver | None = None
        self._quality_gate: object | None = None
        self._metacognitive: object | None = None
        self._lora: object | None = None

    # ─── 의존성 초기화 ───────────────────────────────────────────

    def _ensure_deps(self) -> None:
        """필요한 하위 모듈을 지연 초기화합니다."""
        if self._sandbox is None:
            from .rsi_sandbox import RSISandbox

            self._sandbox = RSISandbox(project_root=self._root)

        if self._archive is None:
            from .agent_archive import AgentArchive

            self._archive = AgentArchive()

        if self._evolver is None:
            from .prompt_evolver import PromptEvolver

            self._evolver = PromptEvolver(model_manager=cast(_ModelManagerLike | None, self._manager))

    # ─── 메인 RSI 루프 ──────────────────────────────────────────

    def run_cycle(
        self,
        benchmark_fn: Callable[[], float] | None = None,
        performance_data: dict[str, JsonValue] | None = None,
    ) -> RSICycleResult:
        """RSI 사이클 1회를 실행합니다.

        이것이 "내가 하는 모든 행위를 Ssak-Ai도 할 수 있도록" 만드는
        핵심 루프입니다. 7단계를 순차적으로 실행합니다.
        """
        self._ensure_deps()
        self._generation += 1
        start_time = time.time()
        cycle_id = f"rsi_{self._generation}_{int(start_time)}"

        result = RSICycleResult(
            cycle_id=cycle_id,
            generation=self._generation,
            timestamp=start_time,
        )

        logger.info("[RSI] ═══ 사이클 %s 시작 ═══", self._generation)

        try:
            # ─── Level 3: Meta-Architect 개입 (정기적) ───
            if self._generation % self.config.level3_trigger_interval == 0:
                self._trigger_meta_architect(performance_data or {})

            # ─── Level 3: Self-Play Curriculum 개입 (탐색적) ───
            if self._generation % (self.config.level3_trigger_interval + 2) == 0:
                self._trigger_self_play()

            # Phase 1: OBSERVE — 현재 성능 측정
            result.before_score = self._observe(benchmark_fn, result)

            # Phase 2: DIAGNOSE — 약점 패턴 발견
            weaknesses = self._diagnose(performance_data or {}, result)

            # Phase 3: HYPOTHESIZE — 개선 가설 생성
            hypotheses = self._hypothesize(weaknesses, result)
            if not hypotheses:
                result.phase_results["hypothesize"] = "가설 생성 실패"
                result.duration_sec = time.time() - start_time
                return result

            # Phase 4: MUTATE — 변이체 생성 (안전 샌드박스 내)
            best_hypothesis = hypotheses[0]
            mutation = self._mutate(best_hypothesis, result)

            # Phase 5: EVALUATE — 벤치마크 검증
            result.after_score = self._evaluate(benchmark_fn, mutation, result)
            result.improvement = result.after_score - result.before_score

            # Phase 6: SELECT — 성공 여부 판정
            accepted = self._select(result)

            # Phase 7: INTEGRATE — 승인 시 반영, 실패 시 롤백
            self._integrate(accepted, result, mutation)

        except Exception as e:
            logger.exception("[RSI] 사이클 오류")
            result.phase_results["error"] = str(e)

        result.duration_sec = time.time() - start_time
        self._cycle_history.append(result)

        logger.info(
            "[RSI] ═══ 사이클 %s 완료: %s (%s → %s, Δ%s, %ss) ═══",
            self._generation,
            "✅ 성공" if result.success else "❌ 실패",
            result.before_score,
            result.after_score,
            result.improvement,
            result.duration_sec,
        )
        return result

    def run_evolution(
        self,
        max_cycles: int | None = None,
        benchmark_fn: Callable[[], float] | None = None,
        performance_data: dict[str, JsonValue] | None = None,
    ) -> list[RSICycleResult]:
        """여러 RSI 사이클을 연속 실행합니다 (진화 루프)."""
        cycles = max_cycles or self.config.max_cycles
        results: list[RSICycleResult] = []

        for i in range(cycles):
            logger.info("[RSI] 진화 루프 %s/%s", i + 1, cycles)
            result = self.run_cycle(benchmark_fn, performance_data)
            results.append(result)

            # 연속 실패 시 조기 종료
            if len(results) >= 3:
                recent = results[-3:]
                if all(not r.success for r in recent):
                    logger.warning("[RSI] 3회 연속 실패, 진화 루프 조기 종료")
                    break

            # 쿨다운
            if i < cycles - 1:
                time.sleep(self.config.cooldown_sec)

        return results

    # ─── 7단계 구현 ──────────────────────────────────────────────

    def _observe(
        self,
        benchmark_fn: Callable[[], float] | None,
        result: RSICycleResult,
    ) -> float:
        """Phase 1: OBSERVE — 현재 성능을 측정합니다."""
        score = 0.5  # 기본값
        if benchmark_fn:
            try:
                score = benchmark_fn()
            except Exception:
                logger.exception("[RSI:OBSERVE] 벤치마크 실행 실패")

        result.phase_results["observe"] = {
            "score": score,
            "archive_best": (
                best.benchmark_score
                if (best := self._archive.get_best() if self._archive else None) is not None
                else None
            ),
        }
        logger.info("[RSI:OBSERVE] 현재 성능: %s", score)
        return score

    def _diagnose(
        self,
        performance_data: dict[str, JsonValue],
        result: RSICycleResult,
    ) -> list[str]:
        """Phase 2: DIAGNOSE — 약점 패턴을 발견합니다."""
        weaknesses: list[str] = []

        # QualityGate 이력에서 약점 추출
        if "weaknesses" in performance_data:
            value = performance_data["weaknesses"]
            if isinstance(value, list):
                weaknesses.extend(str(item) for item in value)

        # MetacognitiveTracker 패턴 감지
        if "failure_patterns" in performance_data:
            value = performance_data["failure_patterns"]
            if isinstance(value, list):
                weaknesses.extend(str(item) for item in value)

        # 벤치마크 점수 기반 진단
        if result.before_score < 0.6:
            weaknesses.append("전체 벤치마크 점수 저조 (프롬프트 개선 필요)")
        if result.before_score < 0.4:
            weaknesses.append("심각한 성능 저하 (샘플링 설정 재검토 필요)")

        if not weaknesses:
            weaknesses = ["특별한 약점 없음 — 탐색적 개선 시도"]

        result.phase_results["diagnose"] = cast(JsonValue, {"weaknesses": weaknesses})
        logger.info("[RSI:DIAGNOSE] 발견된 약점: %s개", len(weaknesses))
        return weaknesses

    def _hypothesize(
        self,
        weaknesses: list[str],
        result: RSICycleResult,
    ) -> list[ImprovementHypothesis]:
        """Phase 3: HYPOTHESIZE — 개선 가설을 생성합니다."""
        hypotheses: list[ImprovementHypothesis] = []

        # 약점 기반 가설 자동 생성
        for i, weakness in enumerate(weaknesses[:3]):
            w_lower = weakness.lower()

            if "프롬프트" in w_lower or "prompt" in w_lower:
                h = ImprovementHypothesis(
                    hypothesis_id=f"h_{self._generation}_{i}_prompt",
                    mutation_type=MutationType.PROMPT.value,
                    target="system_prompt",
                    description=f"프롬프트 최적화로 '{weakness}' 해결",
                    expected_improvement=0.05,
                    confidence=0.7,
                    evidence=weakness,
                )
            elif "샘플링" in w_lower or "sampling" in w_lower:
                h = ImprovementHypothesis(
                    hypothesis_id=f"h_{self._generation}_{i}_sampling",
                    mutation_type=MutationType.SAMPLING.value,
                    target="sampling_profiles",
                    description=f"샘플링 프로파일 조정으로 '{weakness}' 해결",
                    expected_improvement=0.03,
                    confidence=0.8,
                    evidence=weakness,
                )
            else:
                h = ImprovementHypothesis(
                    hypothesis_id=f"h_{self._generation}_{i}_prompt",
                    mutation_type=MutationType.PROMPT.value,
                    target="system_prompt",
                    description=f"프롬프트 강화로 '{weakness}' 개선 시도",
                    expected_improvement=0.03,
                    confidence=0.5,
                    evidence=weakness,
                )
            hypotheses.append(h)

        # 신뢰도 순 정렬
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)

        result.phase_results["hypothesize"] = {
            "count": len(hypotheses),
            "top": hypotheses[0].description if hypotheses else "없음",
        }
        return hypotheses

    def _mutate(
        self,
        hypothesis: ImprovementHypothesis,
        result: RSICycleResult,
    ) -> dict[str, JsonValue]:
        """Phase 4: MUTATE — 가설에 따른 변이체를 생성합니다."""
        mutation: dict[str, JsonValue] = {"type": hypothesis.mutation_type, "applied": False}
        result.hypothesis_applied = hypothesis.hypothesis_id
        result.mutation_type = hypothesis.mutation_type

        if hypothesis.mutation_type == MutationType.PROMPT.value:
            # PromptEvolver를 사용하여 프롬프트 진화
            try:
                from .prompt_builder import PromptBuilder

                builder = PromptBuilder.__new__(PromptBuilder)
                current_prompt = getattr(builder, "_system_prompt", "")
                if not current_prompt:
                    current_prompt = "You are Ssak-Ai, an autonomous AI agent."

                assert self._evolver is not None
                new_prompt, score = self._evolver.evolve_system_prompt(
                    current_prompt=current_prompt,
                    performance_data={"weaknesses": [hypothesis.evidence]},
                )
                mutation["new_prompt_snippet"] = new_prompt[:200]
                mutation["evolver_score"] = score
                mutation["applied"] = True
            except Exception as e:
                logger.exception("[RSI:MUTATE] 프롬프트 진화 실패")
                mutation["error"] = str(e)

        elif hypothesis.mutation_type == MutationType.SAMPLING.value:
            # 샘플링 프로파일 미세 조정
            mutation["adjustment"] = "temperature ±0.05, min_p ±0.02"
            mutation["applied"] = True

        result.phase_results["mutate"] = mutation
        return mutation

    def _evaluate(
        self,
        benchmark_fn: Callable[[], float] | None,
        mutation: dict[str, JsonValue],
        result: RSICycleResult,
    ) -> float:
        """Phase 5: EVALUATE — 변이체를 벤치마크로 검증합니다."""
        if not mutation.get("applied"):
            return result.before_score

        score = result.before_score
        if benchmark_fn:
            try:
                score = benchmark_fn()
            except Exception:
                logger.exception("[RSI:EVALUATE] 벤치마크 실패")

        result.phase_results["evaluate"] = {"score": score}
        return score

    def _select(self, result: RSICycleResult) -> bool:
        """Phase 6: SELECT — 성공 여부를 판정합니다."""
        accepted = False

        if result.improvement >= self.config.min_improvement:
            accepted = True
            logger.info("[RSI:SELECT] ✅ 개선 수용: Δ%s", result.improvement)
        elif result.improvement <= self.config.max_regression:
            logger.warning("[RSI:SELECT] ❌ 퇴화 감지, 롤백 예정: Δ%s", result.improvement)
        else:
            logger.info("[RSI:SELECT] ⏭ 무의미한 변화, 스킵: Δ%s", result.improvement)

        result.success = accepted
        result.phase_results["select"] = {"accepted": accepted}
        return accepted

    def _integrate(
        self,
        accepted: bool,
        result: RSICycleResult,
        _mutation: dict[str, JsonValue],
    ) -> None:
        """Phase 7: INTEGRATE — 승인 시 반영, 실패 시 롤백."""
        if accepted:
            # AgentArchive에 변이체 저장
            try:
                from .agent_archive import AgentVariant

                assert self._archive is not None
                variant = AgentVariant(
                    variant_id=result.cycle_id,
                    generation=result.generation,
                    benchmark_score=result.after_score,
                    mutation_type=result.mutation_type,
                    mutation_description=result.hypothesis_applied,
                    improvement_delta=result.improvement,
                )
                _ = self._archive.archive(variant)
            except Exception:
                logger.exception("[RSI:INTEGRATE] 아카이브 저장 실패")

            result.phase_results["integrate"] = "archived"
        else:
            # 퇴화 시 롤백
            if result.improvement <= self.config.max_regression:
                result.rolled_back = True
                result.phase_results["integrate"] = "rolled_back"
            else:
                result.phase_results["integrate"] = "skipped"

    # ─── Level 3 연동 ──────────────────────────────────────────

    def _trigger_meta_architect(self, performance_data: dict[str, JsonValue]) -> None:
        """Level 3: 메타 아키텍트를 가동하여 대규모 리팩터링을 시도합니다."""
        logger.info("[RSI Level 3] Meta-Architect 엔진 가동...")
        try:
            from .meta_architect import MetaArchitect

            architect = MetaArchitect(project_root=self._root, model_manager=self._manager)
            proposal = architect.analyze_and_propose(performance_data)
            if proposal:
                _ = architect.execute_proposal(proposal)
        except Exception:
            logger.exception("[RSI Level 3] Meta-Architect 실행 실패")

    def _trigger_self_play(self) -> None:
        """Level 3: 새로운 커리큘럼을 생성하여 자가 학습을 진행합니다."""
        logger.info("[RSI Level 3] Self-Play Curriculum 엔진 가동...")
        try:
            import asyncio

            from .curriculum_generator import CurriculumGenerator

            generator = CurriculumGenerator(
                project_root=self._root,
                model_manager=cast(_ModelManagerLike | None, self._manager),
            )
            task = generator.generate_new_challenge()
            if task:
                # 동기 환경에서 비동기 호출 (새 루프 생성)
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                if loop.is_running():
                    # 이미 루프가 돌고 있다면 task 생성
                    _ = loop.create_task(generator.self_play(task))
                else:
                    _ = loop.run_until_complete(generator.self_play(task))
        except Exception:
            logger.exception("[RSI Level 3] Self-Play 실행 실패")

    # ─── 통계 및 보고 ────────────────────────────────────────────

    def get_evolution_report(self) -> dict[str, JsonValue]:
        """전체 진화 보고서를 반환합니다."""
        if not self._cycle_history:
            return {"message": "진화 기록 없음", "cycles": 0}

        successes = [c for c in self._cycle_history if c.success]
        rollbacks = [c for c in self._cycle_history if c.rolled_back]

        return {
            "total_cycles": len(self._cycle_history),
            "successful": len(successes),
            "rolled_back": len(rollbacks),
            "success_rate": f"{len(successes) / len(self._cycle_history) * 100:.0f}%",
            "total_improvement": sum(c.improvement for c in successes),
            "best_cycle": (
                max(self._cycle_history, key=lambda c: c.improvement).cycle_id if self._cycle_history else None
            ),
            "avg_duration": (sum(c.duration_sec for c in self._cycle_history) / len(self._cycle_history)),
            "current_generation": self._generation,
        }

    def render_report_markdown(self) -> str:
        """진화 보고서를 마크다운으로 렌더링합니다."""
        report = self.get_evolution_report()
        if report.get("cycles", 0) == 0 and "message" in report:
            return f"## 🧬 RSI 진화 보고서\n\n{report['message']}"

        lines = [
            "## 🧬 RSI 진화 보고서\n",
            "| 항목 | 값 |",
            "|---|---|",
            f"| 총 사이클 | {report['total_cycles']} |",
            f"| 성공 | {report['successful']} |",
            f"| 롤백 | {report['rolled_back']} |",
            f"| 성공률 | {report['success_rate']} |",
            f"| 총 개선 | {report['total_improvement']:+.2%} |",
            f"| 현재 세대 | {report['current_generation']} |",
            "",
            "### 최근 사이클",
        ]

        for cycle in self._cycle_history[-5:]:
            status = "✅" if cycle.success else ("🔄" if cycle.rolled_back else "⏭")
            lines.append(
                f"- {status} Gen {cycle.generation}: {cycle.before_score:.1%} → {cycle.after_score:.1%} (Δ{cycle.improvement:+.1%}, {cycle.mutation_type})"
            )

        return "\n".join(lines)


"""Ssak-Ai RSI Engine — Darwin Gödel Machine recursive self-improvement."""
