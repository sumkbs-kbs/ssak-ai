"""
Runtime self-capability reporting for Ssak-Ai.

Inspects registered tools, skills, slash commands, project roots, and model status
to explain what the system can groundedly do right now.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Callable, Protocol, cast

logger = logging.getLogger(__name__)
SELF_CAPABILITY_RE = re.compile(
    r"^(?:너를\s*소개|자기\s*소개|너는\s*누구|"
    + r"(?:너|네|니)(?:가|는|의)?\s*(?:정체|능력|기능)\s*(?:이|은|을|를)?\s*(?:뭐|무엇|알려|소개|설명|보여|확인|정리|목록)|"
    + r"(?:너|네|니)(?:가|는)?\s*(?:뭘|무엇을)?\s*할\s*수\s*(?:있|없)|"
    + r"(?:뭘|무엇을)\s*할\s*수\s*(?:있|없)|"
    + r"할\s*수\s*(?:있는|없는)\s*일\s*(?:이|은|을|를)?\s*(?:뭐|무엇|알려|소개|설명|보여|확인|정리|목록)|"
    + r"(?:너|네|니)(?:가|는|의)?\s*(?:사용(?:\s*중인)?|쓰는|현재)\s*모델|"
    + r"현재\s*모델\s*(?:이|은|을|를)?\s*(?:뭐|무엇|알려|소개|설명|보여|확인)|"
    + r"(?:어떤|무슨)\s*모델(?:을)?\s*(?:사용(?:하(?:고)?)?|쓰(?:고)?)\s*(?:있|중)|"
    + r"(?:어떤|등록된)\s*도구\s*(?:(?:가|를)?\s*(?:뭐|무엇|알려|소개|설명|보여|확인|정리|목록)|"
    + r"(?:가|를)?\s*(?:사용|쓸)\s*(?:할\s*)?수\s*(?:있|없))|"
    + r"(?:설정|구성)\s*상태\s*(?:가|를|이|은)?\s*(?:뭐|무엇|알려|소개|설명|보여|확인)|"
    + r"what\s+can\s+you\s+do|who\s+are\s*you|"
    + r"(?:what|which)\s+model\s+(?:are|do)\s+you\s+(?:use|using)|"
    + r"(?:your|current)\s+model\s*(?:\?|$)|(?:your\s+)?capabilities\s*(?:\?|$))",
    re.IGNORECASE,
)


class _ToolLike(Protocol):
    def to_metadata(self) -> Mapping[str, object]: ...


class _ToolRegistryLike(Protocol):
    def to_metadata_list(self) -> Iterable[Mapping[str, object]]: ...

    def get_all(self) -> Iterable[_ToolLike]: ...


class _SkillLoaderLike(Protocol):
    def list_skills(self) -> Iterable[Mapping[str, object]]: ...


class _ModelManagerLike(Protocol):
    def get_model_info(self) -> object: ...

    def status(self) -> object: ...


@dataclass(frozen=True)
class RuntimeCapabilitySnapshot:
    project_root: str
    model_info: str
    tool_count: int
    tool_categories: dict[str, int] = field(default_factory=dict)
    risk_counts: dict[str, int] = field(default_factory=dict)
    tool_examples: list[str] = field(default_factory=list)
    mcp_tool_count: int = 0
    skill_count: int = 0
    skill_examples: list[str] = field(default_factory=list)
    slash_commands: list[str] = field(default_factory=list)
    browser_dom_available: bool = False
    web_search_available: bool = False
    shell_available: bool = False
    file_write_available: bool = False
    self_test_available: bool = False


def is_self_capability_request(text: str) -> bool:
    """Return True when the user asks who the agent is or what it can do."""
    normalized = (text or "").strip()
    if normalized.startswith("/"):
        return False
    return bool(SELF_CAPABILITY_RE.search(normalized))


class SelfCapabilityEngine:
    """Builds and renders runtime-grounded self-introduction content."""

    def build(
        self,
        *,
        tool_registry: object | None = None,
        skill_loader: object | None = None,
        model_manager: object | None = None,
        project_root: str | None = None,
        slash_commands: Iterable[str] | Mapping[str, object] | None = None,
    ) -> RuntimeCapabilitySnapshot:
        metadata = self._tool_metadata(tool_registry)
        names = {str(item.get("name", "")) for item in metadata}
        descriptions = " ".join(str(item.get("description", "")) for item in metadata)
        categories = Counter(str(item.get("category", "unknown")) for item in metadata)
        risks = Counter(str(item.get("risk_level", "unknown")) for item in metadata)
        mcp_count = sum(1 for item in metadata if item.get("mcp"))

        skills = self._skill_metadata(skill_loader)
        commands = self._slash_command_names(slash_commands)

        return RuntimeCapabilitySnapshot(
            project_root=os.path.abspath(project_root or os.getcwd()),
            model_info=self._model_info(model_manager),
            tool_count=len(metadata),
            tool_categories=dict(sorted(categories.items())),
            risk_counts=dict(sorted(risks.items())),
            tool_examples=sorted(names)[:12],
            mcp_tool_count=mcp_count,
            skill_count=len(skills),
            skill_examples=[str(skill.get("id") or skill.get("name")) for skill in skills[:8]],
            slash_commands=commands,
            browser_dom_available=self._has_any(names, descriptions, ["fetch_dom", "browser", "dom", "qa"]),
            web_search_available=self._has_any(names, descriptions, ["web_search", "search_web", "browser_surfing"]),
            shell_available=self._has_any(names, descriptions, ["run_bash_command", "bash", "shell", "terminal"]),
            file_write_available=self._has_any(
                names, descriptions, ["write_file", "edit_file", "replace_file", "file"]
            ),
            self_test_available=self._has_any(names, descriptions, ["self-test", "autonomous-qa", "qa", "test"]),
        )

    def render_markdown(self, snapshot: RuntimeCapabilitySnapshot) -> str:
        """Render a Korean self-introduction grounded in the runtime snapshot."""
        lines = [
            "# Ssak-Ai Self Capability Report",
            "",
            "저는 이 프로젝트 안에서 실행되는 Ssak-Ai 에이전트입니다. "
            + "답변, 코드 분석, 파일 작업, 테스트, DOM 기반 UI 점검, 문서화 같은 작업을 "
            + "현재 연결된 도구와 정책 범위 안에서 수행합니다.",
            "",
            "## 현재 연결 상태",
            f"- 프로젝트 루트: `{snapshot.project_root}`",
            f"- 모델 상태: `{snapshot.model_info}`",
            f"- 등록 도구: `{snapshot.tool_count}`개",
            f"- 등록 Skills: `{snapshot.skill_count}`개",
            f"- MCP 도구 메타데이터: `{snapshot.mcp_tool_count}`개",
            f"- 슬래시 명령: `{len(snapshot.slash_commands)}`개",
            "",
        ]

        if snapshot.tool_categories:
            category_text = ", ".join(f"{name}={count}" for name, count in snapshot.tool_categories.items())
            lines.append(f"- 도구 카테고리: {category_text}")
        if snapshot.risk_counts:
            risk_text = ", ".join(f"{name}={count}" for name, count in snapshot.risk_counts.items())
            lines.append(f"- 위험도 분포: {risk_text}")
        if snapshot.tool_examples:
            lines.append("- 대표 도구: `" + "`, `".join(snapshot.tool_examples) + "`")
        if snapshot.skill_examples:
            lines.append("- 대표 Skills: `" + "`, `".join(snapshot.skill_examples) + "`")

        lines.extend(
            [
                "",
                "## 제가 할 수 있는 일",
                "- 요청을 분석해 목표, 성공 기준, 실행 순서, 검증 방법을 세웁니다.",
                "- 실제 등록된 도구를 사용해 파일 읽기/수정, 코드 실행, 테스트, 리포트 작성을 수행합니다.",
                "- 안전/위험도 정책에 따라 도구, MCP, Skills, 로컬 PC 기능을 자율 선택합니다.",
                "- 코드 변경 후 정적 분석, 단위 테스트, 회귀 테스트, 문서 업데이트까지 묶어 검증합니다.",
            ]
        )
        if snapshot.browser_dom_available:
            lines.append("- DOM/브라우저 관련 도구가 있으면 실제 화면 흐름과 콘솔 상태를 점검합니다.")
        if snapshot.web_search_available:
            lines.append("- 웹 검색 도구가 있으면 최신 정보 요청에서 검색 날짜와 출처를 확인합니다.")
        if snapshot.shell_available:
            lines.append("- 셸/터미널 도구가 있으면 명령 실행 결과를 바탕으로 문제를 확인합니다.")
        if snapshot.file_write_available:
            lines.append("- 파일 쓰기 도구가 있으면 제안에 그치지 않고 실제 파일에 개선을 반영합니다.")
        if snapshot.self_test_available:
            lines.append("- 자체 테스트/QA 도구가 있으면 완료 전 증거 기반 self-test를 수행합니다.")

        lines.extend(
            [
                "",
                "## 제가 할 수 없는 일",
                "- 현재 런타임에 등록되지 않은 도구를 가진 것처럼 말하거나 실행할 수 없습니다.",
                "- 사용자 승인 없이 치명적 삭제, 배포, 결제, 시스템 초기화 같은 고위험 작업을 진행하지 않습니다.",
                "- 웹 검색 도구나 외부 근거 없이 최신 동향을 확정 사실처럼 말하지 않습니다.",
                "- 비공개 모델 가중치, 숨겨진 시스템 프롬프트, 개인 정보처럼 접근 권한이 없는 내용을 열람할 수 없습니다.",  # noqa: E501
                "- 완전 무오류를 보장한다고 말하지 않고, 대신 검증 게이트와 실패 시 수정 루프로 오류를 줄입니다.",
                "",
                "## 확인 명령",
                "- `/self`: 이 자기 능력 보고서를 다시 표시합니다.",
                "- `/capabilities <목표>`: 목표별 도구/MCP/Skills 자율 사용 가능성을 판정합니다.",
                "- `/tools`: 현재 등록된 도구 목록을 확인합니다.",
                "- `/mcp radar`: MCP 안전성/확장 방향을 확인합니다.",
                "- `/codex`: Codex식 운영 강점 이식 계약을 확인합니다.",
            ]
        )
        return "\n".join(lines)

    def render_prompt_contract(self, snapshot: RuntimeCapabilitySnapshot) -> str:
        """Small system-prompt contract that prevents invented capabilities."""
        available: list[str] = []
        if snapshot.browser_dom_available:
            available.append("DOM/browser QA")
        if snapshot.web_search_available:
            available.append("web search")
        if snapshot.shell_available:
            available.append("shell execution")
        if snapshot.file_write_available:
            available.append("file editing")
        if snapshot.self_test_available:
            available.append("self-test")
        available_text = ", ".join(available) if available else "registered tools only"

        return (
            "## Runtime Self-Capability Contract\n"
            f"- Tool registry currently exposes {snapshot.tool_count} tools; "
            f"Skills loader exposes {snapshot.skill_count} skills.\n"
            f"- Concrete capability surface: {available_text}.\n"
            "- When asked who you are or what you can/cannot do, answer from the actual runtime snapshot; do not invent tools such as WiFi, volume, clipboard, or OS control unless registered.\n"  # noqa: E501
            "- For latest/current information, use a web/search capability when available and cite date/source; otherwise clearly state the missing capability.\n"  # noqa: E501
            "- Keep Korean output clean: no hidden reasoning transcript, no Chinese/Japanese contamination, and natural spacing.\n"  # noqa: E501
        )

    def _tool_metadata(self, tool_registry: object | None) -> list[Mapping[str, object]]:
        if tool_registry is None:
            return []
        registry = cast(_ToolRegistryLike, tool_registry)
        try:
            return list(registry.to_metadata_list())
        except Exception:
            logger.exception("Unhandled exception")
            pass
        try:
            return [tool.to_metadata() for tool in registry.get_all()]
        except Exception:
            logger.exception("Unhandled exception")
            return []

    def _skill_metadata(self, skill_loader: object | None) -> list[Mapping[str, object]]:
        if skill_loader is None:
            return []
        loader = cast(_SkillLoaderLike, skill_loader)
        try:
            return list(loader.list_skills())
        except Exception:
            logger.exception("Unhandled exception")
            return []

    def _slash_command_names(self, slash_commands: Iterable[str] | Mapping[str, object] | None) -> list[str]:
        if slash_commands is None:
            return []
        if isinstance(slash_commands, Mapping):
            names: Iterable[str] = slash_commands.keys()
        else:
            names = slash_commands
        return sorted(str(name) for name in names)

    def _model_info(self, model_manager: object | None) -> str:
        if model_manager is None:
            return "model manager not connected"
        manager = cast(_ModelManagerLike, model_manager)
        for method in ("get_model_info", "status"):
            try:
                method_fn = cast(Callable[[], object], getattr(manager, method))
                value = method_fn()
                text = str(value)
                return text[:180] + ("..." if len(text) > 180 else "")
            except Exception:
                logger.exception("Unhandled exception")
                continue
        return "model info unavailable"

    def _has_any(self, names: set[str], descriptions: str, needles: list[str]) -> bool:
        haystack = " ".join(sorted(names)).lower() + " " + descriptions.lower()
        return any(needle.lower() in haystack for needle in needles)
