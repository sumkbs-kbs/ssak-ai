"""Ssak-Ai: Prompt Evolver (OPRO 기반 프롬프트 자동 최적화).

=============================================================
LLM이 자기 시스템 프롬프트를 분석하고 최적화하는 자동 진화 엔진.

연구 근거: OPRO (Google DeepMind), MetaSPO (Bilevel Optimization),
          Grammar-Guided Genetic Programming (G3P)

핵심 개념:
  OPRO 루프:
    1. 현재 프롬프트 + 최근 성능 데이터를 Optimizer LLM에 전달
    2. Optimizer가 새 프롬프트 후보 N개 생성
    3. 각 후보를 동일 테스트 세트에서 실행
    4. 최고 성능 프롬프트를 선택하여 교체

  "내가 하는 것과 같은 행위":
    - 나(Ssak-Ai)가 프롬프트를 수정하는 것과 정확히 같은 방식으로
    - Ssak-Ai의 LLM이 자기 프롬프트를 수정합니다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol, TypeAlias, cast, final

from antigravity_k.config import config
from antigravity_k.tools.egress_policy import safe_urlopen

logger = logging.getLogger("antigravity_k.prompt_evolver")
JsonMap: TypeAlias = dict[str, object]


class ModelManagerLike(Protocol):
    def get_target_for_role(self, role: str, *, default_role: str) -> object: ...

    def generate(self, *args: object, **kwargs: object) -> object: ...


def _as_mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def _as_string_list(value: object) -> list[str]:
    items = cast(list[object], value) if isinstance(value, list) else []
    return [item for item in items if isinstance(item, str)]


def _as_int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _as_float(value: object, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


@dataclass
class PromptCandidate:
    """프롬프트 후보 1건."""

    candidate_id: str
    content: str
    generation: int
    parent_id: str = ""
    score: float = 0.0
    keyword_coverage: float = 0.0
    latency_ms: float = 0.0
    mutation_op: str = ""  # rephrase, expand, compress, restructure
    metadata: JsonMap = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Content Hash.

        Returns:
            str: The str result.

        """
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]


@dataclass
class EvolutionRecord:
    """프롬프트 진화 기록 1건."""

    generation: int
    candidates_tested: int
    best_score: float
    selected_id: str
    timestamp: float
    improvement: float = 0.0


