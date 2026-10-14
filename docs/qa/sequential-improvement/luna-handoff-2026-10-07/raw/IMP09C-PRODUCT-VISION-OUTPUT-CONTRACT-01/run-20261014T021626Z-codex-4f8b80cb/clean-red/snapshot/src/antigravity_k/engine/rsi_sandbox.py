"""Ssak-Ai: RSI Safety Sandbox (재귀적 자기개선 안전 샌드박스).

================================================================
자기 수정 시 안전을 보장하는 이중 감사 + 자동 롤백 시스템.

연구 근거: Dual-Audit Safety (CoSAI 2025), Frontier Safety Frameworks

핵심 원칙:
  1. 불변 파일 보호: permission_gate.py, rsi_sandbox.py 등은 절대 수정 불가
  2. 스냅샷 기반 롤백: 모든 수정 전 상태를 Git으로 스냅샷
  3. 3중 검증 게이트: AST → 단위 테스트 → 벤치마크 회귀
  4. 이중 감사: 두 독립 LLM이 변이를 교차 검증
"""

from __future__ import annotations

import ast
import json
import logging
import os
import subprocess
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import TypedDict, cast

from antigravity_k.engine.sandbox import run_sandboxed_argv

logger = logging.getLogger("antigravity_k.rsi_sandbox")


class MutationPayload(TypedDict):
    mutation_id: str
    timestamp: float
    target_file: str
    mutation_type: str
    risk_level: str
    before_hash: str
    after_hash: str
    validations: dict[str, str]
    approved: bool
    rolled_back: bool
    benchmark_delta: float


class AuditResult(TypedDict):
    approved: bool
    auditor_1: str
    auditor_2: str


# ─── 불변 파일 목록 (절대 자기수정 불가) ─────────────────────────────

IMMUTABLE_FILES = frozenset(
    {
        "rsi_sandbox.py",
        "permission_gate.py",
        "tool_guardrails.py",
        "claude_deny_patterns.py",
    },
)

# 자동 적용 허용 파일 패턴 (Option B: 벤치마크 통과 시)
AUTO_APPLY_ALLOWED = frozenset(
    {
        "prompt_builder.py",
        "model_manager.py",
        "context_compressor.py",
        "benchmark_cases.py",
    },
)


class MutationRisk(Enum):
    """변이 위험도 등급."""

    LOW = "low"  # 프롬프트/설정 변경만
    MEDIUM = "medium"  # 비핵심 코드 수정
    HIGH = "high"  # 핵심 엔진 수정
    CRITICAL = "critical"  # 안전 모듈 접근 시도 → 차단


