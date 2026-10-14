"""계약 시험(승격본) — **문서가 시키는 것과 저장소의 사실이 어긋나지 않게** 고정한다.

왜 계약인가: 이 카드는 문서 오류 하나로 시간을 태웠다. `SCOPE.md` 는 `clean-machine-runtime` 을
`BLOCKED_EXTERNAL`(깨끗한 호스트 필요)로 적었지만, 스크립트를 읽어보니 클린룸 재현 검사였고 실제로
통과했다. 문서와 사실이 갈라지면 **다음 사람이 그 문서를 믿고 움직인다**.

검사하는 것(전부 정적·hermetic — 서브프로세스나 네트워크를 쓰지 않는다. `--help` 를 실제로 돌리는
깊은 점검은 `scripts/verify_docs_commands.py` 가 담당하고, 이 시험은 그 데이터를 계약으로 고정한다):
  1. 문서가 안내한 CLI 플래그가 그 스크립트 소스에 실제로 있는가
  2. 문서의 `AGK_*` 환경변수가 코드에 있거나, pydantic `env_prefix` + 필드명으로 파생되는가
  3. 문서가 참조하는 경로가 실재하는가
  4. 문서의 로컬 상대 링크가 실재하는 파일을 가리키는가
  5. 커밋 대상(dirty+untracked), 또는 clean 트리의 tracked production/config에 비밀 패턴이 없는가

승격 상태: 이 파일은 `tests/test_docs_toolchain_contract.py` 로 옮겨지고, `verify_docs_commands.py` 는
`scripts/verify_docs_commands.py` 로 옮겨진다. 그 전에도 통과하도록 도구를 **탐색**해서 찾는다.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest


def _repo_root() -> Path:
    """`pyproject.toml` 을 만날 때까지 올라간다 — `docs/…` 스테이징과 `tests/` 양쪽에서 성립한다."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise AssertionError("저장소 루트를 찾지 못했다(pyproject.toml 없음)")


REPO = _repo_root()
_TOOL_CANDIDATES = (
    REPO / "scripts" / "verify_docs_commands.py",
    REPO / "docs" / "qa" / "2026-09-16-followup" / "nx10" / "verify_docs_commands.py",
)


def _load_tool() -> object:
    path = next((candidate for candidate in _TOOL_CANDIDATES if candidate.is_file()), None)
    if path is None:
        pytest.fail(f"문서 검사기를 찾지 못했다: {[str(c.relative_to(REPO)) for c in _TOOL_CANDIDATES]}")
    spec = importlib.util.spec_from_file_location("verify_docs_commands_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 가 sys.modules 를 찾는다 — 먼저 등록한다
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def _script_source(relative: str) -> str:
    path = REPO / relative
    assert path.is_file(), f"문서가 안내하는 스크립트가 없다: {relative}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("where", "script", "flags"),
    [
        ("CLOSURE_RUNBOOK/ledger", "scripts/ga_gate.py", ("--manifest", "--output", "--only", "--merge-into")),
        ("CLOSURE_RUNBOOK §0·§4", "scripts/ga_gate_verify.py", ("--report", "--manifest")),
        (
            "docs/09 CR-01 migration",
            "scripts/migrate_conversation_storage.py",
            ("--storage-dir", "--apply", "--dry-run", "--verify-only", "--backup-dir", "--report"),
        ),
        ("nx02 격리 절차", "scripts/run_dashboard_e2e_ambient.py", ()),
        ("docs/09 SC-1~6", "scripts/val02_staging.py", ()),
        ("docs/09 clean-room", "scripts/verify_clean_machine.sh", ("--ref",)),
    ],
)
def test_documented_cli_flags_exist_in_the_script_source(where: str, script: str, flags: tuple[str, ...]) -> None:
    """문서가 안내한 플래그가 스크립트에 실제로 있다(정적 확인 — 없는 플래그를 안내하지 않는다)."""
    source = _script_source(script)
    # 파이썬은 `add_argument("--flag", …)`, 셸은 사용문에 `--ref` 로 적는다 — 둘 다 잡도록
    # 따옴표를 요구하지 않고 소스 내 등장으로 본다(없는 플래그를 안내하는 것이 문제이므로).
    missing = [flag for flag in flags if flag not in source]
    assert not missing, f"{where} → {script} 에 없는 플래그: {missing}"


