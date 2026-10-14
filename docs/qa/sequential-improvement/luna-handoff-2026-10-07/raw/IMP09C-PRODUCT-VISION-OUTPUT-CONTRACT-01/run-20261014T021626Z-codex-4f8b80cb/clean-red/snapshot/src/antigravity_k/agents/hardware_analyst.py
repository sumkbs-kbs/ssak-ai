"""Hardware Analyst module."""

import json
import logging
import platform
from typing import Final

import psutil
from pydantic import JsonValue, TypeAdapter, ValidationError

from ..engine.model_manager import ModelManager

logger = logging.getLogger(__name__)
_PROPOSAL_ADAPTER: Final[TypeAdapter[dict[str, JsonValue]]] = TypeAdapter(dict[str, JsonValue])


class HardwareAnalystAgent:
    """AGI Core: Hardware Analyst Agent (인프라 진단 및 장비 기안 에이전트).

    시스템의 현재 하드웨어 자원을 분석하고, 필요한 초거대 모델을 실행하기 위한
    물리적 한계를 계산하여 사용자에게 정식 '하드웨어 업그레이드 기안서'를 작성합니다.
    """

    def __init__(self, model_manager: ModelManager) -> None:
        """Initialize the HardwareAnalystAgent.

        Args:
            model_manager (ModelManager): ModelManager model manager.

        """
        self.model_manager: ModelManager = model_manager

    def _get_system_specs(self) -> dict[str, object]:
        """현재 시스템의 물리적 스펙을 수집합니다."""
        memory = psutil.virtual_memory()
        total_bytes = getattr(memory, "total", 0)
        available_bytes = getattr(memory, "available", 0)
        total_ram_gb = round(total_bytes / (1024**3), 2) if isinstance(total_bytes, (int, float)) else 0.0
        available_ram_gb = round(available_bytes / (1024**3), 2) if isinstance(available_bytes, (int, float)) else 0.0
        specs: dict[str, object] = {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "cpu_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "total_ram_gb": total_ram_gb,
            "available_ram_gb": available_ram_gb,
        }
        return specs

    def propose_upgrade(self, target_model_name: str, required_memory_gb: float) -> str:
        """특정 모델을 영입하기 위해 필요한 하드웨어 업그레이드 기안서를 작성합니다."""
        logger.info(
            "HardwareAnalystAgent generating upgrade proposal for %s (%sGB needed)",
            target_model_name,
            required_memory_gb,
        )

        sys_specs = self._get_system_specs()

        prompt = f"""You are the Hardware Analyst Agent of Ssak-Ai.

The ScoutAgent found a highly advanced AI model ('{target_model_name}') that requires
{required_memory_gb}GB of memory to run efficiently.
However, our current hardware specifications are:
- OS: {sys_specs["os"]} {sys_specs["architecture"]}
- CPU Cores: {sys_specs["cpu_cores"]}
- Total RAM: {sys_specs["total_ram_gb"]} GB
- Available RAM: {sys_specs["available_ram_gb"]} GB

Write a formal, persuasive Hardware Upgrade Proposal for the human user.
Format as ONLY a JSON object:
{{
    "title": "Hardware Upgrade Proposal for ...",
    "current_bottleneck": "Explanation of why current hardware cannot handle it",
    "target_capabilities": "What the new model will allow us to do (ROI)",
    "recommended_hardware": "Specific hardware recommendation (e.g., Mac Studio M4 Ultra 192GB RAM)",
    "roi_justification": "Why this investment is worth it in terms of developer hours saved"
}}
"""
        response = ""
        try:
            response = self.model_manager.generate(
                prompt,
                target="reasoning-balanced",
                model_id="default",
            )

            if response.startswith("[API Error"):
                logger.error("HardwareAnalystAgent received API error: %s", response)
                # Fallback proposal when API fails
                data: dict[str, JsonValue] = {
                    "current_bottleneck": "시스템 인프라 또는 외부 API 연동 오류 발생",
                    "target_capabilities": "API 복구 및 안정적인 모델 구동",
                    "recommended_hardware": "API 서비스 점검 및 로컬 모델(llama4 등) 가용성 확인",
                    "roi_justification": "API 정상화를 통한 파이프라인 신뢰성 회복",
                }
            else:
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

                if not clean.strip() or (clean.find("{") == -1):
                    raise ValueError(
                        f"모델이 올바른 JSON 형식을 반환하지 않았습니다: {response[:100]}...",
                    )

                data = _PROPOSAL_ADAPTER.validate_json(clean.strip())

            artifact_content = "# 인프라 업그레이드 기안서 (Hardware Evolution Proposal)\n\n"
            artifact_content += f"## 🖥 현재 신체 진단 (Current Bottleneck)\n{data.get('current_bottleneck')}\n\n"
            artifact_content += f"## 🎯 목표 지능 (Target Capabilities)\n{data.get('target_capabilities')}\n\n"
            artifact_content += (
                f"## 💡 장비 업그레이드 제안 (Recommendation)\n**{data.get('recommended_hardware')}**\n\n"
            )
            artifact_content += f"## 📈 투자 대비 효과 (ROI Analysis)\n{data.get('roi_justification')}\n\n"

            artifact_content += "\n> [!TIP]\n> 이 제안서는 시스템 스스로 자신의 물리적 한계를 인지하고 돌파하기 위해 작성한 메타-인지(Meta-Cognitive) 보고서입니다. 장비 업그레이드가"  # noqa: E501
            "완료되면 `config.yaml`의 메모리 제한을 해제해 주십시오.\n"

            return (
                f"HardwareAnalystAgent가 시스템의 한계를 분석하여 인프라 투자 기안서를"
                f" 작성했습니다. 보고서 내용:\n\n{artifact_content}\n\n사용자님, 시스템의"
                "지능을 더 확장하시려면 이 제안을 고려해 주십시오."
            )

        except (json.JSONDecodeError, ValidationError) as e:
            return f"HardwareAnalystAgent failed to parse JSON proposal: {e}\nRaw output: {response[:200]}"
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"HardwareAnalystAgent failed to generate proposal: {e}"
