"""Ssak-Ai: 실행 검증 기반 Best-of-N 샘플러 (Execution-Verified Best-of-N).

========================================================
유사도 다수결(self_consistency)과 달리, N개 후보를 **실제 실행/검증**해서
통과한 답변을 선택한다. 코딩 과제에서 프론티어 격차를 좁히는 핵심 메커니즘은
"더 큰 모델"이 아니라 "더 많은 검증된 시도"라는 테스트타임 컴퓨트 스케일링
(o1/R1 스타일) 법칙에 근거한다.

설계 원칙:
  - generate_fn으로 N개 후보를 온도 다양성과 함께 샘플링 (self_consistency 재사용 패턴)
  - 각 후보를 verifier_fn(코드 추출 → 명령 실행 등)으로 검증
  - 통과 후보 발견 즉시 반환(early exit) — 비용 절제
  - 전부 실패하면 검증 점수 최고 후보를 폴백 선택, feedback_loop 시 실패 사유를
    프롬프트에 붙여 재시도
  - TestTimeComputeScaler.ComputeBudget.branching_factor를 N으로 연동

사용법:
    engine = BestOfNVerifier(
        generate_fn=model.generate,
        verifier_fn=make_command_verifier(["python3", "{file}"]),
    )
    trace = engine.run("버그를 고쳐라")
    answer = trace.selected
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from antigravity_k.engine.sandbox import run_sandboxed_argv

logger = logging.getLogger("antigravity_k.best_of_n")

_GenerateFn = Callable[..., str]
_VerifyFn = Callable[[str], "VerificationOutcome"]


@dataclass
class VerificationOutcome:
    """단일 후보 검증 결과.

    Attributes:
        passed: 검증 통과 여부 (테스트 exit code 0 등).
        score: 상대 순위용 점수 (0.0~1.0). 통과면 보통 1.0.
        detail: 실패 원인 요약 (로그 마지막 줄 등) — 재생성 피드백으로 재사용.
    """

    passed: bool
    score: float = 1.0
    detail: str = ""


@dataclass
class CandidateResult:
    """Best-of-N 단일 후보의 샘플링+검증 결과."""

    index: int
    temperature: float
    text: str
    verification: VerificationOutcome | None = None


@dataclass
class BestOfNTrace:
    """Best-of-N 실행 추적."""

    selected: str = ""
    selected_index: int = -1
    passed_count: int = 0
    n_candidates: int = 0
    candidates: list[CandidateResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    early_exit: bool = False
    latency_ms: float = 0.0


_CODE_FENCE = re.compile(r"```(?:\w+)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str, language_hint: str = "") -> str:
    """답변에서 코드 블록을 추출한다(전후 공백 제거). 펜스가 없으면 전문 반환."""
    fences = cast(list[str], _CODE_FENCE.findall(text or ""))
    if not fences:
        return (text or "").strip()
    if language_hint:
        hinted = cast(
            list[str],
            re.findall(
                rf"```{re.escape(language_hint)}\s*\n(.*?)```",
                text or "",
                re.DOTALL,
            ),
        )
        if hinted:
            return hinted[-1].strip()
    return max(fences, key=len).strip()


def make_command_verifier(
    command: list[str],
    timeout_sec: float = 30.0,
    language_hint: str = "python",
) -> Callable[[str], VerificationOutcome]:
    """후보 코드를 임시 파일에 쓰고 command로 실행 검증하는 verifier 팩토리.

    command는 `{file}` 플레이스홀더를 지원한다 (예: ["python3", "{file}"]).
    플레이스홀더가 없으면 코드 파일 경로가 마지막 인수로 추가된다.
    """
    uses_placeholder = any("{file}" in arg for arg in command)

    def verify(text: str) -> VerificationOutcome:
        code = extract_code(text, language_hint=language_hint)
        if not code.strip():
            return VerificationOutcome(passed=False, score=0.0, detail="empty candidate")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"candidate.{language_hint or 'txt'}"
                _ = path.write_text(code, encoding="utf-8")
                argv = [arg.replace("{file}", str(path)) for arg in command]
                if not uses_placeholder:
                    argv.append(str(path))
                res = run_sandboxed_argv(argv, cwd=tmp, timeout=timeout_sec)
        except OSError as exc:
            return VerificationOutcome(passed=False, score=0.0, detail=f"verifier spawn failed: {exc}")
        if res.timed_out:
            return VerificationOutcome(passed=False, score=0.0, detail="verifier timeout")
        if res.return_code == 0:
            return VerificationOutcome(passed=True, score=1.0, detail="")
        output = (res.stderr or res.stdout or "").strip()
        last_line = output.splitlines()[-1] if output else f"exit {res.return_code}"
        return VerificationOutcome(passed=False, score=0.0, detail=last_line[:300])

    return verify


def make_syntax_verifier(language_hint: str = "python") -> Callable[[str], VerificationOutcome]:
    """후보 코드의 구문 타당성만 빠르게 검증하는 경량 verifier (서브프로세스 없음).

    실행 테스트가 없는 환경에서의 기본 검증자. Python 외 언어는 항상 통과한다.
    """

    def verify(text: str) -> VerificationOutcome:
        code = extract_code(text, language_hint=language_hint)
        if not code.strip():
            return VerificationOutcome(passed=False, score=0.0, detail="empty candidate")
        if language_hint != "python":
            return VerificationOutcome(passed=True)
        import ast

        try:
            _ = ast.parse(code)
        except SyntaxError as exc:
            return VerificationOutcome(
                passed=False,
                score=0.0,
                detail=f"SyntaxError line {exc.lineno}: {exc.msg}",
            )
        return VerificationOutcome(passed=True)

    return verify


def budget_to_n_samples(branching_factor: int) -> int:
    """ComputeBudget.branching_factor(1~5)를 샘플 수로 변환한다."""
    return max(1, min(int(branching_factor), 5))


_FENCE_WITH_PATH = re.compile(
    r"```[\w+#.-]*[ \t]+(?:#|//)?[ \t]*([\w./\\-]+\.[A-Za-z]{1,5})[ \t]*\n(.*?)```",
    re.DOTALL,
)


def parse_file_blocks(text: str) -> dict[str, str]:
    """후보 답변에서 ```` ```lang path/to/file ```` 형태의 파일 블록을 추출한다.

    에이전트 출력 관례(펜스 헤더에 파일 경로 표기)를 지원한다. 상위 디렉터리
    참조("..") 세그먼트가 포함된 경로는 탈출 시도로 보아 제외한다. 경로가 없는
    일반 코드 펜스는 무시한다.
    """
    out: dict[str, str] = {}
    for match in _FENCE_WITH_PATH.finditer(text or ""):
        rel_path, body = match.group(1), match.group(2)
        rel_path = rel_path.replace("\\", "/")
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]
        if not rel_path or rel_path.endswith("/"):
            continue
        if ".." in rel_path.split("/"):
            logger.warning("파일 블록 경로에 '..' 포함 — 제외: %s", rel_path)
            continue
        _ = out.setdefault(rel_path, body.strip("\n") + "\n")
    return out


def make_answer_patch_verifier(
    project_root: str | Path,
    test_command: list[str],
    timeout_sec: float = 120.0,
) -> Callable[[str], VerificationOutcome]:
    """답변 내 파일 블록을 worktree에 적용하고 실제 테스트를 돌리는 verifier.

    parse_file_blocks로 추출한 파일들을 격리 스냅샷에 기록한 뒤 test_command로
    통과 여부를 판정한다. 프로젝트 밖 경로 쓰기(패스 탈출)는 거부한다.
    """
    root = Path(project_root).resolve()

    def apply_fn(candidate_text: str, workspace_path: Path) -> bool:
        files = parse_file_blocks(candidate_text)
        if not files:
            return False
        ws_resolved = Path(workspace_path).resolve()
        for rel_path, content in files.items():
            target = (ws_resolved / rel_path).resolve()
            try:
                _ = target.relative_to(ws_resolved)
            except ValueError:
                logger.warning("패치 경로 탈출 거부: %s", rel_path)
                return False
            target.parent.mkdir(parents=True, exist_ok=True)
            _ = target.write_text(content, encoding="utf-8")
        return True

    return make_worktree_test_verifier(root, apply_fn, test_command, timeout_sec)


def make_worktree_test_verifier(
    project_root: str | Path,
    apply_fn: Callable[[str, Path], bool],
    test_command: list[str],
    timeout_sec: float = 120.0,
) -> Callable[[str], VerificationOutcome]:
    """BoN 후보를 git worktree 격리 공간에 적용한 뒤 실제 테스트를 돌리는 verifier.

    구문 검사(make_syntax_verifier)보다 강한 신호다 — 후보 변경이 실제
    코드베이스 스냅샷에서 테스트를 통과하는지 확인한다.

    Args:
        project_root: 검증 대상 저장소 루트.
        apply_fn: (candidate_text, workspace_path) -> bool. 후보 답변을
            워크스페이스에 반영하는 도메인 로직(파일 매핑은 호출자가 안다).
        test_command: 통과 판정용 명령 (예: ["pytest", "-q", "tests/test_x.py"]).
        timeout_sec: 테스트 명령 타임아웃.
    """
    from antigravity_k.engine.speculative_branching import SpeculativeBranchingEngine

    engine = SpeculativeBranchingEngine(project_root=Path(project_root))

    def verify(text: str) -> VerificationOutcome:
        workspace = engine.open_workspace("bon_verify", prefer_worktree=True)
        try:
            try:
                applied = apply_fn(text, workspace.path)
            except Exception as exc:
                return VerificationOutcome(passed=False, score=0.0, detail=f"patch apply failed: {exc}")
            if not applied:
                return VerificationOutcome(passed=False, score=0.0, detail="patch not applicable")
            try:
                res = run_sandboxed_argv(test_command, cwd=str(workspace.path), timeout=timeout_sec)
            except OSError as exc:
                return VerificationOutcome(passed=False, score=0.0, detail=f"test spawn failed: {exc}")
            if res.timed_out:
                return VerificationOutcome(passed=False, score=0.0, detail="test timeout")
            if res.return_code == 0:
                return VerificationOutcome(passed=True, score=1.0)
            output = (res.stderr or res.stdout or "").strip()
            last_line = output.splitlines()[-1] if output else f"exit {res.return_code}"
            return VerificationOutcome(passed=False, score=0.0, detail=last_line[:300])
        finally:
            workspace.cleanup()

    return verify


class BestOfNVerifier:
    """N샘플링 → 실행 검증 → first-pass-wins / best-score 폴백 선택기.

    SelfConsistencyEngine과 동일한 generate_fn 주입 패턴을 따르므로
    ModelManager.generate 위에 얹어 바로 쓸 수 있다.
    """

    def __init__(
        self,
        generate_fn: _GenerateFn | None = None,
        verifier_fn: _VerifyFn | None = None,
        n_samples: int = 3,
        base_temperature: float = 0.7,
        temperature_spread: float = 0.3,
    ):
        self._generate_fn: _GenerateFn | None = generate_fn
        self._verifier_fn: _VerifyFn | None = verifier_fn
        self.n_samples: int = max(1, int(n_samples))
        self.base_temperature: float = float(base_temperature)
        self.temperature_spread: float = float(temperature_spread)

    def set_generate_fn(self, fn: _GenerateFn) -> None:
        self._generate_fn = fn

    def set_verifier_fn(self, fn: _VerifyFn) -> None:
        self._verifier_fn = fn

    def _sample_temperature(self, i: int) -> float:
        half = max(1, self.n_samples - 1)
        offset = (i / half - 0.5) * 2 * self.temperature_spread
        return max(0.0, min(1.5, self.base_temperature + offset))

    def _sample_one(self, index: int, prompt: str, gen_kwargs: dict[str, object]) -> CandidateResult:
        temp = self._sample_temperature(index)
        if self._generate_fn is None:
            return CandidateResult(index=index, temperature=temp, text="")
        kwargs = dict(gen_kwargs)
        kwargs["temperature"] = temp
        try:
            text = self._generate_fn(prompt, **kwargs)
        except Exception as exc:
            logger.debug("best-of-n candidate %d failed: %s", index, exc)
            text = ""
        return CandidateResult(index=index, temperature=temp, text=text)

    def collect_candidates(self, prompt: str, **gen_kwargs: object) -> list[CandidateResult]:
        """프롬프트를 N회 샘플링해 CandidateResult 리스트를 반환한다.

        run()은 조기 종료를 위해 이 메서드 대신 _sample_one을 사용한다.
        """
        if self._generate_fn is None:
            return []
        return [self._sample_one(i, prompt, gen_kwargs) for i in range(self.n_samples)]

    def run(
        self,
        prompt: str,
        feedback_loop: bool = False,
        max_feedback_rounds: int = 1,
        **gen_kwargs: object,
    ) -> BestOfNTrace:
        """Best-of-N을 실행한다.

        후보를 한 번에 하나씩 샘플링-검증하므로, 중간에 통과하면 남은 후보의
        생성 비용 자체를 생략한다(early exit).

        Args:
            prompt: 작업 프롬프트.
            feedback_loop: 후보가 모두 비었을 때(검증기가 아무것도 평가하지 못했을 때)
                재시도 라운드를 돈다. 검증에 실패한(그러나 출력은 있는) 후보는
                best-effort 폴백으로 즉시 반환된다.
            max_feedback_rounds: 피드백 재시도 라운드 수 (기본 1).
            **gen_kwargs: generate_fn에 전달할 추가 인자.
        """
        start = time.monotonic()
        if self._generate_fn is None or self.n_samples <= 1 or self._verifier_fn is None:
            single = ""
            if self._generate_fn is not None and self._verifier_fn is None and self.n_samples > 1:
                # 검증자가 없으면 다수결의 의미가 없으므로 단일 생성 계약 유지
                single = self._generate_fn(prompt, **gen_kwargs)
            return BestOfNTrace(
                selected=single,
                skipped=True,
                skip_reason="disabled or no verifier",
                latency_ms=(time.monotonic() - start) * 1000,
            )

        current_prompt = prompt
        total_rounds = 1 + max(0, int(max_feedback_rounds)) if feedback_loop else 1

        for round_no in range(total_rounds):
            candidates: list[CandidateResult] = []
            verified_any = False
            last_detail = ""
            for i in range(self.n_samples):
                cand = self._sample_one(i, current_prompt, gen_kwargs)
                candidates.append(cand)
                if not cand.text.strip():
                    continue
                try:
                    outcome = self._verifier_fn(cand.text)
                except Exception as exc:
                    logger.debug("verifier raised for candidate %d: %s", cand.index, exc)
                    outcome = VerificationOutcome(passed=False, score=0.0, detail=str(exc)[:200])
                cand.verification = outcome
                verified_any = True
                if outcome.detail:
                    last_detail = outcome.detail
                if outcome.passed:
                    # first-pass wins — 남은 후보의 샘플링/검증 비용을 절제한다.
                    return self._finish_trace(
                        candidates=candidates,
                        selected=cand,
                        early_exit=True,
                        start=start,
                    )

            if verified_any:
                # 출력이 있었지만 전부 실패 → 검증 점수 최고 후보 best-effort 반환.
                # 실패 답변으로 무한 재시도하는 것보다 호출자가 피드백을 갖게 하는 게 낫다.
                best = self._fallback_best(candidates)
                if best is not None:
                    return self._finish_trace(
                        candidates=candidates,
                        selected=best,
                        early_exit=False,
                        start=start,
                    )

            if round_no + 1 < total_rounds and last_detail:
                current_prompt = (
                    f"{prompt}\n\n[이전 시도 실패 원인]\n{last_detail}\n위 오류를 반드시 수정한 코드를 다시 출력하세요."
                )

        return BestOfNTrace(
            skipped=True,
            skip_reason="no verifiable candidates across rounds",
            latency_ms=(time.monotonic() - start) * 1000,
        )

    @staticmethod
    def _fallback_best(candidates: list[CandidateResult]) -> CandidateResult | None:
        non_empty = [c for c in candidates if c.text.strip()]
        if not non_empty:
            return None
        scored = [c for c in non_empty if c.verification is not None]
        if not scored:
            return non_empty[0]
        scored.sort(key=lambda c: c.verification.score if c.verification else 0.0, reverse=True)
        return scored[0]

    @staticmethod
    def _finish_trace(
        *,
        candidates: list[CandidateResult],
        selected: CandidateResult,
        early_exit: bool,
        start: float,
    ) -> BestOfNTrace:
        passed_count = sum(1 for c in candidates if c.verification is not None and c.verification.passed)
        logger.info(
            "best-of-n selected idx=%d verified=%d/%d early_exit=%s",
            selected.index,
            len([c for c in candidates if c.verification is not None]),
            len(candidates),
            early_exit,
        )
        return BestOfNTrace(
            selected=selected.text,
            selected_index=selected.index,
            passed_count=passed_count,
            n_candidates=len(candidates),
            candidates=candidates,
            early_exit=early_exit,
            latency_ms=(time.monotonic() - start) * 1000,
        )


def config_to_engine_kwargs(cfg: object) -> dict[str, object]:
    """amplification.best_of_n config dict를 BestOfNVerifier kwargs로 매핑."""
    if not isinstance(cfg, dict):
        return {}
    config = cast(Mapping[str, object], cfg)
    out: dict[str, object] = {}
    for key in ("n_samples", "base_temperature", "temperature_spread"):
        raw = config.get(key)
        if raw is None:
            continue
        if not isinstance(raw, (str, int, float)):
            logger.warning("best_of_n.%s 무시(잘못된 값): %r", key, raw)
            continue
        try:
            out[key] = int(raw) if key == "n_samples" else float(raw)
        except (TypeError, ValueError):
            logger.warning("best_of_n.%s 무시(잘못된 값): %r", key, raw)
    return out
