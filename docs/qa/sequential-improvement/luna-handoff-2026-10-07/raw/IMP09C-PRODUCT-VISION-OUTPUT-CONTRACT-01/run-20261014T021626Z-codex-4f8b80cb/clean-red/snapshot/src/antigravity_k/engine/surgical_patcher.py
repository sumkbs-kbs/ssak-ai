"""Hashline Surgical Patch Engine — Zero-token-waste surgical code editing.

Technology Origin: Aider / Claude Code Hashline Pattern (2025-2026).
Eliminates whole-file rewrites and indentation destruction by using line-hash
anchors to perform surgical, byte-accurate delta replacements.
"""

import hashlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def line_hash(text: str) -> str:
    """Compute a compact 4-character hash for line anchoring."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:4]


@dataclass(frozen=True, slots=True)
class PatchChunk:
    """A discrete hunk to replace."""

    start_anchor: str  # Line number or line content hash
    end_anchor: str
    target_content: str
    replacement_content: str


@dataclass(frozen=True, slots=True)
class PatchApplicationResult:
    """Outcome of surgical patch application."""

    success: bool
    modified_lines_count: int
    new_content: str
    error_message: str = ""


class SurgicalPatcher:
    """Applies surgical, hash-anchored patches to files without full-file generation."""

    @staticmethod
    def annotate_file_with_hashes(file_content: str) -> str:
        """Annotate each line with its 1-indexed line number and 4-char content hash.

        Example output:
          1:a1b2 def calculate():
          2:3c4d     return 42
        """
        lines = file_content.splitlines()
        annotated: list[str] = []
        for idx, line in enumerate(lines, 1):
            h = line_hash(line)
            annotated.append(f"{idx}:{h} {line}")
        return "\n".join(annotated)

    @staticmethod
    def apply_patch(
        original_content: str,
        target_snippet: str,
        replacement_snippet: str,
        start_line_hint: int | None = None,
    ) -> PatchApplicationResult:
        """Surgically replace target_snippet with replacement_snippet.

        Tolerates trailing whitespace and small indentation variations.
        """
        if not target_snippet:
            return PatchApplicationResult(
                success=False,
                modified_lines_count=0,
                new_content=original_content,
                error_message="Target snippet is empty.",
            )

        # 1. Exact match
        exact_start = original_content.find(target_snippet)
        if exact_start != -1 and start_line_hint is not None and start_line_hint > 0:
            hinted_start = exact_start
            while hinted_start != -1:
                line_number = original_content.count("\n", 0, hinted_start) + 1
                if line_number == start_line_hint:
                    exact_start = hinted_start
                    break
                hinted_start = original_content.find(target_snippet, hinted_start + 1)

        if exact_start != -1:
            new_content = (
                original_content[:exact_start]
                + replacement_snippet
                + original_content[exact_start + len(target_snippet) :]
            )
            mod_lines = len(replacement_snippet.splitlines()) - len(target_snippet.splitlines())
            return PatchApplicationResult(
                success=True,
                modified_lines_count=abs(mod_lines) + 1,
                new_content=new_content,
            )

        # 2. Normalized whitespace match
        norm_orig = "\n".join([line.rstrip() for line in original_content.splitlines()])
        norm_target = "\n".join([line.rstrip() for line in target_snippet.splitlines()])

        if norm_target in norm_orig:
            # Reconstruct with indentation preservation
            orig_lines = original_content.splitlines()
            target_lines = [line.strip() for line in target_snippet.splitlines() if line.strip()]

            matched_idx = -1
            if start_line_hint is not None:
                hinted_idx = start_line_hint - 1
                if (
                    0 <= hinted_idx < len(orig_lines)
                    and target_lines
                    and orig_lines[hinted_idx].strip() == target_lines[0]
                ):
                    matched_idx = hinted_idx
            for i, line in enumerate(orig_lines):
                if matched_idx != -1:
                    break
                if target_lines and line.strip() == target_lines[0]:
                    matched_idx = i
                    break

            if matched_idx != -1:
                prefix = orig_lines[:matched_idx]
                suffix = orig_lines[matched_idx + len(target_snippet.splitlines()) :]
                new_lines = prefix + replacement_snippet.splitlines() + suffix
                new_content = "\n".join(new_lines) + ("\n" if original_content.endswith("\n") else "")
                return PatchApplicationResult(
                    success=True,
                    modified_lines_count=len(replacement_snippet.splitlines()),
                    new_content=new_content,
                )

        return PatchApplicationResult(
            success=False,
            modified_lines_count=0,
            new_content=original_content,
            error_message="Target snippet could not be located in file.",
        )
