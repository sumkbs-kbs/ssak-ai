"""Trainer Agent module."""

import logging
from typing import Final

from pydantic import JsonValue, TypeAdapter

from ..engine.model_manager import ModelManager
from ..tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)
_PROPOSAL_ADAPTER: Final[TypeAdapter[dict[str, JsonValue]]] = TypeAdapter(dict[str, JsonValue])


class TrainerAgent:
    """AGI Core: TrainerAgent (자가 학습 및 강화 훈련 에이전트).

    시스템이 부족한 도메인 지식을 보완하기 위해 오픈소스 데이터셋을 파악하고,
    동적으로 파인튜닝 스크립트(mlx_lm.lora 등)를 작성하여 자체 훈련 파이프라인을 기안합니다.
    """

    def __init__(self, model_manager: ModelManager, tool_registry: ToolRegistry) -> None:
        """Initialize the TrainerAgent.

        Args:
            model_manager (ModelManager): ModelManager model manager.
            tool_registry (ToolRegistry): ToolRegistry tool registry.

        """
        self.model_manager: ModelManager = model_manager
        self.tool_registry: ToolRegistry = tool_registry

    def propose_training(self, domain_goal: str) -> str:
        """특정 도메인에 대한 학습 제안서를 작성합니다."""
        logger.info("TrainerAgent planning fine-tuning for domain: %s", domain_goal)

        prompt = f"""You are the TrainerAgent of Ssak-Ai AGI Core.

Domain/Goal requiring reinforcement: {domain_goal}

Propose a fine-tuning or RL pipeline.
Generate ONLY a JSON response:
{{
    "dataset_url": "huggingface/...",
    "target_model": "which local model to fine-tune",
    "training_method": "LoRA / QLoRA / Full",
    "estimated_hours": 4,
    "rationale": "Why this training is necessary"
}}
"""
        try:
            response = self.model_manager.generate(prompt, target="reasoning-balanced")

            import re

            clean = response.strip()
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.DOTALL)
            if json_match:
                clean = json_match.group(1)
            else:
                start = clean.find("{")
                end = clean.rfind("}")
                if start != -1 and end != -1:
                    clean = clean[start : end + 1]
            data = _PROPOSAL_ADAPTER.validate_json(clean.strip())

            artifact_content = "# 자가 학습 훈련 기안서 (Self-Training Proposal)\n\n"
            artifact_content += f"## 📚 타겟 도메인: {domain_goal}\n"
            artifact_content += f"- **데이터셋:** {data.get('dataset_url')}\n"
            artifact_content += f"- **대상 모델:** {data.get('target_model')}\n"
            artifact_content += f"- **훈련 기법:** {data.get('training_method')}\n"
            artifact_content += f"- **예상 소요 시간:** {data.get('estimated_hours')}시간\n\n"
            artifact_content += f"### 💡 사유\n{data.get('rationale')}\n\n"

            artifact_content += "\n> [!CAUTION]\n> 이 훈련은 막대한 GPU 메모리와 시간을 소모합니다. 또한 훈련 스크립트가 로컬에 생성되어 자동으로 실행됩니다.\n> 승인(Approve)하시겠습니까?\n"  # noqa: E501

            return f"TrainerAgent가 훈련 기안서를 작성했습니다. 기안서 내용:\n\n{artifact_content}\n\n[APPROVAL REQUIRED] 사용자의 승인이 필요합니다."  # noqa: E501

        except Exception as e:
            logger.exception("Unhandled exception")
            return f"TrainerAgent failed to generate training proposal: {e}"
