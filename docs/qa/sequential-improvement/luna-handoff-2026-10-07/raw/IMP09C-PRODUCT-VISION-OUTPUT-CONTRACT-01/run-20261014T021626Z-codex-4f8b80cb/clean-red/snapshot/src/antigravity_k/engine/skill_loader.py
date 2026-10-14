"""Skill Loader module.

Phase 1 D13: .agent/skills/market/ 디렉토리 연동.
SkillLoader가 글로벌 → 로컬 베이스 → 마켓 순서로
3개 소스에서 스킬을 로드합니다.
"""

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict, cast

import yaml

from antigravity_k.engine.capability_policy import (
    AutonomousCapabilityPolicy,
    CapabilityDecision,
)

logger = logging.getLogger(__name__)


class SkillMetadata(TypedDict):
    id: str
    name: str
    description: str
    content: str
    path: str
    tags: object
    tools: object
    risk_level: str
    trust_level: str
    requires_approval: bool
    is_global: bool
    source: str


# ─── 상수 ─────────────────────────────────────────────────────────────

MARKET_DIR_NAME = "market"
"""마켓 스킬이 설치되는 서브디렉토리 이름."""


def _recover_scalar_metadata(frontmatter: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    supported_keys = {"name", "description", "tags", "tools", "risk_level", "trust_level", "requires_approval"}
    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key not in supported_keys:
            continue
        value = value.strip()
        if key in {"tags", "tools"}:
            try:
                parsed_value = cast(object, yaml.safe_load(value))
            except yaml.YAMLError:
                parsed_value = None
            if isinstance(parsed_value, list):
                metadata[key] = parsed_value
            elif value:
                metadata[key] = [value.strip("[] '\"")]
            else:
                metadata[key] = []
        elif key == "requires_approval":
            metadata[key] = value.lower() in {"true", "yes", "1"}
        else:
            metadata[key] = value.strip("'\"")
    return metadata


class SkillLoader:
    """동적 스킬 로더.

    3개 소스에서 Markdown 지침서(Skills)를 로드합니다:
      1. 글로벌 (~/.agents/skills/)
      2. 로컬 (.agent/skills/)
      3. 마켓 (.agent/skills/market/)  ← Phase 1 D13

    로드 우선순위: 글로벌 → 로컬 → 마켓 (뒤쪽이 앞쪽을 덮어씀).
    """

    def __init__(
        self,
        project_root: str | None = None,
        include_global: bool = True,
        include_market: bool = True,
        capability_policy_config: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize the SkillLoader.

        Args:
            project_root: 프로젝트 루트.
            include_global: 글로벌 스킬 디렉토리 포함 여부.
            include_market: 마켓 스킬 디렉토리 포함 여부 (Phase 1 D13).
            capability_policy_config: 자율 정책 설정.
        """
        self.project_root: Path = Path(project_root) if project_root else Path(os.getcwd())
        self.skills_dir: Path = self.project_root / ".agent" / "skills"
        self.market_dir: Path = self.skills_dir / MARKET_DIR_NAME
        self.include_global: bool = include_global
        self.include_market: bool = include_market

        # 글로벌 스킬 디렉토리 — AGK_GLOBAL_SKILLS_DIR 환경변수로 확장 가능.
        home_dir = Path.home()
        global_skills_dirs = [home_dir / ".agents" / "skills"]
        env_global = os.environ.get("AGK_GLOBAL_SKILLS_DIR", "")
        if env_global:
            global_skills_dirs.insert(0, Path(env_global))
        self.global_skills_dirs: list[Path] = global_skills_dirs

        self._skills: dict[str, SkillMetadata] = {}
        self.active_skills: list[str] = []
        self.last_decisions: list[CapabilityDecision] = []
        policy_config: Mapping[str, object] = capability_policy_config or {}
        self.auto_match_enabled: bool = bool(policy_config.get("auto_match_skills", True))
        self._capability_policy: AutonomousCapabilityPolicy = AutonomousCapabilityPolicy(
            project_root=str(self.project_root),
            max_autonomous_risk=str(policy_config.get("max_autonomous_risk", "high")),
            allow_critical_autonomy=bool(policy_config.get("allow_critical_autonomy", False)),
        )

        self.refresh()

    def refresh(self) -> None:
        """3개 소스에서 스킬 목록을 스캔하여 캐시합니다.

        로드 순서 (뒤쪽이 앞쪽을 덮어씀):
          1. 글로벌 (~/.agents/skills/)
          2. 로컬 (.agent/skills/, market/ 제외)
          3. 마켓 (.agent/skills/market/)  ← Phase 1 D13
        """
        self._skills.clear()

        # 1. 글로벌 스킬 로드
        if self.include_global:
            for global_dir in self.global_skills_dirs:
                if global_dir.exists():
                    self._load_from_dir(global_dir, is_global=True)

        # 2. 로컬 프로젝트 스킬 로드 (market/ 디렉토리 제외)
        if self.skills_dir.exists():
            self._load_from_dir(self.skills_dir, is_global=False, skip_dir=MARKET_DIR_NAME)

        # 3. 마켓 스킬 로드 (Phase 1 D13)
        if self.include_market and self.market_dir.exists():
            self._load_market_skills()

    def _load_from_dir(self, directory: Path, is_global: bool = False, skip_dir: str | None = None) -> None:
        """지정된 디렉토리에서 스킬을 로드합니다.

        Args:
            directory: 스캔할 디렉토리 경로
            is_global: 글로벌 소스 여부
            skip_dir: 건너뛸 서브디렉토리 이름 (로컬 스캔 시 market/ 제외용)
        """
        for root, dirs, files in os.walk(directory):
            # skip_dir이 지정된 서브디렉토리는 탐색에서 제외
            if skip_dir and skip_dir in dirs:
                dirs.remove(skip_dir)

            for file in files:
                if file.endswith(".md"):
                    file_path = Path(root) / file
                    skill_id = file_path.stem
                    # Use directory name as ID if the file is SKILL.md
                    if file == "SKILL.md":
                        skill_id = Path(root).name

                    parsed = self._parse_markdown(file_path)
                    if parsed:
                        parsed["is_global"] = is_global
                        source = "global" if is_global else "local"
                        parsed["source"] = source
                        self._skills[skill_id] = parsed
                        logger.debug(
                            "Loaded %s skill: %s",
                            source,
                            skill_id,
                        )

    def _load_market_skills(self) -> None:
        """마켓 디렉토리(.agent/skills/market/)에서 스킬을 로드합니다.

        각 마켓 스킬은 서브디렉토리로 구성되며 SKILL.md 파일을 포함합니다.
        마켓 스킬은 source="market"으로 태깅됩니다.
        """
        if not self.market_dir.exists():
            return

        for skill_dir in sorted(self.market_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            skill_id = skill_dir.name
            parsed = self._parse_markdown(skill_md)
            if parsed:
                parsed["is_global"] = False
                parsed["source"] = "market"
                self._skills[skill_id] = parsed
                logger.debug("Loaded market skill: %s", skill_id)

    def _parse_markdown(self, path: Path) -> SkillMetadata | None:
        """마크다운 파일에서 YAML Frontmatter와 Body를 추출합니다."""
        try:
            with path.open(encoding="utf-8") as file:
                content = file.read()

            metadata: dict[str, object] = {}
            body = content

            if content.startswith("---\n"):
                parts = content.split("---\n", 2)
                if len(parts) >= 3:
                    try:
                        parsed_metadata = cast(object, yaml.safe_load(parts[1]) or {})
                        if isinstance(parsed_metadata, dict):
                            metadata = dict(cast(Mapping[str, object], parsed_metadata))
                    except yaml.YAMLError:
                        metadata = _recover_scalar_metadata(parts[1])
                        logger.warning("Recovered scalar skill metadata from invalid YAML: %s", path)
                    body = parts[2]

            # YAML에 이름이나 설명이 없으면 파일 이름 사용
            raw_name = metadata.get("name", path.stem)
            name = raw_name if isinstance(raw_name, str) else path.stem
            raw_description = metadata.get("description", "")
            description = raw_description if isinstance(raw_description, str) else ""

            result: SkillMetadata = {
                "id": path.stem if path.name != "SKILL.md" else path.parent.name,
                "name": name,
                "description": description,
                "content": body.strip(),
                "path": str(path),
                "tags": metadata.get("tags", []),
                "tools": metadata.get("tools", []),
                "risk_level": str(metadata.get("risk_level", "safe")).lower(),
                "trust_level": str(metadata.get("trust_level", "local")).lower(),
                "requires_approval": bool(metadata.get("requires_approval", False)),
                "is_global": False,
                "source": "local",
            }
            return result
        except Exception:
            logger.exception("Failed to parse skill file %s", path)
            return None

    def get_skill(self, skill_id: str) -> SkillMetadata | None:
        """ID로 스킬을 조회합니다."""
        return self._skills.get(skill_id)

    def list_skills(self) -> list[dict[str, object]]:
        """모든 스킬 메타데이터를 반환합니다 (source 정보 포함)."""
        return [
            {
                "id": k,
                "name": v["name"],
                "description": v["description"],
                "risk_level": v.get("risk_level", "safe"),
                "trust_level": v.get("trust_level", "local"),
                "source": v.get("source", "local"),
            }
            for k, v in self._skills.items()
        ]

    def list_skills_by_source(self, source: str) -> list[dict[str, object]]:
        """특정 소스에서 로드된 스킬만 필터링하여 반환합니다.

        Args:
            source: 필터링할 소스 ("global", "local", "market")

        Returns:
            해당 소스의 스킬 메타데이터 리스트
        """
        return [s for s in self.list_skills() if s.get("source") == source]

    def get_market_skills(self) -> list[dict[str, object]]:
        """마켓에서 설치된 스킬 목록을 반환합니다.

        Returns:
            소스가 "market"인 스킬 메타데이터 리스트
        """
        return self.list_skills_by_source("market")

    def activate_skill(self, skill_id: str) -> bool:
        """활성 스킬 목록에 추가합니다."""
        if skill_id in self._skills and skill_id not in self.active_skills:
            self.active_skills.append(skill_id)
            return True
        return False

    def deactivate_skill(self, skill_id: str) -> bool:
        """활성 스킬 목록에서 제거합니다."""
        if skill_id in self.active_skills:
            self.active_skills.remove(skill_id)
            return True
        return False

    def clear_active_skills(self) -> None:
        """모든 활성 스킬을 초기화합니다."""
        self.active_skills.clear()

    def get_active_prompts(self) -> str:
        """활성화된 모든 스킬의 내용을 합쳐서 반환합니다."""
        if not self.active_skills:
            return ""

        prompts = ["\n\n=== ACTIVE SKILLS INSTRUCTIONS ==="]
        for s_id in self.active_skills:
            skill = self._skills.get(s_id)
            if skill:
                prompts.append(f"\n--- SKILL: {skill.get('name', s_id)} ---")
                prompts.append(skill["content"])

        prompts.append("==================================\n")
        return "\n".join(prompts)

    def auto_match(self, user_prompt: str, max_skills: int = 3) -> list[str]:
        """사용자 프롬프트와 스킬의 키워드/설명을 비교하여 관련 스킬을 자동 활성화합니다.

        자동화 핵심 기능:
        - 사용자가 /skill activate를 수동으로 입력할 필요 없음
        - 프롬프트 키워드 → 스킬 설명 + 태그 매칭
        - 상위 N개만 활성화 (과도한 컨텍스트 소비 방지)
        """
        if not self._skills:
            return []
        if not self.auto_match_enabled:
            logger.info("[AutoSkill] Auto matching disabled by configuration.")
            return []

        prompt_lower = user_prompt.lower()
        decisions: list[CapabilityDecision] = []

        for skill_id, skill_data in self._skills.items():
            if skill_id in self.active_skills:
                continue  # 이미 활성화된 스킬 스킵

            decision = self._capability_policy.decide_skill(skill_id, skill_data, prompt_lower)
            if decision.score > 3:
                decisions.append(decision)

        # 점수 순으로 정렬하여 상위 N개 활성화
        decisions.sort(key=lambda item: item.score, reverse=True)
        self.last_decisions = decisions[:max_skills]
        activated: list[str] = []
        for decision in self.last_decisions:
            if not decision.allows_autonomous_use:
                logger.info(
                    "[AutoSkill] Skipped '%s' decision=%s risk=%s reason=%s",
                    decision.capability_id,
                    decision.decision,
                    decision.risk_level,
                    decision.reason,
                )
                continue
            _ = self.activate_skill(decision.capability_id)
            activated.append(decision.capability_id)
            logger.info(
                "[AutoSkill] Activated '%s' (score: %.2f, risk=%s)",
                decision.capability_id,
                decision.score,
                decision.risk_level,
            )

        return activated

    def get_last_decisions(self) -> list[CapabilityDecision]:
        """최근 자동 스킬 판단 결과를 반환합니다."""
        return list(self.last_decisions)

    def get_autonomous_manifest(self, objective: str = "") -> list[CapabilityDecision]:
        """전체 스킬의 자율 활성화 판단 결과를 반환합니다."""
        decisions = [
            self._capability_policy.decide_skill(skill_id, skill_data, objective)
            for skill_id, skill_data in self._skills.items()
        ]
        decisions.sort(key=lambda item: item.score, reverse=True)
        return decisions