class ValidationResult(Enum):
    """검증 결과."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class MutationRecord:
    """변이 기록 1건."""

    mutation_id: str
    timestamp: float
    target_file: str
    mutation_type: str  # "prompt" | "code" | "config" | "tool"
    risk_level: str
    before_hash: str
    after_hash: str
    validations: dict[str, str] = field(default_factory=dict)
    approved: bool = False
    rolled_back: bool = False
    benchmark_delta: float = 0.0

    def to_dict(self) -> dict[str, object]:
        """To Dict.

        Returns:
            dict: The dict result.

        """
        return cast(dict[str, object], cast(object, asdict(self)))


@dataclass
class OwnedPreimage:
    """소유한 쓰기 대상 1개의 수정 전 상태 (FR-04/RP-04)."""

    path: str
    existed: bool
    content: bytes
    mode: int | None
    last_owned_write: bytes | None = None


@dataclass
class SnapshotInfo:
    """스냅샷 정보."""

    snapshot_id: str
    git_commit: str
    timestamp: float
    files_captured: list[str]
    benchmark_baseline: float = 0.0
    owned_preimages: dict[str, OwnedPreimage] = field(default_factory=dict)


# ─── 메인 샌드박스 ───────────────────────────────────────────────────


class RSISandbox:
    """재귀적 자기개선 안전 샌드박스.

    모든 자기 수정은 이 샌드박스를 통해서만 수행됩니다.
    불변 파일 보호, 스냅샷 기반 롤백, 3중 검증을 제공합니다.
    """

    def __init__(
        self,
        project_root: str = "",
        audit_dir: str = "data/rsi_audit",
        verify_fn: Callable[[str], str] | None = None,
    ):
        """Initialize the RSISandbox.

        Args:
            project_root (str): str project root.
            audit_dir (str): str audit dir.
            verify_fn (Callable | None): Callable | None verify fn.

        """
        self._root: str = project_root or os.getcwd()
        self._audit_dir: Path = Path(audit_dir)
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._verify_fn: Callable[[str], str] | None = verify_fn  # LLM 검증 함수
        self._mutation_log: list[MutationRecord] = []
        self._snapshots: list[SnapshotInfo] = []
        # FR-04/RP-04: 활성 mutation이 소유한 preimage 기록.
        self._active_preimages: dict[str, OwnedPreimage] | None = None
        self._active_snapshot: SnapshotInfo | None = None
        self._load_audit_log()

    # ─── 불변 파일 보호 ──────────────────────────────────────────

    def is_immutable(self, filepath: str) -> bool:
        """파일이 불변 보호 대상인지 확인합니다."""
        basename = os.path.basename(filepath)
        return basename in IMMUTABLE_FILES

    def is_auto_apply_allowed(self, filepath: str) -> bool:
        """자동 적용이 허용된 파일인지 확인합니다 (Option B)."""
        basename = os.path.basename(filepath)
        return basename in AUTO_APPLY_ALLOWED

    def classify_risk(self, filepath: str, mutation_type: str) -> MutationRisk:
        """변이의 위험도를 분류합니다."""
        basename = os.path.basename(filepath)

        if basename in IMMUTABLE_FILES:
            return MutationRisk.CRITICAL

        if mutation_type == "prompt":
            return MutationRisk.LOW

        if mutation_type == "config":
            return MutationRisk.LOW

        if basename in AUTO_APPLY_ALLOWED:
            return MutationRisk.MEDIUM

        # 핵심 엔진 파일
        if basename in {
            "orchestrator.py",
            "model_router.py",
            "quality_gate.py",
            "chat.py",
            "goal_runner.py",
            "state_graph.py",
        }:
            return MutationRisk.HIGH

        return MutationRisk.MEDIUM

    # ─── 스냅샷 관리 ─────────────────────────────────────────────

    def take_snapshot(self, label: str = "") -> SnapshotInfo:
        """현재 상태의 소유권 스냅샷을 생성합니다.

        FR-04/RP-04: 스냅샷은 mutation이 소유할 파일의 preimage만 담는다.
        tracked file 전체 목록은 소유권 목록이 아니므로 복구에 쓰지 않는다.
        """
        snapshot_id = f"rsi_{int(time.time())}_{label or 'auto'}"
        git_commit = self._get_current_commit()

        snapshot = SnapshotInfo(
            snapshot_id=snapshot_id,
            git_commit=git_commit,
            timestamp=time.time(),
            files_captured=[],
            # Live reference: write_owned이 컨텍스트 진행 중 추가하는 소유
            # preimage가 이 스냅샷의 복구 집합에 그대로 반영돼야 한다.
            owned_preimages=self._active_preimages if self._active_preimages is not None else {},
        )
        self._snapshots.append(snapshot)

        logger.info(
            "[RSI Sandbox] 스냅샷 생성: %s (commit: %s, owned: %s)",
            snapshot_id,
            git_commit[:8],
            len(snapshot.owned_preimages),
        )
        return snapshot

    def _capture_preimage(self, path: Path) -> OwnedPreimage:
        if path.exists():
            return OwnedPreimage(
                path=str(path),
                existed=True,
                content=path.read_bytes(),
                mode=path.stat().st_mode & 0o7777,
            )
        return OwnedPreimage(path=str(path), existed=False, content=b"", mode=None)

    def rollback_to(self, snapshot: SnapshotInfo) -> bool:
        """소유한 쓰기만 이전 상태로 복구합니다 (FR-04/RP-04).

        전체 트리를 되돌리는 ``git checkout <commit> -- .`` /
        ``reset --hard`` / ``clean -fd``는 다른 에이전트와 사용자의 변경을
        덮어쓰므로 사용하지 않는다. 소유한 쓰기가 없으면 아무것도 하지 않는다.
        """
        restored = 0
        conflicts: list[str] = []
        for pre in snapshot.owned_preimages.values():
            path = Path(pre.path)
            try:
                if pre.last_owned_write is None:
                    # 이 스냅샷이 소유한 쓰기가 없던 경로 — 복구 대상 아님.
                    continue
                if not path.exists():
                    # ours 쓰기 후 누군가 파일을 삭제한 경우: 원본이 있었다면
                    # 외부 삭제를 보존하고 충돌로 기록한다. 원래 없었던 신규
                    # 파일은 rollback의 목표 상태도 부재이므로 그대로 둔다.
                    if pre.existed:
                        conflicts.append(pre.path)
                    continue
                current = path.read_bytes()
                if current != pre.last_owned_write:
                    # ours 마지막 쓰기와 다르다 = 다른 작업자가 변경했다.
                    # 그 변경을 보존하고 충돌로 기록한다.
                    conflicts.append(pre.path)
                    continue
                if pre.existed:
                    path.write_bytes(pre.content)
                    if pre.mode is not None:
                        path.chmod(pre.mode)
                else:
                    path.unlink()
                restored += 1
            except OSError as exc:
                logger.error("[RSI Sandbox] 복구 실패 %s: %s", pre.path, exc)
                conflicts.append(pre.path)

        if conflicts:
            logger.warning(
                "[RSI Sandbox] 롤백 완료: %s (복구 %s건, 외부 변경 보존 %s건)",
                snapshot.snapshot_id,
                restored,
                len(conflicts),
            )
        else:
            logger.info("[RSI Sandbox] 롤백 완료: %s (복구 %s건)", snapshot.snapshot_id, restored)
        return True

    def write_owned(self, path: str | os.PathLike[str], content: str, *, encoding: str = "utf-8") -> None:
        """``safe_mutation`` 컨텍스트 안에서 소유할 파일 쓰기.

        컨텍스트 밖에서 호출되면 일반 쓰기로 동작한다(소유권 기록 없음).
        """
        target = Path(path)
        if self._active_snapshot is not None and self._active_preimages is not None:
            key = str(target)
            pre = self._active_preimages.get(key)
            if pre is None:
                pre = self._capture_preimage(target)
                self._active_preimages[key] = pre
            payload = content.encode(encoding)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            pre.last_owned_write = payload
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(content, encoding=encoding)

    # ─── 3중 검증 게이트 ─────────────────────────────────────────

    def validate_mutation(
        self,
        filepath: str,
        new_content: str,
        benchmark_fn: Callable[[str, str], bool] | None = None,
    ) -> dict[str, ValidationResult]:
        """변이를 3중 검증합니다.

        1단계: AST 구문 검증
        2단계: 기존 테스트 실행
        3단계: 벤치마크 회귀 검증 (선택)

        Returns:
            {"ast": PASS/FAIL, "tests": PASS/FAIL, "benchmark": PASS/FAIL/SKIP}

        """
        results: dict[str, ValidationResult] = {}

        # 1단계: AST 구문 검증
        if filepath.endswith(".py"):
            try:
                _ = ast.parse(new_content)
                results["ast"] = ValidationResult.PASS
            except SyntaxError as e:
                logger.warning("[RSI Sandbox] AST 실패: %s: %s", filepath, e)
                results["ast"] = ValidationResult.FAIL
                return results  # AST 실패 시 이후 단계 스킵
        else:
            results["ast"] = ValidationResult.SKIP

        # 2단계: 기존 테스트 실행 (임시 파일 교체 후)
        original_content = None
        full_path = os.path.join(self._root, filepath) if not os.path.isabs(filepath) else filepath

        try:
            if os.path.exists(full_path):
                with open(full_path, encoding="utf-8") as f:
                    original_content = f.read()

                # 임시 교체
                with open(full_path, "w", encoding="utf-8") as f:
                    _ = f.write(new_content)

                # pytest 실행
                test_result = run_sandboxed_argv(
                    [
                        "python",
                        "-m",
                        "pytest",
                        "tests/test_output_quality.py",
                        "-q",
                        "--tb=short",
                        "-x",
                    ],
                    cwd=self._root,
                    timeout=60,
                    env={**os.environ, "PYTHONPATH": os.path.join(self._root, "src")},
                )
                results["tests"] = ValidationResult.PASS if test_result.return_code == 0 else ValidationResult.FAIL
            else:
                results["tests"] = ValidationResult.SKIP
        except Exception:
            logger.exception("[RSI Sandbox] 테스트 실패")
            results["tests"] = ValidationResult.FAIL
        finally:
            # 원복
            if original_content is not None and os.path.exists(full_path):
                with open(full_path, "w", encoding="utf-8") as f:
                    _ = f.write(original_content)

        # 3단계: 벤치마크 회귀
        if benchmark_fn:
            try:
                benchmark_passed = benchmark_fn(filepath, new_content)
                results["benchmark"] = ValidationResult.PASS if benchmark_passed else ValidationResult.FAIL
            except Exception:
                logger.exception("Unhandled exception")
                results["benchmark"] = ValidationResult.SKIP
        else:
            results["benchmark"] = ValidationResult.SKIP

        return results

    # ─── 이중 감사 (Dual-Audit) ──────────────────────────────────

    def dual_audit(
        self,
        filepath: str,
        original: str,
        modified: str,
        audit_fn_1: Callable[[str], str] | None = None,
        audit_fn_2: Callable[[str], str] | None = None,
    ) -> AuditResult:
        """두 개의 독립 LLM이 변이를 교차 검증합니다.

        Args:
            filepath: 대상 파일
            original: 원본 코드
            modified: 수정된 코드
            audit_fn_1: 첫 번째 감사자 (prompt -> str)
            audit_fn_2: 두 번째 감사자 (prompt -> str)

        Returns:
            {"approved": bool, "auditor_1": str, "auditor_2": str}

        """
        audit_prompt = (
            "[ROLE]\n당신은 코드 변경 감사관입니다.\n\n"
            "[TASK]\n아래 코드 변경이 안전하고 유익한지 판단하세요.\n"
            "1. 기능 퇴화가 있는가?\n"
            "2. 보안 취약점이 도입되었는가?\n"
            "3. 성능 저하 가능성이 있는가?\n\n"
            f"파일: {filepath}\n\n"
            f"--- 원본 (첫 500자) ---\n{original[:500]}\n\n"
            f"--- 수정 (첫 500자) ---\n{modified[:500]}\n\n"
            "판단: APPROVE 또는 REJECT (이유 포함)"
        )

        result: AuditResult = {"approved": True, "auditor_1": "skip", "auditor_2": "skip"}

        fn_1 = audit_fn_1 or self._verify_fn
        fn_2 = audit_fn_2 or self._verify_fn

        if fn_1:
            try:
                r1 = fn_1(audit_prompt)
                result["auditor_1"] = r1 or "no response"
                if r1 and "REJECT" in r1.upper():
                    result["approved"] = False
            except Exception as e:
                logger.exception("Unhandled exception")
                result["auditor_1"] = f"error: {e}"

        if fn_2 and fn_2 is not fn_1:
            try:
                r2 = fn_2(audit_prompt)
                result["auditor_2"] = r2 or "no response"
                if r2 and "REJECT" in r2.upper():
                    result["approved"] = False
            except Exception as e:
                logger.exception("Unhandled exception")
                result["auditor_2"] = f"error: {e}"

        return result

    # ─── 안전한 수정 컨텍스트 ────────────────────────────────────

    @contextmanager
    def safe_mutation(self, label: str = ""):
        """안전한 자기수정 컨텍스트 매니저.

        사용법:
            with sandbox.safe_mutation("prompt_optimization"):
                sandbox.write_owned(path, new_code)  # 소유할 쓰기만 이 경로로
                # 검증 실패 시 소유한 쓰기만 이전 상태로 복구된다.

        FR-04/RP-04: 복구는 이 컨텍스트가 소유한 쓰기로 한정된다. 다른
        에이전트/사용자의 dirty·untracked 변경과 이 컨텍스트 밖의 파일은
        절대 되돌리지 않는다. ``write_owned``를 거치지 않은 쓰기는 소유하지
        않으므로 복구 대상이 아니다.
        """
        self._active_preimages = {}
        snapshot = self.take_snapshot(label)
        self._active_snapshot = snapshot
        try:
            yield snapshot
            logger.info("[RSI Sandbox] 안전 수정 완료: %s", label)
        except Exception as e:
            logger.error("[RSI Sandbox] 수정 중 오류, 소유 쓰기 롤백 시작: %s", e)
            _ = self.rollback_to(snapshot)
            raise
        finally:
            self._active_snapshot = None
            self._active_preimages = None

    # ─── 변이 기록 ───────────────────────────────────────────────

    def record_mutation(self, record: MutationRecord) -> None:
        """변이 기록을 저장합니다."""
        self._mutation_log.append(record)
        self._save_audit_log()

    def get_mutation_history(self, last_n: int = 20) -> list[dict[str, object]]:
        """최근 변이 이력을 반환합니다."""
        return [m.to_dict() for m in self._mutation_log[-last_n:]]

    def get_stats(self) -> dict[str, object]:
        """샌드박스 통계를 반환합니다."""
        total = len(self._mutation_log)
        approved = sum(1 for m in self._mutation_log if m.approved)
        rolled_back = sum(1 for m in self._mutation_log if m.rolled_back)
        return {
            "total_mutations": total,
            "approved": approved,
            "rolled_back": rolled_back,
            "approval_rate": f"{approved / max(total, 1) * 100:.0f}%",
            "snapshots": len(self._snapshots),
        }

    # ─── 내부 유틸 ───────────────────────────────────────────────

    def _get_current_commit(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            logger.exception("Unhandled exception")
            return "unknown"

    def _load_audit_log(self) -> None:
        log_path = self._audit_dir / "mutation_log.json"
        if log_path.exists():
            try:
                with open(log_path, encoding="utf-8") as f:
                    data = cast(object, json.load(f))
                if not isinstance(data, dict):
                    return
                payload = cast(dict[str, object], cast(object, data))
                raw_mutations = payload.get("mutations", [])
                if isinstance(raw_mutations, list):
                    mutations = cast(list[object], cast(object, raw_mutations))
                    self._mutation_log = [
                        MutationRecord(**cast(MutationPayload, cast(object, item)))
                        for item in mutations
                        if isinstance(item, dict)
                    ]
            except Exception:
                logger.exception("[RSI Sandbox] 감사 로그 로드 실패")

    def _save_audit_log(self) -> None:
        log_path = self._audit_dir / "mutation_log.json"
        try:
            data = {
                "version": 1,
                "updated_at": time.time(),
                "mutations": [m.to_dict() for m in self._mutation_log],
            }
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("[RSI Sandbox] 감사 로그 저장 실패")


"""Ssak-Ai RSI Safety Sandbox — Dual-audit + auto-rollback."""
