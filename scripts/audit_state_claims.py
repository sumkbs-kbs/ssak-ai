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

감사자 자신이 조용히 눈이 머는 것을 막는 두 장치:

  * **운영 자기시험(self-probe)** — 매 실행마다 어휘·펜스 처리·정정 창을 합성 입력으로 다시 재판정한다.
    어휘를 지우거나 창을 망가뜨리면 그 실행이 바로 실패한다(“주장 0건” 으로 조용히 통과하지 않는다).
  * **탐지력 하한(coverage floor)** — 주장 수뿐 아니라 **node 를 지목한 산문 줄 수(mention)** 를 함께 센다.
    mention 은 상태 어휘가 없어도 세므로 주장보다 큰 상한 집합이다. mention·주장이 하한 아래로 가면 게이트가
    실패한다 — 문서가 정말 주장을 그만둔 것이면 하한 상수를 **근거와 함께 사람이 내린다**.

```sh
.venv/bin/python scripts/audit_state_claims.py             # 표 + 자기시험 + 판정
.venv/bin/python scripts/audit_state_claims.py --emit-json  # 리뷰 검사가 읽는 형태
.venv/bin/python scripts/audit_state_claims.py --gate       # 낡은 주장·정정 누락·탐지력 하한 미달이면 exit 1
.venv/bin/python scripts/audit_state_claims.py --self-test  # 자기시험만 돌리고 종료
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

# 공통 harness 계약(자기시험 · 탐지력 하한) — scripts/ 는 저장소 안의 도구 모음이라 직접 import 한다.
_SCRIPTS_DIR: Final[Path] = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from harness_contract import (  # noqa: E402
    Cases,
    Floor,
    Probe,
    floor_problems,
    floor_records,
)

_NODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"(tests/[A-Za-z0-9_/]+\.py)::([A-Za-z0-9_\[\]\-]+)")
_FAILS: Final[tuple[str, ...]] = ("기존 red", "red", "실패", "failed")
_PASSES: Final[tuple[str, ...]] = ("통과", "passed", "green")
# 정정 표기 — 이 줄 뒤 가까이에 있으면 “그 시점 관찰 + 정정”으로 본다.
_CORRECTION_WINDOW: Final[int] = 5
# 자기시험이 요구하는 최소 어휘 — 상수를 쓸어 보기만 하면 **단어를 지우는 변경**을 못 잡는다.
# 그러므로 “이 말들은 반드시 분류되어야 한다” 를 여기에 고정하고, 빠지면 자기시험이 실패한다.
_REQUIRED_FAIL_WORDS: Final[tuple[str, ...]] = ("기존 red", "red", "실패", "failed")
_REQUIRED_PASS_WORDS: Final[tuple[str, ...]] = ("통과", "passed", "green")
# 탐지력 하한 — 감사가 조용히 눈이 머는 것을 막는다(주장 0건으로 조용히 통과하지 않는다).
# 값만 두면 나중에 누구도 그것을 낮춰도 되는지 판단할 수 없으므로 **근거를 값과 함께 기록**한다.
# 근거는 하한을 정한 시점의 관측이고, 관측이 달라지면 artifact(`state_claims.json`)의 `floors` 가 그 사실을 보여준다.
_MIN_MENTIONS: Final[int] = 1
_MIN_CLAIMS: Final[int] = 1
_WHY_MENTIONS: Final[str] = (
    "2026-09-23 기준 관측: 증거 문서 16개 중 node(test file::test name)를 산문에서 지목한 줄 6개. "
    "하한을 1로 둔 것은 ‘얼마나 많이 보이나’ 가 아니라 ‘보는 능력이 0이 됐나’ 를 잡기 위해서다. "
    "증거 문서가 정말로 시험을 지목하는 문장을 그만두면 이 값을 근거와 함께 내린다."
)
_WHY_CLAIMS: Final[str] = (
    "2026-09-23 기준 관측: 같은 줄에 상태 어휘가 있어 주장으로 센 것 4건(mention 6 중 2줄은 상태 어휘 없음). "
    "어휘·펜스·범위 규칙이 깨지면 이 수가 0이 되므로, 하한은 그 순간을 잡는 안전선이다."
)
# 기록 artifact — 하한의 근거와 그때의 관측을 함께 남긴다(리뷰가 저장본과 새 측정을 대조한다).
ARTIFACT: Final[Path] = Path("docs/ssak-ai-core/evidence/state_claims.json")
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


def _prose_lines(lines: list[str]) -> list[tuple[int, str]]:
    """펜스 밖 줄만 `(0-based index, line)` 로 낸다 — 코드 블록은 그때 돌린 명령·출력의 기록이다."""

    prose: list[tuple[int, str]] = []
    fenced = False
    for index, line in enumerate(lines):
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            prose.append((index, line))
    return prose


def count_mentions(docs: list[Path] | None = None) -> int:
    """node 를 지목한 **산문 줄 수** — 상태 어휘가 없어도 센다(주장의 상한 집합)."""

    total = 0
    for doc in docs if docs is not None else documents():
        lines = doc.read_text(encoding="utf-8").splitlines()
        total += sum(1 for _, line in _prose_lines(lines) if _NODE_PATTERN.search(line))
    return total


def claims_from_lines(name: str, lines: list[str]) -> list[Claim]:
    """한 문서의 줄들에서 주장을 뽑는다 — 파일을 안 건드리는 순수 판독(자기시험이 쓴다)."""

    claims: list[Claim] = []
    for index, line in _prose_lines(lines):
        claimed = _claimed_state(line)
        if claimed is None:
            continue
        for match in _NODE_PATTERN.finditer(line):
            claims.append(
                Claim(
                    doc=name,
                    line=index + 1,
                    node=f"{match.group(1)}::{match.group(2)}",
                    claimed=claimed,
                    actual="unknown",
                    corrected=_corrected(lines, index),
                )
            )
    return claims


def extract_claims(docs: list[Path] | None = None) -> list[Claim]:
    """산문(펜스 밖)에서 test node 를 지목한 상태 주장만 뽑는다."""

    claims: list[Claim] = []
    for doc in docs if docs is not None else documents():
        claims.extend(claims_from_lines(doc.name, doc.read_text(encoding="utf-8").splitlines()))
    # 같은 문서가 같은 node 를 여러 번 주장하면 한 번만 남긴다(판정은 node 단위다).
    unique: dict[tuple[str, str], Claim] = {}
    for claim in claims:
        unique.setdefault((claim.doc, claim.node), claim)
    return sorted(unique.values(), key=lambda claim: (claim.doc, claim.line))


def self_probe() -> Probe:
    """매 실행 자기시험 — 감사자가 조용히 눈이 머는 것을 막는다.

    검사 대상은 세 가지다: ① 상태 어휘가 실제로 분류되는가(어휘 상수를 쓸어 본다),
    ② 펜스 안 문장은 주장으로 세지 않는가, ③ 정정 창이 가까운 표기만 인정하는가.
    """

    cases = Cases()
    node = "tests/x_sample.py::test_y"
    fence = "`" * 3

    cases.covers("실패 어휘", _REQUIRED_FAIL_WORDS, _FAILS)
    cases.covers("통과 어휘", _REQUIRED_PASS_WORDS, _PASSES)

    for word in _FAILS:
        found = claims_from_lines("probe.md", [f"`{node}` 는 {word}."])
        cases.check(f"실패 어휘 {word!r} 가 주장으로 판독된다", len(found) == 1 and found[0].claimed == "fails")
    for word in _PASSES:
        found = claims_from_lines("probe.md", [f"`{node}` 는 {word}."])
        cases.check(f"통과 어휘 {word!r} 가 주장으로 판독된다", len(found) == 1 and found[0].claimed == "passes")

    cases.check(
        "펜스 안 문장을 주장으로 세지 않는다",
        not claims_from_lines("probe.md", [fence, f"`{node}` 는 실패한다.", fence]),
    )
    cases.check(
        "상태 어휘 없는 문장을 주장으로 세지 않는다", not claims_from_lines("probe.md", [f"`{node}` 를 돌린다."])
    )

    near = claims_from_lines("probe.md", [f"`{node}` 는 실패한다.", "", "> **정정 2026-09-23.** 지금은 green 이다."])
    cases.check("가까운 정정 표기를 인정한다", len(near) == 1 and near[0].corrected)
    far_lines = (
        [f"`{node}` 는 실패한다."] + [f"산문 {i}" for i in range(_CORRECTION_WINDOW + 2)] + ["> **정정 2026-09-23.**"]
    )
    far = claims_from_lines("probe.md", far_lines)
    cases.check("먼 정정 표기를 가까운 것으로 보지 않는다", len(far) == 1 and not far[0].corrected)

    statuses = {
        ("fails", False): "ok",
        ("passes", False): "stale",
        ("passes", True): "fixed",
        ("unknown", False): "unknown",
    }
    for (actual, corrected), expected in statuses.items():
        cases.equal(
            f"상태 계산(실제 {actual}·정정 {corrected})",
            Claim(doc="probe.md", line=1, node=node, claimed="fails", actual=actual, corrected=corrected).status,
            expected,
        )
    return cases.probe()


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


