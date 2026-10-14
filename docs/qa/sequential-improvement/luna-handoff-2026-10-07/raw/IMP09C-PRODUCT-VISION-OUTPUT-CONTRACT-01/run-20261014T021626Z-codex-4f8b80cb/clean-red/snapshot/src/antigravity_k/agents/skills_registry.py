"""Skills Registry module.

Phase 1 D13: .agent/skills/market/ 디렉토리 연동.
SkillsRegistry도 마켓 스킬을 동적 로드합니다.
"""

import logging
import re
from pathlib import Path
from typing import Callable, cast

from .. import i18n as i18n_module
from ..security.lintai_scanner import LintaiScanner
from ..tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# ─── 상수 ─────────────────────────────────────────────────────────────

MARKET_DIR_NAME = "market"
type FrontmatterValue = str | list[str]
i18n_t = cast(Callable[..., str], getattr(i18n_module, "t"))


def _parse_yaml_frontmatter(content: str) -> dict[str, FrontmatterValue]:
    """SKILL.md 파일의 YAML frontmatter(--- 블록)를 파싱합니다.

    예시:
    ---
    name: MY_SKILL
    description: 설명 텍스트
    tools:
      - computer_use
      - read_file
    ---

    반환: {"name": "MY_SKILL", "description": "...", "tools": [...]}
    본문은 "body" 키에 저장됩니다.
    """
    result: dict[str, FrontmatterValue] = {}

    # --- 로 시작하고 --- 로 끝나는 블록 추출
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        # frontmatter 없음 → 전체를 body로
        return {"body": content}

    frontmatter_text = match.group(1)
    body = match.group(2)
    result["body"] = body

    # 간단한 key: value 파싱 (yaml 라이브러리 없이)
    current_key = None
    current_list: list[str] | None = None

    for line in frontmatter_text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 리스트 항목 (  - item)
        list_match = re.match(r"^\s*-\s+(.+)", line)
        if list_match and current_key:
            if current_list is None:
                current_list = []
            current_list.append(list_match.group(1).strip())
            result[current_key] = current_list
            continue

        # key: value 쌍
        kv_match = re.match(r"^(\w+)\s*:\s*(.*)", line)
        if kv_match:
            # 이전 리스트 완료
            current_list = None
            current_key = kv_match.group(1).strip()
            value = kv_match.group(2).strip()
            if value:
                result[current_key] = value
            # value가 비어있으면 다음 줄에 리스트가 올 수 있음

    return result


class SkillProfile:
    """Google Skills 패턴 호환 스킬 프로필.

    google/skills 저장소의 구조를 차용:
    - SKILL.md: YAML frontmatter + 본문 (시스템 프롬프트)
    - references/: 참조 문서 폴더 (google/skills/gemini-api/references/ 패턴)
    - compatibility: 스킬 사용 전제 조건
    - clarifying_questions: 에이전트가 사전에 물어야 할 질문
    - validation_logic: 작업 완료 검증 로직
    """

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        tools: list[str],
        compatibility: str = "",
        references: dict[str, str] | None = None,
        clarifying_questions: list[str] | None = None,
        validation_logic: list[str] | None = None,
    ):
        """Initialize the SkillProfile.

        Args:
            name (str): str name.
            description (str): str description.
            system_prompt (str): str system prompt.
            tools (list[str]): list[str] tools.
            compatibility (str): str compatibility.
            references (dict[str, str] | None): dict[str, str] | None references.
            clarifying_questions (list[str] | None): list[str] | None clarifying questions.
            validation_logic (list[str] | None): list[str] | None validation logic.

        """
        self.name: str = name
        self.description: str = description
        self.system_prompt: str = system_prompt
        self.tools: list[str] = tools
        self.compatibility: str = compatibility
        self.references: dict[str, str] = references or {}
        self.clarifying_questions: list[str] = clarifying_questions or []
        self.validation_logic: list[str] = validation_logic or []

    def to_metadata(self) -> dict[str, object]:
        """UI 대시보드용 메타데이터 딕셔너리."""
        return {
            "name": self.name,
            "description": self.description,
            "tools": self.tools,
            "compatibility": self.compatibility,
            "has_references": len(self.references) > 0,
            "reference_count": len(self.references),
            "has_questions": len(self.clarifying_questions) > 0,
            "has_validation": len(self.validation_logic) > 0,
        }


