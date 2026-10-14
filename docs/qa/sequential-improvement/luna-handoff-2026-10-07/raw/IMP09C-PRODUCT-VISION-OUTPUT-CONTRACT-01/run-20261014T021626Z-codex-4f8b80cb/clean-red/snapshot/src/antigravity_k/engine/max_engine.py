"""Ssak-Ai: MAX Mode Parallel Editing Engine (P4).

=============================================================
Codebuff의 MAX 모드에서 영감을 받은 병렬 편집 시스템:

- 동일 태스크를 N개 워커(에디터)가 독립적으로 병렬 실행
- 각 워커는 서로 다른 모델/전략으로 접근 (다양성 확보)
- Selector 엔진이 모든 결과를 검토하고 최적 선정
- 필요 시 여러 결과를 합성하여 최종 출력 생성

아키텍처:
    WorkerPool → [Worker 1 (model A), Worker 2 (model B), ...]
         ↓ 병렬 실행 (thread pool)
    SelectorEngine → 각 결과 리뷰 → 최적 선정 또는 합성
         ↓
    최종 출력
"""

import logging
import os
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias, TypedDict, TypeGuard, final, runtime_checkable

logger = logging.getLogger("antigravity_k.max_engine")

JsonMap: TypeAlias = dict[str, object]
Message: TypeAlias = dict[str, str]


class WorkerConfig(TypedDict):
    model: str
    strategy: str
    temperature: float
    description: str


class CostDecisionProtocol(Protocol):
    allowed: bool
    reason: str
    remaining_budget_usd: float


class CostGuardProtocol(Protocol):
    def check_budget(self, model: str, tokens_in: int, tokens_out: int) -> CostDecisionProtocol: ...


class ModelRouterProtocol(Protocol):
    def get_combo(self, name: str) -> object | None: ...


class ModelManagerProtocol(Protocol):
    def generate(self, prompt: str, target: str, **kwargs: object) -> str: ...


class MaxContextProtocol(Protocol):
    cost_guard: CostGuardProtocol | None


class MaxOrchestratorProtocol(Protocol):
    manager: ModelManagerProtocol
    ctx: MaxContextProtocol

    def _get_model_for_role(self, role: str) -> str: ...


@runtime_checkable
class RoleModelResolver(Protocol):
    def __call__(self, role: str) -> str: ...


def _is_max_orchestrator(value: object) -> TypeGuard[MaxOrchestratorProtocol]:
    return (
        value is not None
        and hasattr(value, "manager")
        and hasattr(value, "ctx")
        and callable(getattr(value, "_get_model_for_role", None))
    )


def _as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _as_messages(value: object) -> list[Message]:
    if not _is_object_list(value):
        return []
    messages: list[Message] = []
    for item in value:
        if not _is_string_mapping(item):
            continue
        role = item.get("role")
        content = item.get("content")
        if isinstance(role, str) and isinstance(content, str):
            messages.append({"role": role, "content": content})
    return messages


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    if _is_string_mapping(value):
        return value
    return {}


def _is_string_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _string_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [str(item) for item in value]


