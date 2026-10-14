"""Ssak-Ai: 스킬 자동 생성기 (Skill Generator).

==================================================
에이전트가 새로운 도구(auto_skill)를 자동으로 생성하는 메타-도구입니다.

워크플로우:
  1. LLM이 BaseTool 서브클래스 코드를 자동 생성
  2. AST 파싱 검증 → _drafts/auto_skills/ 저장
  3. 사용자 승인 시 tools/auto_skill_*.py로 이동
  4. ToolExecutor._load_auto_skills()가 런타임에 핫 로드
"""

import ast
import json
import logging
import os
import re
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol, TypedDict, cast

from antigravity_k.config import config
from antigravity_k.tools.egress_policy import safe_urlopen

logger = logging.getLogger(__name__)

JsonObject = dict[str, object]


class _ModelManagerLike(Protocol):
    def get_target_for_role(self, role_name: str, *, default_role: str = "code") -> str: ...

    def generate(
        self,
        prompt: str,
        target: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> object: ...


class SkillResult(TypedDict, total=False):
    success: bool
    file_path: str
    class_name: str
    tool_name: str
    message: str


def _as_json_map(value: object) -> JsonObject:
    return cast(JsonObject, value) if isinstance(value, dict) else {}


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


# BaseTool 코드 생성용 템플릿
_SKILL_TEMPLATE = '''"""
Auto-generated skill: {skill_name}

Generated at: {timestamp}
Goal: {goal}
"""
import logging
from typing import Any, Dict
from antigravity_k.tools.base_tool import BaseTool, ToolCategory, RenderIn, RiskLevel

logger = logging.getLogger(__name__)


class {class_name}(BaseTool):
    """{description}"""

    category = ToolCategory.CODE_EXEC
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.MEDIUM
    icon = "🔧"
    tags = {tags}

    def __init__(self):
        super().__init__()
        self._name = "{tool_name}"
        self._description = "{description}"
        self._schema = {{
            "type": "object",
            "properties": {properties},
            "required": {required}
        }}

    @property
    def name(self) -> str: return self._name
    @property
    def description(self) -> str: return self._description
    @property
    def parameters_schema(self) -> Dict[str, Any]: return self._schema

    def execute(self, **kwargs) -> Any:
{execute_body}
'''


class SkillGenerator:
    """에이전트가 필요로 하는 새로운 도구를 자동으로 생성하고,.

    안전한 승인 프로세스를 거쳐 시스템에 통합합니다.
    """

    def __init__(self, project_root: str = ".", model_manager: object | None = None):
        """Initialize the SkillGenerator.

        Args:
            project_root (str): str project root.
            model_manager: model manager.

        """
        self.project_root: str = project_root
        self.manager: _ModelManagerLike | None = (
            cast(_ModelManagerLike, model_manager) if model_manager is not None else None
        )
        self._drafts_dir: str = os.path.join(project_root, "_drafts", "auto_skills")
        self._tools_dir: str = os.path.join(project_root, "src", "antigravity_k", "tools")

    def _generation_target(self) -> str:
        configured = os.environ.get("AGK_SKILL_GENERATION_MODEL", "").strip()
        if configured:
            return configured

        if self.manager is not None:
            resolver = getattr(self.manager, "get_target_for_role", None)
            if callable(resolver):
                try:
                    target = resolver("skill_generator", default_role="code")
                    if isinstance(target, str) and target.strip():
                        return target.strip()
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    logger.warning("[SkillGen] Failed to resolve a managed model target", exc_info=True)

        return config.model.code_model or config.model.main_model

    def _generate_with_manager(self, prompt: str, *, max_tokens: int, temperature: float) -> str | None:
        if self.manager is None:
            return None
        generate = getattr(self.manager, "generate", None)
        if not callable(generate):
            return None
        try:
            response = generate(
                prompt,
                self._generation_target(),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            logger.warning("[SkillGen] Managed model generation failed; using configured API fallback", exc_info=True)
            return None
        return response if isinstance(response, str) else None

    @staticmethod
    def _extract_json(text: str) -> JsonObject | None:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch == "{":
                try:
                    obj = cast(object, decoder.raw_decode(text, i)[0])
                    if isinstance(obj, dict):
                        return _as_json_map(cast(object, obj))
                except json.JSONDecodeError:
                    continue
        return None

    def generate_skill(self, requirement: str) -> SkillResult:
        """요구사항을 분석하여 새로운 BaseTool 서브클래스를 생성합니다.

        Args:
            requirement: 어떤 도구가 필요한지 자연어로 설명

        Returns:
            dict with keys: success, file_path, class_name, tool_name, message

        """
        try:
            # 1. LLM으로 도구 스펙 생성
            spec = self._generate_spec(requirement)
            if not spec:
                return {
                    "success": False,
                    "message": "Failed to generate tool specification from LLM",
                }

            # 2. 코드 생성
            code = self._render_code(spec)

            # 3. AST 검증
            try:
                _ = ast.parse(code)
            except SyntaxError as e:
                return {"success": False, "message": f"Generated code has syntax error: {e}"}

            # 4. _drafts/에 저장 (HITL 패턴)
            os.makedirs(self._drafts_dir, exist_ok=True)
            tool_name = _as_text(spec.get("tool_name"), "auto_tool")
            class_name = _as_text(spec.get("class_name"), "AutoGeneratedTool")
            filename = f"auto_skill_{tool_name}.py"
            draft_path = os.path.join(self._drafts_dir, filename)

            with open(draft_path, "w", encoding="utf-8") as f:
                _ = f.write(code)

            # 메타데이터 저장
            meta_path = draft_path + ".meta.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "requirement": requirement,
                        "spec": spec,
                        "generated_at": datetime.now(UTC).isoformat(),
                        "status": "pending_review",
                        "file": filename,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            return {
                "success": True,
                "file_path": draft_path,
                "class_name": class_name,
                "tool_name": tool_name,
                "message": (
                    f"✅ 새 도구 '{tool_name}' 코드가 생성되었습니다.\n"
                    f"📁 위치: {draft_path}\n"
                    f"⚠️ 사용자 승인 후 tools/ 디렉토리로 이동됩니다.\n"
                    f"'/approve_skill {tool_name}' 명령으로 승인할 수 있습니다."
                ),
            }
        except Exception as e:
            logger.exception("Skill generation failed")
            return {"success": False, "message": f"Generation error: {e}"}

    def approve_skill(self, tool_name: str) -> SkillResult:
        """승인된 스킬을 tools/ 디렉토리로 이동하여 활성화합니다."""
        filename = f"auto_skill_{tool_name}.py"
        draft_path = os.path.join(self._drafts_dir, filename)
        target_path = os.path.join(self._tools_dir, filename)

        if not os.path.exists(draft_path):
            return {"success": False, "message": f"Draft not found: {draft_path}"}

        # 최종 AST 검증
        try:
            with open(draft_path, encoding="utf-8") as f:
                code = f.read()
            _ = ast.parse(code)
        except SyntaxError as e:
            return {"success": False, "message": f"Code has syntax error: {e}"}

        # 이동
        import shutil

        os.makedirs(self._tools_dir, exist_ok=True)
        _ = shutil.move(draft_path, target_path)

        # 메타데이터 업데이트
        meta_path = os.path.join(self._drafts_dir, filename + ".meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    meta = _as_json_map(cast(object, json.load(f)))
                meta["status"] = "approved"
                meta["approved_at"] = datetime.now(UTC).isoformat()
                target_meta = target_path + ".meta.json"
                with open(target_meta, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                os.remove(meta_path)
            except Exception:
                logger.exception("Unhandled exception")

        return {
            "success": True,
            "message": (f"✅ 스킬 '{tool_name}' 승인 완료!\n📁 {target_path}\n🔄 다음 요청부터 자동 로드됩니다."),
        }

    def list_pending(self) -> list[JsonObject]:
        """승인 대기 중인 스킬 목록을 반환합니다."""
        if not os.path.exists(self._drafts_dir):
            return []

        pending: list[JsonObject] = []
        for f in os.listdir(self._drafts_dir):
            if f.endswith(".meta.json"):
                try:
                    with open(os.path.join(self._drafts_dir, f)) as fh:
                        meta = _as_json_map(cast(object, json.load(fh)))
                    if meta.get("status") == "pending_review":
                        pending.append(meta)
                except Exception:
                    logger.exception("Unhandled exception")
        return pending

    def _generate_spec(self, requirement: str) -> JsonObject | None:
        """LLM에게 도구 스펙 생성을 요청합니다."""
        prompt = (
            "You are a tool specification generator for the Ssak-Ai AI agent framework.\n"
            "Given a requirement, generate a JSON specification for a new tool.\n\n"
            f"Requirement: {requirement}\n\n"
            "Return ONLY a JSON object with these fields:\n"
            "- tool_name: snake_case name (e.g., 'url_shortener')\n"
            "- class_name: PascalCase class name (e.g., 'UrlShortenerTool')\n"
            "- description: one-line description\n"
            "- tags: list of tags\n"
            "- properties: JSON Schema properties object\n"
            "- required: list of required parameter names\n"
            "- execute_body: Python code for the execute method body (indented with 8 spaces)\n\n"
            "The execute method receives kwargs. Use standard library only.\n"
            "Return ONLY the JSON, no markdown."
        )

        try:
            text = self._generate_with_manager(prompt, max_tokens=1024, temperature=0.4)
            if text is None:
                data = {
                    "model": self._generation_target(),
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 1024, "temperature": 0.4},
                }
                req = urllib.request.Request(
                    f"{config.model.api_base.replace('/v1', '').rstrip('/')}/api/generate",
                    data=json.dumps(data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with safe_urlopen(req, timeout=60) as resp:
                    result = _as_json_map(cast(object, json.loads(resp.read().decode("utf-8"))))
                    text = _as_text(result.get("response"))

            obj = self._extract_json(text)
            if isinstance(obj, dict) and "tool_name" in obj:
                return obj

            logger.warning("[SkillGen] No valid JSON in LLM response")
            return None

        except Exception:
            logger.exception("[SkillGen] LLM spec generation failed")
            return None

    def _render_code(self, spec: Mapping[str, object]) -> str:
        """스펙 딕셔너리를 Python 코드로 렌더링합니다."""
        execute_body = _as_text(spec.get("execute_body"), "        return 'Not implemented'")

        # execute_body 들여쓰기 정규화
        lines: list[str] = execute_body.split("\n")
        normalized: list[str] = []
        for line in lines:
            stripped = line.lstrip()
            if stripped:
                normalized.append("        " + stripped)
            else:
                normalized.append("")
        execute_body = "\n".join(normalized) if normalized else "        return 'Not implemented'"

        return _SKILL_TEMPLATE.format(
            skill_name=spec.get("tool_name", "unknown"),
            timestamp=datetime.now(UTC).isoformat(),
            goal=spec.get("description", ""),
            class_name=spec.get("class_name", "AutoGeneratedTool"),
            description=spec.get("description", "Auto-generated tool"),
            tags=json.dumps(spec.get("tags", ["auto"]), ensure_ascii=False),
            tool_name=spec.get("tool_name", "auto_tool"),
            properties=json.dumps(spec.get("properties", {}), ensure_ascii=False, indent=12),
            required=json.dumps(spec.get("required", []), ensure_ascii=False),
            execute_body=execute_body,
        )
