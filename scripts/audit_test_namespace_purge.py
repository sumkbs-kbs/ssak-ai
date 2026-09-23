"""시험 module이 **import 시점에** `antigravity_k.*` namespace 를 비우는지 감사한다.

계약(이 감사가 지키는 문장):
  pytest 는 실행 전에 모든 시험 module 을 **수집(import) 단계**에서 읽는다. 어떤 시험 파일이 module 수준에서
  `sys.modules` 를 지우면, 그 뒤에 import 되는 module 은 **같은 이름 · 다른 객체**가 되고 먼저 import 된 시험
  파일은 옛 객체를 참조한다. 그러면 같은 판정이 **실행 순서에 따라** 달라진다 (실측: 전량 회귀에서
  `authority.AuthorityProfile` 이 두 객체가 되어 유효한 grant 가 DEFER 로 떨어졌다 · ARCHITECTURE_REVIEW §1.1 ④).

  판정은 **namespace 를 가리지 않는다** — comprehension 의 조건(`if key.startswith(...)`)을 평가하지 않으므로
  다른 namespace 를 대상으로 한 purge 도 위반으로 본다. 오탐이 아니라 보수적 판정이며, 어느 namespace 든
  수집 단계에서 지우면 뒤따르는 시험 파일의 import 결과가 달라진다.

허용 형태는 하나뿐이다 — module 수준 purge 를 **명시적 트리 override**(환경변수)로 감싼 것. nx10 미러
리허설이 트렁크가 아니라 미러의 바이트를 검사하기 위해 쓰는 형태다.

경계(감사하지 않는 것): **함수 본문 안의** purge 는 실행 시점이라 수집 단계가 아니므로 이 감사의 범위 밖이다.
(`docs/qa/.../probe_view_throttle_benefit.py` 처럼 트리를 바꿔가며 재는 단독 probe 가 그 형태다.)

실행:
  .venv/bin/python scripts/audit_test_namespace_purge.py
  .venv/bin/python scripts/audit_test_namespace_purge.py --json /tmp/namespace-audit.json
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCAN_DIRS: Final[tuple[Path, ...]] = (Path("tests"), Path("docs") / "qa")


def resolve_root(root: Path | None = None) -> Path:
    """감사 대상 트리 — 지정이 없으면 저장소 루트(기존 동작 그대로)다."""

    return REPO_ROOT if root is None else Path(root).resolve()


def scan_dirs(root: Path | None = None) -> tuple[Path, ...]:
    """그 트리에서 수집 대상이 사는 자리."""

    base = resolve_root(root)
    return tuple(base / entry for entry in SCAN_DIRS)


def display_path(path: Path, *, root: Path) -> str:
    """보고에 쓰는 경로 — 지정한 트리 기준 상대 경로(밖이면 그대로)."""

    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


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

ENV_TOKENS: Final[tuple[str, ...]] = ("environ", "getenv")
MODULE_SCOPE_NODES: Final[tuple[type[ast.stmt], ...]] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)


@dataclass(frozen=True)
class Violation:
    """import 시점에 namespace 를 비우는 module 수준 문장."""

    file: str
    line: int
    kind: str
    expression: str

    def as_mapping(self) -> dict[str, object]:
        return {"file": self.file, "line": self.line, "kind": self.kind, "expression": self.expression}


def _is_sys_modules(node: ast.AST) -> bool:
    """`sys.modules` attribute 인가."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "modules"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def _is_purge_call(node: ast.AST) -> bool:
    """`sys.modules.pop(...)` / `sys.modules.clear()`."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if not _is_sys_modules(node.func.value):
        return False
    return node.func.attr in {"pop", "clear"}


def _is_purge_delete(node: ast.AST) -> bool:
    """`del sys.modules[...]`."""
    if not isinstance(node, ast.Delete):
        return False
    return any(isinstance(target, ast.Subscript) and _is_sys_modules(target.value) for target in node.targets)


def _iter_pruned(node: ast.AST) -> Iterator[ast.AST]:
    """자식 node 를 돌되 **함수·class 본문으로는 내려가지 않는다**(실행 시점 코드는 범위 밖)."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (*MODULE_SCOPE_NODES, ast.Lambda)):
            continue
        yield child
        yield from _iter_pruned(child)


def contains_purge(node: ast.AST) -> bool:
    """이 문장이 수집 단계에서 `sys.modules` 를 지우는가(문장 자체가 purge 일 수도 있다)."""
    if _is_purge_call(node) or _is_purge_delete(node):
        return True
    return any(_is_purge_call(child) or _is_purge_delete(child) for child in _iter_pruned(node))