@final
class PromptEvolver:
    """OPRO 기반 프롬프트 자동 최적화 엔진.

    LLM이 자기 시스템 프롬프트를 분석하고,
    더 나은 프롬프트 후보를 생성하여 벤치마크로 검증합니다.
    """

    # 프롬프트 변이 연산자
    MUTATION_OPS = [
        "rephrase",  # 동일 의미, 다른 표현
        "expand",  # 세부 지시사항 추가
        "compress",  # 핵심만 남기고 압축
        "restructure",  # 섹션 순서/구조 변경
        "add_constraint",  # 제약 조건 추가 (환각 방지 등)
        "add_example",  # 예시 추가
    ]

    def __init__(
        self,
        ollama_url: str | None = None,
        optimizer_model: str = "",
        candidates_per_gen: int = 3,
        persist_dir: str = "data/prompt_evolution",
        model_manager: object | None = None,
    ):
        """Initialize the PromptEvolver.

        Args:
            ollama_url (str): str ollama url.
            optimizer_model (str): str optimizer model.
            candidates_per_gen (int): int candidates per gen.
            persist_dir (str): str persist dir.

        """
        self._ollama_url: str = ollama_url or config.model.api_base.replace("/v1", "").rstrip("/")
        self._optimizer_model: str = optimizer_model
        self._manager: object | None = model_manager
        self._candidates_per_gen: int = candidates_per_gen
        self._persist_dir: Path = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._history: list[EvolutionRecord] = []
        self._generation = 0
        self._load_history()

    # ─── 핵심 API ────────────────────────────────────────────────

    def evolve_system_prompt(
        self,
        current_prompt: str,
        performance_data: JsonMap,
        eval_fn: Callable[[str], float] | None = None,
    ) -> tuple[str, float]:
        """시스템 프롬프트를 한 세대 진화시킵니다.

        Args:
            current_prompt: 현재 시스템 프롬프트
            performance_data: 최근 성능 데이터 (점수, 실패 패턴 등)
            eval_fn: 프롬프트 평가 함수 (prompt -> score 0.0~1.0)

        Returns:
            (best_prompt, best_score) 튜플

        """
        self._generation += 1
        logger.info(
            "[PromptEvolver] 세대 %s 시작 (후보 %s개 생성)",
            self._generation,
            self._candidates_per_gen,
        )

        # 1. 현재 프롬프트 기준 점수
        current_score = eval_fn(current_prompt) if eval_fn else 0.5
        current_candidate = PromptCandidate(
            candidate_id=f"current_{self._generation}",
            content=current_prompt,
            generation=self._generation,
            score=current_score,
            mutation_op="baseline",
        )

        # 2. 후보 생성 (OPRO: LLM이 자기 프롬프트를 분석하고 개선안 제안)
        candidates = [current_candidate]
        new_candidates = self._generate_candidates(current_prompt, performance_data)
        candidates.extend(new_candidates)

        # 3. 각 후보 평가
        if eval_fn:
            for c in new_candidates:
                try:
                    c.score = eval_fn(c.content)
                except Exception:
                    logger.exception("[PromptEvolver] 평가 실패: %s", c.candidate_id)
                    c.score = 0.0

        # 4. 최고 성능 프롬프트 선택
        best = max(candidates, key=lambda c: c.score)
        improvement = best.score - current_score

        # 진화 기록
        record = EvolutionRecord(
            generation=self._generation,
            candidates_tested=len(candidates),
            best_score=best.score,
            selected_id=best.candidate_id,
            timestamp=time.time(),
            improvement=improvement,
        )
        self._history.append(record)
        self._save_history()

        # 프롬프트 버전 저장
        self._save_prompt_version(best)

        logger.info(
            "[PromptEvolver] 세대 %s 완료: 최고 %s (Δ%s), 선택: %s",
            self._generation,
            best.score,
            improvement,
            best.mutation_op,
        )

        return best.content, best.score

    def evolve_few_shots(
        self,
        current_examples: list[dict[str, str]],
        task_type: str,
        eval_fn: Callable[..., object] | None = None,
    ) -> list[dict[str, str]]:
        """Few-shot 예시를 자동 발견/교체합니다.

        기존 예시를 분석하고 더 효과적인 예시를 LLM에게 생성하게 합니다.
        """
        prompt = (
            "[ROLE] 당신은 AI 프롬프트 엔지니어링 전문가입니다.\n\n"
            + "[TASK] 아래 few-shot 예시를 분석하고, "
            + f"'{task_type}' 작업에 더 효과적인 예시 3개를 생성하세요.\n\n"
            + "현재 예시:\n"
            + json.dumps(current_examples, ensure_ascii=False, indent=2)
            + "\n\n"
            + "더 나은 예시를 JSON 배열로 반환하세요. "
            + '각 예시는 {"input": "...", "output": "..."} 형태입니다.\n'
            + "JSON만 반환하세요."
        )
        _ = eval_fn

        try:
            response = self._call_optimizer(prompt)
            # JSON 추출
            examples = self._extract_json_array(response)
            if examples:
                return [cast(dict[str, str], item) for item in examples[:3] if isinstance(item, dict)]
        except Exception:
            logger.exception("[PromptEvolver] Few-shot 진화 실패")

        return current_examples  # 실패 시 원본 유지

    # ─── 후보 생성 (OPRO 핵심) ───────────────────────────────────

    def _generate_candidates(
        self,
        current_prompt: str,
        performance_data: JsonMap,
    ) -> list[PromptCandidate]:
        """OPRO 패턴: LLM이 프롬프트 개선안을 생성합니다."""
        candidates: list[PromptCandidate] = []

        # 성능 데이터를 분석용 텍스트로 변환
        perf_text = self._format_performance_data(performance_data)

        for i in range(self._candidates_per_gen):
            # 변이 연산자 순환
            mutation_op = self.MUTATION_OPS[i % len(self.MUTATION_OPS)]

            meta_prompt = self._build_meta_prompt(current_prompt, perf_text, mutation_op)

            try:
                result = self._call_optimizer(meta_prompt)
                if result and len(result) > 50:
                    # <think> 태그 제거
                    result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL)
                    result = result.strip()

                    candidate = PromptCandidate(
                        candidate_id=f"gen{self._generation}_c{i}_{mutation_op}",
                        content=result,
                        generation=self._generation,
                        parent_id=f"current_{self._generation}",
                        mutation_op=mutation_op,
                    )
                    candidates.append(candidate)
            except Exception:
                logger.exception("[PromptEvolver] 후보 생성 실패 (%s)", mutation_op)

        return candidates

    def _build_meta_prompt(
        self,
        current_prompt: str,
        performance_data: str,
        mutation_op: str,
    ) -> str:
        """OPRO 메타 프롬프트를 구성합니다."""
        op_instructions = {
            "rephrase": ("동일한 의미를 유지하면서 더 명확하고 간결하게 다시 작성하세요."),
            "expand": ("환각을 방지하는 제약 조건과 구체적인 출력 형식 지시를 추가하세요."),
            "compress": ("핵심 지시사항만 남기고 불필요한 부분을 제거하세요. 토큰 효율을 최대화하세요."),
            "restructure": ("섹션 순서를 [ROLE]→[CONSTRAINTS]→[CONTEXT]→[TASK] 구조로 재배치하세요."),
            "add_constraint": (
                "'절대 하지 말 것' 목록을 추가하세요: 환각 금지, 코드만 출력 금지, 외국어 혼용 금지 등."
            ),
            "add_example": ("좋은 응답과 나쁜 응답의 대비 예시를 1개 추가하세요."),
        }

        return (
            "[ROLE] 당신은 AI 시스템 프롬프트 최적화 전문가입니다.\n\n"
            "[CONTEXT] 아래는 현재 AI 에이전트의 시스템 프롬프트와 최근 성능 데이터입니다.\n\n"
            f"--- 현재 프롬프트 (첫 1000자) ---\n{current_prompt[:1000]}\n\n"
            f"--- 성능 데이터 ---\n{performance_data}\n\n"
            f"[TASK] 변이 연산: **{mutation_op}**\n"
            f"{op_instructions.get(mutation_op, '프롬프트를 개선하세요.')}\n\n"
            "개선된 전체 시스템 프롬프트를 출력하세요. 프롬프트만 출력하세요.\n"
            "마크다운 코드 블록이나 설명 없이, 프롬프트 텍스트만 반환하세요."
        )

    # ─── 통계 및 유틸 ────────────────────────────────────────────

    def get_evolution_trend(self) -> JsonMap:
        """진화 트렌드를 반환합니다."""
        if not self._history:
            return {"generations": 0, "message": "진화 기록 없음"}

        scores = [r.best_score for r in self._history]
        improvements = [r.improvement for r in self._history]

        return {
            "generations": len(self._history),
            "current_generation": self._generation,
            "best_score": max(scores),
            "latest_score": scores[-1],
            "avg_improvement": sum(improvements) / len(improvements),
            "total_improvement": sum(improvements),
            "score_trend": scores[-10:],
            "improving": (sum(1 for i in improvements if i > 0) > len(improvements) / 2),
        }

    def _format_performance_data(self, data: JsonMap) -> str:
        """성능 데이터를 분석용 텍스트로 변환합니다."""
        lines: list[str] = []
        if "quality_avg" in data:
            lines.append(f"평균 품질 점수: {data['quality_avg']:.2%}")
        if "weaknesses" in data:
            lines.append(f"약점: {', '.join(_as_string_list(data['weaknesses']))}")
        if "failure_patterns" in data:
            lines.append(f"반복 실패 패턴: {', '.join(_as_string_list(data['failure_patterns']))}")
        if "keyword_coverage" in data:
            lines.append(f"키워드 커버리지: {data['keyword_coverage']:.2%}")
        if "hallucination_rate" in data:
            lines.append(f"환각 비율: {data['hallucination_rate']:.2%}")
        return "\n".join(lines) if lines else "성능 데이터 없음"

    def _call_optimizer(self, prompt: str) -> str:
        """Optimizer LLM을 호출합니다."""
        if self._manager is not None:
            resolver = getattr(self._manager, "get_target_for_role", None)
            generate = getattr(self._manager, "generate", None)
            if callable(resolver) and callable(generate):
                try:
                    target = resolver("prompt_evolver", default_role="reasoning")
                    if isinstance(target, str) and target.strip():
                        response = generate(
                            prompt,
                            target.strip(),
                            max_tokens=2048,
                            temperature=0.4,
                        )
                        if isinstance(response, str):
                            return response
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                    logger.warning("Managed prompt evolution failed; using API fallback", exc_info=True)
        model = self._optimizer_model
        if not model:
            # 사용 가능한 모델 자동 탐지
            try:
                resp = safe_urlopen(f"{self._ollama_url}/api/tags", timeout=5)
                tags = _as_mapping(cast(object, json.loads(resp.read())))
                raw_models = tags.get("models")
                models: list[str] = []
                if isinstance(raw_models, list):
                    for item in cast(list[object], raw_models):
                        name = _as_mapping(item).get("name")
                        if isinstance(name, str):
                            models.append(name)
                model = models[0] if models else "llama3.2:latest"
            except Exception:
                logger.exception("Unhandled exception")
                model = "llama3.2:latest"

        data = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 2048, "temperature": 0.4},
            },
        ).encode()

        req = urllib.request.Request(
            f"{self._ollama_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        with safe_urlopen(req, timeout=120) as resp:
            result = _as_mapping(cast(object, json.loads(resp.read())))
            return str(result.get("response", ""))

    def _extract_json_array(self, text: str) -> list[object] | None:
        """텍스트에서 JSON 배열을 추출합니다."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch == "[":
                try:
                    decoded = decoder.raw_decode(text, i)
                    obj: object = cast(object, decoded[0])
                    if isinstance(obj, list):
                        return cast(list[object], obj)
                except json.JSONDecodeError:
                    continue
        return None

    def _save_prompt_version(self, candidate: PromptCandidate) -> None:
        """프롬프트 버전을 파일로 저장합니다."""
        version_file = self._persist_dir / f"gen{candidate.generation}_{candidate.mutation_op}.txt"
        try:
            with open(version_file, "w", encoding="utf-8") as f:
                _ = f.write(f"# Generation {candidate.generation}\n")
                _ = f.write(f"# Mutation: {candidate.mutation_op}\n")
                _ = f.write(f"# Score: {candidate.score:.4f}\n")
                _ = f.write(f"# Timestamp: {time.time()}\n\n")
                _ = f.write(candidate.content)
        except Exception:
            logger.exception("[PromptEvolver] 버전 저장 실패")

    def _load_history(self) -> None:
        history_file = self._persist_dir / "evolution_history.json"
        if not history_file.exists():
            return
        try:
            with open(history_file, encoding="utf-8") as f:
                data = _as_mapping(cast(object, json.load(f)))
            records = data.get("records")
            self._history = []
            if isinstance(records, list):
                for raw_record in cast(list[object], records):
                    record = _as_mapping(raw_record)
                    self._history.append(
                        EvolutionRecord(
                            generation=_as_int(record.get("generation")),
                            candidates_tested=_as_int(record.get("candidates_tested")),
                            best_score=_as_float(record.get("best_score")),
                            selected_id=str(record.get("selected_id", "")),
                            timestamp=_as_float(record.get("timestamp")),
                            improvement=_as_float(record.get("improvement")),
                        )
                    )
            self._generation = _as_int(data.get("generation"))
        except Exception:
            logger.exception("[PromptEvolver] 이력 로드 실패")

    def _save_history(self) -> None:
        history_file = self._persist_dir / "evolution_history.json"
        try:
            data = {
                "generation": self._generation,
                "updated_at": time.time(),
                "records": [asdict(r) for r in self._history],
            }
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("[PromptEvolver] 이력 저장 실패")


"""Ssak-Ai Prompt Evolver — OPRO-based automated prompt optimization."""