def _model_names(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    names: list[str] = []
    for item in value:
        if _is_string_mapping(item):
            names.append(str(item.get("name", str(item))))
        else:
            names.append(str(item))
    return names


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


@dataclass
class WorkerResult:
    """단일 워커의 실행 결과."""

    worker_id: int
    model: str
    strategy: str
    output: str
    elapsed_sec: float
    error: str | None = None


@dataclass
class MaxRunResult:
    """MAX 모드 실행 전체 결과."""

    total_workers: int
    successful: int
    results: list[WorkerResult] = field(default_factory=list)
    selected_idx: int = -1
    final_output: str = ""
    selector_reasoning: str = ""
    error: str | None = None


@final
class MaxModeEngine:
    """MAX 모드 병렬 편집 엔진.

    Codebuff의 MAX 모드에서 영감을 받은 시스템.
    동일 태스크를 N개 워커가 독립적으로 병렬 실행하고,
    Selector가 최적 결과를 선정합니다.

    사용법:
        engine = MaxModeEngine(model_manager, project_root)
        result = engine.run(task, context, orchestrator)
        print(result.final_output)
    """

    def __init__(self, model_manager: ModelManagerProtocol | None, project_root: str = "") -> None:
        """Initialize the MaxModeEngine.

        Args:
            model_manager: ModelManager 인스턴스
            project_root: 프로젝트 루트 경로
        """
        self.manager = model_manager
        self.project_root = project_root or os.getcwd()
        self._max_workers = 4  # 기본값, 필요시 조정

    def set_max_workers(self, n: int) -> None:
        """최대 병렬 워커 수를 설정합니다."""
        self._max_workers = max(1, min(n, 8))  # 1~8 범위

    def _check_budget_before_spawn(
        self,
        orchestrator: MaxOrchestratorProtocol,
        worker_count: int,
        messages: list[Message],
        prompt: str,
    ) -> str:
        """N개 워커 spawn 전에 비용 예산을 사전 검사합니다.

        MAX 모드는 (worker_count + selector 1)회의 LLM 호출을 유발하므로,
        병렬 실행 시작 전에 CostGuard로 예산이 충분한지 확인합니다.
        예산 부족 시 에러 메시지를 반환하면, max_execute_handler가
        싱글 에이전트로 폴백합니다.

        Args:
            orchestrator: OrchestratorAgent (orch.ctx.cost_guard 접근용)
            worker_count: 실행할 워커 수
            messages: 대화 메시지 (토큰 추정용)
            prompt: 프롬프트 (토큰 추정용)

        Returns:
            str: 에러 메시지 (차단 시), 빈 문자열 (허용 시)
        """
        cost_guard = orchestrator.ctx.cost_guard
        if cost_guard is None:
            return ""  # CostGuard 미설치 — 통과 (하위 호환)

        # 토큰 추정: 입력 토큰 + 워커당 출력 토큰 * worker_count
        # 각 워커는 동일한 입력을 받고 도구 루프를 돌므로 입력은 대략 동일.
        # 보수적 추정을 위해 입력 토큰은 전체 메시지, 출력은 워커당 2k 토큰으로 가정.
        try:
            input_text = prompt
            for msg in messages:
                input_text += " " + msg.get("content", "")
            # 라틴 4자/토큰, CJK 1.5자/토큰 근사
            tokens_in_est = max(1, len(input_text) // 4)
            tokens_out_per_worker = 2000

            # N개 워커 + 1개 selector의 총 비용을 단일 check_budget로 사전 예약.
            # check_budget가 rate-limit 슬롯 1개를 소비하므로, 워커 수만큼의
            # 예상 비용을 합산하여 한 번에 검사합니다.
            total_tokens_in = tokens_in_est * worker_count
            total_tokens_out = tokens_out_per_worker * worker_count + 512  # selector

            decision = cost_guard.check_budget(
                model="max_mode",  # 가격표에 없으면 $0 추정 → rate limit으로 보호
                tokens_in=total_tokens_in,
                tokens_out=total_tokens_out,
            )
            if not decision.allowed:
                logger.warning(
                    "[MAX] 비용 게이트 차단: %s (잔여 예산 $%.4f)",
                    decision.reason,
                    decision.remaining_budget_usd,
                )
                return f"비용 예산 부족으로 MAX 모드 차단: {decision.reason}. 싱글 에이전트로 폴백합니다."
        except Exception:
            logger.debug("MAX budget check 실패 — 통과 (non-critical)", exc_info=True)
            return ""

        return ""

    def run(
        self,
        task_spec: JsonMap,
        orchestrator: object | None = None,
    ) -> MaxRunResult:
        """MAX 모드 병렬 실행.

        Args:
            task_spec: 태스크 명세
                {
                    "prompt": str,          # 실제 프롬프트
                    "messages": list,       # 대화 메시지
                    "task_type": str,       # 태스크 유형
                    "delegate_to": str,     # 위임 역할
                    "max_steps": int,       # 최대 도구 호출
                    "target_model": str,    # 대상 모델
                }
            orchestrator: OrchestratorAgent 인스턴스

        Returns:
            MaxRunResult: 실행 결과
        """
        prompt = _as_str(task_spec.get("prompt"), "")
        messages = _as_messages(task_spec.get("messages"))
        task_type = _as_str(task_spec.get("task_type"), "coding")
        delegate_to = _as_str(task_spec.get("delegate_to"), "WORKER")
        max_steps = _as_int(task_spec.get("max_steps"), 15)
        target_model = _as_str(task_spec.get("target_model"), "")

        if not self.manager or not _is_max_orchestrator(orchestrator):
            return MaxRunResult(
                total_workers=0,
                successful=0,
                error="MAX Mode requires orchestrator and model_manager",
            )

        # 1. 워커 구성 (가용 모델 목록)
        worker_configs = self._build_worker_configs(delegate_to, target_model)

        if not worker_configs:
            return MaxRunResult(
                total_workers=0,
                successful=0,
                error="No available models for MAX mode workers",
            )

        effective_workers = len(worker_configs)
        logger.info(
            "[MAX] Starting parallel execution with %s workers",
            effective_workers,
        )

        # 1.5 비용 사전 검사 — N배 비용 폭증 방지 (CostGuard 연동)
        # MAX 모드는 N개 워커 + 1개 selector = (N+1)회 LLM 호출을 유발하므로
        # spawn 전에 예산을 확인하여 무제한 과금을 방지합니다.
        budget_error = self._check_budget_before_spawn(orchestrator, effective_workers, messages, prompt)
        if budget_error:
            return MaxRunResult(
                total_workers=0,
                successful=0,
                error=budget_error,
            )

        # 2. 병렬 실행
        results: list[WorkerResult | None] = [None] * effective_workers

        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_map: dict[Future[WorkerResult], int] = {}
            for i, config in enumerate(worker_configs):
                future = executor.submit(
                    self._run_worker,
                    worker_id=i,
                    config=config,
                    prompt=prompt,
                    messages=messages,
                    task_type=task_type,
                    delegate_to=delegate_to,
                    max_steps=max_steps,
                    orchestrator=orchestrator,
                )
                future_map[future] = i

            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.exception("[MAX] Worker %s failed with exception", idx)
                    results[idx] = WorkerResult(
                        worker_id=idx,
                        model=worker_configs[idx].get("model", "unknown"),
                        strategy=worker_configs[idx].get("strategy", "unknown"),
                        output="",
                        elapsed_sec=0.0,
                        error=str(e),
                    )

        # None 결과 필터링
        valid_results = [r for r in results if r is not None]
        successful = [r for r in valid_results if r.error is None and r.output.strip()]

        def _valid_index_of(target: WorkerResult) -> int:
            # selected_idx는 results(전체) 기준으로 보고되어야 한다 —
            # 소비자(max_execute_handler)가 results[selected_idx]로 조회하기
            # 때문에 successful 압축 목록의 인덱스를 재매핑한다.
            for i, r in enumerate(valid_results):
                if r is target:
                    return i
            return -1

        # 3. Selector: 최적 결과 선정
        selected_result: WorkerResult | None = None
        if successful:
            sel = self._select_best(prompt, successful, delegate_to, orchestrator)
            if sel >= 0:
                selected_result = successful[sel]

        # 4. 최종 출력 구성
        if selected_result is not None:
            selected_idx = _valid_index_of(selected_result)
            final_output = selected_result.output
            selector_reasoning = self._format_trace(
                valid_results,
                selected_idx,
                worker_configs,
            )
        elif successful:
            # Selector 실패 시 첫 번째 성공 결과 사용
            selected_result = successful[0]
            selected_idx = _valid_index_of(selected_result)
            final_output = selected_result.output
            selector_reasoning = "> MAX Mode: Selector unavailable, using first successful result.\n\n"
        else:
            selected_idx = -1
            final_output = ""
            selector_reasoning = ""

        # 플래시 효과: 출력 앞에 MAX 모드 메타 표시
        if selector_reasoning and final_output:
            final_output = selector_reasoning + final_output

        return MaxRunResult(
            total_workers=effective_workers,
            successful=len(successful),
            results=valid_results,
            selected_idx=selected_idx,
            final_output=final_output,
            selector_reasoning=selector_reasoning,
        )

    def _build_worker_configs(
        self,
        _delegate_to: str,
        target_model: str,
    ) -> list[WorkerConfig]:
        """워커 구성을 생성합니다. (다양한 모델 + 전략 조합).

        최대 4개 워커:
        - Worker 1: target_model (default strategy, temperature 0.2)
        - Worker 2: 대상 역할의 다른 모델 (creative strategy, temperature 0.7)
        - Worker 3: 대상 역할의 또 다른 모델 (safe strategy, temperature 0.1)
        - Worker 4: fallback 모델 (balanced strategy, temperature 0.4)
        """
        configs: list[WorkerConfig] = []

        if not self.manager:
            return configs

        try:
            # 사용 가능한 모델 목록 조회
            available = self._get_available_models()
        except Exception:
            available = [target_model] if target_model else []

        if not available:
            return configs

        # Worker 1: 기본 모델 + 기본 전략
        primary = available[0] if available else target_model
        configs.append(
            {
                "model": primary,
                "strategy": "default",
                "temperature": 0.2,
                "description": "정밀 실행",
            },
        )

        # Worker 2: 다른 모델 + 창의 전략 (최대 2개까지만)
        if len(available) > 1:
            configs.append(
                {
                    "model": available[1],
                    "strategy": "creative",
                    "temperature": 0.7,
                    "description": "창의적 접근",
                },
            )

        # Worker 3: 세 번째 모델 + 안전 전략
        if len(available) > 2:
            configs.append(
                {
                    "model": available[2],
                    "strategy": "safe",
                    "temperature": 0.1,
                    "description": "안정적 접근",
                },
            )

        # Worker 4: 첫 번째 모델로 균형 전략 (워커가 최소 2개는 되도록)
        if len(configs) >= 2:
            pass  # 이미 충분

        return configs[: self._max_workers]

    def _get_available_models(self) -> list[str]:
        """실제 가용 모델 목록을 조회합니다.

        우선순위:
        1. ModelManager에 실제 로드된 모델 (최우선)
        2. combo 설정에서 사용 가능한 모델
        3. config.yaml의 reasoning/coding 모델
        4. agent_models 매핑
        """
        models: list[str] = []

        try:
            # 1. 실제 로드된 모델 우선
            loaded: Mapping[str, object] | list[object] | None = getattr(
                self.manager, "_loaded_models", None
            ) or getattr(
                self.manager,
                "loaded_models",
                None,
            )
            if loaded and isinstance(loaded, Mapping):
                models = [str(key) for key in list(loaded.keys())[:4]]
            elif loaded and isinstance(loaded, list):
                models = _model_names(loaded[:4])

            # 실제 로드된 모델이 2개 이상 있으면 바로 반환
            if len(models) >= 2:
                return models[: self._max_workers]

            # 2. 로드된 모델 부족 시 config에서 추가
            config = _mapping_or_empty(getattr(self.manager, "config", {}))
            combos = _mapping_or_empty(config.get("combos", {}))

            preferred_combos = ["reasoning-balanced", "fast-response", "coding-swarm"]
            for combo_name in preferred_combos:
                combo = _mapping_or_empty(combos.get(combo_name, {}))
                for model_name in _string_list(combo.get("models", [])):
                    if model_name not in models:
                        models.append(model_name)
                        if len(models) >= 4:
                            break
                if len(models) >= 4:
                    break

            if len(models) < 2:
                agents_config = _mapping_or_empty(config.get("agent_models", {}))
                for role in ("WORKER", "ENG_MANAGER"):
                    model = agents_config.get(role, "")
                    if model and model not in models:
                        models.append(str(model))
        except Exception:
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)

        # 최소 1개는 보장 (loaded or config에서 찾은 것)
        if not models:
            models = ["default"]

        return models[: self._max_workers]

    def _run_worker(
        self,
        worker_id: int,
        config: WorkerConfig,
        prompt: str,
        messages: list[Message],
        task_type: str,
        delegate_to: str,
        max_steps: int,
        orchestrator: MaxOrchestratorProtocol,
    ) -> WorkerResult:
        """단일 워커를 실행합니다."""
        model = config.get("model", "default")
        strategy = config.get("strategy", "default")

        # 워커별 전략이 담긴 프롬프트 주입
        worker_prompt = self._build_worker_prompt(
            original_prompt=prompt,
            model=model,
            strategy=strategy,
            _temperature=float(config.get("temperature", 0.4)),
        )

        worker_messages = list(messages)
        worker_messages[-1] = {"role": "user", "content": worker_prompt}

        # 워커별 온도를 실제 샘플링 파라미터로 전달한다 — 프롬프트 문자열에만
        # 담아 폐기되면 단일 모델 환경에서 N개 워커가 사실상 동일 샘플이 된다.
        worker_sampling = {"temperature": float(config.get("temperature", 0.4))}

        start = time.time()
        try:
            from antigravity_k.engine.tool_loop import ToolLoopEngine

            tool_loop = ToolLoopEngine(orchestrator)
            output_parts: list[str] = []

            for chunk in tool_loop.run_loop(
                worker_messages,
                delegate_to,
                task_type,
                max_steps,
                model,
                sampling_overrides=worker_sampling,
            ):
                output_parts.append(chunk)

            elapsed = time.time() - start
            output = "".join(output_parts)

            logger.info(
                "[MAX] Worker %s (%s, %s) done in %.1fs, %s chars",
                worker_id,
                model,
                strategy,
                elapsed,
                len(output),
            )

            return WorkerResult(
                worker_id=worker_id,
                model=model,
                strategy=strategy,
                output=output,
                elapsed_sec=round(elapsed, 1),
            )
        except Exception as e:
            elapsed = time.time() - start
            logger.exception("[MAX] Worker %s failed", worker_id)
            return WorkerResult(
                worker_id=worker_id,
                model=model,
                strategy=strategy,
                output="",
                elapsed_sec=round(elapsed, 1),
                error=str(e),
            )

    def _build_worker_prompt(
        self,
        original_prompt: str,
        model: str,
        strategy: str,
        _temperature: float,
    ) -> str:
        """워커별 전략이 반영된 프롬프트를 생성합니다."""
        strategy_intro = {
            "default": ("Execute the following task precisely. Focus on correctness and completeness."),
            "creative": (
                "Approach the following task with creative problem-solving. "
                "Consider unconventional approaches, edge cases, and elegant solutions. "
                "Don't be afraid to refactor or restructure if it improves quality."
            ),
            "safe": (
                "Execute the following task with maximum safety and reliability. "
                "Prefer well-established patterns, minimal changes, and defensive programming. "
                "Prioritize backward compatibility and readability."
            ),
            "balanced": (
                "Execute the following task balancing pragmatism and quality. "
                "Use sound engineering judgment. Choose the approach that gives the best "
                "trade-off between simplicity, correctness, and maintainability."
            ),
        }

        intro = strategy_intro.get(strategy, strategy_intro["default"])

        return f"[MAX Mode Worker - {model}, {strategy}]\n\n{intro}\n\n---\n{original_prompt}"

    def _select_best(
        self,
        prompt: str,
        results: list[WorkerResult],
        delegate_to: str,
        orchestrator: MaxOrchestratorProtocol | None,
    ) -> int:
        """Selector: 모든 결과를 검토하고 최적 인덱스를 반환합니다.

        여러 결과를 비교하여 가장 적합한 하나를 선택합니다.
        선택이 불가능하면 -1을 반환합니다.
        """
        if len(results) == 1:
            return 0

        # 결과 포맷팅
        candidates: list[str] = []
        for i, r in enumerate(results):
            output_preview = r.output[:800] if r.output else "(empty)"
            candidates.append(
                f"[Candidate {i + 1}] — Model: {r.model}, Strategy: {r.strategy}\n"
                + f"Time: {r.elapsed_sec}s, Length: {len(r.output)} chars\n"
                + f"---\n{output_preview}\n---\n",
            )

        candidate_text = "\n\n".join(candidates)

        # Selector 프롬프트 — JSON 강제(문법 제약 디코딩)로 형식 실패 제거.
        # 제어 평면은 항상 no-think이므로 thinking 충돌이 없다.
        selector_prompt = (
            "You are the MAX Mode Selector. Review the following candidate outputs "
            "generated by different AI models/strategies for the same task.\n\n"
            "Select the BEST output based on:\n"
            "1. Correctness — Does it solve the task correctly?\n"
            "2. Completeness — Does it handle edge cases?\n"
            "3. Code Quality — Is the code clean, well-structured?\n"
            "4. Efficiency — Is the solution performant?\n\n"
            "Respond in EXACTLY this JSON format:\n"
            '{"selected": <candidate number (1-based)>, "reason": "<one-line reason>"}\n\n'
            f"Original task:\n{prompt[:500]}\n\n"
            f"{candidate_text}"
        )

        try:
            # QA 모델로 Selector 실행
            qa_model = self._get_qa_model(delegate_to, orchestrator)

            if orchestrator is None:
                return 0

            # 비용 게이트: selector LLM 호출 전 예산 확인 (추가 비용 보호)
            cost_guard = orchestrator.ctx.cost_guard
            if cost_guard is not None:
                from antigravity_k.engine.tokenizer import TokenEstimator

                sel_decision = cost_guard.check_budget(
                    model=qa_model,
                    tokens_in=TokenEstimator.estimate_text(selector_prompt),
                    tokens_out=256,
                )
                if not sel_decision.allowed:
                    logger.warning(
                        "[MAX] Selector 비용 게이트 차단: %s — 후보 1번으로 폴백",
                        sel_decision.reason,
                    )
                    # selector 없이 첫 번째 성공 후보 선택
                    successful = [(i, r) for i, r in enumerate(results) if r and r.error is None and r.output.strip()]
                    if successful:
                        return successful[0][0]
                    return -1

            response = orchestrator.manager.generate(
                prompt=selector_prompt,
                target=qa_model,
                max_tokens=256,
                response_format="json",
            )
            response = response.strip()

            # 1차: JSON 파싱 (문법 제약으로 대부분 여기서 성공)
            selected = self._parse_selected_json(response, len(results))
            if selected is not None:
                return selected

            # 2차 폴백: 레거시 "SELECTED: N" 라인 스캔
            for line in response.split("\n"):
                line = line.strip()
                if line.startswith("SELECTED:"):
                    num_str = line.split("SELECTED:")[1].strip()
                    try:
                        selected = int(num_str) - 1  # 1-based → 0-based
                        if 0 <= selected < len(results):
                            return selected
                    except ValueError:
                        logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)

            # SELECTED를 찾지 못하면 첫 번째 결과 사용
            return 0
        except Exception:
            logger.debug("[MAX] Selector failed, using first result")
            return 0

    @staticmethod
    def _parse_selected_json(response: str, n_results: int) -> int | None:
        import json as _json

        try:
            data = _json.loads(response)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        raw = data.get("selected")
        if isinstance(raw, bool) or not isinstance(raw, (int, str)):
            return None
        try:
            selected = int(raw) - 1  # 1-based → 0-based
        except (ValueError, TypeError):
            return None
        if 0 <= selected < n_results:
            return selected
        return None

    def _get_qa_model(self, _delegate_to: str, orchestrator: MaxOrchestratorProtocol | None) -> str:
        """Selector용 QA 모델을 반환합니다."""
        if orchestrator is None:
            return "default"
        resolver: object = getattr(orchestrator, "_get_model_for_role", None)
        if isinstance(resolver, RoleModelResolver):
            return resolver("QA")
        return "default"

    def _format_trace(
        self,
        results: list[WorkerResult],
        selected_idx: int,
        configs: Sequence[Mapping[str, object]],
    ) -> str:
        """MAX 모드 실행 트레이스를 포맷팅합니다."""
        _ = configs
        worker_details: list[str] = []
        for i, r in enumerate(results):
            marker = "← SELECTED" if i == selected_idx else ""
            worker_details.append(
                f"  Worker {i + 1}: {r.model} [{r.strategy}] — {len(r.output)} chars in {r.elapsed_sec}s {marker}",
            )

        return (
            f"⚡ **[MAX Mode]** {len(results)}개 워커 병렬 실행 → Selector 선정 완료\n"
            + "\n".join(worker_details)
            + "\n\n"
        )
