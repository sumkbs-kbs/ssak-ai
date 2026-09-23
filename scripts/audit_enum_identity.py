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

from harness_contract import (  # noqa: E402
    Cases,
    Floor,
    Probe,
    describe_self_test,
    floor_problems,
    floor_records,
    probe_problems,
)

# 감사 대상이 아닌 파일: helper와 그 문서(패턴을 설명으로 담는다).
EXEMPT: Final[frozenset[str]] = frozenset({"src/antigravity_k/engine/cognitive/models.py"})
# 탐지력 하한 — 스캔 대상이 0개면 “위반 0건” 이 아니라 “못 봄” 이다.
_MIN_SCANNED_FILES: Final[int] = 10
_WHY_SCANNED: Final[str] = (
    "2026-09-23 기준 관측: cognitive core 경로에서 21개 파일을 스캔(제외 1 = same_enum 파이프). "
    "하한 10은 경로가 통째로 어긋나거나 순회가 빈손으로 끝나는 순간을 잡는 안전선이다 — ’위반 0건’ 과 ’못 봄’ 을 가른다."
)
_MIN_FOREIGN_FILES: Final[int] = 1
_WHY_FOREIGN: Final[str] = (
    "감사 대상을 `--root` 로 바꾼 실행이다(기본은 저장소 루트). 하한 1은 그 트리에서 ’위반 0건’ 과 ’아무것도 못 봄’ "
    "을 가르는 최소선이다 — 저장소 하한(10)은 저장소를 스캔할 때만 쓴다. 밖의 트리를 저장소 기준으로 재면 오탐이고, "
    "빈손으로 끝나면 그것이 이 감사의 red 재현(리허설)을 조용히 통과시킨다."
)


def resolve_root(root: Path | None = None) -> Path:
    """감사 대상 트리 — 지정이 없으면 저장소 루트(기존 동작 그대로)다."""

    return REPO_ROOT if root is None else Path(root).resolve()


def display_path(path: Path, *, root: Path) -> str:
    """보고에 쓰는 경로 — 지정한 트리 기준 상대 경로(밖이면 그대로)."""

    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


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


def scan_paths(paths: tuple[Path, ...] = SCAN_ROOTS, *, root: Path | None = None) -> tuple[Violation, ...]:
    base = resolve_root(root)
    violations: list[Violation] = []
    for entry in paths:
        resolved = base / entry
        files = sorted(resolved.rglob("*.py")) if resolved.is_dir() else [resolved]
        for path in files:
            if not path.is_file():
                continue  # 없는 감사 대상은 사고가 아니라 “못 봄” 이다 — 하한이 그 사실을 판정한다
            relative = display_path(path, root=base)
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


def scanned_files(paths: tuple[Path, ...] = SCAN_ROOTS, *, root: Path | None = None) -> tuple[str, ...]:
    """이번 스캔이 실제로 본 파일 — “위반 0건” 이 “못 봄” 인지 가른다."""

    base = resolve_root(root)
    files: list[str] = []
    for entry in paths:
        resolved = base / entry
        candidates = sorted(resolved.rglob("*.py")) if resolved.is_dir() else [resolved]
        for path in candidates:
            relative = display_path(path, root=base)
            if relative in EXEMPT or not path.is_file():
                continue
            files.append(relative)
    return tuple(files)


def coverage_floors(*, root: Path | None = None) -> list[Floor]:
    """탐지력 하한 — 저장소 스캔과 바꿔 끼운 트리는 하한이 다르다(값과 근거를 함께 낸다)."""

    observed = len(scanned_files(root=root))
    if resolve_root(root) == REPO_ROOT:
        return [Floor("스캔한 파일", observed, _MIN_SCANNED_FILES, why=_WHY_SCANNED)]
    return [Floor("스캔한 파일", observed, _MIN_FOREIGN_FILES, why=_WHY_FOREIGN)]


def self_probe() -> Probe:
    """매 실행 자기시험 — 판독 규칙(identity 비교만 · 값 비교와 리터럴 제외)을 합성 입력으로 물어본다."""

    cases = Cases()
    found = scan_source(_PROBE_VIOLATIONS, file="probe.py")
    cases.equal("위반 두 건을 찾는다", len(found), 2)
    cases.equal("연산자 종류를 구분한다", sorted(item.kind for item in found), ["is", "is not"])
    cases.equal("값 비교(==)·리터럴 비교는 허용", len(scan_source(_PROBE_ALLOWED, file="probe.py")), 0)
    cases.check("helper module 은 제외 대상이다", any("models.py" in path for path in EXEMPT))
    cases.check("감사 대상에 cognitive core 가 들어 있다", any("engine/cognitive" in str(root) for root in SCAN_ROOTS))
    cases.equal("감사 대상 트리를 바꾸면 그 트리만 본다", scan_paths(root=REPO_ROOT / "docs"), ())
    cases.equal("저장소 스캔은 저장소 하한을 쓴다", coverage_floors()[0].minimum, _MIN_SCANNED_FILES)
    cases.equal(
        "바꿔 끼운 트리는 하한도 그 트리 기준이다",
        coverage_floors(root=REPO_ROOT / "src")[0].minimum,
        _MIN_FOREIGN_FILES,
    )
    cases.check(
        "없는 트리를 가리키면 빈손으로 통과하지 않는다",
        bool(floor_problems(coverage_floors(root=REPO_ROOT / "no_such_tree"))),
    )
    return cases.probe()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_enum_identity",
        description="cognitive core의 enum identity 비교 감사 (same_enum 사용 강제)",
    )
    parser.add_argument("--json", type=Path, default=None, help="결과 JSON artifact 경로")
    parser.add_argument("--quiet", action="store_true", help="표를 출력하지 않는다")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="감사 대상 트리(기본: 저장소 루트) — 저장소 밖에서 red 를 재현하는 리허설이 쓴다",
    )
    args = parser.parse_args(argv)

    probe = self_probe()
    if args.self_test:
        print(describe_self_test("audit_enum_identity", probe))
        return EXIT_OK if probe.ok else EXIT_VIOLATION

    root = resolve_root(args.root)
    violations = scan_paths(root=args.root)
    scanned = scanned_files(root=args.root)
    floors = coverage_floors(root=args.root)
    files = sorted({str(entry) for entry in SCAN_ROOTS})
    if not args.quiet:
        where = "저장소" if root == REPO_ROOT else str(root)
        print(f"감사 대상({where}): {', '.join(files)} (제외 {', '.join(sorted(EXEMPT))})")
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
                    "root": str(root),
                    "probe": probe.as_mapping(),
                    "floors": floor_records(floors),
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
    problems = probe_problems(probe, name="audit_enum_identity") + floor_problems(floors)
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}", file=sys.stderr)
        return EXIT_VIOLATION
    if not args.quiet:
        print(f"스캔한 파일 {len(scanned)}개 — 자기시험 {probe.cases}건 재판정")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
