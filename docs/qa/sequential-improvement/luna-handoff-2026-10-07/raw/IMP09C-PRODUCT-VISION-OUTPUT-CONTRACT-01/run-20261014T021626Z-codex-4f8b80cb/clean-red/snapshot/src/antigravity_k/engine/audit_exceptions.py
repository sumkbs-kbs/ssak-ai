"""audit_exceptions — REL-03 공급망 audit 예외 레지스트리 + license/prohibited gate.

GA-100 plan §REL-03:
  - 취약점 예외는 owner, 근거(justification), 만료일(expires), 대체 통제
    (compensating_controls)를 요구한다.
  - 예외 만료 시 CI가 실패한다 (expired → gate 실패; unknown → gate 실패).
  - license/prohibited package gate가 artifact(SBOM)에 대해 실행된다.

설계 원칙 (SEC/TRN lane과 동일):
  - stdlib + pydantic만 사용. 네트워크 호출 없음 — 판정은 감사 도구 출력과
    SBOM 문서를 입력으로 받아 순수하게 수행한다 (결정적, 테스트 용이).
  - deny-by-default: 레지스트리에 없는 예외는 허용되지 않는다.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, TypeAlias, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

__all__ = [
    "AuditException",
    "AuditExceptionError",
    "LicenseGateVerdict",
    "audit_verdict_with_exceptions",
    "expired_exceptions",
    "license_gate_verdict",
    "load_exceptions",
]

_Ecosystem: TypeAlias = Literal["pypi", "npm"]


class AuditVerdict(TypedDict):
    ok: bool
    unresolved: tuple[str, ...]
    excepted: tuple[str, ...]
    medium_low_count: int


class AuditExceptionError(ValueError):
    """예외 레지스트리/gate 판정이 계약을 위반했다."""


class AuditException(BaseModel):
    """단일 취약점 예외 — 4요소 필수 (owner/근거/만료/대체 통제)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3)  # 예: GHSA-xxxx-xxxx-xxxx 또는 PYSEC-xxxx-xx
    package: str = Field(min_length=1)
    ecosystem: _Ecosystem
    installed_version: str = Field(min_length=1)
    fixed_version: str | None = None
    owner: str = Field(min_length=3)
    justification: str = Field(min_length=10)
    expires: date
    compensating_controls: tuple[str, ...] = Field(min_length=1)


class LicenseGateVerdict(BaseModel):
    """license/prohibited gate 판정 결과."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    checked_packages: int
    unknown_license: tuple[str, ...] = ()
    prohibited: tuple[str, ...] = ()
    #: unknown_license/prohibited 이유를 패키지별로 설명 (보고용, gate 판정과 무관)
    notes: tuple[str, ...] = ()


# 알려진 악성/스푸핑 패키지 — SBOM에 등장하면 버전과 무관하게 차단.
# (license 정책은 THIRD_PARTY_PROVENANCE.toml의 prohibited_spdx가 단일 진실원 —
#  정책 리터럴을 소스에 두면 baseline license-marker 스캐너가 위반으로 판정한다.)
_PROHIBITED_PACKAGES = frozenset({"colors.js", "event-stream", "node-ipc", "fabricjs-sample"})

_LICENSE_UNKNOWN_MARKERS = ("license metadata unavailable", "UNKNOWN", "")


def load_exceptions(path: Path) -> tuple[AuditException, ...]:
    """예외 레지스트리(JSON)를 검증 로드한다. 스키마 위반은 즉시 실패."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditExceptionError(f"예외 레지스트리를 읽을 수 없다: {path}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("exceptions"), list):
        raise AuditExceptionError("레지스트리는 {exceptions: [...]} 형태여야 한다")
    try:
        return tuple(AuditException.model_validate(item) for item in payload["exceptions"])
    except ValidationError as error:
        raise AuditExceptionError(f"예외 항목이 계약을 위반한다: {error}") from error


def expired_exceptions(
    exceptions: tuple[AuditException, ...], *, today: date | None = None
) -> tuple[AuditException, ...]:
    """만료일이 지난 예외 목록 — CI gate가 이 목록이 비지 않으면 실패한다."""
    today = today or datetime.now(UTC).date()
    return tuple(item for item in exceptions if item.expires < today)


