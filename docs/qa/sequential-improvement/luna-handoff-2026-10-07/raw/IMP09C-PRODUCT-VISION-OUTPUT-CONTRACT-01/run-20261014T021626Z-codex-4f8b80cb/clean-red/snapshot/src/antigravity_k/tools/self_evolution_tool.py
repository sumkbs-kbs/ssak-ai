"""Self Evolution Tool module."""

import ast
import json
import logging
import os
from collections.abc import Mapping
from datetime import datetime
from typing import ClassVar, Protocol, TypedDict, cast, final, override

from antigravity_k.config import config
from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from antigravity_k.tools.egress_policy import safe_urlopen

logger = logging.getLogger(__name__)


class _ModelManagerProtocol(Protocol):
    def get_target_for_role(self, role: str, *, default_role: str) -> str | None: ...

    def generate(self, prompt: str, target: str, **kwargs: object) -> str: ...


class EvaluationResult(TypedDict):
    scores: dict[str, int]
    avg: float
    grade: str
    weaknesses: list[str]
    needs_improvement: bool


class EvaluationRecord(TypedDict):
    task: str
    result: EvaluationResult
    timestamp: str


class EvolutionCycle(TypedDict):
    task: str
    before: float
    after: float
    delta: float
    improved: bool
    improvement_applied: bool
    details: str
    timestamp: str


class TrendResult(TypedDict):
    avg_trend: list[float]
    improving: bool | None
    total_evaluations: int


class EffectivenessReport(TypedDict):
    message: str
    total_cycles: int
    improvements_applied: int
    effective_improvements: int
    effectiveness_rate: str
    avg_score_change: float
    best_improvement: EvolutionCycle | None
    worst_regression: EvolutionCycle | None


