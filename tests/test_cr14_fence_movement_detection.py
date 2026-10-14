"""CR-14 — **울타리 이동 탐지기**: 초록이 후보가 아닌 트리를 가리키는 상태를 기계가 잡는다.

attempt-013 에서 실제로 일어난 일 (F-22)
=========================================
후보 `0593dd27` 에서 gate **21/21 초록**을 얻고 그 결과를 **기록 커밋 `f95f22b9`** 로 옮겼는데,
그 커밋이 `README.md` 를 고쳐(후보 SHA·게이트 수를 "최신"으로 갱신) gate 지문을
`2c5a15c8…` → `b9590b01…` 로 옮겼다. `README.md` 는 루트라 지문 **안**이다 — 제외는
`FINGERPRINT_EXCLUDED_PREFIXES = ("docs/", ".omo/")` **접두사뿐**이다. 그 순간 그 초록은
**HEAD 가 아닌 트리**를 가리키게 됐고, "초록은 후보를 증명한다"는 전제가 깨졌다(F-07·F-14 와
같은 병). attempt-014 는 그 **원인**(README 가 손으로 갱신해야 하는 값을 담고 있었다)을 닫았지만,
그 이동을 찾아낸 것은 **사람의 눈**이었다 — attempt-014 는 그 사실을 한계 R-1 로 남겼다:
"지문 이동에 사후 탐지 계약이 없다".

이 파일이 만드는 탐지기
=======================
ARCHIVED 선언은 기록된 후보 커밋에만 결박한다. ACTIVE 선언은 현재 HEAD와 작업 트리까지 요구한다.
과거 C14-F23-2의 docs-only 기록 규율은 아래 합성·실제 이력 이빨로 계속 검증한다.

작업 트리를 건드리지 않고 **git 객체만으로** 커밋의 코드 지문을 계산해, 선언된 값과 울타리의
위치를 대조한다. 그래서 미커밋 상태와 무관하게 과거·현재를 같은 규칙으로 잴 수 있다.

  C14-F23-1  선언된 지문 == 후보 커밋 트리 지문        → 그 값은 실제로 그 커밋의 것이다
  C14-F23-2  ACTIVE 선언은 후보 == HEAD · 작업 트리 지문 일치     → **울타리가 움직이지 않았다**(R-1 의 탐지기)
  C14-F23-3  지문과 `git status` 가 청결에 대해 같은 말 → 지문 함수의 사각지대가 없다
  C14-F23-4  측정 보고서가 이름 붙인 커밋의 트리 == 보고서의 지문 → 보고서가 다른 트리의 초록이 아니다

아래는 활성 후보 측정·기록 당시의 F-22 규율이다. `C14-F23-2` 가 탐지기이며 기록 커밋이 `docs/` 전용이면 통과하고, `README.md`·`tests/**`·
설정·lock 을 건드리면 **그 경로를 이름으로 대며** 실패한다. 진행 중(미커밋 코드 편집)은 커밋
이력과 무관하므로 이 계약을 깨지 않는다 — R-1 이 "진행 중 상태와 구분해야 해서 단순 동등
비교로는 만들 수 없다"고 한 지점이 여기서 성립한다: 이 계약이 보는 것은 **커밋된 이력**이고,
미커밋 진행분을 새 활성 후보로 선언할 때 C14-F23-1 이 값을 요구한다. 보관된 선언에 이 규율을
현재 HEAD까지 연장하지 않는다.

`C14-F23-3` 은 다른 각도에서 같은 경계를 본다: 지문 함수가 어떤 파일을 **조용히 무시**하면
(예: 제외 목록을 늘려 `README.md` 를 빼면) `git status` 는 그 파일을 보고하는데 지문은 "같다"고
말한다 — 그 불일치를 실패로 만든다(attempt-013 의 F-18 과 같은 병: 검사 도구가 대상을 보지 않는다).
왜 필요한가: C14-F23-2 가 "울타리가 움직였는가"를 보는 반면, 이 조항은 "울타리가 **보이는가**"를 본다.

이 파일이 검사하지 **않는** 것: 판정(GO/NO-GO)의 내용, 그리고 `_tree_fingerprint` 의 값 자체가
옳은지(그것은 각 attempt 의 `gate-report.json` 이 소유한다). 여기서 고정하는 것은 **선언된
증거가 지금 이 후보의 것인가**라는 성질이다.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_GATE_SCRIPT = REPO_ROOT / "scripts" / "ga_gate.py"
_CARD = REPO_ROOT / "docs" / "ga" / "CR14_FINAL_CANDIDATE_VERDICT.md"
_EVIDENCE_ROOT = REPO_ROOT / ".omo" / "evidence" / "commercial-reliability" / "CR-14"

# 판정 카드의 선언 자리 — 값의 소유자는 하나다(C14-F15-2).
_CANDIDATE = re.compile(r"code candidate full SHA: \*\*`([0-9a-f]{40})`\*\*")
_DECLARED = re.compile(r"코드 지문 \*\*`([0-9a-f]{64})`\*\*")

# F-22 의 실측 지점(이 저장소의 **이력**에 남아 있다): attempt-013 의 후보와 그 기록 커밋.
# 그 기록 커밋이 `README.md` 를 고쳐 지문을 `2c5a15c8…` → `b9590b01…` 로 옮겼다.
_ATTEMPT_013_CANDIDATE = "0593dd27dbea4a7bc4796ad9807d14b9f3a62165"
_ATTEMPT_013_RECORD = "f95f22b9"
_GITLINK_MODE = "160000"
_SYMLINK_MODE = "120000"


def _load_gate_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cr14_ga_gate_fence_under_test", _GATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_GATE = _load_gate_module()
# 게이트가 **실제로 쓰는** 함수를 쓴다 — 여기서 지문을 다시 구현하면 게이트가 바뀌어도 이
# 계약은 옛 규칙을 검사하는 거짓 통과가 된다(attempt-013 F-18 과 같은 병).
_worktree_fingerprint = cast("Callable[[Path], str]", getattr(_GATE, "_tree_fingerprint"))


def excluded_prefixes() -> tuple[str, ...]:
    """게이트가 지문에서 제외하는 접두사 — 게이트 선언에서 읽는다(복제하지 않는다)."""
    return tuple(cast("Sequence[str]", getattr(_GATE, "FINGERPRINT_EXCLUDED_PREFIXES")))


def git_bytes(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout


def in_code_scope(relative: str, prefixes: tuple[str, ...]) -> bool:
    return not relative.startswith(prefixes)


def index_modes(root: Path) -> dict[str, str]:
    """경로 → 인덱스 모드. gitlink(160000)·심볼릭 링크(120000)를 구분하기 위해 필요하다."""
    modes: dict[str, str] = {}
    for entry in git_bytes(root, "ls-files", "-s", "-z").split(b"\0"):
        if not entry:
            continue
        meta, _, raw_path = entry.partition(b"\t")
        modes[raw_path.decode("utf-8", "surrogateescape")] = meta.split(b" ")[0].decode()
    return modes


# 커밋측 지문·울타리 판정은 **게이트가 실제로 쓰는 함수**에서 온다. 여기서 다시 구현하면
# 규칙이 갈라져 계약이 옛 규칙을 검사하는 거짓 통과가 된다(attempt-013 F-18 과 같은 병).
# `prefixes` 를 주지 않으면 게이트 모듈의 전역을 읽으므로, 이빨이 그 전역을 바꿔 끼울 수 있다.
_commit_fingerprint = cast(
    "Callable[[Path, str, Sequence[str] | None], str]", getattr(_GATE, "tree_fingerprint_of_commit")
)
_code_scope_changes = cast(
    "Callable[[Path, str, str, Sequence[str] | None], list[str]]", getattr(_GATE, "code_scope_changes")
)


def commit_fingerprint(root: Path, rev: str, prefixes: tuple[str, ...] | None = None) -> str:
    """`rev` 커밋 **트리**의 코드 지문 — 작업 트리를 건드리지 않고 git 객체만으로 계산한다.

    내용을 git blob 에서 읽으므로 커밋을 체크아웃하지 않고도 과거 후보를 잴 수 있고, 그 덕분에
    "그때의 초록이 지금도 이 후보의 것인가"를 미커밋 상태와 무관하게 물을 수 있다.
    gitlink(160000)는 내용이 없어 `missing` 으로 본다 — 작업 트리에서 그 경로는 디렉터리라
    게이트의 `_sha256` 도 `OSError` 로 같은 값에 도달한다(F-13 의 ` M vault_data` 가 지문을
    움직이지 않는 이유가 이것이다).
    """
    return _commit_fingerprint(root, rev, prefixes)


def code_scope_changes(root: Path, base: str, head: str, prefixes: tuple[str, ...] | None = None) -> list[str]:
    """`base`..`head` 에서 **코드 스코프**가 바뀐 경로 — 빈 목록이면 울타리는 그대로다."""
    return _code_scope_changes(root, base, head, prefixes)


def worktree_code_scope_dirt(root: Path, prefixes: tuple[str, ...] | None = None) -> list[str]:
    """`git status` 가 코드 스코프에서 보고한 내용 변경 — gitlink 는 지문과 같은 이유로 무시한다."""
    scope = excluded_prefixes() if prefixes is None else prefixes
    gitlinks = {path for path, mode in index_modes(root).items() if mode == _GITLINK_MODE}
    records = git_bytes(root, "status", "--porcelain=v1", "-z").split(b"\0")
    dirt: list[str] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        status = record[:2].decode("ascii", "replace")
        path = record[3:].decode("utf-8", "surrogateescape")
        if status[0] in ("R", "C"):  # 이름 바꿈·복사 — 다음 레코드가 원본 경로다
            index += 1
        if path in gitlinks or not in_code_scope(path, scope):
            continue
        dirt.append(path)
    return dirt


# 지문 스코프의 **기준선** — 게이트 선언과 별개로 이 계약이 들고 있는 두 번째 의견.
# `C14-F15-4` 는 "게이트 목록 == 문서가 말하는 범위"를 보고, 여기서는 **git 이 보는 코드**와
# 대조한다: 게이트가 목록을 넓혀 어떤 파일을 조용히 무시하기 시작하면 그 차이가 드러난다.
_REFERENCE_SCOPE: tuple[str, ...] = ("docs/", ".omo/")


def scope_agreement_violations(root: Path, base_rev: str) -> list[str]:
    """지문 함수와 `git status` 가 코드 스코프 청결에 대해 **같은 말**을 하는가(빈 목록 = 통과).

    지문 쪽은 **게이트가 실제로 쓰는 스코프**로, `git status` 쪽은 **기준선 스코프**로 잰다 —
    둘이 갈라지면(게이트가 제외를 늘리면) 지문이 "같다"고 하는 동안 git 은 변경을 보고한다.
    """
    same = _worktree_fingerprint(root) == commit_fingerprint(root, base_rev)
    dirt = worktree_code_scope_dirt(root, _REFERENCE_SCOPE)
    violations: list[str] = []
    if same and dirt:
        violations.append(
            "지문은 '같다'고 하는데 git status 는 코드 스코프 변경을 본다(지문의 사각지대): " + ", ".join(dirt)
        )
    if not same and not dirt:
        violations.append("지문은 '다르다'고 하는데 git status 는 조용하다(지문이 git 이 모르는 것을 본다)")
    return violations


def declared_values(card_text: str) -> tuple[str, str]:
    """판정 카드가 선언한 (후보 SHA, 코드 지문). 각각 **정확히 하나**여야 한다."""
    candidates = _CANDIDATE.findall(card_text)
    fingerprints = _DECLARED.findall(card_text)
    if len(candidates) != 1 or len(fingerprints) != 1:
        raise AssertionError(f"선언 자리가 각각 하나여야 한다 — 후보 {len(candidates)}개, 지문 {len(fingerprints)}개")
    return candidates[0], fingerprints[0]


def declaration_violations(card_text: str, root: Path) -> list[str]:
    """Bind archives to their recorded commit; active declarations also bind to HEAD."""
    candidate, declared = declared_values(card_text)
    statuses = re.findall(r"^- release declaration status: \*\*([A-Z]+)\*\*$", card_text, re.M)
    assert len(statuses) == 1 and statuses[0] in {"ARCHIVED", "ACTIVE"}, "Explicit declaration status required"
    violations: list[str] = []
    if commit_fingerprint(root, candidate) != declared:
        violations.append("Recorded candidate fingerprint mismatch")
    if statuses == ["ARCHIVED"]:
        current = re.findall(r"^- Current HEAD release status: \*\*([A-Z_]+)\*\*$", card_text, re.M)
        if current != ["NOT_APPROVED"]:
            violations.append("Archive must not certify current HEAD")
    else:
        head = git_bytes(root, "rev-parse", "HEAD").decode().strip()
        if candidate != head:
            violations.append("Active candidate must equal current HEAD")
        if commit_fingerprint(root, head) != declared:
            violations.append("Active HEAD fingerprint mismatch")
        if _worktree_fingerprint(root) != declared:
            violations.append("Active worktree fingerprint mismatch")
    return violations


def report_violations(
    evidence_root: Path, declared: str, root: Path = REPO_ROOT, prefixes: tuple[str, ...] | None = None
) -> list[str]:
    """선언된 지문을 측정했다고 주장하는 보고서가 **다른 트리의 초록**이 아닌지 본다.

    보고서는 `git.sha`(측정 시각의 HEAD)와 `git.tree_fingerprint`(측정한 트리)를 함께 남긴다.
    둘이 가리키는 트리가 다르면 그 보고서는 **이름 붙인 커밋의 증거가 아니다**(미커밋 코드를
    잰 채 sha 만 HEAD 로 적은 경우) — 그래서 attempt-014 는 순서를 규율로 박았다: 후보를
    **커밋한 뒤에** 잰다(D-52). required gate 가 실패한 초록도 같이 거부한다.
    """
    scope = excluded_prefixes() if prefixes is None else prefixes
    violations: list[str] = []
    for path in sorted(evidence_root.glob("attempt-*/gate-report.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:  # 손상된 보고서도 조용히 넘기지 않는다
            violations.append(f"{path.parent.name}: 보고서를 읽을 수 없다 ({error})")
            continue
        git = data.get("git") or {}
        if git.get("tree_fingerprint") != declared:
            continue
        sha = str(git.get("sha") or "")
        if sha and _commit_exists(root, sha) and commit_fingerprint(root, sha, scope) != declared:
            violations.append(
                f"{path.parent.name}: 보고서 지문이 이름 붙인 커밋 {sha[:12]} 의 코드 트리와 다르다 "
                "— 커밋되지 않은 트리를 쟀거나, 측정 뒤에 그 커밋의 지문이 바뀌었다"
            )
        required = [gate for gate in (data.get("gates") or []) if gate.get("required")]
        failed = [gate.get("id") for gate in required if gate.get("status") != "passed"]
        if not required:
            violations.append(f"{path.parent.name}: required gate 가 하나도 선언되지 않았다")
        elif failed:
            violations.append(f"{path.parent.name}: required gate 실패 {failed}")
    return violations


def _commit_exists(root: Path, sha: str) -> bool:
    result = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=root, capture_output=True, check=False)
    return result.returncode == 0


def _head() -> str:
    return git_bytes(REPO_ROOT, "rev-parse", "HEAD").decode().strip()


def _init_repo(root: Path) -> None:
    """합성 이빨용 최소 저장소 — 주변 설정(전역 gitconfig·서명)에 영향받지 않게 격리한다."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    _commit_all(root, "seed")


