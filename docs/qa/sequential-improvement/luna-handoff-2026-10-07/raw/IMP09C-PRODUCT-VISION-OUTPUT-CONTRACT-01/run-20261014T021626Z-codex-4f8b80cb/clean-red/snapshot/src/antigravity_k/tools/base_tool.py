"""Base Tool module."""

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import Enum

logger = logging.getLogger(__name__)


# ─────────────────── 도구 메타데이터 Enum ───────────────────
# tiptap-vuetify의 ExtensionActionRenderInEnum, Theme 패턴에서 영감


class ToolCategory(str, Enum):
    """도구 카테고리 분류 (tiptap-vuetify의 Extension 그룹 패턴)."""

    FILE_IO = "file_io"  # 파일 읽기/쓰기
    CODE_EXEC = "code_exec"  # 코드/명령 실행
    SEARCH = "search"  # 검색/조회
    COMPUTER_USE = "computer_use"  # 데스크탑 자동화
    DATA = "data"  # 데이터베이스/API
    SECURITY = "security"  # 보안 스캔/검증
    MANAGEMENT = "management"  # 프로젝트/태스크 관리
    SYSTEM = "system"  # 시스템 명령/메모리 제어
    WEB = "web"  # 웹/비전 상호작용
    DANGEROUS = "dangerous"  # 위험/DB 마이그레이션 등
    CUSTOM = "custom"  # 사용자 정의


class RenderIn(str, Enum):
    """도구가 표시될 위치 (tiptap-vuetify의 toolbar vs bubbleMenu 패턴)."""

    TOOLBAR = "toolbar"  # 항상 노출 (주요 도구)
    CONTEXTUAL = "contextual"  # 상황에 따라 자동 선택
    BACKGROUND = "background"  # 사용자에게 비노출 (자동 실행)


class RiskLevel(str, Enum):
    """도구 위험도 등급."""

    SAFE = "safe"  # 읽기 전용, 부작용 없음
    LOW = "low"  # 경미한 부작용 (파일 쓰기)
    MEDIUM = "medium"  # 상태 변경 (DB 수정 등)
    HIGH = "high"  # 시스템 변경 (명령 실행)
    CRITICAL = "critical"  # 치명적 (삭제, 네트워크 등)


class BaseTool(ABC):
    """모든 도구(Tool)가 상속받아야 하는 기본 클래스.

    MCP 도구 및 로컬 커스텀 도구의 일관된 인터페이스를 제공합니다.

    tiptap-vuetify의 AbstractExtension 패턴을 차용하여,
    도구마다 카테고리(category), 렌더 위치(render_in), 위험도(risk_level),
    아이콘(icon) 등의 메타데이터를 선언적으로 지정할 수 있습니다.
    """

    # ── 서브클래스에서 오버라이드 가능한 메타데이터 ──
    category: ToolCategory = ToolCategory.CUSTOM
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "🔧"  # 이모지 또는 mdi 아이콘 이름
    tags: list[str] = []  # 검색/필터링용 태그

    @property
    def requires_approval(self) -> bool:
        """이 도구가 실행 전 사용자 승인이 필요한지 여부.

        Claw Code의 PermissionPolicy 패턴.
        risk_level이 MEDIUM 이상이면 기본적으로 True.
        """
        return self.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)

    def pre_execute(self, **kwargs: object) -> str | None:
        """도구 실행 전 훅. Claw Code의 pre-flight check 패턴.

        None을 반환하면 실행 진행, 문자열을 반환하면 실행 중단 + 오류 메시지.
        서브클래스에서 오버라이드하여 입력 검증, 전제 조건 확인 등에 사용.
        """
        _ = kwargs
        return None

    def post_execute(self, result: object, **kwargs: object) -> object:
        """도구 실행 후 훅. Claw Code의 result-shaping 패턴.

        결과를 가공하거나 로깅하는 데 사용.
        서브클래스에서 오버라이드 가능.
        """
        _ = kwargs
        return result

    @property
    @abstractmethod
    def name(self) -> str:
        """도구의 고유 이름."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """도구의 기능 설명 (LLM에 전달됨)."""
        pass

    @property
    @abstractmethod
    def parameters_schema(self) -> Mapping[str, object]:
        """도구 실행에 필요한 매개변수 JSON 스키마.

        예:
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
        """
        pass

    @abstractmethod
    def execute(self, **kwargs: object) -> object:
        """도구를 실제 실행하는 메서드.

        매개변수는 kwargs 형태로 전달됩니다.
        """
        pass

    def to_tool_call_schema(self) -> dict[str, object]:
        """LLM(Anthropic/OpenAI)에 전달하기 위한 도구 스키마 포맷으로 변환합니다."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters_schema,
        }

    def to_metadata(self) -> dict[str, object]:
        """UI/대시보드에 도구 정보를 표시하기 위한 메타데이터를 반환합니다.

        tiptap-vuetify의 테마/아이콘 시스템에서 착안.
        """
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "render_in": self.render_in.value,
            "risk_level": self.risk_level.value,
            "icon": self.icon,
            "tags": self.tags,
        }

    def __call__(self, **kwargs: object) -> str:
        """Claw Code 스타일 실행 파이프라인:

        pre_execute → execute → post_execute
        결과를 문자열로 반환하여 LLM에 쉽게 피드백할 수 있도록 합니다.
        """
        try:
            # Pre-flight check
            pre_error = self.pre_execute(**kwargs)
            if pre_error is not None:
                logger.warning("Pre-execute check failed for %s: %s", self.name, pre_error)
                return f"[Pre-check Failed] {pre_error}"

            # Execute
            result = self.execute(**kwargs)

            # Post-execute hook
            result = self.post_execute(result, **kwargs)

            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Error executing tool %s: %s", self.name, e, exc_info=True)
            return f"Error executing tool {self.name}: {str(e)}"
