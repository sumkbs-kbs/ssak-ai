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

# 감사 대상이 아닌 파일: helper와 그 문서(패턴을 설명으로 담는다).
EXEMPT: Final[frozenset[str]] = frozenset({"src/antigravity_k/engine/cognitive/models.py"})

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_enum_identity",
        description="cognitive core의 enum identity 비교 감사 (same_enum 사용 강제)",
    )
    parser.add_argument("--json", type=Path, default=None, help="결과 JSON artifact 경로")
    parser.add_argument("--quiet", action="store_true", help="표를 출력하지 않는다")
    args = parser.parse_args(argv)

    violations = scan_paths()
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
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