@final
class SelfEvolutionTool(BaseTool):
    """SelfEvolutionTool: 자체 진화 도구.

    =================================
    Ssak-Ai가 자기 자신의 코드베이스를 분석하고 개선하는 메타-도구입니다.

    워크플로우:
      1. 진화 목표 분석 (LLM)
      2. 현재 코드베이스 스캔 (관련 파일 자동 탐색)
      3. 웹 검색으로 최신 기술/패턴 학습
      4. 개선 코드 생성 (LLM)
      5. _drafts/ 저장 → AST 검증 → 사용자 승인 대기
      6. 승인 시 적용 + Git 커밋 + Vault 스냅샷
    """

    category: ToolCategory = ToolCategory.CODE_EXEC
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.HIGH
    icon: str = "🧬"

    def __init__(self, model_manager: _ModelManagerProtocol | None = None) -> None:
        """Initialize the SelfEvolutionTool."""
        super().__init__()
        self.manager: _ModelManagerProtocol | None = model_manager
        self.tags: list[str] = ["evolve", "meta", "self_healing", "refactor"]
        self._name: str = "trigger_self_evolution"
        self._description: str = (
            "Triggers the Self-Evolution Engine to analyze and improve the Ssak-Ai codebase. "
            "Use when the user asks to 'evolve', 'upgrade yourself', 'refactor your core engine', "
            "or 'create a new tool/skill'. Supports two modes:\n"
            "  - mode='evolve': Improve existing code\n"
            "  - mode='generate_skill': Create a brand new tool"
        )
        self._schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "evolution_goal": {
                    "type": "string",
                    "description": "A detailed explanation of what to optimize, add, or create.",
                },
                "mode": {
                    "type": "string",
                    "enum": [
                        "evolve",
                        "generate_skill",
                        "rsi_cycle",
                        "meta_architect",
                        "self_play",
                    ],
                    "description": (
                        "Evolution mode: 'evolve' (improve code), 'generate_skill' (create tool), "
                        "'rsi_cycle' (full RSI), 'meta_architect' (system-wide refactor), "
                        "'self_play' (autonomous dataset learning)."
                    ),
                },
                "target_files": {
                    "type": "string",
                    "description": "Optional comma-separated list of files to focus on.",
                },
                "dataset_name": {
                    "type": "string",
                    "description": "Optional Hugging Face dataset name when mode='self_play'. Leave empty for random or default dataset.",
                },
            },
            "required": ["evolution_goal"],
        }

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
    def parameters_schema(self) -> dict[str, object]:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        goal_value = kwargs.get("evolution_goal")
        goal = goal_value if isinstance(goal_value, str) else ""
        mode_value = kwargs.get("mode", "evolve")
        mode = mode_value if isinstance(mode_value, str) else "evolve"
        target_files_value = kwargs.get("target_files", "")
        target_files = target_files_value if isinstance(target_files_value, str) else ""

        if not goal:
            return "Error: Missing evolution_goal parameter."

        if mode == "generate_skill":
            return self._generate_new_skill(goal)
        elif mode == "rsi_cycle":
            return self._run_rsi_cycle(goal)
        elif mode == "meta_architect":
            return self._run_meta_architect(goal)
        elif mode == "self_play":
            dataset_name_value = kwargs.get("dataset_name", "")
            dataset_name = dataset_name_value if isinstance(dataset_name_value, str) else ""
            return self._run_self_play(dataset_name)
        else:
            return self._evolve_codebase(goal, target_files)

    def _run_rsi_cycle(self, goal: str) -> str:
        """RSI Engine을 통한 재귀적 자기개선 사이클을 실행합니다."""
        try:
            from antigravity_k.engine.rsi_engine import RSIConfig, RSIEngine

            project_root = self._find_project_root()
            config = RSIConfig(max_cycles=1, auto_apply_prompts=True)
            engine = RSIEngine(config=config, project_root=project_root, model_manager=self.manager)

            result = engine.run_cycle(performance_data={"weaknesses": [goal]})

            report = engine.render_report_markdown()
            status = "✅ 성공" if result.success else "❌ 실패"
            return (
                f"🧬 **[RSI 사이클 완료]** {status}\n\n"
                f"- 개선 전: {result.before_score:.1%}\n"
                f"- 개선 후: {result.after_score:.1%}\n"
                f"- 변화량: Δ{result.improvement:+.1%}\n"
                f"- 변이 유형: {result.mutation_type}\n"
                f"- 소요 시간: {result.duration_sec:.1f}s\n\n"
                f"{report}"
            )
        except Exception as e:
            logger.exception("RSI cycle error")
            return f"❌ RSI 사이클 오류: {e}"

    def _generate_new_skill(self, goal: str) -> str:
        """새로운 도구를 자동 생성합니다."""
        try:
            from antigravity_k.engine.skill_generator import SkillGenerator

            project_root = self._find_project_root()
            generator = SkillGenerator(project_root=project_root, model_manager=self.manager)
            result = cast(dict[str, object], cast(object, generator.generate_skill(goal)))

            if result.get("success") is True:
                message = result.get("message", "")
                return message if isinstance(message, str) else str(message)
            else:
                return f"❌ 스킬 생성 실패: {result.get('message', '')}"
        except Exception as e:
            logger.exception("Skill generation error")
            return f"❌ 스킬 생성 중 오류: {e}"

    def _run_meta_architect(self, goal: str) -> str:
        """Level 3: Meta-Architect를 호출하여 전체 시스템 아키텍처 수준의 리팩터링을 수행합니다."""
        try:
            from antigravity_k.engine.meta_architect import MetaArchitect

            project_root = self._find_project_root()
            architect = MetaArchitect(project_root=project_root, model_manager=self.manager)
            proposal = architect.analyze_and_propose({"weaknesses": [goal]})
            if proposal:
                _ = architect.execute_proposal(proposal)
                return f"✅ Meta-Architect가 제안을 성공적으로 실행했습니다.\n\n목표: {goal}\n개요: {str(proposal)[:300]}..."
            return "⚠️ Meta-Architect가 적절한 개선 제안을 생성하지 못했습니다."
        except Exception as e:
            logger.exception("Meta-Architect error")
            return f"❌ Meta-Architect 실행 중 오류: {e}"

    def _run_self_play(self, dataset_name: str) -> str:
        """Level 3: 지정된(또는 무작위) 데이터셋을 활용해 자율 훈련(Self-Play) 사이클을 가동합니다."""
        try:
            import asyncio

            from antigravity_k.engine.curriculum_generator import CurriculumGenerator

            project_root = self._find_project_root()
            generator = CurriculumGenerator(project_root=project_root, model_manager=self.manager)

            task = generator.generate_new_challenge(dataset_name=dataset_name)
            if not task:
                return "⚠️ 자가 학습 과제를 생성하지 못했습니다."

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                _ = loop.create_task(generator.self_play(task))
            else:
                _ = loop.run_until_complete(generator.self_play(task))

            dataset_label = dataset_name or "Auto/Synthetic"
            return (
                f"✅ 자가 학습(Self-Play) 모드가 시작되었습니다.\n"
                f"테스크 ID: {task.task_id}\n대상 데이터셋: {dataset_label}"
            )

        except Exception as e:
            logger.exception("Self-Play error")
            return f"❌ 자가 학습 실행 중 오류: {e}"

    def _evolve_codebase(self, goal: str, target_files: str) -> str:
        """기존 코드베이스를 분석하고 개선합니다."""
        project_root = self._find_project_root()
        drafts_dir = os.path.join(project_root, "_drafts", "evolution")
        os.makedirs(drafts_dir, exist_ok=True)

        try:
            # 1. 대상 파일 탐색
            targets = self._find_target_files(project_root, target_files, goal)
            if not targets:
                return "⚠️ 진화 대상 파일을 찾을 수 없습니다."

            # 2. 현재 코드 읽기
            code_context: dict[str, str] = {}
            for fpath in targets[:5]:  # 최대 5개 파일
                try:
                    with open(fpath, encoding="utf-8") as f:
                        content = f.read()
                    # 파일이 너무 크면 첫 200줄만
                    lines = content.split("\n")
                    if len(lines) > 200:
                        content = "\n".join(lines[:200]) + f"\n... ({len(lines) - 200} more lines)"
                    code_context[os.path.relpath(fpath, project_root)] = content
                except Exception:
                    logger.exception("Unhandled exception")

            # 3. 웹에서 최신 패턴 학습 (선택적)
            web_context = ""
            try:
                from antigravity_k.tools.web_search import WebSearchTool

                search = WebSearchTool()
                web_context = search.execute(query=f"{goal} best practices Python 2025")
            except Exception:
                logger.exception("Unhandled exception")

            # 4. LLM으로 개선 코드 생성
            patches = self._generate_patches(goal, code_context, web_context)

            if not patches:
                return "⚠️ LLM이 개선 사항을 생성하지 못했습니다."

            # 5. _drafts/에 저장 + AST 검증
            results: list[str] = []
            for filename, patch_code in patches.items():
                # AST 검증
                try:
                    _ = ast.parse(patch_code)
                except SyntaxError as e:
                    results.append(f"❌ {filename}: 구문 오류 — {e}")
                    continue

                # 저장
                draft_path = os.path.join(drafts_dir, filename)
                os.makedirs(os.path.dirname(draft_path), exist_ok=True)
                with open(draft_path, "w", encoding="utf-8") as f:
                    _ = f.write(patch_code)
                results.append(f"✅ {filename}: 패치 저장 ({len(patch_code)} bytes)")

            # 메타데이터 저장
            meta: dict[str, object] = {
                "goal": goal,
                "target_files": list(code_context),
                "patches": list(patches),
                "generated_at": datetime.now().isoformat(),
                "status": "pending_review",
            }
            with open(os.path.join(drafts_dir, "_evolution_meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            report = "\n".join(results)
            return (
                f"🧬 **[자체 진화 완료]** 목표: {goal}\n\n"
                f"📋 결과:\n{report}\n\n"
                f"📁 패치 위치: {drafts_dir}\n"
                f"⚠️ 패치는 `_drafts/evolution/`에 저장되었습니다.\n"
                f"사용자가 검토 후 승인해야 실제 적용됩니다."
            )
        except Exception as e:
            logger.exception("Evolution error")
            return f"❌ 진화 프로세스 오류: {e}"

    def _find_project_root(self) -> str:
        """프로젝트 루트를 찾습니다."""
        # 현재 파일 기준으로 탐색
        current = os.path.dirname(os.path.abspath(__file__))
        for _ in range(5):
            if os.path.exists(os.path.join(current, "config.yaml")):
                return current
            current = os.path.dirname(current)
        return os.getcwd()

    def _find_target_files(self, project_root: str, target_files: str, goal: str) -> list[str]:
        """진화 대상 파일을 탐색합니다."""
        targets: list[str] = []

        # 명시적 대상 파일이 있으면 우선 사용
        if target_files:
            for tf in target_files.split(","):
                tf = tf.strip()
                full_path = os.path.join(project_root, "src", "antigravity_k", "engine", tf)
                if os.path.exists(full_path):
                    targets.append(full_path)
                else:
                    # 전체 프로젝트에서 검색
                    for root, _dirs, files in os.walk(os.path.join(project_root, "src")):
                        if tf in files:
                            targets.append(os.path.join(root, tf))
                            break

        # 명시적 대상이 없으면 goal 키워드로 관련 파일 탐색
        if not targets:
            keywords = goal.lower().split()
            engine_dir = os.path.join(project_root, "src", "antigravity_k", "engine")
            tools_dir = os.path.join(project_root, "src", "antigravity_k", "tools")

            for search_dir in [engine_dir, tools_dir]:
                if not os.path.exists(search_dir):
                    continue
                for fname in os.listdir(search_dir):
                    if not fname.endswith(".py"):
                        continue
                    basename = fname[:-3].lower()
                    if any(kw in basename for kw in keywords):
                        targets.append(os.path.join(search_dir, fname))

        return targets

    def _generate_patches(self, goal: str, code_context: dict[str, str], web_context: str) -> dict[str, str]:
        """LLM으로 개선 패치를 생성합니다."""
        import re
        import urllib.request

        files_text = ""
        for fname, content in code_context.items():
            files_text += f"\n--- {fname} ---\n{content}\n"

        prompt = (
            "You are an expert Python developer evolving the Ssak-Ai AI framework.\n\n"
            f"Evolution Goal: {goal}\n\n"
            f"Current Code:\n{files_text}\n"
        )
        if web_context:
            prompt += f"\nWeb Research (latest patterns):\n{web_context[:2000]}\n"

        prompt += (
            "\nGenerate improved versions of the files. Return ONLY a JSON object where:\n"
            "- keys are filenames (e.g., 'orchestrator.py')\n"
            "- values are the complete improved Python code\n\n"
            "Return ONLY valid JSON. No markdown, no explanation."
        )

        try:
            text: str | None = None
            if self.manager is not None:
                resolver = getattr(self.manager, "get_target_for_role", None)
                generate = getattr(self.manager, "generate", None)
                if callable(resolver) and callable(generate):
                    try:
                        target = resolver("self_evolution", default_role="code")
                        if isinstance(target, str) and target.strip():
                            generated = generate(
                                prompt,
                                target.strip(),
                                max_tokens=4096,
                                temperature=0.3,
                            )
                            text = generated if isinstance(generated, str) else None
                    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                        logger.warning(
                            "Managed self-evolution generation failed; using configured API fallback", exc_info=True
                        )
            if not isinstance(text, str):
                data = {
                    "model": config.model.code_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 4096, "temperature": 0.3},
                }
                req = urllib.request.Request(
                    f"{config.model.api_base.replace('/v1', '').rstrip('/')}/api/generate",
                    data=json.dumps(data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with safe_urlopen(req, timeout=120) as resp:
                    result = cast(dict[str, object], json.loads(resp.read().decode("utf-8")))
                    response = result.get("response", "")
                    text = response if isinstance(response, str) else ""

            # <think> 태그 제거
            text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)

            # JSON 추출
            decoder = json.JSONDecoder()
            for i, ch in enumerate(text):
                if ch == "{":
                    try:
                        obj, _ = cast(tuple[object, int], decoder.raw_decode(text or "", i))
                        if isinstance(obj, dict):
                            obj_dict = cast(dict[object, object], obj)
                            if all(isinstance(v, str) for v in obj_dict.values()):
                                return {str(k): v for k, v in obj_dict.items() if isinstance(v, str)}
                    except json.JSONDecodeError:
                        continue

        except Exception:
            logger.exception("Patch generation failed")

        return {}


# ─── Self-Reward 평가 엔진 ────────────────────────────────────────


@final
class SelfRewardEvaluator:
    """Self-Reward Loop: 에이전트 출력 품질 자가 평가.

    LLM이 자기 출력을 4가지 기준으로 평가하고,
    낮은 점수 항목에 대해 자동으로 개선 방향을 제시합니다.

    평가 기준:
        1. 정확성 (accuracy): 사실적으로 올바른가?
        2. 완전성 (completeness): 요청을 빠짐없이 충족했는가?
        3. 효율성 (efficiency): 최적의 방법을 사용했는가?
        4. 사용자 만족도 (user_satisfaction): 사용자 의도에 부합하는가?

    사용법:
        evaluator = SelfRewardEvaluator()
        score = evaluator.evaluate(task, output)
        if score["avg"] < 7:
            improvements = evaluator.suggest_improvements(score)
    """

    CRITERIA: ClassVar[list[str]] = ["accuracy", "completeness", "efficiency", "user_satisfaction"]
    CRITERIA_KR: ClassVar[dict[str, str]] = {
        "accuracy": "정확성",
        "completeness": "완전성",
        "efficiency": "효율성",
        "user_satisfaction": "사용자 만족도",
    }

    def __init__(self, threshold: float = 7.0) -> None:
        """Initialize the SelfRewardEvaluator.

        Args:
            threshold (float): float threshold.

        """
        self.threshold: float = threshold
        self._history: list[EvaluationRecord] = []

    def evaluate(self, task: str, output: str, context: str = "") -> EvaluationResult:
        """에이전트 출력을 자가 평가합니다 (LLM 호출 없이 휴리스틱 기반).

        LLM 기반 평가가 필요한 경우 evaluate_with_llm()을 사용하세요.

        Returns:
            {"scores": {...}, "avg": float, "grade": str, "weaknesses": [...]}

        """
        _ = context
        scores: dict[str, int] = {}

        # 1. 정확성: 에러 메시지 포함 여부
        output_lower = output.lower()
        error_indicators = ["error", "traceback", "exception", "failed", "실패", "오류"]
        error_count = sum(1 for ind in error_indicators if ind in output_lower)
        scores["accuracy"] = max(1, 10 - error_count * 2)

        # 2. 완전성: 출력 길이와 구조
        if len(output) < 20:
            scores["completeness"] = 3
        elif len(output) < 100:
            scores["completeness"] = 5
        elif len(output) < 500:
            scores["completeness"] = 7
        else:
            scores["completeness"] = 9

        # 3. 효율성: 반복 패턴 감지
        lines = output.split("\n")
        unique_ratio = len(set(lines)) / max(len(lines), 1)
        scores["efficiency"] = min(10, int(unique_ratio * 10) + 2)

        # 4. 사용자 만족도: 태스크 키워드가 출력에 포함되는지
        task_words = task.lower().split()
        match_count = sum(1 for w in task_words if len(w) > 2 and w in output_lower)
        match_ratio = match_count / max(len(task_words), 1)
        scores["user_satisfaction"] = min(10, int(match_ratio * 8) + 3)

        # 종합
        avg = sum(scores.values()) / len(scores)
        grade = self._score_to_grade(avg)

        # 약점 식별
        weaknesses = [self.CRITERIA_KR[c] for c, s in scores.items() if s < self.threshold]

        result: EvaluationResult = {
            "scores": scores,
            "avg": round(avg, 1),
            "grade": grade,
            "weaknesses": weaknesses,
            "needs_improvement": avg < self.threshold,
        }

        self._history.append(
            {
                "task": task[:100],
                "result": result,
                "timestamp": datetime.now().isoformat(),
            },
        )

        return result

    def suggest_improvements(self, evaluation: Mapping[str, object]) -> list[str]:
        """낮은 점수 항목에 대한 개선 제안을 생성합니다."""
        suggestions: list[str] = []
        scores = cast(Mapping[str, int], evaluation.get("scores", {}))

        if scores.get("accuracy", 10) < 7:
            suggestions.append(
                "🎯 정확성 개선: 출력에 에러가 포함되었습니다. 도구 실행 결과를 검증하고, 실패한 명령은 대안을 시도하세요.",
            )
        if scores.get("completeness", 10) < 7:
            suggestions.append(
                "📋 완전성 개선: 출력이 너무 짧거나 불완전합니다. 사용자 요청의 모든 측면을 다루었는지 확인하세요.",
            )
        if scores.get("efficiency", 10) < 7:
            suggestions.append(
                "⚡ 효율성 개선: 반복되는 내용이 많습니다. 중복을 제거하고 핵심 정보에 집중하세요.",
            )
        if scores.get("user_satisfaction", 10) < 7:
            suggestions.append(
                "💬 만족도 개선: 사용자 의도와 출력이 불일치합니다. 원래 요청을 다시 읽고 핵심 키워드에 직접 답변하세요.",
            )

        return suggestions

    def get_trend(self, last_n: int = 10) -> TrendResult:
        """최근 N개 평가의 트렌드를 반환합니다."""
        recent = self._history[-last_n:]
        if not recent:
            return {"avg_trend": [], "improving": None, "total_evaluations": 0}

        avgs: list[float] = [h["result"]["avg"] for h in recent]
        improving = None
        if len(avgs) >= 3:
            first_half = sum(avgs[: len(avgs) // 2]) / max(len(avgs) // 2, 1)
            second_half = sum(avgs[len(avgs) // 2 :]) / max(len(avgs) - len(avgs) // 2, 1)
            improving = second_half > first_half

        return {
            "avg_trend": avgs,
            "improving": improving,
            "total_evaluations": len(self._history),
        }

    @staticmethod
    def _score_to_grade(avg: float) -> str:
        if avg >= 9:
            return "S"
        if avg >= 8:
            return "A"
        if avg >= 7:
            return "B"
        if avg >= 5:
            return "C"
        return "F"


# ─── 메타인지 트래커 ──────────────────────────────────────────────


@final
class MetacognitiveTracker:
    """메타인지 트래커: 에이전트의 "학습 과정 자체"를 추적합니다.

    Self-Reward 결과를 누적하여:
    - 어떤 유형의 작업에서 반복적으로 실패하는지 패턴 감지
    - 개선이 실제로 효과가 있었는지 검증
    - 진화 사이클의 ROI 측정

    사용법:
        tracker = MetacognitiveTracker()
        tracker.record_evolution_cycle(task, before_score, after_score, improvement_applied)
    """

    def __init__(self, persist_path: str | None = None) -> None:
        """Initialize the MetacognitiveTracker.

        Args:
            persist_path (str): str persist path.

        """
        self._cycles: list[EvolutionCycle] = []
        self._persist_path: str | None = persist_path

    def record_evolution_cycle(
        self,
        task: str,
        before_score: float,
        after_score: float,
        improvement_applied: bool,
        improvement_details: str = "",
    ) -> None:
        """진화 사이클 결과를 기록합니다."""
        cycle: EvolutionCycle = {
            "task": task[:200],
            "before": before_score,
            "after": after_score,
            "delta": round(after_score - before_score, 1),
            "improved": after_score > before_score,
            "improvement_applied": improvement_applied,
            "details": improvement_details,
            "timestamp": datetime.now().isoformat(),
        }
        self._cycles.append(cycle)

        logger.info(
            "[Metacognitive] Cycle recorded: %s→%s (Δ%s, applied=%s)",
            before_score,
            after_score,
            cycle["delta"],
            improvement_applied,
        )

        if self._persist_path:
            self._save()

    def get_effectiveness_report(self) -> EffectivenessReport:
        """진화 효과 종합 보고서를 반환합니다."""
        if not self._cycles:
            return {
                "message": "기록된 진화 사이클 없음",
                "total_cycles": 0,
                "improvements_applied": 0,
                "effective_improvements": 0,
                "effectiveness_rate": "0%",
                "avg_score_change": 0.0,
                "best_improvement": None,
                "worst_regression": None,
            }

        applied = [c for c in self._cycles if c["improvement_applied"]]
        effective = [c for c in applied if c["improved"]]

        avg_delta = sum(c["delta"] for c in self._cycles) / len(self._cycles)

        return {
            "message": "",
            "total_cycles": len(self._cycles),
            "improvements_applied": len(applied),
            "effective_improvements": len(effective),
            "effectiveness_rate": f"{len(effective) / max(len(applied), 1) * 100:.0f}%",
            "avg_score_change": round(avg_delta, 2),
            "best_improvement": (max(self._cycles, key=lambda c: c["delta"]) if self._cycles else None),
            "worst_regression": (min(self._cycles, key=lambda c: c["delta"]) if self._cycles else None),
        }

    def detect_failure_patterns(self) -> list[str]:
        """반복 실패 패턴을 감지합니다."""
        patterns: list[str] = []
        # 최근 사이클에서 개선 실패 패턴 탐지
        recent_failures = [c for c in self._cycles[-20:] if c["improvement_applied"] and not c["improved"]]

        if len(recent_failures) >= 3:
            patterns.append(
                f"⚠️ 최근 {len(recent_failures)}개 개선 시도가 효과 없음 — 개선 전략 자체를 재검토해야 합니다.",
            )

        # 특정 점수대에서 정체
        recent_scores = [c["after"] for c in self._cycles[-10:]]
        if recent_scores and max(recent_scores) - min(recent_scores) < 0.5:
            patterns.append(
                f"📊 점수 정체 감지: 최근 10 사이클 평균 {sum(recent_scores) / len(recent_scores):.1f} — 근본적인 접근 방식 변경 필요.",
            )

        return patterns

    def _save(self) -> None:
        """메타인지 데이터를 디스크에 저장합니다."""
        if not self._persist_path:
            return
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(self._cycles, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("Metacognitive persist error")
