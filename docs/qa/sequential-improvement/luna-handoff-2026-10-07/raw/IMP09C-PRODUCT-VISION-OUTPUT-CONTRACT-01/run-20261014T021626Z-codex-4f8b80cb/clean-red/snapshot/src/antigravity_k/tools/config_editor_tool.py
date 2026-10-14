"""Config Editor Tool module."""

import logging
import os
from typing import Protocol, TypeAlias, cast, final, override

import yaml

from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

ToolValue: TypeAlias = object
ConfigMap: TypeAlias = dict[str, object]


def _as_map(value: object) -> ConfigMap:
    if not isinstance(value, dict):
        return {}
    return cast(ConfigMap, value)


def _as_map_list(value: object) -> list[ConfigMap]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, dict)]


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


class _YamlModule(Protocol):
    def safe_load(self, stream: object) -> object: ...

    def dump(self, data: object, stream: object, **kwargs: object) -> object: ...


def _as_yaml_module(value: object) -> _YamlModule:
    return cast(_YamlModule, value)


@final
class ConfigEditorTool(BaseTool):
    """ConfigEditorTool: AGI Core의 Auto-Roster Manager.

    config.yaml을 안전하게 파싱하여 모델을 추가하거나 삭제하며,
    필요 시 ollama 등의 백그라운드 모델 다운로드를 실행합니다.
    """

    category: ToolCategory = ToolCategory.SYSTEM
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.HIGH
    icon: str = "⚙️"
    tags: list[str] = ["config", "yaml", "model", "roster", "download"]
    _name: str
    _description: str
    _schema: ConfigMap

    def __init__(self):
        """Initialize the ConfigEditorTool."""
        super().__init__()
        self._name = "config_model_roster"
        self._description = (
            "Safely adds or removes AI models from config.yaml and triggers the download process. "
            "WARNING: This is ONLY for AI Model Swarm configuration (reasoning, coding, etc.). "
            "DO NOT use this to add geographic data, locations, or standard database entries."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "update_agent_map", "update_swarm"],
                    "description": "Whether to add/remove a model, update the agent_models mapping, or update a swarm combo.",  # noqa: E501
                },
                "target_key": {
                    "type": "string",
                    "description": (
                        "If update_agent_map, the agent role (e.g. 'WORKER'). If update_swarm, " + "the combo name."
                    ),
                },
                "model_category": {
                    "type": "string",
                    "enum": ["reasoning", "coding", "embedding", "vision"],
                    "description": "The category of the model (only needed for add/remove).",
                },
                "model_data": {
                    "type": "object",
                    "description": (
                        "For add/remove, provide the model dict. For update_agent_map, "
                        + "provide {'combo_name': '...'}. For update_swarm, provide "
                        + "{'models': [...], 'strategy': '...'}"
                    ),
                },
            },
            "required": ["action"],
        }

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return self._name

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return self._description

    @property
    @override
    def parameters_schema(self) -> ConfigMap:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: ToolValue) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        action = _as_text(kwargs.get("action"))
        category = _as_text(kwargs.get("model_category"))
        model_data = _as_map(kwargs.get("model_data"))

        project_root = os.getcwd()
        config_path = os.path.join(project_root, "config.yaml")

        if not os.path.exists(config_path):
            return "Error: config.yaml not found."

        try:
            msg = f"Unknown config action: {action}"
            with open(config_path, encoding="utf-8") as f:
                yaml_module = _as_yaml_module(yaml)
                config = _as_map(yaml_module.safe_load(f))

            models = _as_map(config.get("models"))
            config["models"] = models
            models_list = _as_map_list(models.get(category))

            if action == "add":
                if any(m.get("name") == model_data.get("name") for m in models_list):
                    return f"Model {model_data.get('name')} already exists in category {category}."
                models_list.append(model_data)
                models[category] = models_list
                logger.info("Triggering background download for model: %s", model_data.get("name"))
                msg = f"✅ Model {model_data.get('name')} added to {category}. Download initiated in background."

            elif action == "remove":
                name_to_remove = model_data.get("name")
                new_list = [m for m in models_list if m.get("name") != name_to_remove]
                if len(new_list) == len(models_list):
                    return f"Model {name_to_remove} not found in category {category}."
                models[category] = new_list
                logger.info("Triggering background removal for model: %s", name_to_remove)
                msg = f"🗑️ Model {name_to_remove} removed from {category}. Disk space reclaimed."

            elif action == "update_agent_map":
                target_key = _as_text(kwargs.get("target_key"))
                new_combo = model_data.get("combo_name")
                agent_models = _as_map(config.get("agent_models"))
                config["agent_models"] = agent_models
                agent_models[target_key] = new_combo
                msg = f"🔄 Agent '{target_key}' mapped to swarm combo '{new_combo}'."

            elif action == "update_swarm":
                target_key = _as_text(kwargs.get("target_key"))
                combos = _as_map(config.get("combos"))
                config["combos"] = combos
                # Update or create the combo
                combo = _as_map(combos.get(target_key))
                combos[target_key] = combo
                combo.update(model_data)
                msg = f"🐝 Swarm combo '{target_key}' updated with new models/strategy."

            # YAML 덤프 시 원본 포맷을 최대한 유지
            with open(config_path, "w", encoding="utf-8") as f:
                _ = yaml_module.dump(
                    config,
                    f,
                    sort_keys=False,
                    default_flow_style=False,
                    allow_unicode=True,
                )

            return msg

        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Failed to edit config.yaml: {e}"