def _commit_all(root: Path, message: str) -> str:
    options = ["-c", "user.name=cr14", "-c", "user.email=cr14@example.invalid", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", *options, "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", *options, "commit", "-q", "-m", message], cwd=root, check=True, capture_output=True)
    return git_bytes(root, "rev-parse", "HEAD").decode().strip()


# ---------------------------------------------------------------------------
# 계약
# ---------------------------------------------------------------------------


def test_declared_fingerprint_is_the_declared_candidates_own_tree() -> None:
    """C14-F23-1 — 선언된 지문은 **그 후보 커밋의 트리**에서 나온 값이다(git 객체로 확인).

    값을 손으로 적어 넣거나 다른 트리의 값을 옮겨 적으면 여기서 깨진다.
    """
    candidate, declared = declared_values(_CARD.read_text(encoding="utf-8"))
    value = commit_fingerprint(REPO_ROOT, candidate)
    assert value == declared, (
        f"판정 카드가 선언한 지문이 후보 커밋 {candidate[:12]} 의 트리가 아니다 — 선언 {declared} / 그 커밋 {value}"
    )


def test_release_declaration_binds_to_its_explicit_status() -> None:
    violations = declaration_violations(_CARD.read_text(encoding="utf-8"), REPO_ROOT)
    assert not violations, " / ".join(violations)


@pytest.mark.parametrize("status", ["ARCHIVED", "ACTIVE"])
def test_teeth_declaration_scope_preserves_archive_and_rejects_active_drift(tmp_path: Path, status: str) -> None:
    # Given: a recorded candidate and its exact fingerprint.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    _init_repo(repo)
    candidate = git_bytes(repo, "rev-parse", "HEAD").decode().strip()
    fingerprint = commit_fingerprint(repo, candidate)
    card = (
        f"- release declaration status: **{status}**\n"
        "- Current HEAD release status: **NOT_APPROVED**\n"
        f"code candidate full SHA: **`{candidate}`**\n코드 지문 **`{fingerprint}`**\n"
    )
    assert declaration_violations(card, repo) == []
    # When: the source moves, first uncommitted and then committed.
    (repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    dirty = declaration_violations(card, repo)
    _commit_all(repo, "next candidate")
    moved = declaration_violations(card, repo)
    # Then: archives retain historical binding; active claims reject both drifts.
    assert bool(dirty) == (status == "ACTIVE")
    assert bool(moved) == (status == "ACTIVE")
    wrong = card.replace(fingerprint, commit_fingerprint(repo, "HEAD"))
    assert "Recorded candidate fingerprint mismatch" in declaration_violations(wrong, repo)
    for malformed in (
        card.replace(f"**{status}**", "**UNKNOWN**"),
        card.replace(f"- release declaration status: **{status}**\n", ""),
        card + f"- release declaration status: **{status}**\n",
    ):
        with pytest.raises(AssertionError, match="Explicit declaration status required"):
            declaration_violations(malformed, repo)
    if status == "ARCHIVED":
        assert declaration_violations(card.replace("**NOT_APPROVED**", "**APPROVED**"), repo)
        assert declaration_violations(card + "- Current HEAD release status: **APPROVED**\n", repo)


def test_teeth_active_declaration_requires_head_even_after_docs_only_commit(tmp_path: Path) -> None:
    # Given: an active declaration at a clean candidate.
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    _init_repo(repo)
    candidate = git_bytes(repo, "rev-parse", "HEAD").decode().strip()
    card = (
        "- release declaration status: **ACTIVE**\n"
        f"code candidate full SHA: **`{candidate}`**\n"
        f"코드 지문 **`{commit_fingerprint(repo, candidate)}`**\n"
    )
    assert declaration_violations(card, repo) == []
    # When: even a docs-only commit moves HEAD.
    (repo / "docs" / "note.md").write_text("record\n", encoding="utf-8")
    _commit_all(repo, "record")
    # Then: an active declaration must name the current HEAD explicitly.
    assert declaration_violations(card, repo) == ["Active candidate must equal current HEAD"]


def test_fingerprint_function_and_git_status_agree_on_the_working_tree() -> None:
    """C14-F23-3 — 지문이 보는 것과 git 이 보는 것이 일치한다(제외 목록을 늘리면 여기서 깨진다)."""
    violations = scope_agreement_violations(REPO_ROOT, _head())
    assert not violations, " / ".join(violations)


def test_code_scope_holds_no_symlink() -> None:
    """탐지기의 전제를 **가정하지 않고 검사한다**.

    게이트의 `_sha256` 은 링크를 **따라가** 내용을 해시하지만, git tree 의 blob 은 **링크 텍스트**를
    담는다 — 그래서 코드 스코프에 심볼릭 링크가 들어오면 커밋 측 지문과 작업 트리 지문이 갈라지고,
    이 탐지기의 비교가 거짓 실패(또는 거짓 통과)를 낼 수 있다. 그때는 이 검사가 먼저 알려준다.
    """
    symlinks = sorted(path for path, mode in index_modes(REPO_ROOT).items() if mode == _SYMLINK_MODE)
    assert not symlinks, (
        "코드 스코프에 심볼릭 링크가 생겼다 — 커밋 측 지문 계산을 링크 의미에 맞게 확장해야 한다: "
        + ", ".join(symlinks)
    )


def test_gate_report_for_the_declared_fingerprint_measured_this_tree() -> None:
    """C14-F23-4 — 보고서가 이름 붙인 커밋의 트리 == 보고서의 지문(측정 뒤 코드가 안 움직였다).

    증거 트리(`.omo/`)는 gitignore 라 clean 머신에는 없다 — 그때는 이 조항이 적용되지 않는다.
    보고서는 게이트 실행 **끝**에 쓰이므로, 아직 없는 것은 위반이 아니라 "미측정"이다.
    """
    if not _EVIDENCE_ROOT.is_dir():
        pytest.skip("증거 트리(.omo/)가 없다 — clean 머신/`git archive` 실행에는 이 조항이 적용되지 않는다")
    _candidate, declared = declared_values(_CARD.read_text(encoding="utf-8"))
    violations = report_violations(_EVIDENCE_ROOT, declared)
    assert not violations, " / ".join(violations)


# ---------------------------------------------------------------------------
# 이빨 — 탐지기가 **실제로 무는지** 위반을 심어 확인한다
# ---------------------------------------------------------------------------


def test_teeth_docs_only_commit_does_not_move_the_fence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "docs" / "plan.md").write_text("plan\n", encoding="utf-8")
    _init_repo(repo)
    candidate = git_bytes(repo, "rev-parse", "HEAD").decode().strip()

    (repo / "docs" / "plan.md").write_text("plan v2\n", encoding="utf-8")
    (repo / ".omo").mkdir()
    (repo / ".omo" / "evidence.md").write_text("evidence\n", encoding="utf-8")
    record = _commit_all(repo, "docs: record")

    assert code_scope_changes(repo, candidate, record) == []
    assert commit_fingerprint(repo, candidate) == commit_fingerprint(repo, record)


def test_teeth_code_scope_commit_moves_the_fence_and_names_the_path(tmp_path: Path) -> None:
    """F-22 의 합성 재현 — 기록 커밋이 `README.md`(지문 **안**)를 고치면 탐지기가 물어야 한다."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("current state\n", encoding="utf-8")
    _init_repo(repo)
    candidate = git_bytes(repo, "rev-parse", "HEAD").decode().strip()

    (repo / "README.md").write_text("current state — candidate abc1234, 21/21 gates\n", encoding="utf-8")
    record = _commit_all(repo, "docs: record latest values")

    assert code_scope_changes(repo, candidate, record) == ["README.md"]
    assert commit_fingerprint(repo, candidate) != commit_fingerprint(repo, record), (
        "이빨 없음 — README 만 고쳤는데 지문이 그대로다(제외 목록이 넓어졌다는 뜻)"
    )


def test_teeth_declared_value_from_another_tree_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    _init_repo(repo)
    first = git_bytes(repo, "rev-parse", "HEAD").decode().strip()

    (repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    second = _commit_all(repo, "feat: change value")

    assert commit_fingerprint(repo, first) != commit_fingerprint(repo, second)
    # 카드가 두 번째 커밋을 후보로 선언하면서 첫 번째 커밋의 지문을 적어 두면 C14-F23-1 이 잡는다.
    assert commit_fingerprint(repo, second) != commit_fingerprint(repo, first)


def test_teeth_silently_widened_scope_is_caught_by_the_agreement_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """지문이 `README.md` 를 조용히 무시하도록 제외 목록을 넓히면 C14-F23-3 이 물어야 한다."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("current state\n", encoding="utf-8")
    _init_repo(repo)
    head = git_bytes(repo, "rev-parse", "HEAD").decode().strip()

    (repo / "README.md").write_text("current state — candidate abc1234\n", encoding="utf-8")

    baseline = excluded_prefixes()
    assert "README.md" not in baseline, "전제 불성립 — README 는 지문 안이다"
    assert scope_agreement_violations(repo, head) == [], "기준선에서 이미 불일치가 보고된다 — 기준선이 깨졌다: " + str(
        scope_agreement_violations(repo, head)
    )
    monkeypatch.setattr(_GATE, "FINGERPRINT_EXCLUDED_PREFIXES", (*baseline, "README.md"))

    violations = scope_agreement_violations(repo, head)
    assert violations, "이빨 없음 — README 를 지문에서 빼도 불일치를 보고하지 않았다"
    assert "README.md" in violations[0]


def test_teeth_report_measured_on_a_tree_that_is_not_the_named_commit_is_rejected(
    tmp_path: Path,
) -> None:
    """보고서가 `git.sha` 로 이름 붙인 커밋과 **다른 트리**를 측정했으면 보고서 조항이 물어야 한다.

    이 저장소의 규율은 "후보를 커밋한 뒤에 잰다"이다. 미커밋 코드가 있는 상태로 게이트를 돌리면
    보고서의 sha 는 HEAD 인데 측정한 트리는 그 커밋이 아니다 — 그 보고서는 후보의 증거가 아니고,
    F-22 뒤에 attempt-014 가 세운 순서(D-52)가 그 이유다.
    """
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    _init_repo(repo)
    head = git_bytes(repo, "rev-parse", "HEAD").decode().strip()
    committed_fingerprint = commit_fingerprint(repo, head)

    (repo / "app.py").write_text("value = 2\n", encoding="utf-8")  # 미커밋 변경
    dirty_fingerprint = _worktree_fingerprint(repo)
    assert dirty_fingerprint != committed_fingerprint, "전제 불성립 — 미커밋 변경이 지문을 안 움직였다"

    evidence_root = repo / "evidence"
    report = evidence_root / "attempt-999" / "gate-report.json"
    report.parent.mkdir(parents=True)

    def write_report(fingerprint: str) -> None:
        report.write_text(
            json.dumps(
                {
                    "git": {"sha": head, "tree_fingerprint": fingerprint},
                    "gates": [{"id": "python-tests", "status": "passed", "required": True}],
                }
            ),
            encoding="utf-8",
        )

    write_report(dirty_fingerprint)  # 커밋되지 않은 트리를 측정한 보고서
    violations = report_violations(evidence_root, dirty_fingerprint, root=repo)
    assert violations and "다르다" in violations[0], f"이빨 없음: {violations}"

    write_report(committed_fingerprint)  # 이름 붙인 커밋의 트리를 측정한 보고서 — 통과해야 한다
    assert report_violations(evidence_root, committed_fingerprint, root=repo) == []

    report.write_text(
        json.dumps(
            {
                "git": {"sha": head, "tree_fingerprint": committed_fingerprint},
                "gates": [{"id": "python-tests", "status": "failed", "required": True}],
            }
        ),
        encoding="utf-8",
    )
    failed = report_violations(evidence_root, committed_fingerprint, root=repo)
    assert failed and "required gate 실패" in failed[0], f"이빨 없음 — 실패한 초록을 넘겼다: {failed}"


def test_teeth_this_repositorys_own_f22_move_is_detected() -> None:
    """실제 이력의 F-22 — attempt-013 의 기록 커밋이 옮긴 경로를 탐지기가 **이름으로** 짚는지."""
    if not _commit_exists(REPO_ROOT, _ATTEMPT_013_CANDIDATE) or not _commit_exists(REPO_ROOT, _ATTEMPT_013_RECORD):
        pytest.skip("얕은 clone 이라 그 객체가 없다 — 합성 이빨이 같은 규칙을 확인한다")
    assert code_scope_changes(REPO_ROOT, _ATTEMPT_013_CANDIDATE, _ATTEMPT_013_RECORD) == ["README.md"]
