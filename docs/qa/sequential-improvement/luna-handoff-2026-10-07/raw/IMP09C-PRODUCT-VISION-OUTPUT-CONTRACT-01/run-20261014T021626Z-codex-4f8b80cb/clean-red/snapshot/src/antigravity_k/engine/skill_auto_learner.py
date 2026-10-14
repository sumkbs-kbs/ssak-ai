"""Ssak-Ai: Skill Auto-Learner (Closed Learning Loop).

=========================================================
Hermes Agent의 핵심 기술을 흡수한 폐쇄 학습 루프.
태스크 완료 시 도구 호출 시퀀스를 분석하여 반복 패턴을 감지하고,
재사용 가능한 스킬을 자율적으로 생성/개선합니다.

학습 루프:
  1. Observe: 도구 호출 시퀀스 수집
  2. Detect: 반복 패턴 및 다단계 워크플로우 감지
  3. Generate: LLM에게 스킬 마크다운 생성 요청
  4. Validate: 기존 스킬과 중복 검사 + 품질 검증
  5. Persist: .agent/skills/auto-learned/ 에 저장
  6. Improve: 재사용 시 피드백으로 스킬 자동 패치
"""

import json
import logging
import os
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, TypeAlias, TypedDict, cast

from antigravity_k.config import config
from antigravity_k.tools.egress_policy import safe_urlopen

logger = logging.getLogger(__name__)

JsonObject: TypeAlias = dict[str, object]


class SkillRecordPayload(TypedDict):
    name: str
    description: str
    source_pattern: list[str]
    created_at: str
    use_count: int
    success_count: int
    last_used: str
    file_path: str


class SkillModelManager(Protocol):
    def get_target_for_role(self, role_name: str, *, default_role: str) -> str: ...

    def generate(self, prompt: str, target: str, **kwargs: object) -> object: ...


@dataclass
class ToolCall:
    """단일 도구 호출 기록."""

    name: str
    arguments: JsonObject
    result_summary: str = ""
    success: bool = True
    timestamp: str = ""


@dataclass
class LearnedPattern:
    """감지된 도구 호출 패턴."""

    tool_sequence: list[str]
    frequency: int
    context_keywords: list[str] = field(default_factory=list)
    example_args: list[JsonObject] = field(default_factory=list)


@dataclass
class SkillRecord:
    """자동 생성된 스킬의 메타데이터."""

    name: str
    description: str
    source_pattern: list[str]
    created_at: str
    use_count: int = 0
    success_count: int = 0
    last_used: str = ""
    file_path: str = ""