def _guarded_by_env(test: ast.AST) -> bool:
    """`if os.environ.get(...)` 처럼 환경변수 조회로 감싼 조건인가."""
    for node in ast.walk(test):
        if isinstance(node, ast.Attribute) and node.attr in ENV_TOKENS:
            return True
        if isinstance(node, ast.Name) and node.id in ENV_TOKENS:
            return True
    return False


def _expression(node: ast.stmt) -> str:
    try:
        text = ast.unparse(node)
    except Exception:  # pragma: no cover - unparse 실패는 관찰용 문자열만 포기한다
        return f"<line {node.lineno}>"
    first = text.splitlines()[0] if text else ""
    return first[:100]


def scan_source(source: str, *, file: str) -> tuple[Violation, ...]:
    """source 한 건을 검사한다 — 감싸이지 않은 module 수준 purge 만 위반이다."""
    tree = ast.parse(source, filename=file)
    violations: list[Violation] = []

    def visit(statement: ast.stmt, guarded: bool) -> None:
        if isinstance(statement, ast.If):
            inner = guarded or _guarded_by_env(statement.test)
            for child in statement.body:
                visit(child, inner)
            for child in statement.orelse:
                visit(child, guarded)
            return
        if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
            for child in statement.body:
                visit(child, guarded)
            for child in statement.orelse:
                visit(child, guarded)
            return
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            for child in statement.body:
                visit(child, guarded)
            return
        if isinstance(statement, ast.Try):
            for child in (*statement.body, *statement.orelse, *statement.finalbody):
                visit(child, guarded)
            for handler in statement.handlers:
                for child in handler.body:
                    visit(child, guarded)
            return
        if isinstance(statement, MODULE_SCOPE_NODES):
            return  # 실행 시점 purge — 수집 단계가 아니므로 범위 밖
        if not guarded and contains_purge(statement):
            violations.append(
                Violation(
                    file=file,
                    line=statement.lineno,
                    kind="unguarded_purge",
                    expression=_expression(statement),
                )
            )

    for statement in tree.body:
        visit(statement, False)
    return tuple(violations)


# 자기시험 입력 — 수집 단계 purge(위반)와 허용 형태(트리 override·실행 시점)의 최소본.
_PROBE_UNGUARDED: Final[str] = "import sys\n\nsys.modules.pop('antigravity_k.x', None)\n"
_PROBE_GUARDED: Final[str] = (
    "import os\nimport sys\n\nif os.environ.get('NX10_FLUSH_TREE'):\n    sys.modules.pop('antigravity_k.x', None)\n"
)
_PROBE_DELETE: Final[str] = "import sys\n\ndel sys.modules['antigravity_k.x']\n"
_PROBE_IN_FUNCTION: Final[str] = "import sys\n\n\ndef purge():\n    sys.modules.pop('antigravity_k.x', None)\n"
_PROBE_UNRELATED: Final[str] = "import sys\n\nregistry = {}\nregistry.pop('x', None)\n"
_MIN_SCANNED_FILES: Final[int] = 1
_WHY_SCANNED: Final[str] = (
    "2026-09-23 기준 관측: tests/ 와 docs/qa/ 아래 수집 대상 시험 파일 537개를 스캔. "
    "하한 1은 ’위반 0건’ 과 ’수집 패턴(_is_collected)이 어긋나 한 개도 안 봤다’ 를 가르는 최소선이다."
)
_WHY_FOREIGN: Final[str] = (
    "감사 대상을 `--root` 로 바꾼 실행이다(기본은 저장소 루트). 하한 1은 그 트리에서 ’위반 0건’ 과 ’아무것도 못 봄’ "
    "을 가르는 최소선으로, 저장소 스캔과 같은 값을 쓴다 — 밖에서 red 를 재현하는 리허설이 빈손으로 끝나면 "
    "그 리허설은 아무것도 증명하지 못한다."
)