def audit_verdict_with_exceptions(
    *,
    findings: tuple[dict[str, object], ...],
    exceptions: tuple[AuditException, ...],
    today: date | None = None,
) -> AuditVerdict:
    """감사 결과(findings)를 예외 레지스트리로 판정한다.

    findings 항목 계약: {id, package, ecosystem, installed_version, severity}
    (pip-audit/pnpm-audit 출력을 정규화한 형태 — 도구 어댑터가 만든다.)

    규칙:
      - 예외 없는 high/critical finding → gate 실패
      - 예외가 있어도 만료됐거나 4요소가 불완전하면 → gate 실패 (deny-by-default)
      - 예외는 id+package+ecosystem+version이 정확히 일치할 때만 유효
    """
    today = today or datetime.now(UTC).date()
    by_key = {(item.id, item.package, item.ecosystem, item.installed_version): item for item in exceptions}
    unresolved: list[str] = []
    excepted: list[str] = []
    for finding in findings:
        severity = str(finding.get("severity", "")).lower()
        if severity not in {"high", "critical"}:
            continue  # medium/low는 보고 전용 (숨기지 않고 별도 기록)
        key = (
            str(finding.get("id", "")),
            str(finding.get("package", "")),
            _as_ecosystem(finding.get("ecosystem")),
            str(finding.get("installed_version", "")),
        )
        exception = by_key.get(key)
        if exception is None or exception.expires < today:
            unresolved.append(str(finding.get("id", "?")))
        else:
            excepted.append(str(finding.get("id", "?")))
    return {
        "ok": not unresolved,
        "unresolved": tuple(unresolved),
        "excepted": tuple(excepted),
        "medium_low_count": sum(1 for f in findings if str(f.get("severity", "")).lower() not in {"high", "critical"}),
    }


def _as_ecosystem(value: object) -> _Ecosystem:
    text = str(value or "").lower()
    if text == "npm":
        return "npm"
    return "pypi"


def license_gate_verdict(
    python_sbom: dict[str, object],
    dashboard_sbom: dict[str, object],
    marker_platform_packages: tuple[str, ...] = (),
    *,
    prohibited_licenses: tuple[str, ...] | frozenset[str],
) -> LicenseGateVerdict:
    """SBOM artifact에 대해 license/prohibited package gate를 실행한다.

    계약:
      - ``prohibited_licenses`` (THIRD_PARTY_PROVENANCE.toml의 prohibited_spdx —
        정책 단일 진실원)에 해당하는 라이선스 component → prohibited (실패)
      - 모든 production component의 license를 검사한다.
      - 메타데이터가 없거나 판독 불가 라이선스 → unknown_license (실패)
      - 알려진 악성 패키지 → prohibited (실패)
      - ``marker_platform_packages`` (provenance에서 승인된 플랫폼 마커
        패키지)의 메타데이터 부재는 marker-allowed로 판정해 실패로 세지
        않되, 보고(notes)에는 명시적으로 남긴다 — 숨기지 않는다.
    """
    unknown: list[str] = []
    prohibited: list[str] = []
    notes: list[str] = []
    checked = 0

    for document, ecosystem in ((python_sbom, "pypi"), (dashboard_sbom, "npm")):
        components = document.get("components")
        if not isinstance(components, list):
            raise AuditExceptionError(f"{ecosystem} SBOM에 components 배열이 없다")
        for component in components:
            if not isinstance(component, dict):
                continue
            name = str(component.get("name", ""))
            # 애플리케이션 자체(파이썬 패키지/대시보드 루트)는 제외 — 브랜드
            # 변경과 무관하게 "-react" 접미 루트로 판별한다.
            if not name or name == "antigravity-k" or name.endswith("-dashboard-react"):
                continue
            checked += 1
            version = str(component.get("version", "?"))
            identifier = f"{ecosystem}:{name}@{version}"
            if name.lower() in _PROHIBITED_PACKAGES:
                prohibited.append(identifier)
                notes.append(f"{identifier}: 알려진 악성/스푸핑 패키지")
                continue
            license_id = _component_license_id(component)
            if license_id is not None and _license_is_provenance_declared(component):
                # 출처를 숨기지 않는다: lock이 아니라 provenance 정책의 명시 승인으로
                # 채워진 라이선스임을 gate 출력에 남긴다.
                notes.append(f"{identifier}: provenance-declared ({license_id})")
            if license_id is None:
                if name.lower() in {p.lower() for p in marker_platform_packages}:
                    notes.append(f"{identifier}: marker-allowed (플랫폼 마커 패키지 — 메타데이터 부재 승인)")
                else:
                    unknown.append(identifier)
                    notes.append(f"{identifier}: 라이선스 메타데이터 없음/판독 불가")
            elif license_id in prohibited_licenses:
                prohibited.append(identifier)
                notes.append(f"{identifier}: 금지 라이선스 {license_id}")

    return LicenseGateVerdict(
        ok=not unknown and not prohibited,
        checked_packages=checked,
        unknown_license=tuple(sorted(unknown)),
        prohibited=tuple(sorted(prohibited)),
        notes=tuple(notes),
    )


def _license_is_provenance_declared(component: dict[str, object]) -> bool:
    properties = component.get("properties")
    if not isinstance(properties, list):
        return False
    return any(
        isinstance(entry, dict)
        and entry.get("name") == "agk:license-source"
        and entry.get("value") == "provenance-declared"
        for entry in properties
    )


def _component_license_id(component: dict[str, object]) -> str | None:
    licenses = component.get("licenses")
    if not isinstance(licenses, list) or not licenses:
        return None
    first = licenses[0]
    if not isinstance(first, dict):
        return None
    license_obj = first.get("license")
    if isinstance(license_obj, dict) and isinstance(license_obj.get("id"), str):
        return license_obj["id"]
    if isinstance(first.get("expression"), str):
        return first["expression"]
    return None
