"""T14 회귀가 찾은 결함의 회귀 시험 — enum identity에 기대지 않는 판정.

전체 suite에서 같은 이름의 `AuthorityDimension` class가 두 번 생기자 `grant.dimension is query.dimension`이
False가 되어 유효한 grant가 NOT_GRANTED → DEFER로 떨어졌다(권한 판정이 조용히 달라짐). 이 시험은 세 가지를
고정한다.

1. `same_enum`의 계약: module 중복 로드에는 관대하고(same module·same name·same value), 다른 enum에는 엄격하다.
2. 그 계약이 실제 판정(authority)에서 동작한다 — 중복 class로 만든 grant도 매칭된다.
3. cognitive core에 raw `is`/`is not` enum 비교가 남아 있지 않다(`scripts/audit_enum_identity.py`).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import ModuleType

import pytest

import antigravity_k.engine.cognitive.models as cognitive_models
from antigravity_k.engine.cognitive.authority import (
    AuthorityProfile,
    AuthorityQuery,
    AuthorityVerdict,
)
from antigravity_k.engine.cognitive.models import (
    EntityType,
    ProducerKind,
    RiskLevel,
    same_enum,
)
from antigravity_k.tools.base_tool import RiskLevel as ToolRiskLevel

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_enum_identity.py"
NOW = datetime(2026, 9, 22, tzinfo=UTC)


class OutcomeStatus(StrEnum):
    """다른 module에 정의된 **같은 이름·같은 값**의 enum — 엄격성 확인용."""

    MATCH = "MATCH"
    UNKNOWN = "UNKNOWN"


def load_audit() -> ModuleType:
    spec = importlib.util.spec_from_file_location("audit_enum_identity", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_enum_identity"] = module
    spec.loader.exec_module(module)
    return module


def load_duplicate_module(module: ModuleType) -> ModuleType:
    """같은 module 이름으로 source를 한 번 더 실행해 **같은 이름·다른 객체**를 가진 copy를 만든다."""

    spec = importlib.util.spec_from_file_location(module.__name__, Path(module.__file__ or ""))
    assert spec is not None and spec.loader is not None
    duplicate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(duplicate)
    return duplicate


def test_same_member_and_different_member() -> None:
    assert same_enum(cognitive_models.OutcomeStatus.MATCH, cognitive_models.OutcomeStatus.MATCH) is True
    assert same_enum(cognitive_models.OutcomeStatus.MATCH, cognitive_models.OutcomeStatus.UNKNOWN) is False
    assert same_enum(EntityType.EVIDENCE, EntityType.DECISION) is False


def test_duplicate_class_with_the_same_name_matches() -> None:
    duplicate = load_duplicate_module(cognitive_models).OutcomeStatus
    assert duplicate is not cognitive_models.OutcomeStatus
    assert duplicate.__module__ == cognitive_models.OutcomeStatus.__module__
    assert duplicate.__qualname__ == cognitive_models.OutcomeStatus.__qualname__

    assert same_enum(duplicate.MATCH, cognitive_models.OutcomeStatus.MATCH) is True
    assert same_enum(duplicate.MATCH, cognitive_models.OutcomeStatus.UNKNOWN) is False


def test_different_enum_with_the_same_name_and_value_does_not_match() -> None:
    """이름·값이 같아도 정의 module이 다르면 같지 않다(값 비교로 새면 안 되는 경계)."""

    assert OutcomeStatus.__qualname__ == cognitive_models.OutcomeStatus.__qualname__
    assert OutcomeStatus.MATCH.value == cognitive_models.OutcomeStatus.MATCH.value
    assert OutcomeStatus.__module__ != cognitive_models.OutcomeStatus.__module__
    assert same_enum(OutcomeStatus.MATCH, cognitive_models.OutcomeStatus.MATCH) is False

    # 도구 위험도는 이름은 같고 값 규칙도 다르다(도구는 소문자) — 어느 쪽이든 같지 않다.
    assert RiskLevel.HIGH.value != ToolRiskLevel.HIGH.value
    assert same_enum(RiskLevel.HIGH, ToolRiskLevel.HIGH) is False
    assert same_enum(ToolRiskLevel.HIGH, RiskLevel.HIGH) is False


def test_non_enum_values_never_match() -> None:
    assert same_enum("MATCH", cognitive_models.OutcomeStatus.MATCH) is False
    assert same_enum(None, cognitive_models.OutcomeStatus.MATCH) is False
    assert same_enum(ProducerKind.HUMAN, "HUMAN") is False
    assert same_enum(object(), object()) is False


def test_authority_profile_accepts_a_duplicate_class_grant() -> None:
    """중복 로드된 class로 만든 값이 들어와도 유효한 scope면 승인되어야 한다.

    두 겹으로 막힌다: pydantic이 검증 시점에 canonical enum으로 정규화하고(아래 첫 assert),
    남는 비교는 same_enum이 같은 module·이름·값을 보고 매칭한다.
    """

    duplicate = load_duplicate_module(cognitive_models)
    duplicate_grant = duplicate.AuthorityGrant(
        revision=1,
        subject="body:tool-executor",
        dimension=duplicate.AuthorityDimension.TOOL_WRITE,
        resource_scope="/tmp/scope",
        allowed_operations=("execute_tool",),
        granted_by="human:mr.k",
        issued_at=NOW,
    )
    assert duplicate.AuthorityDimension.TOOL_WRITE is not cognitive_models.AuthorityDimension.TOOL_WRITE
    # pydantic은 검증 시점에 자기 module의 enum으로 정규화한다 — 어느 copy로 정규화되든 same_enum은 통과해야 한다.
    assert same_enum(duplicate_grant.dimension, cognitive_models.AuthorityDimension.TOOL_WRITE) is True

    profile = AuthorityProfile(revision=1, grants=(duplicate_grant,))
    decision = profile.evaluate(
        AuthorityQuery(
            subject="body:tool-executor",
            dimension=cognitive_models.AuthorityDimension.TOOL_WRITE,
            resource_scope="/tmp/scope/wide.txt",
            operation="execute_tool",
        ),
        now=NOW,
    )

    assert decision.allowed is True, decision.reason
    assert decision.verdict is AuthorityVerdict.ALLOWED


def test_cognitive_core_has_no_raw_enum_identity_comparison() -> None:
    audit = load_audit()
    violations = audit.scan_paths()
    details = [f"{v.file}:{v.line} {v.expression}" for v in violations]
    assert violations == (), f"raw enum identity 비교가 남아 있다: {details}"


def test_audit_detects_identity_comparisons() -> None:
    audit = load_audit()
    source = (
        "def f(value):\n"
        "    if value is OutcomeStatus.MATCH:\n"
        "        return 1\n"
        "    if value is not OutcomeStatus.MATCH:\n"
        "        return 2\n"
        "    if value is None:\n"
        "        return 3\n"
        "    if value is other.member:\n"  # 소문자 attribute는 enum member로 보지 않는다
        "        return 4\n"
        "    return 0\n"
    )
    violations = audit.scan_source(source, file="sample.py")
    assert sorted(v.kind for v in violations) == ["is", "is not"]
    assert {v.line for v in violations} == {2, 4}


def test_audit_reports_clean_tree_via_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    audit = load_audit()
    output = tmp_path / "audit.json"
    exit_code = audit.main(["--json", str(output)])
    captured = capsys.readouterr()
    assert exit_code == 0, captured.out
    assert "enum identity 비교 없음" in captured.out
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["count"] == 0
    assert payload["violations"] == []