def self_probe() -> Probe:
    """매 실행 자기시험 — 판독 규칙(수집 단계·가드·실행 시점 제외)을 합성 입력으로 다시 물어본다."""

    cases = Cases()
    cases.equal("감싸이지 않은 module 수준 purge", len(scan_source(_PROBE_UNGUARDED, file="test_probe.py")), 1)
    cases.equal("del 형태도 위반", len(scan_source(_PROBE_DELETE, file="test_probe.py")), 1)
    cases.equal("트리 override 로 감싼 형태는 허용", len(scan_source(_PROBE_GUARDED, file="test_probe.py")), 0)
    cases.equal("함수 본문(실행 시점)은 범위 밖", len(scan_source(_PROBE_IN_FUNCTION, file="test_probe.py")), 0)
    cases.equal("무관한 mapping 의 pop 은 위반이 아니다", len(scan_source(_PROBE_UNRELATED, file="test_probe.py")), 0)
    cases.check(
        "위반 문장을 문장 단위로 지목한다",
        any("modules" in violation.expression for violation in scan_source(_PROBE_UNGUARDED, file="test_probe.py")),
    )
    cases.check("감사 대상은 저장소 안의 tests/ 와 docs/qa/ 다", all(entry.is_dir() for entry in scan_dirs()))
    cases.equal("감사 대상 트리를 바꾸면 그 트리만 본다", scan_paths(root=REPO_ROOT / "scripts"), ())
    cases.check(
        "없는 트리를 가리키면 빈손으로 통과하지 않는다",
        bool(floor_problems(coverage_floors(root=REPO_ROOT / "no_such_tree"))),
    )
    return cases.probe()


def scanned_files(paths: Sequence[Path] | None = None, *, root: Path | None = None) -> tuple[str, ...]:
    """이번 스캔이 실제로 본 파일 — “위반 0건” 이 “못 봄” 인지 가리는 근거다."""

    base = resolve_root(root)
    roots = tuple(paths) if paths is not None else scan_dirs(root)
    files: list[str] = []
    for entry in roots:
        if not entry.is_dir():
            continue
        for path in sorted(entry.rglob("*.py")):
            if "__pycache__" in path.parts or not _is_collected(path):
                continue
            files.append(display_path(path, root=base))
    return tuple(files)


def coverage_floors(paths: Sequence[Path] | None = None, *, root: Path | None = None) -> list[Floor]:
    """스캔 대상이 하나도 없으면 통과가 아니라 “볼 수 없음” 이다."""

    why = _WHY_SCANNED if resolve_root(root) == REPO_ROOT else _WHY_FOREIGN
    return [Floor("수집 대상 시험 파일", len(scanned_files(paths, root=root)), _MIN_SCANNED_FILES, why=why)]


def _is_collected(path: Path) -> bool:
    """pytest 가 수집하는 이름인가(`conftest.py` 또는 `test_*.py`)."""
    return path.name == "conftest.py" or (path.suffix == ".py" and path.name.startswith("test_"))


def _display(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def scan_paths(paths: Sequence[Path] | None = None, *, root: Path | None = None) -> tuple[Violation, ...]:
    """수집 대상 시험 파일 전체를 검사한다."""

    base = resolve_root(root)
    roots = tuple(paths) if paths is not None else scan_dirs(root)
    violations: list[Violation] = []
    for entry in roots:
        if not entry.is_dir():
            continue
        for path in sorted(entry.rglob("*.py")):
            if "__pycache__" in path.parts or not _is_collected(path):
                continue
            violations.extend(scan_source(path.read_text(encoding="utf-8"), file=display_path(path, root=base)))
    return tuple(violations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="import 시점 namespace purge 감사")
    _ = parser.add_argument("--json", type=Path, default=None, help="결과를 JSON 으로 남길 경로")
    _ = parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다")
    _ = parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="감사 대상 트리(기본: 저장소 루트) — 저장소 밖에서 red 를 재현하는 리허설이 쓴다",
    )
    args = parser.parse_args(argv)

    probe = self_probe()
    if args.self_test:
        print(describe_self_test("audit_test_namespace_purge", probe))
        return 0 if probe.ok else 1

    root = resolve_root(args.root)
    violations = scan_paths(root=args.root)
    scanned = scanned_files(root=args.root)
    floors = coverage_floors(root=args.root)
    payload = {
        "violations": [violation.as_mapping() for violation in violations],
        "count": len(violations),
        "probe": probe.as_mapping(),
        "floors": floor_records(floors),
        "root": str(root),
        "coverage": {"scanned": sorted(scanned)},
    }
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if violations:
        where = "저장소" if root == REPO_ROOT else str(root)
        print(f"import 시점 namespace purge 위반 {len(violations)}건 ({where})")
        for violation in violations:
            print(f"  · {violation.file}:{violation.line} {violation.expression}")
        return 1

    problems = probe_problems(probe, name="audit_test_namespace_purge") + floor_problems(floors)
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"import 시점 namespace purge 없음 — 수집 대상 시험 파일 {len(scanned)}개를 봤다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
