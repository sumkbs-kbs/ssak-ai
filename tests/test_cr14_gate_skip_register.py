"""CR-14 F-30 — 게이트에서 **조용히 사라지는 테스트**를 소유한다 (R-8 감사).

왜 필요한가
===========
게이트 초록은 "이 후보가 검증됐다"는 주장이다. 그런데 **스킵은 그 주장에서 조용히 빠지는
자리**다 — 게이트는 초록인데 그 테스트는 어디서도 돌지 않는다. attempt-011/012 는 ambient
도구로 돌아 성능/의존성 문제를 숨겼고(F-18·F-19), 게이트 환경을 lock 에 고정한 attempt-013
부터 스킵이 **40건**이 됐다. 도구 출처는 바로잡혔지만 **그 대가(커버리지 손실)는 아무도 세지
않았다** — attempt-013 이 스스로 "이 감사를 하지 않았다"고 적었고(R-8), attempt-021 이 그
감사를 수행했다.

감사가 찾은 것
==============
**어떤 파이프라인도 `documents` extra(pypdf)를 설치하지 않았다.** 그래서 출하 능력인
PDF/DOCX 수집을 재는 **23건**이 게이트·CI·weekly 어디서도 돌지 않았다(게이트는 초록).
게이트 환경에 그 extra 를 넣어 23건을 되살렸고(실측 87 passed / 0 skipped), 남은 **17건**을
이 등록부로 옮겼다. 그중 **4건은 어디서도 돌지 않는 제품 능력**이었다(에이전트 루프 2건 ·
제품 설정 약속 2건). **attempt-022·023 이 그 4건을 모두 닫았다** — 남은 **13건은 전부
소유자가 있다**(mlx 4 · unsloth 7 · access-pin 2).

규칙은 한 곳
============
"무엇이 스킵되는가"의 소유자는 **등록부**(`scripts/gate_skip_register.json`)다. 이 파일은
판정하지 않고 **대조한다**: 등록부와 (a) 스키마·소유자·만료, (b) **실제로 돌린 게이트 환경의
스킵 집합**을 한 건씩 맞춘다. 등록되지 않은 스킵이 생기면 실패한다(무엇이 사라졌는지 적어라).
등록된 스킵이 사라져도 실패한다(등록부가 낡았다). 양쪽 다 "조용한 변화 금지"의 구현이다.

게이트 전수로 넓힌 소유 (attempt-024 가 R-16 을 닫으면서)
=========================================================
처음 scope 는 **게이트 `python-tests` 한 곳**이었다("다른 파이프라인의 스킵은 소관이 아니다").
그런데 같은 후보가 **required gate 21개**로 초록을 만들고, 그중 다섯이 테스트를 돈다 — 다른
게이트의 스킵은 아무도 세지 않았다(R-16). 이제 등록부의 `gate_visibility` 가 21개를 전수
분류하고, 이 파일이 ① 분류의 **전수성**(게이트를 추가하면 분류도 적어야 한다) ② pytest 게이트의
**귀속 플래그** ③ vitest·playwright 의 **이름 보고** ④ 스크립트 게이트의 스킵 채널**선언**과
게이트 명령에서의 **미사용**을 잰다. 실제 실행의 스킵 건수는 게이트 안에서 순환하므로 마감 검사가
편입된 보고서에서 읽는다(`scripts/verify_attempt_close.py` — F-24 가 세운 위치).

관측 목록은 선언에서 파생하지 않는다 (attempt-022 가 찾은 구멍)
=============================================================
처음에는 관측 대상 파일을 `entries` 의 스킵 목록에서 파생했다. 그러면 **항목을 닫는 순간**
그 파일이 관측에서도 사라진다 — 능력을 되찾아 스킵이 0이 된 파일이 다시 스킵되기 시작해도
아무도 모른다(무엇보다 **닫는 일이 관측을 줄인다**: 보상을 뒤집은 셈이다). 그래서 관측 대상은
등록부가 `observed_files` 로 **고정**하고(선언된 파일을 모두 포함해야 한다), 닫힌 항목은
`closed` 에 적혀 그 파일이 계속 관측된다 — 그 파일에 스킵이 돌아오면 대조가 즉시 실패한다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTER_FILE = REPO_ROOT / "scripts" / "gate_skip_register.json"
GATE_FILE = REPO_ROOT / "scripts" / "commercial_ga_gates.json"
BOUNDARY_DOC = REPO_ROOT / "docs" / "ga" / "CR14_GATE_COVERAGE_BOUNDARY.md"

# 스킵을 실제로 관측하는 게이트 — 게이트 환경(도구 출처)의 소유자다.
OBSERVED_GATE_ID = "python-tests"
SKIP_LINE = re.compile(r"^SKIPPED \[(\d+)\] ([^:]+):\d+: (.*)$")

VALID_CLASSES = ("ENV_PLATFORM", "ENV_CONFIG", "KNOWN_GAP")

requires_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="uv 없이는 게이트 환경을 잴 수 없다")


def _register() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(REGISTER_FILE.read_text(encoding="utf-8"))
    return payload


def _declared_skips() -> Counter[tuple[str, str]]:
    """등록부가 선언한 (파일, 사유) → 건수. 등록부가 스킵의 유일한 선언 자리다."""
    counted: Counter[tuple[str, str]] = Counter()
    for entry in _register()["entries"]:
        for skip in entry["skips"]:
            counted[(str(skip["file"]), str(skip["reason"]))] += int(skip["count"])
    return counted


def _gate_prefix() -> list[str]:
    """게이트 `python-tests` 의 **환경 접두사**(도구 토큰 앞까지) — 게이트 파일이 소유한다."""
    payload = json.loads(GATE_FILE.read_text(encoding="utf-8"))
    for gate in payload["gates"]:
        if gate["id"] != OBSERVED_GATE_ID:
            continue
        command = [str(token) for token in gate["command"]]
        index = 2
        while index < len(command) and command[index].startswith("-"):
            index += 2 if command[index] == "--extra" else 1
        return command[:index]
    raise AssertionError(f"게이트 파일에서 {OBSERVED_GATE_ID} 를 찾지 못했다")


def _observed_files() -> list[str]:
    """관측 대상 파일 — 등록부가 **고정 목록**으로 소유한다(선언에서 파생하지 않는다)."""
    return sorted({str(name) for name in _register()["observed_files"]})


def _observed_skips() -> Counter[tuple[str, str]]:
    """게이트 환경을 **그대로 재현해** 실제로 스킵된 (파일, 사유) → 건수를 센다.

    `--extra` 목록은 게이트 파일에서 읽는다: 그래서 F-30 의 수정(출하 extra 를 게이트에
    넣는다)이 이 관측에도 그대로 반영되고, 누군가 그 extra 를 빼면 23건이 다시 스킵되어
    **여기서** 드러난다.
    """
    files = _observed_files()
    command = [*_gate_prefix(), "pytest", *files, "-q", "-rs", "--no-header"]
    completed = subprocess.run(  # noqa: S603 — 게이트 환경 접두사 + 이 계약의 대상 파일
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if completed.returncode not in (0, 1):
        raise AssertionError(f"게이트 환경 재현이 실패했다(exit {completed.returncode}):\n{completed.stderr[-2000:]}")

    counted: Counter[tuple[str, str]] = Counter()
    for line in (completed.stdout + completed.stderr).splitlines():
        match = SKIP_LINE.match(line.strip())
        if match:
            counted[(match.group(2), match.group(3))] += 1
    return counted


def _as_lines(counter: Counter[tuple[str, str]]) -> list[str]:
    return [f"{counted}건  {file}  ← {reason}" for (file, reason), counted in sorted(counter.items())]


# ─── 스키마: 등록부가 스스로 완전한가 ─────────────────────────────────


def test_every_registered_skip_is_well_formed() -> None:
    """등록부 — 모든 항목이 분류·이유·실재 파일·양수 건수를 갖는다."""
    register = _register()
    assert register["entries"], "등록부가 비어 있다 — 그 자체가 스킵이 사라졌다는 주장이다"

    seen: set[str] = set()
    for entry in register["entries"]:
        entry_id = str(entry["id"])
        assert entry_id not in seen, f"등록부 id 가 중복이다: {entry_id}"
        seen.add(entry_id)
        assert entry["class"] in VALID_CLASSES, f"{entry_id}: 알 수 없는 class {entry['class']!r}"
        assert str(entry["why"]).strip(), f"{entry_id}: why 가 비었다 — 왜 허용되는 스킵인지 적어라"
        assert entry["skips"], f"{entry_id}: skips 가 비었다 — 스킵하지 않는 항목은 등록부에 두지 않는다"
        for skip in entry["skips"]:
            assert (REPO_ROOT / str(skip["file"])).is_file(), f"{entry_id}: 파일이 없다 {skip['file']}"
            assert str(skip["reason"]).strip(), f"{entry_id}: reason 이 비었다"
            assert int(skip["count"]) > 0, f"{entry_id}: count 는 1 이상이어야 한다"


def test_declared_counts_are_unique_per_file_and_reason() -> None:
    """(파일, 사유)는 등록부에서 **한 번만** 선언된다 — 두 항목이 같은 스킵을 주장하면 대조가 무의미해진다."""
    counted = _declared_skips()
    declared_pairs = [
        (str(skip["file"]), str(skip["reason"])) for entry in _register()["entries"] for skip in entry["skips"]
    ]
    assert len(declared_pairs) == len(set(declared_pairs)), "같은 (파일, 사유)가 여러 항목에 있다"
    assert sum(counted.values()) > 0, "등록부가 한 건도 선언하지 않는다"


def test_observed_files_cover_every_declared_skip_and_exist() -> None:
    """관측 목록 — 선언된 파일을 모두 포함하고, **닫힌 항목의 파일도 잃지 않는다**.

    닫는 일이 관측을 줄이면 안 된다: 닫힌 파일이 관측에서 빠지는 순간 그 자리가 다시 열려도
    계약은 침묵한다. 그래서 `closed` 의 파일도 관측 목록에 있어야 한다.
    """
    observed = set(_observed_files())
    declared = {file for file, _ in _declared_skips()}
    assert declared <= observed, (
        f"선언된 스킵 파일이 관측 목록에 없다: {sorted(declared - observed)} — 그 파일은 재현되지 않아 대조되지 않는다"
    )
    for name in sorted(observed):
        assert (REPO_ROOT / name).is_file(), f"관측 목록에 없는 파일이 있다: {name}"

    for entry_id, closed in cast(Mapping[str, Mapping[str, object]], _register().get("closed") or {}).items():
        assert int(cast(int, closed["skips"])) > 0, f"closed.{entry_id}: 닫은 스킵 수가 0 이다"
        assert str(closed["how"]).strip(), f"closed.{entry_id}: 어떻게 닫았는지 적어라"
        for closed_file in cast(Sequence[object], closed["files"]):
            assert str(closed_file) in observed, (
                f"closed.{entry_id}: 닫은 파일 {closed_file} 이 관측 목록에 없다 — 닫은 자리가 다시 열려도 보이지 않는다"
            )


# ─── 소유자: 스킵을 정당화하는 파이프라인이 실제로 도는가 ────────────────


def test_platform_entries_name_a_pipeline_that_actually_runs_them() -> None:
    """ENV_PLATFORM — `owner_run` 의 파일 이름이 owner 워크플로 안에 **실재해야** 한다.

    "다른 job 이 돌린다"는 주장은 그 job 의 파일을 읽어 확인한다: 주장만 적어 두고 아무도
    돌리지 않는 상태(가장 흔한 거짓)를 계약이 막는다.
    """
    for entry in _register()["entries"]:
        if entry["class"] != "ENV_PLATFORM":
            continue
        owner = REPO_ROOT / str(entry["owner"])
        assert owner.is_file(), f"{entry['id']}: owner 워크플로가 없다 {entry['owner']}"
        workflow = owner.read_text(encoding="utf-8")
        runs = [str(name) for name in entry.get("owner_run", [])]
        assert runs, f"{entry['id']}: owner_run 이 비었다 — 어느 파일을 도는지 밝혀라"
        for name in runs:
            assert name in workflow, (
                f"{entry['id']}: {entry['owner']} 가 {name} 를 돌리지 않는다 — 그 능력은 아무도 재지 않는다"
            )


def test_config_entries_point_at_the_gate_that_measures_the_same_boundary() -> None:
    """ENV_CONFIG — 같은 경계를 재는 파일을 가리키고, **등록부가 그 파일을 스킵으로 선언하지 않는다**.

    두 조각이 이 주장을 완성한다(각각 다른 자리가 소유한다):
      ① 여기서는 **등록부 안의 자기모순**을 본다 — "X 가 대신 잰다"고 적으면서 동시에 X 를
         스킵으로 적으면 그 경계는 아무도 안 잰다.
      ② 런타임 쪽은 아래 `test_gate_environment_skips_exactly_what_the_register_declares` 가
         소유한다 — 관측이 등록부와 달라지면 실패하므로, X 가 실제로 스킵되기 시작하면
         (선언하지 않았어도) 그 자리에서 드러난다.

    여기서 ②를 다시 재지 않는 이유: 같은 실행을 두 번 돌리면 계약이 느려지고, 측정을 두 곳이
    들고 있으면 갈라진다(F-27 의 병).
    """
    declared = _declared_skips()
    for entry in _register()["entries"]:
        if entry["class"] != "ENV_CONFIG":
            continue
        covering = REPO_ROOT / str(entry["owner"])
        assert covering.is_file(), f"{entry['id']}: owner 파일이 없다 {entry['owner']}"
        assert str(entry.get("note", "")).strip(), f"{entry['id']}: note 가 비었다 — 무엇이 대신 재는가"
        covered = {file for file, _ in declared if file == str(entry["owner"])}
        assert not covered, (
            f"{entry['id']}: 등록부가 대신 잰다는 {entry['owner']} 마저 스킵으로 적고 있다"
            " — 그러면 그 경계는 아무도 안 잰다(자기모순)"
        )


def test_known_gaps_are_owned_and_expire() -> None:
    """KNOWN_GAP — 미검증 능력은 **소유자·계획·만료일**을 갖고, 판정서 경계 문서에도 적힌다.

    만료일이 지나면 계약이 실패한다: 그 자리를 다시 보라는 뜻이다(감사 예외의 만료와 같은 규율).

    항목이 **0건이면** 이 루프는 아무것도 재지 않는다 — 그 침묵을 "미검증 능력이 없다"는 주장으로
    읽지 않도록, 그 사실을 경계 문서가 **명시**하게 한다(침묵은 증거가 아니다: 이 저장소에서 반복된
    병이 바로 "검사가 대상이 아니라 그 부재를 본다"이다).
    """
    register = _register()
    boundary = BOUNDARY_DOC.read_text(encoding="utf-8")
    today = date.today()

    gaps = [entry for entry in register["entries"] if entry["class"] == "KNOWN_GAP"]
    if not gaps:
        assert "미검증 능력 0건" in boundary, (
            f"KNOWN_GAP 이 0건인데 경계 문서({BOUNDARY_DOC.name})가 그 사실을 적지 않았다 — 침묵은 증거가 아니다"
        )

    for entry in gaps:
        entry_id = str(entry["id"])
        assert str(entry["owner"]).strip(), f"{entry_id}: owner 가 비었다"
        assert str(entry["plan"]).strip(), f"{entry_id}: plan 이 비었다 — 어떻게 닫을 것인가"
        assert str(entry.get("capability", "")).strip(), f"{entry_id}: capability 가 비었다 — 무엇이 미검증인가"
        due = date.fromisoformat(str(entry["review_due"]))
        assert due > today, f"{entry_id}: review_due({due}) 가 지났다 — 이 미검증 능력을 다시 보거나 계획을 갱신하라"
        assert entry_id in boundary, (
            f"{entry_id}: 경계 문서({BOUNDARY_DOC.name})에 적히지 않았다 — 보이지 않는 결함이다"
        )


# ─── 대조: 게이트 환경이 실제로 스킵하는 것과 같은가 ─────────────────────


@requires_uv
def test_gate_environment_skips_exactly_what_the_register_declares() -> None:
    """기능 계약 — 게이트 환경을 재현해 스킵 집합을 **한 건씩** 대조한다.

    실패하는 두 방향 모두 뜻이 있다: 관측이 더 많으면 **등록되지 않은 스킵이 생겼다**
    (커버리지가 조용히 줄었다), 관측이 더 적으면 **등록부가 낡았다**(능력이 돌아왔거나
    스킵이 다른 사유로 바뀌었다). 어느 쪽이든 사람이 그 변화를 적어야 한다.
    """
    observed = _observed_skips()
    declared = _declared_skips()

    assert observed == declared, (
        "게이트 환경의 스킵 집합이 등록부와 다르다.\n"
        f"  등록부에만 있음: {_as_lines(declared - observed)}\n"
        f"  관측에만 있음:   {_as_lines(observed - declared)}"
    )


# ─── 게이트 전수: 다른 게이트의 스킵도 이름을 갖는다 (R-16 · attempt-024) ────

# 스킵을 **테스트 단위로** 귀속시키는 pytest 플래그(`-v` 스킵 줄, `-rs` 스킵 요약).
PYTEST_ATTRIBUTION_FLAGS = ("-v", "-rs", "-ra")
VALID_ATTRIBUTIONS = ("per_test", "no_skip_concept")
VALID_OBSERVATIONS = ("registered", "close_check", "none")
# 스크립트 게이트의 스킵 채널 — `--skip-*` 플래그와 `SKIP_*` 변수가 그 흔적이다.
SCRIPT_SKIP_MARKER = re.compile(r"--skip-[a-z0-9][a-z0-9-]*|SKIP_[A-Z][A-Z0-9_]*")
# vitest·playwright 소스의 스킵 마커 — 등록되지 않은 마커가 생기면 이 계약이 먼저 본다.
DASHBOARD_TEST_MARKER = re.compile(r"\b(?:it|test|describe)\.(?:skip|todo|only)\b|\btest\.(?:skip|fixme|only)\b")


@dataclass(frozen=True)
class RegisteredSkip:
    """소스에 남긴 조건부 스킵 하나의 회계 — 사유·owner·재검토 기한."""

    count: int
    condition: str
    reason: str
    owner: str
    review_due: date


# 소스 마커의 회계. 등록부(`gate_skip_register.json`)의 `entries`·`observed_files` 는 **python-tests
# 게이트의 스킵 집합**을 대조하는 자리라(등록부 scope 참조) playwright 소스 마커를 담을 채널이 없다.
# 그래서 소스 마커는 그 마커를 세는 이 contract 옆에 등록한다 — 등록은 **양방향**이다: 등록되지 않은
# 마커는 실패하고, 조건 토큰이 사라진 등록도 실패한다(등록이 면죄부가 되지 않게). review_due 는 그
# 자리를 다시 보라는 규율이다(audit 예외의 만료와 같은 형태 — 등록부 `KNOWN_GAP` 규칙).
DASHBOARD_SKIP_REGISTER: dict[str, RegisteredSkip] = {
    "dashboard/e2e/ssak-web-integration.spec.ts": RegisteredSkip(
        count=1,
        condition="AGK_E2E_SSAK_BUNDLE",
        reason=(
            "S1 만 **실 번들 바이너리**(64MB)를 요구한다 — 번들이 없는 환경에서 그 케이스를 통과로 위장하지 "
            "않으려고 조건부 skip 으로 두고, 건너뛴 이유를 이름과 사유로 말한다(opt-in 계약의 기록: "
            ".omo/evidence/ssak-ai-web-integration/2026-09-18T1112Z/task-14/assertions.json)"
        ),
        owner="dashboard/e2e/ssak-web-integration.spec.ts (dashboard-e2e-witnesses 게이트)",
        review_due=date(2026, 12, 31),
    ),
}


@dataclass(frozen=True)
class SkipAudit:
    """소스 마커 회계의 판정 — 양방향(등록되지 않은 마커 / 낡은 등록)과 전제 위반."""

    unregistered: tuple[str, ...]
    stale: tuple[str, ...]
    registration: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not (self.unregistered or self.stale or self.registration)

    def describe(self) -> str:
        parts: list[str] = []
        if self.unregistered:
            parts.append(f"등록되지 않은 스킵 마커: {list(self.unregistered)}")
        if self.stale:
            parts.append(f"등록만 남은 스킵 마커(등록 정리 필요): {list(self.stale)}")
        parts.extend(self.registration)
        return " / ".join(parts)


def audit_dashboard_skips(
    markers: Mapping[str, list[str]] | None = None,
    *,
    texts: Mapping[str, str] | None = None,
    today: date | None = None,
) -> SkipAudit:
    """소스 마커와 등록을 대조한다.

    `markers`·`texts`·`today` 를 주면 그 값으로 판정한다 — 이빨(등록 없이 늘어난 마커, 조건 토큰이
    사라진 등록, 기한 경과)을 실물 없이 시험할 수 있게 한다.
    """

    observed = dashboard_skip_markers() if markers is None else dict(markers)
    reference = today or date.today()

    def text_of(path: str) -> str:
        if texts is not None:
            return texts.get(path, "")
        return (REPO_ROOT / path).read_text(encoding="utf-8")

    registration: list[str] = []
    for path, entry in sorted(DASHBOARD_SKIP_REGISTER.items()):
        hits = observed.get(path)
        if hits is None:
            continue
        if len(hits) > entry.count:
            registration.append(f"{path}: 마커 {len(hits)}건 > 등록 {entry.count}건 — 등록 없이 늘었다 {hits}")
        if entry.condition not in text_of(path):
            registration.append(f"{path}: 조건 {entry.condition!r} 이 사라졌다 — 등록된 스킵의 전제가 바뀌었다")
        if reference > entry.review_due:
            registration.append(f"{path}: 재검토 기한 {entry.review_due.isoformat()} 이 지났다(owner: {entry.owner})")

    return SkipAudit(
        unregistered=tuple(sorted(path for path in observed if path not in DASHBOARD_SKIP_REGISTER)),
        stale=tuple(sorted(path for path in DASHBOARD_SKIP_REGISTER if path not in observed)),
        registration=tuple(registration),
    )


def dashboard_skip_markers() -> dict[str, list[str]]:
    """vitest·playwright 가 수집하는 소스의 스킵 마커 — 파일 → ["경로:줄", ...]."""
    markers: dict[str, list[str]] = {}
    roots = (REPO_ROOT / "dashboard" / "src", REPO_ROOT / "dashboard" / "e2e")
    for base in roots:
        for path in sorted(base.rglob("*.ts")) + sorted(base.rglob("*.tsx")):
            if "node_modules" in path.parts:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if DASHBOARD_TEST_MARKER.search(line):
                    markers.setdefault(relative, []).append(f"{relative}:{number}")
    return markers


def _required_gates() -> list[dict[str, Any]]:
    payload: dict[str, Any] = json.loads(GATE_FILE.read_text(encoding="utf-8"))
    return [gate for gate in payload["gates"] if gate.get("required")]


def _visibility() -> dict[str, Mapping[str, Any]]:
    entries = cast(Sequence[Mapping[str, Any]], _register()["gate_visibility"]["gates"])
    return {str(entry["gate"]): entry for entry in entries}


def _gate_commands() -> dict[str, list[str]]:
    return {str(gate["id"]): [str(token) for token in gate["command"]] for gate in _required_gates()}


def _script_of(command: Sequence[str]) -> Path | None:
    """게이트 명령에서 그 게이트가 도는 **스크립트**를 찾는다(실재하는 파일만).

    스크립트 토큰만 본다: `bandit … -x src/…/secret_scanner.py` 처럼 **인자로 들어간 소스 파일**을
    스크립트로 오인하면 엉뚝한 파일을 스캔하게 된다(`scripts/` 아래이거나 `.sh` 여야 한다).
    """
    for token in command:
        if token.endswith(".sh") or (token.startswith("scripts/") and token.endswith(".py")):
            candidate = REPO_ROOT / token
            if candidate.is_file():
                return candidate
    return None


def test_every_required_gate_is_classified_for_skip_visibility() -> None:
    """전수성 — **required 게이트를 추가하면 분류도 함께 적어야 한다**.

    이것이 R-16 의 구조적 절반이다: 게이트를 하나 늘리고 분류를 빠뜨리면 그 게이트의 스킵은
    다시 익명이 되므로, 계약이 그 자리에서 멈춘다(개수를 손으로 맞추는 대신 목록을 맞춘다 —
    F-21 이 개수 고정을 목록 고정으로 바꾼 것과 같은 이유).
    """
    classified = _visibility()
    required = {str(gate["id"]) for gate in _required_gates()}
    missing = sorted(required - set(classified))
    extra = sorted(set(classified) - required)
    assert not missing, (
        f"required 게이트가 스킵 가시성 분류에 없다: {missing}"
        " — 그 게이트가 조용히 테스트를 빼도 아무 자리가 아프지 않다(R-16)"
    )
    assert not extra, f"분류에만 있는 게이트가 있다(오타이거나 게이트가 사라졌다): {extra}"

    for gate_id, entry in sorted(classified.items()):
        assert str(entry.get("runner", "")).strip(), f"{gate_id}: runner 가 비었다"
        assert entry["attribution"] in VALID_ATTRIBUTIONS, (
            f"{gate_id}: 알 수 없는 attribution {entry['attribution']!r}"
            f" — 허용: {VALID_ATTRIBUTIONS}. `summary_only` 는 허용하지 않는다: 귀속 플래그를 붙이면 `per_test` 가 된다"
        )
        assert entry["observation"] in VALID_OBSERVATIONS, (
            f"{gate_id}: 알 수 없는 observation {entry['observation']!r} — 허용: {VALID_OBSERVATIONS}"
        )
        assert str(entry.get("how", "")).strip(), f"{gate_id}: how 가 비었다 — 스킵이 어떻게 드러나는지 적어라"
        if entry["attribution"] == "per_test":
            assert entry["observation"] in {"registered", "close_check"}, (
                f"{gate_id}: 귀속이 가능한데 관측 자리가 없다 — 누가 세는가"
            )


def test_pytest_gates_can_attribute_a_skip_to_a_test() -> None:
    """pytest 게이트 — 스킵이 **테스트 단위로 귀속**되어야 한다.

    attempt-024 의 측정: `api-e2e` 는 `-q` 뿐이어서 스킵이 생기면 `N skipped` 만 남고 **이름이
    없었다**(그 자리가 익명이 되면 등록부가 세야 할 대상이 이름을 잃는다). `-rs` 를 넣어 고쳤다.
    """
    for gate_id, command in sorted(_gate_commands().items()):
        if not any("pytest" in token for token in command):
            continue
        assert any(flag in command for flag in PYTEST_ATTRIBUTION_FLAGS), (
            f"{gate_id}: pytest 인데 스킵을 테스트 단위로 귀속시키는 플래그가 없다 {command}"
            f" — 필요: {list(PYTEST_ATTRIBUTION_FLAGS)}. `N skipped` 만 남으면 무엇이 검증되지 않았는지 알 수 없다"
        )


def test_non_pytest_gates_report_skip_names() -> None:
    """vitest·playwright — 스킵이 **이름으로** 보고되어야 한다(둘 다 실측으로 확인했다).

    vitest 기본 리포터는 `1 skipped` 건수만 내고 이름을 내지 않는다(스크래치 테스트로 측정) —
    `--reporter=verbose` 가 `↓ <파일> > <describe> > <테스트>` 로 이름을 낸다.
    playwright 는 `list` 리포터가 `- <n> [project] › <파일>:<줄> › <이름>` 으로 낸다.
    """
    commands = _gate_commands()
    assert "--reporter=verbose" in commands["dashboard-test"], (
        f"dashboard-test: vitest 기본 리포터는 건수만 낸다 — `--reporter=verbose` 가 이름을 낸다 {commands['dashboard-test']}"
    )
    config = (REPO_ROOT / "dashboard" / "playwright.config.ts").read_text(encoding="utf-8")
    assert re.search(r"reporter:\s*\[[\s\S]{0,400}?['\"]list['\"]", config), (
        "accessibility-e2e: playwright 의 `list` 리포터가 스킵을 이름으로 낸다"
        " — 리포터를 바꾸면 그 게이트의 스킵이 익명이 된다"
    )


def test_dashboard_sources_have_no_unregistered_skip_markers() -> None:
    """소스 스킵 마커 — **등록된 것만** 허용하고, 등록이 낡으면 그쪽도 실패한다(양방향 tripwire).

    마커가 생기면 vitest·playwright 는 그 테스트를 건너뛰고 게이트는 초록으로 남는다(이름은 verbose
    리포터가 내지만, 등록은 사람이 해야 한다). 그래서 새 마커는 **여기서 먼저 멈춘다**. 등록된 마커도
    **전제(조건 토큰)가 사라지거나 재검토 기한이 지나면** 멈춘다 — 등록이 면죄부가 되지 않게 한다.
    """
    audit = audit_dashboard_skips()
    assert audit.clean, (
        f"{audit.describe()} — vitest·playwright 는 스킵된 테스트를 건너뛰면서 게이트는 초록으로 남는다. "
        "등록하거나 제거하라(등록은 사유·owner·재검토 기한을 갖는다)"
    )
    assert DASHBOARD_SKIP_REGISTER, "등록부가 비었는데 스킵이 0건이라는 주장은 근거가 없다"


def test_dashboard_skip_marker_accounting_has_teeth() -> None:
    """등록이 면죄부가 되지 않는지 — 가짜 마커·가짜 텍스트로 네 가지 위반을 모두 재현한다."""

    real = "dashboard/e2e/ssak-web-integration.spec.ts"
    registered_text = (REPO_ROOT / real).read_text(encoding="utf-8")

    # ① 등록되지 않은 파일의 마커
    audit = audit_dashboard_skips({"dashboard/src/새파일.test.ts": ["dashboard/src/새파일.test.ts:3"]})
    assert audit.unregistered == ("dashboard/src/새파일.test.ts",)

    # ② 등록된 파일인데 조건 토큰이 사라졌다
    audit = audit_dashboard_skips({real: [f"{real}:191"]}, texts={real: "test.skip(!BUNDLE, 'no bundle')"})
    assert audit.registration and "조건" in audit.registration[0]

    # ③ 마커가 등록 건수를 넘었다
    audit = audit_dashboard_skips({real: [f"{real}:191", f"{real}:200"]}, texts={real: registered_text})
    assert audit.registration and "등록 없이 늘었다" in audit.registration[0]

    # ④ 재검토 기한 경과
    entry = DASHBOARD_SKIP_REGISTER[real]
    audit = audit_dashboard_skips(
        {real: [f"{real}:191"]}, texts={real: registered_text}, today=date(entry.review_due.year + 1, 1, 1)
    )
    assert audit.registration and "재검토 기한" in audit.registration[0]

    # ⑤ 등록만 남았다(마커가 사라졌는데 등록이 살아 있다)
    assert audit_dashboard_skips({}).stale == (real,)


def test_script_gates_declare_their_skip_channels_and_the_gate_uses_none() -> None:
    """스크립트 게이트 — 스킵 채널은 **선언**되고, 게이트 명령은 그 채널을 **쓰지 않아야** 한다.

    attempt-024 의 측정: `clean-machine-runtime` 의 스크립트는 `--skip-e2e`·`--skip-wheel` 을 갖고
    그 플래그가 켜지면 요약에 `SKIP` 행이 생기면서 **게이트는 초록으로 남는다**. 지금 게이트 명령에는
    두 플래그가 **없다** — 이 조항은 그 사실을 고정한다. 누군가 편의를 위해 `--skip-wheel` 을
    명령에 넣으면 wheel 검증이 통째로 사라지는데 계약은 그대로 통과할 뻔했다(게이트 안에서는
    사라진 단계와 존재하는 단계가 같은 초록을 낸다).
    """
    classified = _visibility()
    commands = _gate_commands()
    for gate_id, entry in sorted(classified.items()):
        if entry["runner"] not in {"bash", "python-script", "script"}:
            continue
        script = _script_of(commands[gate_id])
        assert script is not None, (
            f"{gate_id}: 스크립트 게이트인데 명령에서 실재하는 스크립트를 찾지 못했다 {commands[gate_id]}"
        )
        text = script.read_text(encoding="utf-8")
        # `skip_channels` 는 스크립트 안의 **모든** 스킵 표기(CLI 플래그와 내부 토글)를 적는다 —
        # 하나라도 빠지면 그것이 조용한 자리다. 게이트 명령 검사는 그중 `--` 로 시작하는 것만 본다.
        declared = [str(channel) for channel in entry.get("skip_channels", [])]
        found = sorted(set(SCRIPT_SKIP_MARKER.findall(text)))
        undeclared = [marker for marker in found if marker not in declared]
        assert not undeclared, (
            f"{gate_id}: {script.name} 에 선언되지 않은 스킵 채널이 있다 {undeclared}"
            f" — 등록부 `gate_visibility.gates[{gate_id}].skip_channels` 에 적어라(모르는 스킵 채널은 조용한 자리다)"
        )
        used = [channel for channel in declared if channel.startswith("--") and channel in commands[gate_id]]
        assert not used, f"{gate_id}: 게이트 명령이 스킵 플래그 {used} 를 쓴다 — 그 단계가 사라져도 게이트는 초록이다"
