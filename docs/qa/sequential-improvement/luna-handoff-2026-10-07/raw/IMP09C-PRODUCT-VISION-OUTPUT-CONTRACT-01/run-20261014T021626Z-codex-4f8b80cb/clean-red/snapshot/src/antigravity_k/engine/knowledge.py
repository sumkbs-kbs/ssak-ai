"""Knowledge base management and retrieval utilities."""

import json
import logging
import os
from collections.abc import Mapping
from typing import Final, TypeVar

from pydantic import TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

# persistent_context 주입 상한(문자). KI가 누적될수록 매 요청 비용이
# 선형 증가하는 것을 막는다 — 최신 KI 우선으로 예산 내에서만 포함한다.
type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]
type JsonMap = dict[str, JsonValue]

MAX_KI_PROMPT_CHARS: Final[int] = 4000
_JSON_MAP_ADAPTER: Final[TypeAdapter[JsonMap]] = TypeAdapter(JsonMap)
_JsonInput = TypeVar("_JsonInput")


class KIEngine:
    """Knowledge Items (KIs) 시스템.

    이전 대화의 지식 구조화 및 패턴을 `.antigravity/knowledge/` 내부에 저장하고,
    에이전트가 호출될 때 로컬 맥락(KIs)을 시스템 프롬프트에 자동으로 주입합니다.
    (Tolaria Advanced Agentic Architecture 패리티)
    """

    def __init__(self, project_root: str) -> None:
        """Initialize the KIEngine.

        Args:
            project_root (str): str project root.

        """
        self.project_root: str = project_root
        self.ki_dir: str = os.path.join(project_root, ".antigravity", "knowledge")

    def ensure_dir(self) -> None:
        """Ensure Dir."""
        os.makedirs(self.ki_dir, exist_ok=True)

    def load_kis(self) -> list[JsonMap]:
        """Load kis.

        Returns:
            list[dict[str, Any]]: The list[dict[str, any]] result.

        """
        self.ensure_dir()
        kis: list[JsonMap] = []
        for file in os.listdir(self.ki_dir):
            if file.endswith("metadata.json"):
                try:
                    path = os.path.join(self.ki_dir, file)
                    with open(path, encoding="utf-8") as f:
                        entry = _JSON_MAP_ADAPTER.validate_json(f.read())
                    try:
                        entry["_mtime"] = os.path.getmtime(path)
                    except OSError:
                        entry["_mtime"] = 0.0
                    kis.append(entry)
                except (OSError, UnicodeError, ValidationError, json.JSONDecodeError):
                    logger.exception("Failed to load KI %s", file)
        return kis

    def save_ki(self, ki_id: str, data: Mapping[str, _JsonInput]) -> None:
        """새로운 지식(KI)을 JSON 파일로 저장합니다."""
        self.ensure_dir()
        file_path = os.path.join(self.ki_dir, f"{ki_id}_metadata.json")
        try:
            validated = _JSON_MAP_ADAPTER.validate_python(dict(data))
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(validated, f, ensure_ascii=False, indent=2)
            logger.info("Saved new KI: %s", ki_id)
        except (OSError, TypeError, ValueError, ValidationError):
            logger.exception("Failed to save KI %s", ki_id)

    def build_ki_prompt(self) -> str:
        """KIs 정보를 읽어 에이전트용 시스템 프롬프트 주입 텍스트를 생성합니다.

        최신 KI 우선으로 MAX_KI_PROMPT_CHARS 예산 내에서만 포함합니다.
        """
        kis = self.load_kis()
        if not kis:
            return ""

        ordered = sorted(kis, key=_ki_mtime, reverse=True)

        prompt = "\n\n<persistent_context>\n# Knowledge Items (KIs)\n"
        prompt += "다음은 이전에 요약된 지식 구조(KIs)입니다. 기존에 확립된 패턴을 유지하고 중복 작업을 방지하세요.\n\n"

        included = 0
        skipped = 0
        for ki in ordered:
            block = self._render_ki_block(ki)
            if included > 0 and len(prompt) + len(block) > MAX_KI_PROMPT_CHARS:
                skipped += 1
                continue
            # 첫 KI는 예산을 넘어도 항상 포함 (빈 지식 주입 방지)
            if included == 0 and len(prompt) + len(block) > MAX_KI_PROMPT_CHARS:
                block = block[: MAX_KI_PROMPT_CHARS - len(prompt)] + "\n\n"
            prompt += block
            included += 1

        if skipped:
            prompt += f"_(오래된 KI {skipped}개는 예산 초과로 생략됨)_\n\n"

        prompt += "</persistent_context>\n"
        return prompt

    @staticmethod
    def _render_ki_block(ki: Mapping[str, JsonValue]) -> str:
        """단일 KI를 프롬프트 블록 문자열로 렌더링합니다."""
        title_value = ki.get("title")
        title = title_value if isinstance(title_value, str) else "Untitled KI"
        summary_value = ki.get("summary")
        summary = summary_value if isinstance(summary_value, str) else ""
        artifacts_value = ki.get("artifacts")
        artifacts = (
            [artifact for artifact in artifacts_value if isinstance(artifact, str)]
            if isinstance(artifacts_value, list)
            else []
        )

        block = f"## {title}\n"
        commit_hash = ki.get("commit_hash")
        if commit_hash:
            block += f"*(Anchored to Commit: {commit_hash})*\n"
        block += f"{summary}\n"
        if artifacts:
            block += "Related Artifacts: " + ", ".join(artifacts) + "\n"
        return block + "\n"


def _ki_mtime(ki: Mapping[str, JsonValue]) -> float:
    value = ki.get("_mtime")
    return float(value) if isinstance(value, int | float) else 0.0
