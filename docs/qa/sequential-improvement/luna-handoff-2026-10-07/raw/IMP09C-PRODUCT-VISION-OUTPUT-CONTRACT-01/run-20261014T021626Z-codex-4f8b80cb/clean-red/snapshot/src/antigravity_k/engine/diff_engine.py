"""Ssak-Ai: Diff/Apply 엔진 (P0-1).

====================================
정교한 패치 적용을 위한 unified diff 파싱 + apply 엔진.
Aider/Codex 수준의 신뢰성 있는 코드 수정을 지원합니다.

지원 포맷:
  1. apply_patch 포맷 (Aider 스타일):
     *** Begin Patch
     *** Add File: path/to/new.py
     +new content
     *** End File
     *** Update File: path/to/existing.py
     @@ context line
     -old line
     +new line
     *** End Patch

  2. Unified diff (git diff 포맷):
     --- a/path
     +++ b/path
     @@ -start,count +start,count @@
      context
     -removed
     +added

특징:
  - context line 기반 정확 매칭
  - 매치 실패 시 퍼지 매칭 폴백 (공백 정규화)
  - 부분 매칭 (fingerprint 기반 블록 특정)
  - 충돌 시 명확한 에러 메시지 + 유사 라인 제안
"""

from __future__ import annotations

import logging
import re

from .diff_models import ApplyResult, FilePatch, Hunk
from .diff_parser import parse_apply_patch

logger = logging.getLogger("antigravity_k.diff_engine")