class SkillAutoLearner:
    """Closed Learning Loop 엔진.

    매 태스크 완료 시 도구 호출 시퀀스를 분석하여
    반복 패턴을 감지하고 재사용 가능한 스킬을 자율 생성합니다.
    """

    # 최소 2회 이상 등장한 시퀀스만 스킬로 추출
    MIN_PATTERN_FREQUENCY: int = 2
    # 패턴에 포함될 최소 도구 호출 수
    MIN_SEQUENCE_LENGTH: int = 2
    # 자동 보존 임계값: 3회 이상 성공적으로 재사용된 스킬만 영구 보존
    PERMANENT_THRESHOLD: int = 3

    def __init__(self, project_root: str, model_manager: object | None = None):
        """Initialize the SkillAutoLearner.

        Args:
            project_root (str): str project root.
            model_manager: model manager.

        """
        self.project_root: str = project_root
        self.manager: SkillModelManager | None = (
            cast(SkillModelManager, model_manager) if model_manager is not None else None
        )
        self._skills_dir: str = os.path.join(project_root, ".agent", "skills", "auto-learned")
        self._registry_path: str = os.path.join(self._skills_dir, "_registry.json")
        self._history: list[list[ToolCall]] = []  # 세션 내 태스크별 도구 호출 이력
        self._current_task_calls: list[ToolCall] = []
        self._registry: dict[str, SkillRecord] = {}
        self._load_registry()

    def _generation_target(self, role_name: str, default_role: str = "code") -> str:
        configured = os.environ.get("AGK_SKILL_GENERATION_MODEL", "").strip()
        if configured:
            return configured
        if self.manager is not None:
            resolver = getattr(self.manager, "get_target_for_role", None)
            if callable(resolver):
                try:
                    target = resolver(role_name, default_role=default_role)
                    if isinstance(target, str) and target.strip():
                        return target.strip()
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    logger.warning("[AutoLearn] Failed to resolve managed model target", exc_info=True)
        return config.model.code_model or config.model.main_model

    def _generate_with_manager(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        role_name: str,
        default_role: str = "code",
    ) -> str | None:
        if self.manager is None:
            return None
        generate = getattr(self.manager, "generate", None)
        if not callable(generate):
            return None
        try:
            response = generate(
                prompt,
                self._generation_target(role_name, default_role),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            logger.warning("[AutoLearn] Managed generation failed; using configured API fallback", exc_info=True)
            return None
        return response if isinstance(response, str) else None

    def _load_registry(self) -> None:
        """스킬 레지스트리를 디스크에서 로드합니다."""
        if os.path.exists(self._registry_path):
            try:
                with open(self._registry_path, encoding="utf-8") as f:
                    data = cast(object, json.load(f))
                if not isinstance(data, dict):
                    return
                payload = cast(dict[str, object], cast(object, data))
                for name, rec in payload.items():
                    if isinstance(rec, dict):
                        self._registry[name] = SkillRecord(
                            **cast(SkillRecordPayload, cast(object, rec)),
                        )
            except Exception:
                logger.exception("[AutoLearn] Registry load error")

    def _save_registry(self) -> None:
        """스킬 레지스트리를 디스크에 저장합니다."""
        os.makedirs(self._skills_dir, exist_ok=True)
        try:
            data: dict[str, JsonObject] = {}
            for name, rec in self._registry.items():
                data[name] = {
                    "name": rec.name,
                    "description": rec.description,
                    "source_pattern": rec.source_pattern,
                    "created_at": rec.created_at,
                    "use_count": rec.use_count,
                    "success_count": rec.success_count,
                    "last_used": rec.last_used,
                    "file_path": rec.file_path,
                }
            with open(self._registry_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("[AutoLearn] Registry save error")

    # ─── 1. Observe: 도구 호출 수집 ───

    def record_tool_call(
        self,
        name: str,
        arguments: JsonObject,
        result: str = "",
        success: bool = True,
    ) -> None:
        """도구 호출을 현재 태스크의 시퀀스에 기록합니다."""
        call = ToolCall(
            name=name,
            arguments=arguments,
            result_summary=result[:200] if result else "",
            success=success,
            timestamp=datetime.now(UTC).replace(tzinfo=None).isoformat(),
        )
        self._current_task_calls.append(call)

    def flush_task(self):
        """현재 태스크의 도구 호출 시퀀스를 이력에 저장하고 초기화합니다."""
        if self._current_task_calls:
            self._history.append(list(self._current_task_calls))
        self._current_task_calls = []

    # ─── 2. Detect: 패턴 감지 ───

    def detect_patterns(self) -> list[LearnedPattern]:
        """이력에서 반복되는 도구 호출 시퀀스를 감지합니다."""
        if len(self._history) < self.MIN_PATTERN_FREQUENCY:
            return []

        # N-gram 기반 시퀀스 추출 (2~5개 도구 조합)
        sequence_counter: Counter[tuple[str, ...]] = Counter()
        sequence_examples: dict[tuple[str, ...], list[JsonObject]] = {}

        for task_calls in self._history:
            tool_names = [c.name for c in task_calls if c.success]
            if len(tool_names) < self.MIN_SEQUENCE_LENGTH:
                continue

            for n in range(self.MIN_SEQUENCE_LENGTH, min(len(tool_names) + 1, 6)):
                for i in range(len(tool_names) - n + 1):
                    seq = tuple(tool_names[i : i + n])
                    sequence_counter[seq] += 1
                    if seq not in sequence_examples:
                        sequence_examples[seq] = [c.arguments for c in task_calls[i : i + n]]

        # 이미 스킬로 생성된 패턴 필터링
        existing_patterns = {tuple(rec.source_pattern) for rec in self._registry.values()}

        patterns: list[LearnedPattern] = []
        for seq, count in sequence_counter.most_common(10):
            if count >= self.MIN_PATTERN_FREQUENCY and seq not in existing_patterns:
                patterns.append(
                    LearnedPattern(
                        tool_sequence=list(seq),
                        frequency=count,
                        example_args=sequence_examples.get(seq, []),
                    ),
                )

        return patterns

    # ─── 3. Generate: 스킬 생성 ───

    def generate_skill(self, pattern: LearnedPattern, user_context: str = "") -> str | None:
        """감지된 패턴을 기반으로 재사용 가능한 스킬 마크다운을 자동 생성합니다.

        Returns:
            생성된 스킬 파일 경로, 실패 시 None

        """
        prompt = (
            "[ROLE] You are a skill author for an AI agent framework.\n"
            "[TASK] Given a repeated tool-call pattern, create a reusable SKILL.md file.\n\n"
            f"Pattern detected (used {pattern.frequency} times):\n"
            f"  Tool sequence: {' → '.join(pattern.tool_sequence)}\n"
            f"  Example arguments: {json.dumps(pattern.example_args[:2], ensure_ascii=False)}\n"
            f"  User context: {user_context[:200]}\n\n"
            "[OUTPUT FORMAT]\n"
            "Return a YAML frontmatter + markdown skill file. Example:\n"
            "---\n"
            "name: auto-skill-name\n"
            "description: What this skill does\n"
            "---\n"
            "# Skill Name\n"
            "Instructions for the agent to follow when this skill is triggered.\n"
            "Include step-by-step workflow that replaces the manual tool sequence.\n\n"
            "[CONSTRAINTS]\n"
            "- Skill name must be lowercase-with-hyphens\n"
            "- Description must be one line in Korean\n"
            "- Instructions must be in Korean\n"
            "- Return ONLY the skill file content, no explanation\n"
        )

        try:
            skill_content = self._generate_with_manager(
                prompt,
                max_tokens=1024,
                temperature=0.3,
                role_name="skill_auto_learner",
            )
            if skill_content is None:
                data = {
                    "model": self._generation_target("skill_auto_learner"),
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 1024, "temperature": 0.3},
                }
                req = urllib.request.Request(
                    f"{config.model.api_base.replace('/v1', '').rstrip('/')}/api/generate",
                    data=json.dumps(data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with safe_urlopen(req, timeout=60) as resp:
                    result = cast(object, json.loads(resp.read().decode("utf-8")))
                    if isinstance(result, dict):
                        result_map = cast(dict[str, object], cast(object, result))
                        response = result_map.get("response", "")
                        skill_content = response if isinstance(response, str) else ""
                    else:
                        skill_content = ""

            # <think> 태그 제거
            skill_content = re.sub(
                r"<think>.*?</think>",
                "",
                skill_content,
                flags=re.DOTALL,
            ).strip()

            if not skill_content or "---" not in skill_content:
                logger.warning("[AutoLearn] LLM did not produce valid skill content")
                return None

            # 스킬 이름 추출
            name_match = re.search(r"name:\s*(.+)", skill_content)
            desc_match = re.search(r"description:\s*(.+)", skill_content)
            skill_name = name_match.group(1).strip() if name_match else f"auto-{'-'.join(pattern.tool_sequence[:3])}"
            description = desc_match.group(1).strip() if desc_match else "자동 생성된 스킬"

            # 파일 저장
            skill_dir = os.path.join(self._skills_dir, skill_name)
            os.makedirs(skill_dir, exist_ok=True)
            skill_path = os.path.join(skill_dir, "SKILL.md")
            with open(skill_path, "w", encoding="utf-8") as f:
                _ = f.write(skill_content)

            # 레지스트리 등록
            record = SkillRecord(
                name=skill_name,
                description=description,
                source_pattern=pattern.tool_sequence,
                created_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
                file_path=skill_path,
            )
            self._registry[skill_name] = record
            self._save_registry()

            logger.info(
                "[AutoLearn] Skill created: %s from pattern %s",
                skill_name,
                pattern.tool_sequence,
            )
            return skill_path

        except Exception:
            logger.exception("[AutoLearn] Skill generation failed")
            return None

    # ─── 4. On Task Complete: 메인 훅 ───

    def on_task_complete(self, user_message: str = "") -> str | None:
        """태스크 완료 시 호출되는 메인 훅.

        도구 호출 이력을 분석하여 패턴을 감지하고 스킬을 생성합니다.

        Returns:
            생성된 스킬에 대한 사용자 알림 메시지, 없으면 None

        """
        self.flush_task()

        patterns = self.detect_patterns()
        if not patterns:
            return None

        # 가장 빈도가 높은 패턴부터 스킬 생성 시도 (최대 1개)
        for pattern in patterns[:1]:
            skill_path = self.generate_skill(pattern, user_context=user_message)
            if skill_path:
                return (
                    f"\n💡 **[Auto-Learn]** 반복 패턴을 감지하여 새 스킬을 자동 생성했습니다!\n"
                    f"  📁 `{os.path.basename(os.path.dirname(skill_path))}`\n"
                    f"  🔄 패턴: {' → '.join(pattern.tool_sequence)} ({pattern.frequency}회 반복)\n"
                )
        return None

    # ─── 5. Skill Usage Tracking ───

    def mark_skill_used(self, skill_name: str, success: bool = True) -> None:
        """스킬 사용을 기록합니다."""
        if skill_name in self._registry:
            rec = self._registry[skill_name]
            rec.use_count += 1
            if success:
                rec.success_count += 1
            rec.last_used = datetime.now(UTC).replace(tzinfo=None).isoformat()
            self._save_registry()

    # ─── 6. Garbage Collection ───

    def gc_stale_skills(self) -> list[str]:
        """PERMANENT_THRESHOLD 미만의 성공 횟수를 가진 스킬 중.

        30일 이상 사용되지 않은 스킬을 제거합니다.
        """
        removed: list[str] = []
        now = datetime.now(UTC).replace(tzinfo=None)
        for name, rec in list(self._registry.items()):
            if rec.success_count >= self.PERMANENT_THRESHOLD:
                continue  # 영구 보존

            if not rec.last_used:
                last = datetime.fromisoformat(rec.created_at)
            else:
                last = datetime.fromisoformat(rec.last_used)

            days_idle = (now - last).days
            if days_idle > 30 and rec.use_count < self.PERMANENT_THRESHOLD:
                # 스킬 디렉토리 삭제
                skill_dir = os.path.dirname(rec.file_path)
                if os.path.isdir(skill_dir):
                    import shutil

                    shutil.rmtree(skill_dir, ignore_errors=True)
                del self._registry[name]
                removed.append(name)
                logger.info("[AutoLearn] GC removed stale skill: %s (idle %sd)", name, days_idle)

        if removed:
            self._save_registry()
        return removed

    def summary(self) -> str:
        """자동 학습 현황 요약."""
        total = len(self._registry)
        permanent = sum(1 for r in self._registry.values() if r.success_count >= self.PERMANENT_THRESHOLD)
        probation = total - permanent
        total_uses = sum(r.use_count for r in self._registry.values())
        return (
            f"📊 Auto-Learn Status: {total}개 스킬 (영구 {permanent}개, 관찰 중 {probation}개, 총 {total_uses}회 사용)"
        )
