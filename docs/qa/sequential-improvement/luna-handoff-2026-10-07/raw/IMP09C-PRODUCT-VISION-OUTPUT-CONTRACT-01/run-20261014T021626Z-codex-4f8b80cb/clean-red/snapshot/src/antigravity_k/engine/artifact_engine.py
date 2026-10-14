"""Ssak-Ai: Artifact Engine (Phase 1 Enhanced).

===========================================================================
계획 모드(Planning Mode) 시 생성되는 implementation_plan.md, task.md,
walkthrough.md 등 아티팩트를 안전하게 생성/검증/추출합니다.

Phase 1 강화 사항:
  - validate_plan_complete(): Plan 아티팩트 완전성 검증
  - extract_plan_tasks(): Plan에서 태스크 리스트 추출
  - list_artifacts(): 아티팩트 디렉토리 조회
  - auto_create_kanban_tasks(): Plan → Kanban 태스크 자동 생성
  - inject_planning_prompt(): Plan→Build 자동 전환 참조 업데이트
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeAlias, TypedDict, cast, final, override

from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

JsonValue: TypeAlias = object
JsonMap: TypeAlias = dict[str, JsonValue]


class _PlanSection(TypedDict):
    name: str
    patterns: list[str]
    weight: float


class _ToolRegistryProtocol:
    def install(self, _tool: BaseTool) -> object:
        raise NotImplementedError


class _PlanTaskData(TypedDict):
    title: str
    description: str
    priority: int
    status: str
    depends_on: list[str]
    section: str


class _PlanValidationData(TypedDict):
    is_complete: bool
    score: float
    missing_sections: list[str]
    issues: list[str]
    task_count: int


class _ArtifactWriteResult(TypedDict):
    success: bool
    filepath: str
    message: str
    request_feedback: bool
    error: str


class _ArtifactInfo(TypedDict):
    filename: str
    path: str
    size: int
    modified: str
    type: str


class _KanbanResult(TypedDict):
    success: bool
    board: object | None
    task_count: int
    message: str


# ─── Plan Task 데이터 타입 ───────────────────────────────────────────


@dataclass
class PlanTask:
    """Plan 아티팩트에서 추출된 단일 태스크."""

    title: str
    description: str = ""
    priority: int = 0  # 0=normal, 1=high, 2=critical
    status: str = "todo"  # todo | in_progress | done
    depends_on: list[str] = field(default_factory=list)
    section: str = ""  # 원본 Plan 내 섹션 이름
    line_number: int = 0  # 마크다운 내 라인 번호

    def to_dict(self) -> _PlanTaskData:
        return {
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "depends_on": self.depends_on,
            "section": self.section,
        }


# ─── Plan Validation Result ──────────────────────────────────────────


@dataclass
class PlanValidationResult:
    """Plan 검증 결과."""

    is_complete: bool
    score: float  # 0.0 ~ 1.0
    missing_sections: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    task_count: int = 0

    def to_dict(self) -> _PlanValidationData:
        return {
            "is_complete": self.is_complete,
            "score": self.score,
            "missing_sections": self.missing_sections,
            "issues": self.issues,
            "task_count": self.task_count,
        }


# ─── Artifact Metadata ────────────────────────────────────────────────


@dataclass
class ArtifactMetadata:
    """아티팩트 메타데이터."""

    artifact_type: str  # implementation_plan | task | walkthrough | other
    summary: str
    request_feedback: bool = False


# ─── Required Plan Sections (완전성 검증 기준) ────────────────────────

REQUIRED_PLAN_SECTIONS: list[_PlanSection] = [
    {
        "name": "Overview",
        "patterns": [r"#+\s*개요", r"#+\s*overview", r"#+\s*목표", r"#+\s*goal"],
        "weight": 0.2,
    },
    {
        "name": "Technical Approach",
        "patterns": [
            r"#+\s*기술\s*접근",
            r"#+\s*technical\s*approach",
            r"#+\s*설계",
            r"#+\s*design",
            r"#+\s*아키텍처",
            r"#+\s*architecture",
        ],
        "weight": 0.25,
    },
    {
        "name": "Implementation Steps",
        "patterns": [
            r"#+\s*구현\s*단계",
            r"#+\s*implementation\s*steps",
            r"#+\s*작업\s*계획",
            r"#+\s*plan",
            r"#+\s*steps?",
            r"#+\s*tasks?",
        ],
        "weight": 0.25,
    },
    {
        "name": "Task List",
        "patterns": [r"[-*]\s*\[[\sx]\]"],  # checkbox list
        "weight": 0.15,
    },
    {
        "name": "Timeline / Priority",
        "patterns": [
            r"#+\s*일정",
            r"#+\s*timeline",
            r"#+\s*우선순위",
            r"#+\s*priority",
        ],
        "weight": 0.15,
    },
]


# ─── 메인 엔진 ─────────────────────────────────────────────────────────


@final
class ArtifactEngine:
    """Plan 아티팩트 생성을 담당하는 엔진.

    Phase 1 확장:
    - Plan 완전성 검증 (validate_plan_complete)
    - 태스크 추출 및 Kanban 연동 (extract_plan_tasks, auto_create_kanban_tasks)
    - 아티팩트 목록 조회 (list_artifacts)
    - ModeManager 연동 (set_plan_artifact, set_plan_quality_passed)
    """

    def __init__(self, project_root: str):
        """Initialize the ArtifactEngine.

        Args:
            project_root: 프로젝트 루트 경로
        """
        self.project_root: str = project_root
        self.artifacts_dir: str = os.path.join(project_root, "artifacts")
        os.makedirs(self.artifacts_dir, exist_ok=True)

    # ─── 기본 CRUD ─────────────────────────────────────────────────

    def write_artifact(
        self,
        target_file: str,
        code_content: str,
        metadata: ArtifactMetadata | None = None,
    ) -> _ArtifactWriteResult:
        """아티팩트 파일을 작성합니다.

        Args:
            target_file: 대상 파일 이름 또는 경로 (artifacts/ 내부에 저장됨)
            code_content: 작성할 마크다운 내용
            metadata: ArtifactMetadata 객체

        Returns:
            {"success": bool, "filepath": str, "message": str, ...}
        """
        filename = os.path.basename(target_file)
        if not filename.endswith(".md"):
            filename += ".md"

        filepath = os.path.join(self.artifacts_dir, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                _ = f.write(code_content)

            feedback_msg = ""
            if metadata and metadata.request_feedback:
                feedback_msg = " [APPROVAL REQUIRED]"

            logger.info("Artifact created: %s%s", filepath, feedback_msg)

            return {
                "success": True,
                "filepath": filepath,
                "message": f"Artifact {filename} successfully written.{feedback_msg}",
                "request_feedback": metadata.request_feedback if metadata else False,
                "error": "",
            }
        except Exception as e:
            logger.exception("Failed to write artifact %s", filepath)
            return {
                "success": False,
                "filepath": "",
                "message": "",
                "request_feedback": False,
                "error": str(e),
            }

    def read_artifact(self, target_file: str) -> str | None:
        """아티팩트 파일 내용을 읽습니다.

        Args:
            target_file: 대상 파일 이름 (artifacts/ 기준)

        Returns:
            파일 내용 또는 None (파일 없음)
        """
        filename = os.path.basename(target_file)
        if not filename.endswith(".md"):
            filename += ".md"

        filepath = os.path.join(self.artifacts_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, encoding="utf-8") as f:
                return f.read()
        return None

    def delete_artifact(self, target_file: str) -> bool:
        """아티팩트 파일을 삭제합니다.

        Args:
            target_file: 대상 파일 이름

        Returns:
            삭제 성공 여부
        """
        filename = os.path.basename(target_file)
        if not filename.endswith(".md"):
            filename += ".md"

        filepath = os.path.join(self.artifacts_dir, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.info("Artifact deleted: %s", filepath)
                return True
            except Exception:
                logger.exception("Failed to delete artifact %s", filepath)
                return False
        return False

    # ─── Plan 완전성 검증 ──────────────────────────────────────────

    def validate_plan_complete(self, target_file: str = "implementation_plan.md") -> PlanValidationResult:
        """Plan 아티팩트의 완전성을 검증합니다.

        REQUIRED_PLAN_SECTIONS에 정의된 필수 섹션이 모두 포함되어 있는지,
        태스크 리스트가 존재하는지, 최소 길이를 충족하는지 확인합니다.

        Args:
            target_file: 검증할 Plan 파일 이름

        Returns:
            PlanValidationResult
        """
        content = self.read_artifact(target_file)
        if not content:
            return PlanValidationResult(
                is_complete=False,
                score=0.0,
                missing_sections=["(artifact not found)"],
                issues=["Plan 아티팩트 파일이 존재하지 않습니다."],
                task_count=0,
            )

        content_lower = content.lower()
        issues: list[str] = []
        missing_sections: list[str] = []
        score = 0.0

        # 1. 섹션 존재 여부 검증
        for section in REQUIRED_PLAN_SECTIONS:
            found = any(re.search(p, content_lower) for p in section["patterns"])
            if found:
                score += section["weight"]
            else:
                missing_sections.append(section["name"])
                issues.append(f"필수 섹션 누락: '{section['name']}'")

        # 2. 최소 길이 검증
        if len(content.strip()) < 200:
            score *= 0.5
            issues.append("Plan 내용이 너무 짧습니다 (200자 미만)")

        # 3. 태스크/체크박스 존재 여부
        checkbox_count = len(re.findall(r"[-*]\s*\[[\sx]\]", content))
        if checkbox_count == 0:
            score = max(0.0, score - 0.15)
            issues.append("실행 가능한 태스크(체크박스)가 없습니다")
        elif checkbox_count < 3:
            score = max(0.0, score - 0.05)
            issues.append("태스크 수가 적습니다 (3개 미만)")

        # 4. 파일 참조 존재 여부 (권장)
        has_file_refs = bool(re.search(r"`[^`]+`", content))
        if not has_file_refs:
            score = max(0.0, score - 0.05)
            issues.append("파일 참조(백틱)가 없습니다 — 구체적인 파일명을 명시하세요")

        score = round(min(score, 1.0), 2)
        is_complete = score >= 0.6 and len(missing_sections) <= 1

        return PlanValidationResult(
            is_complete=is_complete,
            score=score,
            missing_sections=missing_sections,
            issues=issues,
            task_count=checkbox_count,
        )

    def is_plan_ready_for_build(self, target_file: str = "implementation_plan.md") -> bool:
        """Plan이 Build 모드 전환 조건을 충족하는지 확인합니다.

        validate_plan_complete()의 결과가 is_complete=True이고
        score가 0.6 이상이면 True를 반환합니다.
        """
        result = self.validate_plan_complete(target_file)
        return result.is_complete and result.score >= 0.6

    # ─── 태스크 추출 ───────────────────────────────────────────────

    def extract_plan_tasks(self, target_file: str = "implementation_plan.md") -> list[PlanTask]:
        """Plan 마크다운에서 실행 가능한 태스크 리스트를 추출합니다.

        다음 패턴을 인식합니다:
        - [ ] 일반 태스크
        - [x] 완료된 태스크
        - ## 섹션 제목 (태스크 그룹화)
        - **굵은 글씨** 설명 (태스크 상세)

        Args:
            target_file: Plan 파일 이름

        Returns:
            PlanTask 객체 리스트
        """
        content = self.read_artifact(target_file)
        if not content:
            return []

        tasks: list[PlanTask] = []
        current_section = "General"
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # 섹션 제목 감지
            section_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
            if section_match:
                current_section = section_match.group(2).strip()
                continue

            # 체크박스 태스크 감지: "- [ ] title" 또는 "- [x] title"
            task_match = re.match(r"^[-*]\s*\[([\sx])\]\s+(.+)$", stripped)
            if not task_match:
                continue

            is_done = task_match.group(1).lower() == "x"
            raw_title = task_match.group(2).strip()

            # 우선순위 감지: "P0:", "P1:", "🔴", "🟡", "[HIGH]" 등
            priority = 0
            description = ""
            title = raw_title

            priority_patterns = [
                (r"^🔴\s*", 2),
                (r"^🟡\s*", 1),
                (r"^\[CRITICAL\]\s*", 2),
                (r"^\[HIGH\]\s*", 2),
                (r"^P0[:.\s]+", 2),
                (r"^P1[:.\s]+", 1),
                (r"^\[MEDIUM\]\s*", 1),
            ]
            for pattern, pri in priority_patterns:
                if re.search(pattern, title, re.IGNORECASE):
                    priority = pri
                    title = re.sub(pattern, "", title, flags=re.IGNORECASE).strip()
                    break

            # 설명 분리: "title: description" 또는 "title — description"
            desc_match = re.match(r"^(.+?)[:\s—–-]{1,3}\s*(.+)$", title)
            if desc_match:
                title = desc_match.group(1).strip()
                description = desc_match.group(2).strip()

            # 의존성 감지: "depends: #task-id" 또는 "after: X"
            dep_match = re.search(r"(?:depends\s*(?::\s*|on\s+)|after\s*:\s*)([^\s,;]+)", title, re.IGNORECASE)
            depends_on = [dep_match.group(1).strip()] if dep_match else []

            task = PlanTask(
                title=title[:200],
                description=description[:500] if description else "",
                priority=priority,
                status="done" if is_done else "todo",
                depends_on=depends_on,
                section=current_section,
                line_number=line_num,
            )
            tasks.append(task)

        return tasks

    # ─── Kanban 연동 ───────────────────────────────────────────────

    def auto_create_kanban_tasks(self, target_file: str = "implementation_plan.md") -> _KanbanResult:
        """Plan에서 태스크를 추출하여 Kanban 보드에 자동 등록합니다.

        KanbanEngine이 로드 가능할 때만 동작합니다.

        Args:
            target_file: Plan 파일 이름

        Returns:
            {"success": bool, "board": KanbanBoard | None, "task_count": int, "message": str}
        """
        tasks = self.extract_plan_tasks(target_file)
        if not tasks:
            return {
                "success": False,
                "board": None,
                "task_count": 0,
                "message": "Plan에서 추출할 태스크가 없습니다. 체크박스 목록을 확인하세요.",
            }

        try:
            from antigravity_k.engine.kanban_engine import KanbanBoard

            board = KanbanBoard(name=f"Plan: {os.path.basename(target_file)}")

            # 태스크 등록 (todo 상태만)
            prev_id: str | None = None
            registered = 0
            for task in tasks:
                if task.status == "done":
                    continue

                kanban_task = board.add_task(
                    title=task.title,
                    description=task.description,
                    priority=task.priority,
                    depends_on=task.depends_on or ([prev_id] if prev_id else []),
                )
                prev_id = kanban_task.task_id
                registered += 1

            return {
                "success": True,
                "board": board,
                "task_count": registered,
                "message": (f"✅ Plan에서 {registered}개 태스크를 Kanban에 등록했습니다.\n{board.to_markdown()}"),
            }

        except ImportError:
            logger.warning("[ArtifactEngine] KanbanEngine not available — skipping task creation")
            return {
                "success": False,
                "board": None,
                "task_count": len(tasks),
                "message": f"Plan에서 {len(tasks)}개 태스크를 추출했지만 KanbanEngine이 설치되지 않았습니다.",
            }
        except Exception as e:
            logger.exception("[ArtifactEngine] Kanban task creation failed")
            return {
                "success": False,
                "board": None,
                "task_count": len(tasks),
                "message": f"Kanban 태스크 생성 실패: {e}",
            }

    # ─── 아티팩트 목록 ─────────────────────────────────────────────

    def list_artifacts(self) -> list[_ArtifactInfo]:
        """artifacts/ 디렉토리의 모든 아티팩트 정보를 반환합니다.

        Returns:
            [{"filename": str, "path": str, "size": int, "modified": str, "type": str}, ...]
        """
        if not os.path.exists(self.artifacts_dir):
            return []

        artifacts: list[_ArtifactInfo] = []
        for fname in sorted(os.listdir(self.artifacts_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(self.artifacts_dir, fname)
            try:
                stat = os.stat(fpath)
                artifact_type = self._classify_artifact(fname)
                artifacts.append(
                    {
                        "filename": fname,
                        "path": fpath,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                        .astimezone()
                        .replace(tzinfo=None)
                        .isoformat(),
                        "type": artifact_type,
                    },
                )
            except (OSError, ValueError):
                logger.debug("Unable to inspect artifact: %s", fpath)
                continue

        return artifacts

    @staticmethod
    def _classify_artifact(filename: str) -> str:
        """파일명으로 아티팩트 유형을 분류합니다."""
        name_lower = filename.lower()
        if "implementation_plan" in name_lower or "plan" in name_lower:
            return "implementation_plan"
        if "task" in name_lower:
            return "task"
        if "walkthrough" in name_lower or "summary" in name_lower:
            return "walkthrough"
        return "other"

    # ─── Planning Prompt ────────────────────────────────────────────

    def inject_planning_prompt(self) -> str:
        """계획 모드 진입을 강제하기 위한 프롬프트를 주입합니다.

        Phase 1 업데이트:
        - Plan→Build 자동 전환 참조 추가
        - QualityGate 통과 조건 명시
        """
        return (
            "\n\n[CRITICAL ALGORITHM OVERRIDE: ARTIFACT-BASED PLANNING MODE]\n"
            "You are executing a COMPLEX task or requested to plan. You MUST enter PLANNING MODE.\n"
            "1. DO NOT write functional code yet. Research and plan first.\n"
            "2. You MUST use the `write_artifact` tool to create `implementation_plan."
            "md` outlining your technical plan.\n"
            "3. The plan MUST include these sections: Overview, Technical Approach, "
            "Implementation Steps, Task List (checkbox list), Timeline/Priority.\n"
            "4. After the plan is complete and validated, the system will "
            "automatically transition to BUILD MODE where you can execute code.\n"
            "5. Plan quality is verified by QualityGate — ensure score >= 0.6 "
            "for auto-transition.\n"
            "6. After approval, create a `task.md` using `write_artifact` with a checkbox list.\n"
            "7. After completion, create a `walkthrough.md` summarizing the changes.\n"
            "\n[ANTIGRAVITY MARKDOWN STANDARDS - STRICT COMPLIANCE REQUIRED]\n"
            "- Use GitHub Alerts (`> [!NOTE]`, `> [!WARNING]`, etc.) to highlight critical info.\n"
            "- NEVER wrap file link text in backticks. Correct: `[utils.py](file:///...)`, "
            "Incorrect: `[`utils.py`](file:///...)`.\n"
            "- When writing Mermaid diagrams, NEVER include HTML tags inside node labels.\n"
            "- For presenting multiple sequential visual or code blocks, use ````carousel` "
            "syntax with `<!-- slide -->` separators.\n"
            "- Ensure your output has high information density. Do not generate long, "
            "repetitive filler text.\n"
        )

    # ─── Utility: Plan 요약 ────────────────────────────────────────

    def summarize_plan(self, target_file: str = "implementation_plan.md") -> str:
        """Plan 아티팩트의 요약 정보를 반환합니다.

        Args:
            target_file: Plan 파일 이름

        Returns:
            마크다운 형식의 요약 문자열
        """
        validation = self.validate_plan_complete(target_file)
        tasks = self.extract_plan_tasks(target_file)

        lines = [
            "## 📋 Plan Summary",
            "",
            f"**File:** `{target_file}`",
            f"**Validation:** {'✅ Pass' if validation.is_complete else '❌ Fail'} (score: {validation.score})",
            "",
        ]

        if validation.missing_sections:
            lines.append("**Missing Sections:**")
            for s in validation.missing_sections:
                lines.append(f"  - {s}")
            lines.append("")

        if validation.issues:
            lines.append("**Issues:**")
            for issue in validation.issues:
                lines.append(f"  - {issue}")
            lines.append("")

        if tasks:
            done = sum(1 for t in tasks if t.status == "done")
            todo = sum(1 for t in tasks if t.status == "todo")
            lines.append(f"**Tasks:** {len(tasks)} total ({todo} todo, {done} done)")
            lines.append("")
            for task in tasks[:10]:  # 최대 10개
                status_icon = "✅" if task.status == "done" else "⬜"
                priority_tag = " 🔴" if task.priority >= 2 else (" 🟡" if task.priority == 1 else "")
                lines.append(f"  {status_icon}{priority_tag} {task.title[:80]}")
            if len(tasks) > 10:
                lines.append(f"  ... and {len(tasks) - 10} more")
        else:
            lines.append("**Tasks:** No checkbox tasks found.")

        return "\n".join(lines)


# ─── Tool Registry 연동 ────────────────────────────────────────────────


def register_artifact_tool(tool_registry: _ToolRegistryProtocol, project_root: str) -> ArtifactEngine:
    """도구 레지스트리에 write_artifact 도구를 등록합니다."""
    engine = ArtifactEngine(project_root)

    @final
    class WriteArtifactTool(BaseTool):
        category: ToolCategory = ToolCategory.FILE_IO
        render_in: RenderIn = RenderIn.CONTEXTUAL
        risk_level: RiskLevel = RiskLevel.LOW
        icon: str = "📝"
        tags: list[str] = ["artifact", "markdown", "write", "plan"]

        def __init__(self) -> None:
            super().__init__()
            self._name: str = "write_artifact"
            self._description: str = (
                "Create or update planning artifacts like implementation_plan.md, task.md, and walkthrough.md"
            )

        @property
        @override
        def name(self) -> str:
            return self._name

        @property
        @override
        def description(self) -> str:
            return self._description

        @property
        @override
        def parameters_schema(self) -> JsonMap:
            return {
                "type": "object",
                "properties": {
                    "target_file": {
                        "type": "string",
                        "description": "The target file to create (e.g., implementation_plan.md)",
                    },
                    "code_content": {
                        "type": "string",
                        "description": "The markdown content to write",
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "artifact_type": {
                                "type": "string",
                                "enum": [
                                    "implementation_plan",
                                    "task",
                                    "walkthrough",
                                    "other",
                                ],
                            },
                            "summary": {"type": "string"},
                            "request_feedback": {
                                "type": "boolean",
                                "description": "Set to true to pause and request user approval",
                            },
                        },
                        "required": ["artifact_type"],
                    },
                },
                "required": ["target_file", "code_content"],
            }

        @override
        def execute(self, **kwargs: object) -> str:
            target_file_value = kwargs.get("target_file", "")
            target_file = target_file_value if isinstance(target_file_value, str) else ""
            content_value = kwargs.get("code_content", "")
            code_content = content_value if isinstance(content_value, str) else ""
            metadata_value = kwargs.get("metadata")
            metadata = cast(JsonMap, metadata_value) if isinstance(metadata_value, dict) else None
            meta_obj: ArtifactMetadata | None = None
            if metadata is not None:
                artifact_type_value = metadata.get("artifact_type", "other")
                summary_value = metadata.get("summary", "")
                request_feedback_value = metadata.get("request_feedback", False)
                meta_obj = ArtifactMetadata(
                    artifact_type=artifact_type_value if isinstance(artifact_type_value, str) else "other",
                    summary=summary_value if isinstance(summary_value, str) else "",
                    request_feedback=request_feedback_value if isinstance(request_feedback_value, bool) else False,
                )
            result = engine.write_artifact(target_file, code_content, meta_obj)
            if result.get("success") is True:
                msg = result["message"]
                if result.get("request_feedback") is True:
                    msg += "\n\nWAITING_FOR_USER_APPROVAL"
                return msg
            return f"Error writing artifact: {result.get('error', '')}"

    _ = tool_registry.install(WriteArtifactTool())
    return engine
