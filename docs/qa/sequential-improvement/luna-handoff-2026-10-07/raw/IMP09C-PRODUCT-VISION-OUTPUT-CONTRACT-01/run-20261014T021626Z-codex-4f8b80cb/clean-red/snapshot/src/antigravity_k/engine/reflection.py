"""Self-reflection engine for post-action quality assessment."""

import ast
import logging
import os
import subprocess
import uuid
from datetime import datetime
from typing import Final

from pydantic import JsonValue, TypeAdapter, ValidationError

from .knowledge import KIEngine
from .model_manager import ModelManager

logger = logging.getLogger(__name__)
_REFLECTION_JSON_ADAPTER: Final[TypeAdapter[dict[str, JsonValue]]] = TypeAdapter(dict[str, JsonValue])


class ReflectionAgent:
    """ECA (Evolutionary Cognitive Architecture)의 핵심 컴포넌트입니다.

    작업(Task)이 완료되면 Git Diff와 대화 내역을 바탕으로 스스로 학습(Reflection)하고,
    KIs (지식)를 추출하거나 새로운 파이썬 스킬(Auto-Skill)을 합성합니다.
    """

    def __init__(self, project_root: str, model_manager: ModelManager) -> None:
        """Initialize the ReflectionAgent.

        Args:
            project_root (str): str project root.
            model_manager (ModelManager): ModelManager model manager.

        """
        self.project_root: str = project_root
        self.model_manager: ModelManager = model_manager
        self.ki_engine: KIEngine = KIEngine(project_root)

    def reflect_on_task(self, task_id: str, worktree_path: str, task_desc: str) -> None:
        """태스크 완료 시 자동 회고를 수행하고 지식/스킬을 추출합니다."""
        logger.info("Starting auto-reflection for task %s", task_id)

        # 1. 변경된 코드 파악 (간단한 git diff 래핑 로직)
        diff_output = ""
        commit_hash = "unknown"
        try:
            if os.path.exists(worktree_path):
                res = subprocess.run(
                    ["git", "diff", "HEAD"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                )
                diff_output = res.stdout[:3000]  # truncate to save tokens

                res_hash = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                )
                commit_hash = res_hash.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            logger.exception("Failed to get git diff for reflection")

        if not diff_output:
            logger.info("No diff found. Skipping reflection.")
            return

        # 2. 메타 인지 프롬프트 구성
        prompt = f"""You are the ECA (Evolutionary Cognitive Architecture) Reflection Agent for Ssak-Ai.

A task has just been completed. Your job is to extract long-term architectural knowledge or identify repetitive skills.

Task Description: {task_desc}

Git Diff:
{diff_output}

Based on this, return ONLY a JSON object:
{{
    "learned_knowledge": {{
        "title": "...",
        "summary": "...",
        "target_files": ["..."]
    }},
    "propose_auto_skill": false,
    "skill_description": "If propose_auto_skill is true, describe the python tool to be generated."
}}
"""

        try:
            response = self.model_manager.generate(
                prompt,
                target="reasoning-balanced",
                model_id="default",
            )

            import re

            clean_json = response.strip()
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_json, re.DOTALL)
            if json_match:
                clean_json = json_match.group(1)
            else:
                start = clean_json.find("{")
                end = clean_json.rfind("}")
                if start != -1 and end != -1:
                    clean_json = clean_json[start : end + 1]
            data = _REFLECTION_JSON_ADAPTER.validate_json(clean_json.strip())

            # 3. KIs 저장 (Code-Anchored Knowledge)
            learned_knowledge = data.get("learned_knowledge")
            if isinstance(learned_knowledge, dict):
                title = learned_knowledge.get("title")
                summary = learned_knowledge.get("summary")
                target_files = learned_knowledge.get("target_files")
            else:
                title = None
                summary = None
                target_files = None

            if isinstance(title, str) and title:
                ki_id = f"ki_{uuid.uuid4().hex[:8]}"
                target_file_names = (
                    [item for item in target_files if isinstance(item, str)] if isinstance(target_files, list) else []
                )
                ki_data = {
                    "id": ki_id,
                    "title": title,
                    "summary": summary if isinstance(summary, str) else "",
                    "target_files": target_file_names,
                    "commit_hash": commit_hash,
                    "created_at": datetime.now().isoformat(),
                    "task_id": task_id,
                }
                self.ki_engine.save_ki(ki_id, ki_data)

            # 4. Auto-Skill Synthesis Trigger
            skill_description = data.get("skill_description")
            if data.get("propose_auto_skill") is True and isinstance(skill_description, str) and skill_description:
                self._synthesize_skill(skill_description)

        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError, ValidationError):
            logger.exception("Reflection failed or returned invalid JSON")

    def _synthesize_skill(self, desc: str) -> None:
        """자동으로 새로운 도구(BaseTool) 파이썬 스크립트를 합성합니다."""
        logger.info("Synthesizing new auto-skill based on: %s", desc)

        prompt = f"""You are the ECA (Evolutionary Cognitive Architecture) Skill Synthesizer.

Based on the following skill description, write a Python class that inherits
from `BaseTool` (from .base_tool import BaseTool,
    ToolCategory, RenderIn, RiskLevel))

The tool should implement the `execute(self, **kwargs)` method and return a string.

Skill Description: {desc}

Return ONLY valid Python code inside a ```python ``` block. No markdown explanations.
Ensure the class name is descriptive and ends with `Tool` (e.g. `RegexParserTool`).
Do not use undefined variables. Handle exceptions safely.
"""
        try:
            response = self.model_manager.generate(
                prompt,
                target="reasoning-balanced",
                model_id="default",
            )
            code = response.strip()
            if code.startswith("```python"):
                code = code[9:]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()

            if "class " in code and "(BaseTool):" in code:
                # 안전장치: AST 구문 검증 — 구문 오류 코드가 tools/에 저장되면
                # 다음 세션에서 importlib 동적 임포트 시 전체 도구 등록이 실패함
                try:
                    _ = ast.parse(code)
                except SyntaxError as e:
                    logger.warning("[ReflectionAgent] Auto-skill syntax error, NOT saving: %s", e)
                    return

                skill_id = uuid.uuid4().hex[:6]
                file_path = os.path.join(
                    self.project_root,
                    "src",
                    "antigravity_k",
                    "tools",
                    f"auto_skill_{skill_id}.py",
                )

                with open(file_path, "w", encoding="utf-8") as f:
                    _ = f.write(code)

                logger.info("Successfully synthesized and saved new skill to %s", file_path)
            else:
                logger.warning("Synthesized skill code is invalid or missing BaseTool inheritance.")
        except (AttributeError, OSError, RuntimeError, SyntaxError, TypeError, ValueError):
            logger.exception("Failed to synthesize skill")