class DiffApplyEngine:
    """패치 파싱 + 적용 엔진.

    사용법:
        engine = DiffApplyEngine()
        patches = engine.parse_apply_patch(patch_text)
        for patch in patches:
            result = engine.apply_patch(patch, file_content)
            if result.success:
                write(result.new_content)
    """

    # 허용 오차: 퍼지 매칭 시 최소 유사도
    FUZZY_THRESHOLD: float = 0.80

    def parse_apply_patch(self, text: str) -> list[FilePatch]:
        """apply_patch 포맷(Aider 스타일)을 파싱합니다.

        Args:
            text: apply_patch 포맷 텍스트

        Returns:
            FilePatch 리스트 (파일별)
        """
        return parse_apply_patch(text)

    def apply_patch(self, patch: FilePatch, file_content: str) -> ApplyResult:
        """파일에 패치를 적용합니다.

        Args:
            patch: 적용할 FilePatch
            file_content: 원본 파일 내용

        Returns:
            ApplyResult
        """
        if patch.is_new_file:
            return ApplyResult(
                success=True,
                file_path=patch.file_path,
                new_content="\n".join(patch.new_file_content),
                hunks_applied=1,
                hunks_total=1,
            )

        if patch.is_delete_file:
            return ApplyResult(
                success=True,
                file_path=patch.file_path,
                new_content="",
                hunks_applied=1,
                hunks_total=1,
            )

        if not patch.hunks:
            return ApplyResult(
                success=False,
                file_path=patch.file_path,
                error="패치에 hunk가 없습니다.",
            )

        content_lines = file_content.splitlines(keepends=False)
        result_lines = list(content_lines)
        fuzzy_count = 0
        applied = 0
        offset = 0  # 이전 hunk 적용으로 인한 라인 오프셋

        for i, hunk in enumerate(patch.hunks):
            match_result = self._find_hunk_position(result_lines, hunk, offset)

            if match_result is None:
                return ApplyResult(
                    success=False,
                    file_path=patch.file_path,
                    new_content="",
                    hunks_applied=applied,
                    hunks_total=len(patch.hunks),
                    error=self._build_hunk_error(result_lines, hunk, i),
                    fuzzy_matches=fuzzy_count,
                )

            start_idx, was_fuzzy = match_result
            if was_fuzzy:
                fuzzy_count += 1

            # 블록 교체: _find_hunk_position은 removals 블록의 시작 인덱스를 반환.
            # context_before는 이미 매칭 앵커로 사용되었으므로, 교체는 removals 영역에서만.
            # 순수 추가(hunk.removals가 빈 경우)는 start_idx 위치에 additions를 삽입.
            if hunk.removals:
                end_idx = start_idx + len(hunk.removals)
                result_lines[start_idx:end_idx] = hunk.additions
                offset += len(hunk.additions) - len(hunk.removals)
            else:
                # 순수 추가 — start_idx 위치에 삽입
                result_lines[start_idx:start_idx] = hunk.additions
                offset += len(hunk.additions)
            applied += 1

        new_content = "\n".join(result_lines)
        # 원본이 줄바꿈으로 끝났으면 유지
        if file_content.endswith("\n") and not new_content.endswith("\n"):
            new_content += "\n"

        return ApplyResult(
            success=True,
            file_path=patch.file_path,
            new_content=new_content,
            hunks_applied=applied,
            hunks_total=len(patch.hunks),
            fuzzy_matches=fuzzy_count,
        )

    def _find_hunk_position(
        self,
        lines: list[str],
        hunk: Hunk,
        offset: int,
    ) -> tuple[int, bool] | None:
        """hunk가 적용될 위치(removals 블록 시작 인덱스)를 찾습니다.

        전략:
          1. context_before를 앵커로 사용해 위치 특정
          2. removals 블록이 해당 위치에 존재하는지 검증
          3. 퍼지 매칭 폴백 (공백 정규화)

        Returns:
            (removals_start_index, was_fuzzy) — 매치 실패 시 None.
            순수 추가의 경우 삽입 위치 인덱스.
        """
        # 순수 추가 (removals 없음) — context_after 기반 위치 결정
        if not hunk.removals:
            if hunk.context_before:
                # 마지막 context_before 라인 다음에 삽입
                anchor = hunk.context_before[-1]
                for idx in range(max(0, offset), len(lines)):
                    if lines[idx] == anchor:
                        return idx + 1, False
                # 퍼지
                for idx in range(max(0, offset), len(lines)):
                    if self._normalize(lines[idx]) == self._normalize(anchor):
                        return idx + 1, True
            elif hunk.context_after:
                # context_after 첫 라인 위치에 삽입 (그 앞에)
                anchor = hunk.context_after[0]
                for idx in range(max(0, offset), len(lines)):
                    if lines[idx] == anchor:
                        return idx, False
            else:
                # 컨텍스트 없는 순수 추가 — 파일 끝
                return len(lines), False
            return None

        # removals가 있는 경우 — context_before로 앵커 위치 찾기
        removals = hunk.removals
        removals_len = len(removals)

        if hunk.context_before:
            # 마지막 context_before 라인을 찾고, 그 다음이 removals 시작
            anchor = hunk.context_before[-1]
            anchor_positions: list[int] = []
            for idx in range(max(0, offset - removals_len), len(lines)):
                if lines[idx] == anchor:
                    anchor_positions.append(idx)
                # 퍼지 앵커도 후보에 추가
                elif self._normalize(lines[idx]) == self._normalize(anchor):
                    anchor_positions.append(idx)

            # 각 앵커 위치에서 removals가 매치하는지 검증
            for anchor_idx in anchor_positions:
                removals_start = anchor_idx + 1
                if removals_start + removals_len <= len(lines):
                    if lines[removals_start : removals_start + removals_len] == removals:
                        is_fuzzy = (
                            anchor_idx not in range(max(0, offset - removals_len), len(lines))
                            or lines[anchor_idx] != anchor
                        )
                        return removals_start, is_fuzzy
            # 정규화된 removals 매칭
            norm_removals = [self._normalize(r) for r in removals]
            for anchor_idx in anchor_positions:
                removals_start = anchor_idx + 1
                if removals_start + removals_len <= len(lines):
                    window = [self._normalize(ln) for ln in lines[removals_start : removals_start + removals_len]]
                    if window == norm_removals:
                        return removals_start, True

        # context_before 없이 removals만 있는 경우 — 직접 검색
        search_start = max(0, offset - removals_len)
        for idx in range(search_start, len(lines) - removals_len + 1):
            if lines[idx : idx + removals_len] == removals:
                return idx, False

        # 퍼지: 정규화된 removals 검색
        norm_removals = [self._normalize(r) for r in removals]
        for idx in range(search_start, len(lines) - removals_len + 1):
            window = [self._normalize(ln) for ln in lines[idx : idx + removals_len]]
            if window == norm_removals:
                return idx, True

        # 유사도 기반 매칭
        if removals_len >= 2:
            best_idx, best_ratio = self._find_best_match(lines, removals, search_start)
            if best_ratio >= self.FUZZY_THRESHOLD and best_idx >= 0:
                return best_idx, True

        return None

    @staticmethod
    def _normalize(line: str) -> str:
        """라인 정규화 — 앞뒤 공백 제거 + 연속 공백 축소."""
        return re.sub(r"\s+", " ", line.strip())

    def _find_best_match(
        self,
        lines: list[str],
        block: list[str],
        search_start: int,
    ) -> tuple[int, float]:
        """블록과 가장 유사한 위치를 찾습니다 (SequenceMatcher)."""
        import difflib

        block_len = len(block)
        best_idx = -1
        best_ratio = 0.0

        for idx in range(search_start, len(lines) - block_len + 1):
            window = lines[idx : idx + block_len]
            # 라인별 유사도 평균
            ratios: list[float] = []
            for a, b in zip(block, window):
                ratios.append(difflib.SequenceMatcher(None, a, b).ratio())
            avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
            if avg_ratio > best_ratio:
                best_ratio = avg_ratio
                best_idx = idx

        return best_idx, best_ratio

    @staticmethod
    def _build_hunk_error(lines: list[str], hunk: Hunk, hunk_idx: int) -> str:
        """hunk 매치 실패 시 유용한 에러 메시지를 생성합니다."""
        import difflib

        old_block = hunk.old_block
        first_line = old_block[0][:60] if old_block else ""

        # 유사한 위치 제안
        suggestions: list[str] = []
        if old_block:
            target = DiffApplyEngine._normalize(first_line)
            for i, line in enumerate(lines[:200]):  # 처음 200라인만 검색
                if DiffApplyEngine._normalize(line) == target:
                    suggestions.append(f"L{i + 1}: '{line.strip()[:60]}'")
                    if len(suggestions) >= 3:
                        break

        msg = f"hunk #{hunk_idx + 1} 매치 실패: '{first_line}...'를 찾을 수 없습니다. "
        if suggestions:
            msg += f"유사 위치: {'; '.join(suggestions)}"
        else:
            # 가장 유사한 라인 제안
            if old_block:
                close = difflib.get_close_matches(first_line, lines, n=1, cutoff=0.6)
                if close:
                    msg += f"가장 유사한 라인: '{close[0][:60]}'"
                else:
                    msg += "유사한 라인을 찾지 못했습니다. 컨텍스트를 확인하세요."
        return msg
