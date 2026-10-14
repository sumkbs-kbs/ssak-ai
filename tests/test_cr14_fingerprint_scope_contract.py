"""CR-14 — 기록이 **증거를 낡게 만드는 경계**를 규율이 아니라 계약으로 고정한다.

attempt-010 에서 실측한 사실
============================
게이트 코드 지문(`scripts/ga_gate.py:_tree_fingerprint`)은 추적+미추적 파일 **내용**의
hash 이고, 제외 목록은 `("docs/", ".omo/")` **접두사뿐**이다. 즉 `README.md`(루트)와
`tests/**` 는 지문 **안**이다. 그래서:

  attempt-009 의 기록 커밋이 계약 파일(`tests/test_cr12_docs_alignment.py`) 하나를
  고쳐 지문을 `dd34a76b…` → `d4a42ab8…` 로 **옮겼고**, 그 순간 그 시점의 20/20 초록은
  **후보가 아닌 트리**를 가리키게 됐다(F-07 과 같은 병 — 초록이 확인하려던 대상이 아니다).

즉 "결과 문서를 쓰는 것만으로는 gate 증거가 낡지 않는다"는 이 저장소의 전제는
**`docs/` 안에 쓸 때만** 참이다. 이 파일은 그 경계를 사후 진단이 아니라 계약으로 만든다.

고정하는 것
===========
  C14-F15-1  README 는 지문 **값**을 담지 않는다. 값을 박으면 다음 README 수정이
             스스로 그 값을 낡게 만든다(자기모순).
  C14-F15-2  README 는 지문을 **소유한 문서**를 가리킨다(값 대신 출처).
  C14-F15-3  코드 스코프(README · `tests/**`)는 **선언된 현재 지문**을 인용하지 않는다.
  C14-F15-4  지문 제외 목록이 바뀌면 **기록도 같이 바뀌어야** 한다 — 목록을 조용히
             늘리면 "문서를 써도 증거가 안 낡는다"는 주장이 몰래 참이 된다.

이 파일이 검사하지 **않는** 것: 지문 값 자체가 옳은지(그것은 각 attempt 의
`gate-report.json` 이 소유하고, 증거 트리는 gitignore 라 clean 머신에 없다), 그리고
판정(GO/NO-GO)의 내용. 여기서 고정하는 것은 **기록이 증거를 낡게 만들지 않는다**는 성질이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_README = REPO_ROOT / "README.md"
_OWNER_DOC = REPO_ROOT / "docs" / "ga" / "CR14_FINAL_CANDIDATE_VERDICT.md"
_CHECKLIST = REPO_ROOT / "docs" / "17_COMMERCIAL_RELIABILITY_CHECKLIST.md"
_PLAN = REPO_ROOT / "docs" / "16_COMMERCIAL_RELIABILITY_DEVELOPMENT_PLAN.md"
_GATE_SCRIPT = REPO_ROOT / "scripts" / "ga_gate.py"

_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
# 판정 카드가 기록된 후보 지문을 선언하는 자리. 이 표기가 값의 유일한 소유자다.
_DECLARED = re.compile(r"코드 지문 \*\*`([0-9a-f]{64})`\*\*")
_EXCLUDED = re.compile(r"FINGERPRINT_EXCLUDED_PREFIXES[^=\n]*=\s*\(([^)]*)\)")
_OWNER_POINTER = "CR14_FINAL_CANDIDATE_VERDICT"
_FULL_FINGERPRINT_PREFIX = 16  # 산문에서 `d4a42ab8…` 처럼 쓰는 길이
# F-22 — README 의 **휘발성 값**(후보 SHA·게이트 수)도 같은 병을 만든다: 값을 박으면 다음
# 기록 커밋이 `README.md` 를 고쳐야 하고(값이 낡았으니까), `README.md` 는 지문 **안**이라
# 그 순간 gate 증거가 낡는다. attempt-013 의 기록 커밋이 실제로 이 경로로 지문을 옮겼다.
# 앞자리 `(?=[0-9a-f]*[a-f])` 는 날짜·버전 같은 순수 숫자열을 오탐하지 않기 위한 것이다.
_HEX_TOKEN = re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
_GATE_COUNT = re.compile(r"required gate\s*\d+")
# 기록 커밋이 `docs/` 밖을 건드리면 지문이 옮겨진다 — 그 규율을 기록 문서가 말해야 한다.
_DOCS_ONLY_RULE = "기록 커밋은 `docs/` 전용"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def declared_fingerprint(text: str) -> str:
    """판정 카드가 선언한 기록된 후보의 코드 지문. 0개거나 2개 이상이면 실패시킨다."""
    matches = _DECLARED.findall(text)
    if len(matches) != 1:
        raise AssertionError(
            f"현재 코드 지문을 선언하는 자리가 정확히 하나여야 한다 — {len(matches)}개 발견: {matches}"
        )
    return matches[0]


def fingerprint_literals(text: str) -> list[str]:
    return _HEX64.findall(text)


def readme_violations(text: str, declared: str) -> list[str]:
    """README 텍스트에서 D-51 위반을 모은다(빈 목록 = 통과). 단위 검사에 그대로 쓴다."""
    problems: list[str] = []
    if fingerprint_literals(text):
        problems.append("README 가 64자리 지문 값을 직접 담고 있다")
    if declared and (declared in text or declared[:_FULL_FINGERPRINT_PREFIX] in text):
        problems.append("README 가 선언된 후보 지문을 인용한다")
    if _OWNER_POINTER not in text:
        problems.append("README 가 지문을 소유한 문서를 가리키지 않는다")
    return problems


def readme_value_violations(text: str) -> list[str]:
    """F-22 — README 가 **휘발성 릴리스 값**을 담았는지(빈 목록 = 통과).

    값을 담으면 다음 기록 커밋이 README 를 고쳐야 하고, README 는 지문 안이므로 그때
    증거가 낡는다. 값의 소유자는 판정 카드 하나다.
    """
    problems: list[str] = []
    tokens = sorted(set(_HEX_TOKEN.findall(text)))
    if tokens:
        problems.append("README 가 커밋 SHA·지문으로 보이는 값을 담고 있다: " + ", ".join(tokens))
    counts = _GATE_COUNT.findall(text)
    if counts:
        problems.append("README 가 required gate 개수 값을 담고 있다: " + ", ".join(counts))
    return problems


def docs_only_rule_violations(text: str) -> list[str]:
    """F-22 — 기록 문서가 '기록 커밋은 docs 전용' 규율을 말하는지."""
    return [] if _DOCS_ONLY_RULE in text else ["기록 커밋 docs 전용 규율 없음"]


def code_scope_violations(declared: str, root: Path = REPO_ROOT) -> list[str]:
    """지문 스코프에 들어가는 파일(README · `tests/**`)이 현재 지문을 인용하면 보고한다."""
    prefix = declared[:_FULL_FINGERPRINT_PREFIX]
    offenders: list[str] = []
    candidates = [root / "README.md", *sorted((root / "tests").rglob("*.py"))]
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if declared in text or prefix in text:
            offenders.append(str(path.relative_to(root)))
    return offenders


def excluded_prefixes(script_text: str) -> tuple[str, ...]:
    match = _EXCLUDED.search(script_text)
    if match is None:
        raise AssertionError("`FINGERPRINT_EXCLUDED_PREFIXES` 선언을 찾지 못했다")
    return tuple(part.strip().strip('"').strip("'") for part in match.group(1).split(",") if part.strip())


# ---------------------------------------------------------------------------
# 계약
# ---------------------------------------------------------------------------


def test_owner_document_declares_exactly_one_recorded_fingerprint() -> None:
    """값의 소유자는 하나다 — 판정 카드가 기록된 후보 지문을 선언한다(C14-F15-2 의 전제)."""
    declared = declared_fingerprint(_read(_OWNER_DOC))
    assert len(declared) == 64


def test_readme_does_not_pin_the_tree_fingerprint() -> None:
    """C14-F15-1/2 — README 는 값을 담지 않고 출처를 가리킨다."""
    declared = declared_fingerprint(_read(_OWNER_DOC))
    problems = readme_violations(_read(_README), declared)
    assert not problems, "README 가 지문을 직접 고정하고 있다: " + " / ".join(problems)


def test_readme_carries_no_volatile_release_values() -> None:
    """C14-F22-1/2 — README 는 값(후보 SHA·게이트 수)을 담지 않는다.

    값을 담으면 기록 커밋이 README 를 고쳐야 하고, 그 순간 지문이 옮겨 증거가 낡는다.
    attempt-013 의 기록 커밋이 정확히 그렇게 지문을 `2c5a15c8…` → 다른 값으로 옮겼다.
    """
    problems = readme_value_violations(_read(_README))
    assert not problems, "README 가 휘발성 값을 직접 고정하고 있다: " + " / ".join(problems)


def test_record_documents_state_that_recording_is_docs_only() -> None:
    """C14-F22-3 — 기록 커밋은 `docs/` 전용이다(README·`tests/**` 는 지문 안)."""
    for path in (_OWNER_DOC, _CHECKLIST, _PLAN):
        assert not docs_only_rule_violations(_read(path)), (
            f"{path.name} 이 '기록 커밋은 docs 전용' 규율을 밝히지 않는다"
        )


def test_code_scope_does_not_quote_the_declared_fingerprint() -> None:
    """C14-F15-3 — 지문 스코프 안의 파일은 현재 지문을 인용하지 않는다."""
    declared = declared_fingerprint(_read(_OWNER_DOC))
    offenders = code_scope_violations(declared)
    assert not offenders, (
        "지문 스코프(README · tests/**) 안에서 현재 코드 지문을 인용하고 있다 — "
        "그 파일을 고치는 순간 gate 증거가 낡는다: " + ", ".join(offenders)
    )


def test_gate_exclusion_list_is_the_documented_one() -> None:
    """C14-F15-4 — 제외 목록이 바뀌면 이 계약이 먼저 깨져야 한다."""
    prefixes = excluded_prefixes(_read(_GATE_SCRIPT))
    assert prefixes == ("docs/", ".omo/"), (
        f"지문 제외 목록이 바뀌었다 — 기록(판정서·체크리스트)이 말하는 범위와 같아야 한다: {prefixes!r}"
    )


def test_record_documents_state_the_fingerprint_boundary() -> None:
    """경계를 아는 사람만 규율을 지킬 수 있다 — 기록이 그 경계를 말해야 한다."""
    for path in (_OWNER_DOC, _CHECKLIST, _PLAN):
        text = _read(path)
        assert "FINGERPRINT_EXCLUDED_PREFIXES" in text, f"{path.name} 이 지문 경계를 밝히지 않는다"
        assert "docs/" in text and ".omo/" in text, f"{path.name} 이 제외 접두사를 밝히지 않는다"


# ---------------------------------------------------------------------------
# 이빨 — 계약이 **실제로 잡는지** 위반을 심어 확인한다
# ---------------------------------------------------------------------------


def test_teeth_readme_volatile_value_is_detected() -> None:
    healthy = _read(_README)
    cases = {
        "후보 SHA 박음": healthy + "\n| 후보 | `0593dd27` |\n",
        "게이트 수 박음": healthy + "\nrequired gate 21/21 PASS\n",
        "지문 앞 16자 박음": healthy + "\n진행 중 지문 `2c5a15c8dbea4a7b`\n",
    }
    if readme_value_violations(healthy):
        pytest.fail("기준 README 가 이미 값을 담고 있다: " + ", ".join(readme_value_violations(healthy)))
    for label, text in cases.items():
        assert readme_value_violations(text), f"이빨 없음 — 심은 값을 놓쳤다: {label}"


def test_teeth_docs_only_rule_removal_is_detected() -> None:
    doc = _read(_OWNER_DOC)
    assert not docs_only_rule_violations(doc), "기준 판정서에 docs 전용 규율이 없다"
    assert docs_only_rule_violations(doc.replace(_DOCS_ONLY_RULE, "기록 커밋은 어디든 쓴다")), (
        "이빨 없음 — 규율 문장을 지웠는데도 통과했다"
    )


def test_teeth_readme_violation_is_detected() -> None:
    declared = declared_fingerprint(_read(_OWNER_DOC))
    healthy = _read(_README)

    cases = {
        "값을 그대로 박음": healthy + f"\n| 지문 | `{declared}` |\n",
        "앞 16자만 인용": healthy + f"\n| 지문 | `{declared[:16]}…` |\n",
        "출처 포인터 제거": healthy.replace(_OWNER_POINTER, "판정서"),
    }
    for label, text in cases.items():
        assert readme_violations(text, declared), f"이빨 없음 — 심은 위반을 놓쳤다: {label}"


def test_teeth_missing_or_duplicated_declaration_is_rejected() -> None:
    doc = _read(_OWNER_DOC)
    declared = declared_fingerprint(doc)

    with pytest.raises(AssertionError):
        declared_fingerprint(doc.replace(declared, "값 없음"))
    with pytest.raises(AssertionError):
        declared_fingerprint(doc + f"\n코드 지문 **`{declared}`**\n")


def test_teeth_scope_widening_is_rejected() -> None:
    """제외 목록을 조용히 늘리면(예: README 까지 제외) 이빨이 물어야 한다."""
    script = _read(_GATE_SCRIPT)
    widened = script.replace(
        'FINGERPRINT_EXCLUDED_PREFIXES: Final = ("docs/", ".omo/")',
        'FINGERPRINT_EXCLUDED_PREFIXES: Final = ("docs/", ".omo/", "README.md")',
    )
    assert widened != script, "이빨 없음 — ga_gate.py 의 선언 문자열을 찾지 못했다"
    assert excluded_prefixes(widened) != ("docs/", ".omo/")


def test_teeth_planted_fingerprint_in_code_scope_is_detected(tmp_path: Path) -> None:
    declared = declared_fingerprint(_read(_OWNER_DOC))
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tmp_path / "README.md").write_text("문서 참조\n", encoding="utf-8")
    planted = tests_dir / "test_planted.py"
    planted.write_text(f'FINGERPRINT = "{declared}"\n', encoding="utf-8")

    offenders = code_scope_violations(declared, root=tmp_path)
    assert offenders == ["tests/test_planted.py"], f"이빨 없음 — 심은 인용을 놓쳤다: {offenders}"