def coverage_floors(mentions: int, claims: int) -> list[Floor]:
    """하한과 **그 근거**를 함께 돌려준다 — 값·관측·여유·왜 그 값인지."""

    return [
        Floor("node 지목 산문", mentions, _MIN_MENTIONS, why=_WHY_MENTIONS),
        Floor("상태 주장", claims, _MIN_CLAIMS, why=_WHY_CLAIMS),
    ]


def as_mapping(claims: list[Claim], mentions: int, probe: Probe, docs: int) -> dict[str, object]:
    return {
        "command": ["python", "scripts/audit_state_claims.py"],
        "claims": [claim.as_mapping() for claim in claims],
        "coverage": {"docs": docs, "mentions": mentions, "min_mentions": _MIN_MENTIONS},
        "floors": floor_records(coverage_floors(mentions, len(claims))),
        "probe": probe.as_mapping(),
        "counts": {
            "claims": len(claims),
            "ok": sum(1 for claim in claims if claim.status == "ok"),
            "fixed": sum(1 for claim in claims if claim.status == "fixed"),
            "stale": sum(1 for claim in claims if claim.stale),
            "unknown": sum(1 for claim in claims if claim.actual == "unknown"),
        },
    }


def describe(claims: list[Claim], mentions: int, probe: Probe, docs: int) -> str:
    lines = [
        f"[state-claims] 증거 문서 {docs}개 · node 지목 산문 {mentions}줄 · 상태 주장 {len(claims)}건",
        f"[self-probe] {probe.cases}건 재판정 — " + ("통과" if probe.ok else "실패: " + "; ".join(probe.failures)),
    ]
    marks = {"ok": "OK     ", "fixed": "FIXED  ", "stale": "STALE  ", "unknown": "UNKNOWN"}
    for claim in claims:
        mark = marks[claim.status]
        note = " · 정정 표기 있음" if claim.corrected else ""
        lines.append(
            f"  {mark} {claim.doc}:{claim.line} · {claim.node} · 주장 {claim.claimed} / 실제 {claim.actual}{note}"
        )
    lines.append("* 낡은 주장은 지우지 말고 그 줄 가까이에 `> ... 정정 YYYY-MM-DD` 를 붙인다(역사를 지우지 않는다).")
    lines.append("* 자기시험이 실패하면 판독 규칙이 깨진 것이다 — 판정 결과와 무관하게 이 실행은 실패다.")
    return "\n".join(lines)