class SkillsRegistry:
    """Ssak-Ai의 페르소나 및 스킬 맵핑을 관리합니다.

    에이전트 생성 시 이 레지스트리에서 역할을 조회하여 해당 역할에 맞는
    시스템 프롬프트와 사용 가능한 도구(Tool) 목록을 제공합니다.

    동적 스킬은 .agent/skills/ 디렉토리의 SKILL.md 파일에서 로드되며,
    YAML frontmatter에서 name, description, tools 필드를 자동 추출합니다.
    """

    def __init__(self, skills_dir: str = ".agent/skills"):
        """Initialize the SkillsRegistry.

        Args:
            skills_dir (str): str skills dir.

        """
        self.profiles: dict[str, SkillProfile] = {}
        self.skills_dir: Path = Path(skills_dir)
        self.scanner: LintaiScanner = LintaiScanner()
        self._initialize_default_profiles()
        self._load_dynamic_skills()

    def _initialize_default_profiles(self):
        # PM (Project Manager / CTO)
        self.register_profile(
            name="PM",
            description="프로젝트 관리 및 아키텍처 결정 담당",
            system_prompt="당신은 최고 기술 책임자(CTO) 겸 프로젝트 매니저입니다. 작업 우선순위를 정하고 다른 에이전트에게 작업을 할당하세요.",  # noqa: E501
            tools=["manage_kanban", "delegate_task", "search_web"],
        )
        # Backend Engineer
        self.register_profile(
            name="BACKEND",
            description="서버, API 및 데이터베이스 로직 개발 담당",
            system_prompt="당신은 시니어 백엔드 엔지니어입니다. 파이썬, FastAPI, Node.js 등 백엔드 개발에 특화되어 있습니다.",  # noqa: E501
            tools=["read_file", "write_file", "run_python", "execute_sql"],
        )
        # Frontend Engineer
        self.register_profile(
            name="FRONTEND",
            description="웹 및 앱 UI/UX 개발 담당",
            system_prompt="당신은 시니어 프론트엔드 엔지니어입니다. React, Flutter, CSS 등을 다룹니다.",
            tools=["read_file", "write_file", "run_npm_build"],
        )
        # QA Engineer
        self.register_profile(
            name="QA",
            description="코드 리뷰, 테스트 작성 및 버그 헌팅",
            system_prompt="당신은 품질 보증(QA) 엔지니어입니다. 주어진 코드의 버그를 찾고 테스트 코드를 작성하세요.",
            tools=["read_file", "run_pytest", "lint_code"],
        )
        # DevOps / SecOps (computer_use 도구 추가)
        self.register_profile(
            name="DEVOPS",
            description="배포 파이프라인, 보안 점검 및 데스크탑 자동화",
            system_prompt="당신은 DevSecOps 엔지니어입니다. 인프라 배포 코드와 보안 취약점을 검토하고, 필요 시 데스크탑 UI를 직접 조작할 수 있습니다.",  # noqa: E501
            tools=["read_file", "run_docker", "scan_security", "computer_use"],
        )

    def _load_dynamic_skills(self):
        """디렉토리에서 동적으로 스킬 파일을 로드합니다.

        Phase 1 D13: .agent/skills/market/도 스캔.
        """
        if not self.skills_dir.exists():
            return

        for skill_folder in self.skills_dir.iterdir():
            # market/ 디렉토리는 별도 처리
            if skill_folder.name == MARKET_DIR_NAME:
                continue
            if skill_folder.is_dir():
                skill_md_path = skill_folder / "SKILL.md"
                if skill_md_path.exists():
                    self._load_skill_file(skill_md_path, skill_folder.name)

        # 마켓 스킬 로드 (Phase 1 D13)
        market_dir = self.skills_dir / MARKET_DIR_NAME
        if market_dir.exists():
            for skill_folder in market_dir.iterdir():
                if skill_folder.is_dir():
                    skill_md_path = skill_folder / "SKILL.md"
                    if skill_md_path.exists():
                        self._load_skill_file(skill_md_path, skill_folder.name)

    def _load_skill_file(self, file_path: Path, skill_name: str):
        # Lintai 보안 스캔 수행
        is_safe = self.scanner.scan_skill_file(str(file_path))
        if not is_safe:
            logger.warning("Skill %s failed lintai security scan. Skipping load.", skill_name)
            return

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # YAML frontmatter 파싱
            parsed = _parse_yaml_frontmatter(content)

            # frontmatter에서 메타데이터 추출
            description_value = parsed.get("description")
            description = (
                description_value
                if isinstance(description_value, str)
                else f"Dynamic skill loaded from {file_path.name}"
            )
            compatibility_value = parsed.get("compatibility")
            compatibility = compatibility_value if isinstance(compatibility_value, str) else ""
            tools_value = parsed.get("tools")
            if isinstance(tools_value, str):
                tools = [t.strip() for t in tools_value.split(",")]
            elif isinstance(tools_value, list):
                tools = tools_value
            else:
                tools = []

            # 본문을 시스템 프롬프트로 사용 (frontmatter 제외)
            body_value = parsed.get("body")
            body = body_value if isinstance(body_value, str) else content

            # Google Skills 패턴: 본문에서 Clarifying Questions / Validation Logic 섹션 추출
            clarifying_questions = self._extract_section_list(body, "Clarifying Questions")
            validation_logic = self._extract_section_list(body, "Validation Logic")

            # references/ 폴더에서 참조 문서 로드 (google/skills/gemini-api/references/ 패턴)
            references = self._load_references(file_path.parent)

            self.register_profile(
                name=skill_name.upper(),
                description=description,
                system_prompt=body,
                tools=tools,
                compatibility=compatibility,
                references=references,
                clarifying_questions=clarifying_questions,
                validation_logic=validation_logic,
            )
            logger.info(i18n_t("skill.loaded", skill_name=skill_name.upper(), tools=str(tools)))
        except Exception:
            logger.exception("Error loading skill file %s", file_path)

    @staticmethod
    def _extract_section_list(body: str, section_name: str) -> list[str]:
        """마크다운 본문에서 특정 섹션(## 제목) 아래의 리스트 항목들을 추출합니다.

        Google Skills의 'Clarifying Questions', 'Validation Logic' 섹션 패턴 적용.
        """
        items: list[str] = []
        pattern = re.compile(rf"^##\s+{re.escape(section_name)}\s*$", re.MULTILINE | re.IGNORECASE)
        match = pattern.search(body)
        if not match:
            return items

        # 섹션 시작 지점 이후의 텍스트에서 리스트 항목 추출
        rest = body[match.end() :]
        for line in rest.split("\n"):
            stripped = line.strip()
            # 다음 섹션 시작 시 중단
            if stripped.startswith("## ") or stripped.startswith("# "):
                break
            # 리스트 항목 (마크다운 순서없는/순서있는 리스트)
            list_match = re.match(r"^[-*]\s+\*\*(.+?)\*\*[:\s]*(.*)", stripped)
            if list_match:
                items.append(f"{list_match.group(1).strip()}: {list_match.group(2).strip()}")
                continue
            list_match2 = re.match(r"^[-*\d.]+\s+(.+)", stripped)
            if list_match2:
                items.append(list_match2.group(1).strip())

        return items

    @staticmethod
    def _load_references(skill_dir: Path) -> dict[str, str]:
        """references/ 폴더의 .md 파일들을 읽어 {'파일명': '내용'} 딕셔너리로 반환합니다.

        google/skills 저장소의 references/ 패턴 적용:
        - gemini-api/references/text_and_multimodal.md
        - gemini-api/references/embeddings.md
        """
        refs: dict[str, str] = {}
        # references/ 또는 reference/ 폴더 모두 지원 (Google Skills 일관성 없음 대응)
        for ref_dir_name in ["references", "reference"]:
            ref_dir = skill_dir / ref_dir_name
            if ref_dir.is_dir():
                for ref_file in sorted(ref_dir.glob("*.md")):
                    try:
                        refs[ref_file.stem] = ref_file.read_text(encoding="utf-8")
                        logger.debug("  Loaded reference: %s", ref_file.name)
                    except Exception:
                        logger.exception("  Failed to load reference %s", ref_file)
        return refs

    def save_skill(self, name: str, content: str):
        """새로운 스킬을 동적으로 저장합니다."""
        skill_folder = self.skills_dir / name.lower()
        skill_folder.mkdir(parents=True, exist_ok=True)
        skill_file = skill_folder / "SKILL.md"

        with open(skill_file, "w", encoding="utf-8") as f:
            _ = f.write(content)

        logger.info("Skill %s saved to %s", name, skill_file)
        self._load_skill_file(skill_file, name)

    def register_profile(
        self,
        name: str,
        description: str,
        system_prompt: str,
        tools: list[str],
        compatibility: str = "",
        references: dict[str, str] | None = None,
        clarifying_questions: list[str] | None = None,
        validation_logic: list[str] | None = None,
    ):
        """Register profile.

        Args:
            name (str): str name.
            description (str): str description.
            system_prompt (str): str system prompt.
            tools (list[str]): list[str] tools.
            compatibility (str): str compatibility.
            references (dict[str, str] | None): dict[str, str] | None references.
            clarifying_questions (list[str] | None): list[str] | None clarifying questions.
            validation_logic (list[str] | None): list[str] | None validation logic.

        """
        self.profiles[name.upper()] = SkillProfile(
            name=name.upper(),
            description=description,
            system_prompt=system_prompt,
            tools=tools,
            compatibility=compatibility,
            references=references,
            clarifying_questions=clarifying_questions,
            validation_logic=validation_logic,
        )
        logger.info("Registered skill profile: %s", name.upper())

    def get_profile(self, name: str) -> SkillProfile:
        """Retrieve profile.

        Args:
            name (str): str name.

        Returns:
            SkillProfile: The skillprofile result.

        """
        profile = self.profiles.get(name.upper())
        if not profile:
            raise ValueError(f"Skill profile '{name}' not found in registry.")
        return profile

    def list_profiles(self) -> list[str]:
        """List Profiles.

        Returns:
            list[str]: The list[str] result.

        """
        return list(self.profiles.keys())

    def to_metadata_list(self) -> list[dict[str, object]]:
        """UI 대시보드용 전체 스킬 메타데이터 목록."""
        return [p.to_metadata() for p in self.profiles.values()]

    def get_reference(self, skill_name: str, ref_name: str) -> str | None:
        """스킬의 특정 참조 문서 내용을 반환합니다.

        예: get_reference("GEMINI_API", "embeddings")
             → references/embeddings.md 내용 반환
        """
        profile = self.profiles.get(skill_name.upper())
        if not profile:
            return None
        return profile.references.get(ref_name)

    def list_references(self, skill_name: str) -> list[str]:
        """스킬의 참조 문서 이름 목록을 반환합니다."""
        profile = self.profiles.get(skill_name.upper())
        if not profile:
            return []
        return list(profile.references.keys())

    def validate_skill_tools(self, tool_registry: ToolRegistry) -> dict[str, list[str]]:
        """등록된 스킬들이 참조하는 도구가 ToolRegistry에 실제 존재하는지 검증합니다.

        Returns:
            {"스킬명": ["누락된_도구1", ...]} 형태의 검증 결과

        """
        missing_map: dict[str, list[str]] = {}
        registry_tool_names: set[str] = set(tool_registry.get_names())

        for profile_name, profile in self.profiles.items():
            missing = [t for t in profile.tools if t not in registry_tool_names]
            if missing:
                missing_map[profile_name] = missing
                logger.warning(
                    "Skill '%s' references unregistered tools: %s",
                    profile_name,
                    missing,
                )

        return missing_map