def test_documented_agk_env_vars_exist_or_are_prefix_derived() -> None:
    """문서의 `AGK_*` 가 코드에 직접 있거나, pydantic `env_prefix` + 필드명 파생인가.

    이 검사기는 처음에 `AGK_SERVER_PORT` 를 STALE 로 잘못 보고했다 — `ServerConfig` 는
    `env_prefix="AGK_SERVER_"` 이므로 그 이름은 코드에 **문자열로 없다**. 검사기가 틀렸지
    문서가 틀리지 않았고, 그래서 파생 규칙을 검사에 넣었다.
    """
    code_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in list((REPO / "src").rglob("*.py")) + list((REPO / "scripts").glob("*.py"))
    )
    prefixes = set(re.findall(r"env_prefix\s*=\s*['\"]([A-Z0-9_]+)['\"]", code_text))

    documented: dict[str, set[str]] = {}
    for relative in TOOL.DOCS:  # type: ignore[attr-defined]
        doc = REPO / relative
        if not doc.is_file():
            continue
        for name in re.findall(r"\bAGK_[A-Z0-9_]+\b", doc.read_text(encoding="utf-8")):
            documented.setdefault(name, set()).add(Path(relative).name)

    stale = [
        name
        for name in documented
        if name not in code_text and not any(name.startswith(p) and len(name) > len(p) for p in prefixes)
    ]
    assert not stale, f"문서에만 있고 코드에 없는 AGK_* 변수: {sorted(stale)}"


def test_referenced_paths_exist() -> None:
    """문서가 참조하는 경로가 실재한다(경로 이동·이름 변경을 문서가 따라가지 못한 경우를 잡는다)."""
    missing = [p for p in TOOL.REFERENCED_PATHS if not (REPO / p).exists()]  # type: ignore[attr-defined]
    assert not missing, f"문서가 참조하지만 없는 경로: {missing}"


def test_local_relative_links_resolve() -> None:
    """문서의 로컬 상대 링크가 실재하는 파일을 가리킨다(깨진 `../` 깊이를 잡는다)."""
    docs = [REPO / rel for rel in TOOL.DOCS]  # type: ignore[attr-defined]
    docs += sorted((REPO / "docs" / "qa" / "2026-09-16-followup").rglob("*.md"))
    broken: list[str] = []
    checked = 0
    for doc in docs:
        if not doc.is_file():
            continue
        text = doc.read_text(encoding="utf-8", errors="replace")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            bare = target.split("#")[0].split(" ")[0]
            if not bare or target.startswith(("http://", "https://", "mailto:", "/", "#")):
                continue
            if re.match(r"^[\w./-]+:\d+$", target):
                continue
            checked += 1
            if not (doc.parent / bare).resolve().exists():
                broken.append(f"{doc.relative_to(REPO)} → {target}")
    assert checked > 0, "검사한 링크가 0개다 — 문서 집합이 비었거나 파서가 깨졌다"
    assert not broken, "깨진 로컬 상대 링크: " + " | ".join(broken[:8])


# Clean-tree baseline: tracked production and deployment/package configuration.
# Historical evidence and fixture corpora are not this baseline; every dirty/untracked
# text candidate still uses the original content rules, regardless of its directory.
_BASELINE_PATHS: Final = (
    "src/",
    "scripts/",
    "config/",
    "dashboard/src/",
    ".github/",
    "deploy/",
    "desktop/",
    "vscode-extension/src/",
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "uv.lock",
    "config.yaml",
    "policy.yaml",
    "Dockerfile",
    "docker-compose.vllm.yml",
    "docker-entrypoint.sh",
    "Makefile",
    "run.sh",
    "setup_env.sh",
    ".pre-commit-config.yaml",
    "dashboard/package.json",
    "dashboard/pnpm-lock.yaml",
    "dashboard/vite.config.ts",
    "dashboard/tsconfig*.json",
    "vscode-extension/package.json",
    "vscode-extension/package-lock.json",
)