def gate_failures(claims: list[Claim], mentions: int, probe: Probe) -> list[str]:
    problems: list[str] = []
    if not probe.ok:
        problems.append("자기시험 실패(판독 규칙이 깨졌다): " + "; ".join(probe.failures))
    problems.extend(floor_problems(coverage_floors(mentions, len(claims))))
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
    parser.add_argument("--gate", action="store_true", help="낡은 주장·판정 불가·탐지력 하한 미달이면 실패")
    parser.add_argument("--emit-json", action="store_true", help="측정 결과만 stdout 으로 낸다")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다(시험을 돌리지 않는다)")
    parser.add_argument("--artifact", type=Path, default=ARTIFACT, help="하한 근거·관측을 남길 artifact 경로")
    args = parser.parse_args(argv)

    docs = documents()
    probe = self_probe()
    if args.self_test:
        print(describe([], count_mentions(docs), probe, len(docs)))
        return EXIT_OK if probe.ok else EXIT_GATE

    claims = measure()
    mentions = count_mentions(docs)
    payload = as_mapping(claims, mentions, probe, len(docs))
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    print(describe(claims, mentions, probe, len(docs)))
    for floor in coverage_floors(mentions, len(claims)):
        print(f"  하한 {floor.label}: 관측 {floor.observed} · 최소 {floor.minimum} · 여유 {floor.margin}")
    print(f"측정 artifact: {display(args.artifact)}")
    if not args.gate:
        return EXIT_OK
    problems = gate_failures(claims, mentions, probe)
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_GATE if problems else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
