#!/usr/bin/env python
"""증거 문서의 **현재 상태 주장**이 아직 참인지 검사한다(“이 시험은 실패한다” 류).

증거 문서에는 시점 기록(`verified_at`)과 **지금 이 트리에 대한 주장**이 섞여 있다. 앞의 것은 스냅샷이라
낡아도 역사이고, 뒤의 것은 낡으면 **틀린 문장**이다. 실제로 그런 문장이 있었다: 세 문서가
`tests/test_tool_sandbox_coverage.py::test_all_process_execution_paths_are_accounted_for` 를
“기존 red” 라고 적고 있었는데, 그 시험은 그 뒤 등록으로 **green** 이 됐다.

이 감사가 보는 범위를 좁게 잡은 이유:

  * **test node id 를 지목한 문장만** 본다(`tests/x.py::test_y`). 파일 단위 서술은 “그렇지 않으면 실패한다”
    같은 조건문과 섞여 기계가 참·거짓을 가를 수 없다.    * **코드 블록 안은 보지 않는다.** 펜스 안은 그때 돌린 명령·출력의 **기록**이고, 펜스 밖 산문만 주장이다.
  * 상태 어휘(red·실패·failed ↔ green·통과·passed)가 같은 줄에 있어야 주장으로 센다.
  * **증거 문서만 본다.** 리뷰 문서는 증거의 관찰을 **인용·분석**하므로, 낡은 문장을 그대로 옮겨 적은
    문단이 주장처럼 보인다(실제로 그랬다). 관찰을 주장하는 자리는 증거 문서다.

낡은 주장을 지우지 않고 인정하는 방법은 **정정 표기**다: 그 줄 뒤 5줄 안에 `> ... 정정 YYYY-MM-DD` 형태의
인용문이 있으면 “그 시점의 관찰 + 정정”으로 본다(역사를 지우지 않는다는 규칙과 같은 방식).

```sh
.venv/bin/python scripts/audit_state_claims.py             # 표 + 판정
.venv/bin/python scripts/audit_state_claims.py --emit-json  # 리뷰 검사가 읽는 형태
.venv/bin/python scripts/audit_state_claims.py --gate       # 낡은 주장·정정 누락이면 exit 1
```
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

EXIT_OK: Final[int] = 0
EXIT_GATE: Final[int] = 1

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DOCS_ROOT: Final[Path] = Path("docs/ssak-ai-core")
EVIDENCE_DIR: Final[Path] = DOCS_ROOT / "evidence"

_NODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"(tests/[A-Za-z0-9_/]+\.py)::([A-Za-z0-9_\[\]\-]+)")
_FAILS: Final[tuple[str, ...]] = ("기존 red", "red", "실패", "failed")
_PASSES: Final[tuple[str, ...]] = ("통과", "passed", "green")
# 정정 표기 — 이 줄 뒤 가까이에 있으면 “그 시점 관찰 + 정정”으로 본다.
_CORRECTION_WINDOW: Final[int] = 5
# 인용문(`>`) 안에 “정정” 과 날짜가 함께 있어야 정정으로 본다 — 날짜 위치는 묻지 않는다.
_CORRECTION_PATTERN: Final[re.Pattern[str]] = re.compile(r">(?=.*정정)(?=.*\d{4}-\d{2}-\d{2}).*")


@dataclass(frozen=True, slots=True)
class Claim:
    """한 문서가 지금 트리에 대해 한 상태 주장."""

    doc: str
    line: int
    node: str
    claimed: str  # fails | passes
    actual: str  # fails | passes | unknown
    corrected: bool

    @property
    def corrected_mismatch(self) -> bool:
        """주장과 실제가 다르지만 정정 표기가 붙은 경우 — 역사로 남긴 상태다."""

        return self.actual not in {"unknown", self.claimed} and self.corrected

    @property
    def stale(self) -> bool:
        return self.actual != "unknown" and self.actual != self.claimed and not self.corrected

    @property
    def status(self) -> str:
        """판정 이름 — 문장에 쓰이는 상태 표기와 계산 상태를 분리한다."""

        if self.actual == "unknown":
            return "unknown"
        if self.actual == self.claimed:
            return "ok"
        return "fixed" if self.corrected else "stale"

    def as_mapping(self) -> dict[str, object]:
        return {
            "doc": self.doc,
            "line": self.line,
            "node": self.node,
            "claimed": self.claimed,
            "actual": self.actual,
            "corrected": self.corrected,
            "status": self.status,
            "stale": self.stale,
        }


def display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def documents() -> list[Path]:
    """감사 대상 문서 — **증거 문서**만.

    리뷰 문서는 증거가 한 관찰을 인용하며 낡은 문장을 해설하므로, 그 문단이 상태 주장처럼 잡힌다.
    관찰을 주장하는 자리는 증거 문서이므로 범위를 그쪽으로 좁힌다(넓히면 자기 해설로 오탐이 난다).
    """

    return sorted(EVIDENCE_DIR.glob("*.md"))


def _claimed_state(line: str) -> str | None:
    """이 줄이 실패를 주장하는지 통과를 주장하는지 — 둘 다면 더 강한 쪽(실패)으로 본다."""

    if any(word in line for word in _FAILS):
        return "fails"
    if any(word in line for word in _PASSES):
        return "passes"
    return None


def _corrected(lines: list[str], index: int) -> bool:
    """주장 줄 뒤 가까이에 정정 표기가 있는가."""

    window = lines[index + 1 : index + 1 + _CORRECTION_WINDOW]
    return any(_CORRECTION_PATTERN.search(line) for line in window)


def extract_claims(docs: list[Path] | None = None) -> list[Claim]:
    """산문(펜스 밖)에서 test node 를 지목한 상태 주장만 뽑는다."""

    claims: list[Claim] = []
    for doc in docs if docs is not None else documents():
        lines = doc.read_text(encoding="utf-8").splitlines()
        fenced = False
        for index, line in enumerate(lines):
            if line.strip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            claimed = _claimed_state(line)
            if claimed is None:
                continue
            for match in _NODE_PATTERN.finditer(line):
                node = f"{match.group(1)}::{match.group(2)}"
                claims.append(
                    Claim(
                        doc=doc.name,
                        line=index + 1,
                        node=node,
                        claimed=claimed,
                        actual="unknown",
                        corrected=_corrected(lines, index),
                    )
                )
    # 같은 문서가 같은 node 를 여러 번 주장하면 한 번만 남긴다(판정은 node 단위다).
    unique: dict[tuple[str, str], Claim] = {}
    for claim in claims:
        unique.setdefault((claim.doc, claim.node), claim)
    return sorted(unique.values(), key=lambda claim: (claim.doc, claim.line))


def run_node(node: str, timeout: int = 180) -> str:
    """그 node 를 지금 돌려 본다 — 실패면 fails, 통과면 passes, 판정 불가면 unknown."""

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            node,
            "-q",
            "--tb=no",
            "-p",
            "no:randomly",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    # pytest 의 4(사용 오류)·5(수집 0)는 “그 node 를 돌리지 못했다” 는 뜻이다 — 실패와 구분한다.
    if result.returncode in {4, 5}:
        return "unknown"
    return "passes" if result.returncode == 0 else "fails"


def measure(docs: list[Path] | None = None) -> list[Claim]:
    """주장을 뽑아 각 node 를 실제로 돌려 판정한다."""

    judged: list[Claim] = []
    cache: dict[str, str] = {}
    for claim in extract_claims(docs):
        if claim.node not in cache:
            cache[claim.node] = run_node(claim.node)
        judged.append(
            Claim(
                doc=claim.doc,
                line=claim.line,
                node=claim.node,
                claimed=claim.claimed,
                actual=cache[claim.node],
                corrected=claim.corrected,
            )
        )
    return judged


def as_mapping(claims: list[Claim]) -> dict[str, object]:
    return {
        "command": ["python", "scripts/audit_state_claims.py"],
        "claims": [claim.as_mapping() for claim in claims],
        "counts": {
            "claims": len(claims),
            "ok": sum(1 for claim in claims if claim.status == "ok"),
            "fixed": sum(1 for claim in claims if claim.status == "fixed"),
            "stale": sum(1 for claim in claims if claim.stale),
            "unknown": sum(1 for claim in claims if claim.actual == "unknown"),
        },
    }


def describe(claims: list[Claim]) -> str:
    lines = [f"[state-claims] 산문 상태 주장 {len(claims)}건"]
    marks = {"ok": "OK     ", "fixed": "FIXED  ", "stale": "STALE  ", "unknown": "UNKNOWN"}
    for claim in claims:
        mark = marks[claim.status]
        note = " · 정정 표기 있음" if claim.corrected else ""
        lines.append(
            f"  {mark} {claim.doc}:{claim.line} · {claim.node} · 주장 {claim.claimed} / 실제 {claim.actual}{note}"
        )
    lines.append("* 낡은 주장은 지우지 말고 그 줄 가까이에 `> ... 정정 YYYY-MM-DD` 를 붙인다(역사를 지우지 않는다).")
    return "\n".join(lines)


def gate_failures(claims: list[Claim]) -> list[str]:
    problems: list[str] = []
    unknown = [claim for claim in claims if claim.actual == "unknown"]
    if unknown:
        problems.append("상태를 판정하지 못한 주장: " + ", ".join(f"{claim.doc}:{claim.node}" for claim in unknown))
    stale = [claim for claim in claims if claim.stale]
    if stale:
        problems.append(
            "지금 트리와 어긋나는 상태 주장(정정 표기 없음): "
            + ", ".join(f"{claim.doc}:{claim.line}:{claim.node}(주장 {claim.claimed})" for claim in stale)
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="증거 문서의 현재 상태 주장을 실제 시험으로 재판정한다")
    parser.add_argument("--gate", action="store_true", help="낡은 주장·판정 불가가 있으면 실패")
    parser.add_argument("--emit-json", action="store_true", help="측정 결과만 stdout 으로 낸다")
    args = parser.parse_args(argv)

    claims = measure()
    if args.emit_json:
        print(json.dumps(as_mapping(claims), ensure_ascii=False, indent=2))
        return EXIT_OK
    print(describe(claims))
    if not args.gate:
        return EXIT_OK
    problems = gate_failures(claims)
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_GATE if problems else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
