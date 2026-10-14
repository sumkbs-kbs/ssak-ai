"""Scout Agent module."""

import logging
import os
import re
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError

from ..engine.model_manager import ModelManager
from ..tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)
_MEMORY_GB_PATTERN = re.compile(r"(?m)^\s*total_system_gb\s*:\s*['\"]?(?P<value>\d+(?:\.\d+)?)['\"]?\s*$")


class _ScoutAddProposal(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    name: str = ""
    repo: str = ""
    description: str = ""
    estimated_memory_gb: float = 0.0


class _ScoutResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    propose_add: _ScoutAddProposal | None = None
    propose_remove: str | None = None


class ScoutAgent:
    """AGI Core: ScoutAgent (모델 헤드헌터).

    주기적으로 또는 명시적 요청에 의해 인터넷의 최신 오픈소스 모델 동향을 파악하고,
    시스템에 적합한 모델을 영입(Download)하거나 불필요한 모델을 해고(Remove)할 것을 제안합니다.
    """

    def __init__(self, model_manager: ModelManager, tool_registry: ToolRegistry):
        """Initialize the ScoutAgent.

        Args:
            model_manager (ModelManager): ModelManager model manager.
            tool_registry (ToolRegistry): ToolRegistry tool registry.

        """
        self.model_manager: ModelManager = model_manager
        self.tool_registry: ToolRegistry = tool_registry

    def propose_model_scout(self, search_query: str) -> str:
        """웹 검색 도구를 사용하여 모델을 스카우트하고 기안서를 작성합니다.

        (시뮬레이션을 위해 프롬프트로 처리)
        """
        logger.info("ScoutAgent started searching for: %s", search_query)

        # 1. 실제로는 WebSearchTool을 내부적으로 호출하여 정보를 수집합니다.
        # 여기서는 AGI Core의 기안서 작성 로직에 집중합니다.

        prompt = f"""You are the ScoutAgent (Headhunter) of Ssak-Ai.

Search query or goal: {search_query}

Your task is to propose the addition of a new open-source model (e.g., Llama-3.2, Qwen-2.5) that fits this goal,
    and optionally propose the removal of an older model to save disk space)

Generate ONLY a JSON response in the following format:
{{
    "propose_add": {{
        "name": "model_name:latest",
        "repo": "repo/model_name",
        "description": "Why we should recruit this model",
        "estimated_memory_gb": 10
    }},
    "propose_remove": "old_model_name:latest" or null
}}
"""
        try:
            response = self.model_manager.generate(
                prompt,
                target="reasoning-balanced",
                model_id="default",
            )

            clean = response.strip()
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.DOTALL)
            if json_match:
                clean = json_match.group(1)
            else:
                start = clean.find("{")
                end = clean.rfind("}")
                if start != -1 and end != -1:
                    clean = clean[start : end + 1]
            data = _ScoutResponse.model_validate_json(clean.strip())

            # Check Memory Constraints
            if data.propose_add is not None:
                proposal = data.propose_add
                required_mem = proposal.estimated_memory_gb
                config_path = os.path.join(os.getcwd(), "config.yaml")
                sys_total_mem = 128.0
                if os.path.exists(config_path):
                    with open(config_path, encoding="utf-8") as f:
                        memory_match = _MEMORY_GB_PATTERN.search(f.read())
                        if memory_match:
                            sys_total_mem = float(memory_match.group("value"))

                if required_mem > sys_total_mem * 0.8:  # If required is more than 80% of total system RAM
                    from .hardware_analyst import HardwareAnalystAgent

                    analyst = HardwareAnalystAgent(self.model_manager)
                    hw_report = analyst.propose_upgrade(proposal.name, required_mem)
                    return f"⚠️ **ScoutAgent가 초거대 모델을 발견했으나 하드웨어 한계에 부딪혔습니다.**\n\n{hw_report}"

            # 2. 기안서(Artifact) 작성 및 승인 대기 (Approval Gate)
            artifact_content = "# 모델 영입 기안서 (Model Recruitment Proposal)\n\n"
            if data.propose_add is not None:
                proposal = data.propose_add
                artifact_content += f"## 🌟 영입 제안: {proposal.name}\n"
                artifact_content += f"- **저장소:** {proposal.repo}\n"
                artifact_content += f"- **예상 메모리:** {proposal.estimated_memory_gb} GB\n"
                artifact_content += f"- **사유:** {proposal.description}\n\n"

            if data.propose_remove:
                artifact_content += f"## 🗑 해고 제안: {data.propose_remove}\n"
                artifact_content += "- **사유:** 디스크 및 메모리 최적화를 위해 제거합니다.\n\n"

            artifact_content += "\n> [!CAUTION]\n> 이 기안서를 승인(Approve)하시면, 시스템이 백그라운드에서 기가바이트 단위의 모델 다운로드 및 삭제를 진행하며 `config.yaml`"  # noqa: E501
            "코어를 수정합니다. 승인하시겠습니까?\n"

            return f"ScoutAgent가 인터넷을 분석하여 모델 영입 기안서를 작성했습니다. 기안서 내용:\n\n{artifact_content}\n\n[APPROVAL REQUIRED] 사용자의 승인이 필요합니다. 승인 시 Auto-Roster Manager가 작동합니다."

        except (OSError, RuntimeError, TypeError, ValueError, ValidationError) as e:
            logger.exception("Unhandled exception")
            return f"ScoutAgent failed to generate proposal: {e}"