def _scan_secret_candidates(root: Path) -> tuple[int, list[str]]:
    """Scan the commit set, falling back to tracked production/config on clean trees."""
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    candidates = []
    for line in status:
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ")[-1]
        candidates.append(path)
    scanned, hits = _scan_secret_paths(root, candidates)
    if scanned == 0:
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "--", *_BASELINE_PATHS],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("\0")
        scanned, hits = _scan_secret_paths(root, tracked)
    return scanned, hits


def _scan_secret_paths(root: Path, candidates: list[str]) -> tuple[int, list[str]]:
    """Apply the documentation scanner's unchanged text and placeholder rules."""
    text_suffixes = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".sh", ".yaml", ".yml", ".toml", ".txt", ""}
    hits: list[str] = []
    scanned = 0
    for path in candidates:
        target = root / path
        if not path or not target.is_file() or target.suffix not in text_suffixes:
            continue
        if target.stat().st_size > 2_000_000:
            continue
        body = target.read_text(encoding="utf-8", errors="replace")
        scanned += 1
        for label, pattern in TOOL.SECRET_PATTERNS:  # type: ignore[attr-defined]
            for match in pattern.finditer(body):
                quoted = re.findall(r"['\"]([^'\"]+)['\"]", match.group(0))
                if quoted and all(TOOL.PLACEHOLDER_RE.match(q) or len(q) < 12 for q in quoted):  # type: ignore[attr-defined]
                    continue
                hits.append(f"{path}:{body[: match.start()].count(chr(10)) + 1} ({label})")
    return scanned, hits


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="No git worktree for commit-set/production scan")
def test_commit_set_has_no_secret_patterns() -> None:
    scanned, hits = _scan_secret_candidates(REPO)
    assert scanned > 0, "No eligible commit-set or tracked production/config files scanned"
    assert not hits, "커밋 대상에서 비밀 패턴 의심: " + ", ".join(hits[:8])


@pytest.mark.parametrize("planted", [False, True])
def test_clean_tracked_production_baseline_detects_synthetic_secret(tmp_path: Path, planted: bool) -> None:
    # Given: a clean tracked production source, with an optional deliberately fake pattern.
    (tmp_path / "src").mkdir()
    body = "value = 1\n"
    if planted:
        body += 'token = "' + "sk-" + "0" * 24 + '"\n'
    (tmp_path / "src" / "app.py").write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "src/app.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=contract",
            "-c",
            "user.email=contract@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "synthetic baseline",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=tmp_path) == b""
    # When: the clean tree has no dirty or untracked scan targets.
    scanned, hits = _scan_secret_candidates(tmp_path)
    # Then: production is scanned and the planted pattern cannot pass.
    assert scanned == 1
    assert hits == (["src/app.py:2 (openai_key)"] if planted else [])
    # Changed fixture/evidence paths retain the original scan rules, without exclusions.
    (tmp_path / "tests").mkdir()
    fixture = tmp_path / "tests" / "fixture.py"
    fixture.write_text('token = "' + "sk-" + "0" * 24 + '"\n', encoding="utf-8")
    subprocess.run(["git", "add", "tests/fixture.py"], cwd=tmp_path, check=True, capture_output=True)
    assert _scan_secret_candidates(tmp_path) == (1, ["tests/fixture.py:1 (openai_key)"])


def test_tool_docs_manifest_is_json_serialisable() -> None:
    """검사기의 문서 집합 자기선언이 비어 있지 않다(검사 대상이 조용히 0개가 되는 것을 막는다)."""
    docs = list(TOOL.DOCS)  # type: ignore[attr-defined]
    assert docs, "검사 대상 문서 목록이 비었다"
    assert len(json.dumps(docs)) > 2
