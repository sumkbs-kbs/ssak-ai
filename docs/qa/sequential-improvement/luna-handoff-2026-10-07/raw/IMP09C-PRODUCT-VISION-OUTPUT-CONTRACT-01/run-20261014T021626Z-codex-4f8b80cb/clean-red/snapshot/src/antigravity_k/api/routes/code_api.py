"""Code Intelligence API — Inline code editing suggestions.

Provides an endpoint for generating inline code suggestions
when the user invokes Ctrl+K (Cursor-style inline edit).
"""

import json
import logging
from typing import ClassVar, TypeVar

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

logger = logging.getLogger("antigravity_k.api.code_api")
router = APIRouter()
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class _InlineSuggestRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    language: StrictStr = "python"
    original_code: StrictStr = ""
    instruction: StrictStr = ""
    cursor_line: StrictInt = Field(default=1, ge=1)
    cursor_column: StrictInt = Field(default=0, ge=0)


async def _parse_json_body(request: Request, model: type[_ModelT]) -> _ModelT:
    try:
        return model.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc


@router.post("/api/code/inline-suggest")
async def inline_suggest(request: Request):
    """Generate an inline code suggestion based on user instruction.

    Invoked when user presses Ctrl+K in the editor, types an instruction,
    and presses Enter. The backend returns a suggestion or falls back
    to a simple LLM-based generation.

    Request Body:
        file_path (str): Path to the file being edited
        language (str): Programming language of the file
        original_code (str): The current file content
        instruction (str): User's edit instruction (e.g., "rename to camelCase")
        cursor_line (int): Current cursor line number
        cursor_column (int): Current cursor column number

    Returns:
        dict: { ok: bool, suggested_code: str, start_line: int, end_line: int }
    """
    payload = await _parse_json_body(request, _InlineSuggestRequest)
    language = payload.language
    original_code = payload.original_code
    instruction = payload.instruction
    cursor_line = payload.cursor_line

    try:
        if not instruction.strip():
            return {"ok": False, "error": "Instruction is required."}

        if not original_code.strip():
            return {"ok": False, "error": "No code to edit."}

        # Try to use the model manager for LLM-based suggestion
        try:
            from antigravity_k.api.dependencies import get_model_manager

            # Build a focused prompt for the edit task
            lines = original_code.split("\n")
            # Provide context: a few lines before and after the cursor
            context_start = max(0, cursor_line - 10)
            context_end = min(len(lines), cursor_line + 10)
            context_lines = lines[context_start:context_end]

            prompt = (
                f"You are an expert {language} code editor. "
                f"Given the following code context around line {cursor_line}, "
                f"apply this edit instruction: '{instruction}'.\n\n"
                f"```{language}\n{chr(10).join(context_lines)}\n```\n\n"
                "Return ONLY the modified lines (the complete new version of "
                "the affected code section). Do NOT include any explanation, "
                "markdown formatting, or backticks."
            )

            mm = get_model_manager()
            try:
                result = mm.generate(
                    prompt=prompt,
                    target="default",
                    max_tokens=2048,
                    temperature=0.3,
                )
                suggested = result
            except Exception:
                logger.exception("Model generation failed, using fallback")
                suggested = _fallback_suggestion(original_code, instruction, cursor_line)
        except ImportError:
            logger.warning("Model manager not available, using fallback")
            suggested = _fallback_suggestion(original_code, instruction, cursor_line)

        if not suggested.strip():
            return {"ok": False, "error": "Could not generate suggestion."}

        # Clean up the response
        suggested = suggested.strip()
        # Remove markdown code fences if present
        import re

        suggested = re.sub(r"^```\w*\n?", "", suggested)
        suggested = re.sub(r"\n```$", "", suggested)

        return {
            "ok": True,
            "suggested_code": suggested,
            "start_line": max(1, cursor_line - 1),
            "end_line": min(len(original_code.split("\n")), cursor_line + 1),
            "language": language,
        }

    except Exception as e:
        logger.exception("Inline suggest error")
        return {"ok": False, "error": str(e)}


def _fallback_suggestion(original_code: str, instruction: str, cursor_line: int) -> str:
    """Simple fallback when no LLM is available.

    Provides a basic diff-style suggestion by extracting context
    around the cursor. In production, this would use the model.
    """
    lines = original_code.split("\n")
    if not lines:
        return ""

    # For fallback, just return the context around cursor with a comment
    start = max(0, cursor_line - 3)
    end = min(len(lines), cursor_line + 3)
    context = lines[start:end]

    result: list[str] = []
    for line in context:
        result.append(line)

    if result:
        result.insert(0, f"// TODO: {instruction}")
        result.insert(1, "")

    return "\n".join(result)
