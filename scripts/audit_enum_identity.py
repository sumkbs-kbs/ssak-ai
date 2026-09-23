#!/usr/bin/env python
"""cognitive core의 enum identity 비교 감사.

`value is Enum.MEMBER` / `value is not Enum.MEMBER`는 판정 주체와 값이 **같은 이름의 class를 다른
객체**로 들고 있으면(module이 두 번 로드되는 경우) False가 된다. 실제로 그것 때문에 유효한 authority
grant가 NOT_GRANTED→DEFER로 떨어지는 결함을 전체 회귀에서 한 번 겪었다(T14). 값 비교(`==`)만 쓰면
정의 module이 다른 enum(예: cognitive `RiskLevel`과 도구 `RiskLevel`)까지 같다고 본다.

그래서 두 성질을 모두 만족하는 ``models.same_enum``을 쓰고, 위 패턴이 남아 있으면 이 감사가 실패한다.

```sh
.venv/bin/python scripts/audit_enum_identity.py            # 감사만
.venv/bin/python scripts/audit_enum_identity.py --json /tmp/enum-audit.json
```
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

EXIT_OK: Final[int] = 0
EXIT_VIOLATION: Final[int] = 1

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCAN_ROOTS: Final[tuple[Path, ...]] = (
    Path("src/antigravity_k/engine/cognitive"),
    Path("src/antigravity_k/engine/cognitive_surface.py"),
    Path("src/antigravity_k/engine/growth_fixture_tools.py"),
)

# 공통 harness 계약(자기시험 · 탐지력 하한) — scripts/ 는 저장소 안의 도구 모음이라 직접 import 한다.
_SCRIPTS_DIR: Final[Path] = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from harness_contract import Cases, Floor, Probe, describe_self_test, floor_problems, probe_problems  # noqa: E402

# 감사 대상이 아닌 파일: helper와 그 문서(패턴을 설명으로 담는다).
EXEMPT: Final[frozenset[str]] = frozenset({"src/antigravity_k/engine/cognitive/models.py"})
# 탐지력 하한 — 스캔 대상이 0개면 “위반 0건” 이 아니라 “못 봄” 이다.
_MIN_SCANNED_FILES: Final[int] = 10

_ENUM_MEMBER: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Za-z0-9_]*\.[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True, slots=True)
class Violation:
    file: str
    line: int
    expression: str
    kind: str

    def as_mapping(self) -> dict[str, object]:
        return {"file": self.file, "line": self.line, "expression": self.expression, "kind": self.kind}


def _enum_member_name(node: ast.expr) -> str | None:
    """`SomeEnum.MEMBER` 형태면 그 원문을 돌려준다(대문자 attribute만)."""

    if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
        return None
    if not node.attr.isupper():
        return None
    if not re.match(r"^[A-Z][A-Za-z0-9_]*$", node.value.id):
        return None
    return f"{node.value.id}.{node.attr}"


def scan_source(source: str, *, file: str) -> tuple[Violation, ...]:
    """한 source에서 identity 비교 위반을 찾는다."""

    tree = ast.parse(source)
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        candidates = [_enum_member_name(node.left), *(_enum_member_name(c) for c in node.comparators)]
        if not any(candidates):
            continue
        for op in node.ops:
            if not isinstance(op, (ast.Is, ast.IsNot)):
                continue
            expression = ast.get_source_segment(source, node) or ""
            violations.append(
                Violation(
                    file=file,
                    line=node.lineno,
                    expression=" ".join(expression.split()),
                    kind="is" if isinstance(op, ast.Is) else "is not",
                )
            )
    return tuple(violations)


def scan_paths(paths: tuple[Path, ...] = SCAN_ROOTS) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    for root in paths:
        resolved = REPO_ROOT / root
        files = sorted(resolved.rglob("*.py")) if resolved.is_dir() else [resolved]
        for path in files:
            relative = str(path.relative_to(REPO_ROOT))
            if relative in EXEMPT:
                continue
            violations.extend(scan_source(path.read_text(encoding="utf-8"), file=relative))
    return tuple(violations)


# 자기시험 입력 — 같은 파일 안에서 위반과 허용 형태를 나란히 둔다.
_PROBE_VIOLATIONS: Final[str] = """\nRED = status is RiskLevel.HIGH
NOT_RED = status is not RiskLevel.LOW
"""
_PROBE_ALLOWED: Final[str] = """\nSAME = status == RiskLevel.HIGH
VALUE = int(status) is not 0
"""


def scanned_files(paths: tuple[Path, ...] = SCAN_ROOTS) -> tuple[str, ...]:
    """이번 스캔이 실제로 본 파일 — “위반 0건” 이 “못 봄” 인지 가른다."""

    files: list[str] = []
    for root in paths:
        resolved = REPO_ROOT / root
        candidates = sorted(resolved.rglob("*.py")) if resolved.is_dir() else [resolved]
        for path in candidates:
            relative = str(path.relative_to(REPO_ROOT))
            if relative in EXEMPT or not path.is_file():
                continue
            files.append(relative)
    return tuple(files)


def coverage_floors() -> list[Floor]:
    return [Floor("스캔한 파일", len(scanned_files()), _MIN_SCANNED_FILES)]


def self_probe() -> Probe:
    """매 실행 자기시험 — 판독 규칙(identity 비교만 · 값 비교와 리터럴 제외)을 합성 입력으로 물어본다."""

    cases = Cases()
    found = scan_source(_PROBE_VIOLATIONS, file="probe.py")
    cases.equal("위반 두 건을 찾는다", len(found), 2)
    cases.equal("연산자 종류를 구분한다", sorted(item.kind for item in found), ["is", "is not"])
    cases.equal("값 비교(==)·리터럴 비교는 허용", len(scan_source(_PROBE_ALLOWED, file="probe.py")), 0)
    cases.check("helper module 은 제외 대상이다", any("models.py" in path for path in EXEMPT))
    cases.check("감사 대상에 cognitive core 가 들어 있다", any("engine/cognitive" in str(root) for root in SCAN_ROOTS))
    return cases.probe()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_enum_identity",
        description="cognitive core의 enum identity 비교 감사 (same_enum 사용 강제)",
    )
    parser.add_argument("--json", type=Path, default=None, help="결과 JSON artifact 경로")
    parser.add_argument("--quiet", action="store_true", help="표를 출력하지 않는다")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다")
    args = parser.parse_args(argv)

    probe = self_probe()
    if args.self_test:
        print(describe_self_test("audit_enum_identity", probe))
        return EXIT_OK if probe.ok else EXIT_VIOLATION

    violations = scan_paths()
    scanned = scanned_files()
    files = sorted({root for root in SCAN_ROOTS})
    if not args.quiet:
        print(f"감사 대상: {', '.join(str(f) for f in files)} (제외 {', '.join(sorted(EXEMPT))})")
        if violations:
            for violation in violations:
                print(f"위반 {violation.file}:{violation.line} [{violation.kind}] {violation.expression}")
        else:
            print("enum identity 비교 없음 — 모든 enum 비교가 same_enum을 쓴다")
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "violations": [v.as_mapping() for v in violations],
                    "count": len(violations),
                    "scanned": [str(f) for f in files],
                    "scanned_files": list(scanned),
                    "probe": probe.as_mapping(),
                    "exempt": sorted(EXEMPT),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")

    if violations:
        return EXIT_VIOLATION
    problems = probe_problems(probe, name="audit_enum_identity") + floor_problems(coverage_floors())
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}", file=sys.stderr)
        return EXIT_VIOLATION
    if not args.quiet:
        print(f"스캔한 파일 {len(scanned)}개 — 자기시험 {probe.cases}건 재판정")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
