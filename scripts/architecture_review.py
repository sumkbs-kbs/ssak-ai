#!/usr/bin/env python
"""T14 최종 Architecture Review harness — 헌법 24원칙·원문 §63·§52 drift 질문을 증거에 연결한다.

이 스크립트는 "리뷰 문서를 사람이 잘 썼는가"를 검사하지 않는다. 다음을 기계적으로 검사한다.

1. 매핑이 인용한 evidence 문서·시험 파일·module이 실제로 존재하는가.
2. `docs/ssak-ai-core` 안의 상대 link가 전부 해석되는가(frontmatter/표 포함).
3. 인수 체크리스트의 모든 항목(T00a~T14)이 원칙 매핑에 등장하고, 매핑의 카드 ID가 실재하는가.
4. `evidence/` 의 각 문서가 실제로 인용되는가(고아 증거 방지).
5. 리뷰 문서가 24원칙·§63 질문·§52 질문을 모두 다루고, 매핑의 artifact 경로를 그대로 담고 있는가.
6. 리뷰 문서의 `<!-- measured:key=value -->` 마커가 실제 측정값과 일치하는가(시험 개수 drift 방지).
7. 전량 회귀 원장(`evidence/regression_ledger.json`)이 **scope 별로 두 회차**를 갖고 결정적 실패에 전부
   소유자가 있는가. 한 회차짜리 scope 는 "결정적"과 "seed 민감"을 구분하지 못하므로 수치로 쓰지 않는다.

값을 못 박지 않은 서술은 통과시키지 않는다. 마커가 없으면 실패하며, 실패 메시지가 기대값을 그대로 알려준다.

```sh
.venv/bin/python scripts/architecture_review.py                     # 검사 + 표 출력
.venv/bin/python scripts/architecture_review.py --output /tmp/t14.json
```
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Final, Literal

# 공통 harness 계약(자기시험 · 탐지력 하한) — scripts/ 는 저장소 안의 도구 모음이라 직접 import 한다.
_SCRIPTS_DIR: Final[Path] = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from harness_contract import Floor, Probe, floor_problems, probe_problems  # noqa: E402, Literal

EXIT_OK: Final[int] = 0
EXIT_FAILED: Final[int] = 1

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DOCS_ROOT: Final[Path] = Path("docs/ssak-ai-core")
CHECKLIST: Final[Path] = DOCS_ROOT / "ACCEPTANCE_CHECKLIST.md"
REVIEW_DOC: Final[Path] = DOCS_ROOT / "ARCHITECTURE_REVIEW.md"
CONSTITUTION: Final[Path] = DOCS_ROOT / "SSAK_AI_CONSTITUTION.md"
EVIDENCE_DIR: Final[Path] = DOCS_ROOT / "evidence"

# 전량 회귀 원장(`scripts/regression_ledger.py`)의 산출물 — 리뷰가 인용하는 회귀 수치의 출처.
REGRESSION_LEDGER: Final[Path] = EVIDENCE_DIR / "regression_ledger.json"

# 증거가 못 박은 sha256 의 현재 일치 여부(`scripts/digest_drift.py`)의 산출물.
DIGEST_DRIFT_SCRIPT: Final[Path] = REPO_ROOT / "scripts" / "digest_drift.py"
DIGEST_DRIFT_ARTIFACT: Final[Path] = EVIDENCE_DIR / "digest_drift.json"

# 문서의 “이 시험은 실패한다” 류 상태 주장을 재판정하는 감사(`scripts/audit_state_claims.py`).
STATE_CLAIMS_SCRIPT: Final[Path] = REPO_ROOT / "scripts" / "audit_state_claims.py"
STATE_CLAIMS_ARTIFACT: Final[Path] = EVIDENCE_DIR / "state_claims.json"

# 탐지력 하한이 **실제로 무는지**를 확인하는 카나리아(`scripts/harness_canary.py`).
CANARY_SCRIPT: Final[Path] = REPO_ROOT / "scripts" / "harness_canary.py"

# 위반 0건인 감사가 **실제로 빨간을 낼 수 있는지** 저장소 밖 트리에서 재현하는 red 리허설(`scripts/red_rehearsal.py`).
REHEARSAL_SCRIPT: Final[Path] = REPO_ROOT / "scripts" / "red_rehearsal.py"

# 하한 원장(`scripts/floor_ledger.py`) — 어떤 하한이 있고 무엇을 보고 언제 누가 승인했는가.
# 방향은 **리뷰 → 원장** 한 쪽뿐이다: 원장은 카나리아 roster 의 harness 들만 읽고 이 리뷰를 부르지 않으므로
# (게이트 ↔ 리뷰와 달리) 돌려도 서로를 부르지 않는다.
LEDGER_SCRIPT: Final[Path] = REPO_ROOT / "scripts" / "floor_ledger.py"
# 원장이 “승인을 읽지 못했다” 를 적는 문장(`floor_ledger.approval_text`) — 그 문장이 표에 있으면 통과가 아니다.
UNREAD_APPROVAL: Final[str] = "**못 읽음**"

# 여섯 층을 한 번에 도는 증거 게이트(`scripts/evidence_gate.py`). 리뷰는 이 게이트를 **돌리지 않고** roster 와
# 자기시험만 읽는다 — 게이트의 stage 중 하나가 이 리뷰라서, 돌리면 서로를 불러 끝나지 않는다(단방향 계약).
EVIDENCE_GATE_SCRIPT: Final[Path] = REPO_ROOT / "scripts" / "evidence_gate.py"

Status = Literal["covered", "partial", "gap"]
Answer = Literal["yes", "yes_with_limits", "no"]


@dataclass(frozen=True, slots=True)
class Principle:
    """헌법 원칙 하나와 그 근거(카드·증거·시험·module)."""

    number: int
    title: str
    cards: tuple[str, ...]
    evidence: tuple[str, ...]
    tests: tuple[str, ...]
    modules: tuple[str, ...]
    status: Status
    limit: str


@dataclass(frozen=True, slots=True)
class SourceQuestion:
    """원문 §63 최종 Architecture Review 질문."""

    key: str
    section: str
    question: str
    answer: Answer
    basis: str
    limit: str


@dataclass(frozen=True, slots=True)
class DriftQuestion:
    """원문 §52 drift 질문. triggered=True는 "YES가 있다"이며 Architecture Review 대상이다."""

    key: str
    question: str
    triggered: bool
    basis: str
    note: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str
    observed: object = None


@dataclass(slots=True)
class ReviewMeasurement:
    principles: tuple[Principle, ...]
    source_questions: tuple[SourceQuestion, ...]
    drift_questions: tuple[DriftQuestion, ...]
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)
    measured: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(check.detail for check in self.checks if not check.passed)

    def as_mapping(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail, "observed": c.observed} for c in self.checks
            ],
            "failures": list(self.failures),
            "measured": dict(sorted(self.measured.items())),
            "principles": [
                {
                    "number": p.number,
                    "title": p.title,
                    "cards": list(p.cards),
                    "evidence": list(p.evidence),
                    "tests": list(p.tests),
                    "modules": list(p.modules),
                    "status": p.status,
                    "limit": p.limit,
                }
                for p in self.principles
            ],
            "source_questions": [
                {
                    "key": q.key,
                    "section": q.section,
                    "question": q.question,
                    "answer": q.answer,
                    "basis": q.basis,
                    "limit": q.limit,
                }
                for q in self.source_questions
            ],
            "drift_questions": [
                {
                    "key": d.key,
                    "question": d.question,
                    "triggered": d.triggered,
                    "basis": d.basis,
                    "note": d.note,
                }
                for d in self.drift_questions
            ],
        }


# --------------------------------------------------------------------------------------
# 헌법 24원칙 ↔ 카드/증거/시험/module 매핑
# --------------------------------------------------------------------------------------

_PRINCIPLES: Final[tuple[Principle, ...]] = (
    Principle(
        number=1,
        title="Brain Replaceability",
        cards=("T01a", "T02", "T04"),
        evidence=("T01a_typed_model.md", "T02_canonical_store.md", "T03_T04_context_brain.md"),
        tests=("test_models.py", "test_brain.py", "test_store.py"),
        modules=("models.py", "brain.py", "store.py"),
        status="partial",
        limit="교체성 guard(도구/UI import 금지)와 canonical record 유지 시험은 있다. 실제 A/B provider 교체는 실 provider가 필요해 미실행.",
    ),
    Principle(
        number=2,
        title="Brain-Centered Cognition",
        cards=("T04", "T05", "T06"),
        evidence=("T03_T04_context_brain.md", "T05_governance.md", "T06_commit.md"),
        tests=("test_brain.py", "test_governance.py", "test_readiness.py"),
        modules=("brain.py", "governance.py", "readiness.py"),
        status="covered",
        limit="Body는 판단의 정답을 심사하지 않고 구조·권한·readiness만 본다(provider LLM 호출 0 spy). 실제 prompt 수준 검증은 실모델 QA 이월.",
    ),
    Principle(
        number=3,
        title="Experienced Cognitive Orchestrator",
        cards=("T08", "T10", "T13"),
        evidence=("T08_T09_episode.md", "T10_learning.md", "T13_growth.md"),
        tests=("test_episode.py", "test_learning.py", "test_growth.py"),
        modules=("runtime.py", "learning.py", "growth.py"),
        status="partial",
        limit="운영 학습 target은 CONTEXT_DEPTH 하나이고, 사용자 대화 경로는 아직 core를 부르지 않는다(P11).",
    ),
    Principle(
        number=4,
        title="Responsibility Boundary",
        cards=("T04", "T05", "T06"),
        evidence=("T05_governance.md", "T06_commit.md", "T03_T04_context_brain.md"),
        tests=("test_governance.py", "test_readiness.py", "test_brain.py"),
        modules=("governance.py", "readiness.py", "decisions.py"),
        status="covered",
        limit="공유 영역의 의미 통합 주체는 Primary(또는 human-assisted)이며, Body 다수결·semantic merge는 시험으로 금지되어 있다.",
    ),
    Principle(
        number=5,
        title="Human Authority",
        cards=("T01b", "T05", "T11"),
        evidence=("T01b_protection.md", "T05_governance.md", "T11_surface.md"),
        tests=("test_protection.py", "test_governance.py", "test_surface.py", "test_enum_identity.py"),
        modules=("authority.py", "protected_targets.py", "../cognitive_surface.py"),
        status="partial",
        limit="ACTIVE 전환은 사람 승인·dispatch port·canonical project id가 모두 필요하고 fail-closed다. dimension 비교는 same_enum(정의 module·class 이름·값)으로 고정되어 중복 로드나 값이 같은 다른 enum에 흔들리지 않는다. 승인 발급 주체·보호 hook의 실제 연결은 T01b 이월.",
    ),
    Principle(
        number=6,
        title="Current-State Primacy",
        cards=("T03", "T10"),
        evidence=("T03_T04_context_brain.md", "T10_learning.md"),
        tests=("test_context.py", "test_learning.py"),
        modules=("context.py", "learning.py"),
        status="covered",
        limit="과거 confidence가 높아도 현재 applicability가 MISMATCH면 advisory로만 제시된다(현재 결론으로 강제되지 않음).",
    ),
    Principle(
        number=7,
        title="Historical Preservation",
        cards=("T02", "T06", "T09", "T12"),
        evidence=("T02_canonical_store.md", "T06_commit.md", "T08_T09_episode.md", "T12_migration.md"),
        tests=("test_readiness.py", "test_episode.py", "test_migration.py"),
        modules=("decisions.py", "experience.py", "migration.py"),
        status="covered",
        limit="재해석은 새 version record이고, reopen은 append다. migration dry-run은 source를 `mode=ro`로만 열어 digest 불변을 확인한다.",
    ),
    Principle(
        number=8,
        title="Experience Ownership",
        cards=("T09",),
        evidence=("T08_T09_episode.md",),
        tests=("test_episode.py",),
        modules=("experience.py", "models.py"),
        status="covered",
        limit="Brain Output 자체는 Experience가 아니며, Context·판단·거버넌스·행동·결과가 연결된 episode만 Experience 후보가 된다.",
    ),
    Principle(
        number=9,
        title="Experience Must Change Future Behavior",
        cards=("T10", "T13"),
        evidence=("T10_learning.md", "T13_growth.md", "T13_live_pilot.md"),
        tests=("test_learning.py", "test_growth.py", "test_live_pilot.py"),
        modules=("learning.py", "growth.py", "live_pilot.py"),
        status="covered",
        limit="후보→검증→승격→다음 task의 실제 선택→outcome이 trace로 연결된다. 성능 수치는 deterministic fixture 한정이고 live pilot은 NOT_RUN.",
    ),
    Principle(
        number=10,
        title="Simple to Start, Designed to Mature",
        cards=("T08", "T13"),
        evidence=("T08_T09_episode.md", "T13_growth.md"),
        tests=("test_readiness.py", "test_growth.py"),
        modules=("runtime.py", "growth.py"),
        status="covered",
        limit="초기 규칙 기반 경로와 성장 경로가 둘 다 있고, 성장 arm은 FINAL split에서 실제 선택을 바꾼다(작은 표본).",
    ),
    Principle(
        number=11,
        title="Earned Complexity",
        cards=("T00a", "T00b", "T10", "T13", "T14"),
        evidence=(
            "T00_baseline.md",
            "T10_learning.md",
            "T13_growth.md",
            "T14_namespace_isolation.md",
            "T14_regression_ledger.md",
            "docs/ssak-ai-core/ARCHITECTURE_REVIEW.md",
        ),
        tests=(
            "test_learning.py",
            "test_growth.py",
            "test_architecture_review.py",
            "test_module_namespace_isolation.py",
            "test_regression_ledger.py",
        ),
        modules=("learning.py", "growth.py"),
        status="partial",
        limit="baseline·metric·split을 실행 전에 등록하고(T00b), ablation 6종이 전부 MEASURED이며 미사용 mechanism은 NOT_RUN으로 no-op 증거에서 배제된다. 다만 live 성능 증거가 없어 core 승격은 아직 아니다.",
    ),
    Principle(
        number=12,
        title="Intentional Cognitive Expansion",
        cards=("T03", "T08"),
        evidence=("T03_T04_context_brain.md", "T08_T09_episode.md"),
        tests=("test_context.py", "test_readiness.py"),
        modules=("context.py", "readiness.py"),
        status="covered",
        limit="확장은 goal/evidence linked이고 bounded다. 무관한 과거 기록은 여유 budget이 있어도 기본 Context에 들어가지 않는다.",
    ),
    Principle(
        number=13,
        title="Stop Rule",
        cards=("T08",),
        evidence=("T08_T09_episode.md",),
        tests=("test_readiness.py", "test_episode.py"),
        modules=("runtime.py", "readiness.py"),
        status="covered",
        limit="material cognitive delta가 없으면 유한 종료하고, stop을 READY로 승격하지 않는다(BLOCKED/DEFER로 남는다).",
    ),
    Principle(
        number=14,
        title="COMMIT Boundary",
        cards=("T06",),
        evidence=("T06_commit.md",),
        tests=("test_readiness.py",),
        modules=("readiness.py", "decisions.py"),
        status="covered",
        limit="9 readiness checks만 보고 semantic judge를 호출하지 않는다(LLM 호출 0 spy). 의미 해석이 더 필요하면 Primary로 돌려보낸다.",
    ),
    Principle(
        number=15,
        title="Decision Closure",
        cards=("T06",),
        evidence=("T06_commit.md",),
        tests=("test_readiness.py", "test_store.py"),
        modules=("decisions.py", "store.py"),
        status="covered",
        limit="material trigger로만 최소 범위 reopen하고 원래 DecisionTrace는 불변이다. 단순 불안·표현 변경으로는 반복 reopen하지 않는다.",
    ),
    Principle(
        number=16,
        title="Risk Philosophy",
        cards=("T05", "T13"),
        evidence=("T05_governance.md", "T13_growth.md"),
        tests=("test_governance.py", "test_growth.py"),
        modules=("governance.py", "growth.py"),
        status="covered",
        limit="RESHAPE는 grant 안에서 scope 축소·checkpoint·verification으로 위험을 줄인다. 고위험이라는 이유만으로 자동 human escalation하지 않는다.",
    ),
    Principle(
        number=17,
        title="Unknown is Valid",
        cards=("T05", "T06"),
        evidence=("T05_governance.md", "T06_commit.md"),
        tests=("test_governance.py", "test_readiness.py"),
        modules=("governance.py", "readiness.py"),
        status="covered",
        limit="ACCEPTABLE Unknown 하나로 NOT_READY가 되지 않고, BLOCKING Unknown만 관련 action을 막는다. N_A에는 사유가 필요하다.",
    ),
    Principle(
        number=18,
        title="Knowledge is Evidence, not Authority",
        cards=("T03", "T10"),
        evidence=("T03_T04_context_brain.md", "T10_learning.md"),
        tests=("test_context.py", "test_learning.py"),
        modules=("context.py", "learning.py"),
        status="covered",
        limit="confidence·applicability·assurance를 분리해 기록하고, learned policy는 헌법·보호 권한을 바꾸지 못한다.",
    ),
    Principle(
        number=19,
        title="Context Philosophy",
        cards=("T03",),
        evidence=("T03_T04_context_brain.md",),
        tests=("test_context.py",),
        modules=("context.py", "references.py"),
        status="partial",
        limit="재구성·최소충분·넓게 검색하고 좁게 주입하는 계약이 시험으로 고정되어 있다. 실제 provider context window에서의 동작 확인은 P11 이월.",
    ),
    Principle(
        number=20,
        title="Brain Steering",
        cards=("T04",),
        evidence=("T03_T04_context_brain.md",),
        tests=("test_brain.py",),
        modules=("brain.py",),
        status="partial",
        limit="Body는 질문·범위를 조정하고 결론을 암시하지 않는다. 실제 모델 응답에서의 편향 부재는 실 provider QA 이월.",
    ),
    Principle(
        number=21,
        title="Targeted Re-reasoning",
        cards=("T04", "T08", "T13"),
        evidence=("T03_T04_context_brain.md", "T08_T09_episode.md", "T13_growth.md"),
        tests=("test_brain.py", "test_readiness.py", "test_growth.py"),
        modules=("brain.py", "runtime.py", "growth.py"),
        status="covered",
        limit="약한 reasoning 범위만 재사고하고 기존 판단은 append 계보로 남는다. ablation에서 이 mechanism을 끄면 safety violation이 재현된다.",
    ),
    Principle(
        number=22,
        title="Cognitive Resource Philosophy",
        cards=("T07", "T13"),
        evidence=("T07_actions.md", "T13_growth.md"),
        tests=("test_actions.py", "test_growth.py"),
        modules=("actions.py", "growth.py"),
        status="partial",
        limit="tool·retry·verification 자원은 측정하지만 latency는 0으로 보고되어 실측이 없다. CPU/GPU/network 자원 배분은 v1 core 범위 밖.",
    ),
    Principle(
        number=23,
        title="Runtime Maturity",
        cards=("T13",),
        evidence=("T13_growth.md",),
        tests=("test_growth.py",),
        modules=("growth.py",),
        status="partial",
        limit="FINAL 18 task에서 retry 39→15, success 비열등으로 '적게 계산하고 같거나 나은 결과'를 관찰했다. 소표본이고 live pilot은 NOT_RUN.",
    ),
    Principle(
        number=24,
        title="Ultimate Relationship",
        cards=("T05", "T11"),
        evidence=("T05_governance.md", "T11_surface.md"),
        tests=("test_governance.py", "test_surface.py"),
        modules=("authority.py", "../cognitive_surface.py"),
        status="partial",
        limit="human-only boundary는 reshape로 우회할 수 없고 ACTIVE 전환은 사람 승인을 요구한다. 실제 Human Partner 표면(대시보드 상태·결정 trace)은 P11 잔여.",
    ),
)


# --------------------------------------------------------------------------------------
# 원문 §63 최종 Architecture Review 질문
# --------------------------------------------------------------------------------------

_SOURCE_QUESTIONS: Final[tuple[SourceQuestion, ...]] = (
    SourceQuestion(
        key="identity",
        section="Identity",
        question="Primary Brain을 교체해도 SSAK-AI인가?",
        answer="yes_with_limits",
        basis="State/Memory/Experience/Decision/Knowledge/Governance/Authority는 canonical store에 남고, cognitive 패키지는 도구·UI 계층을 import하지 못하게 architecture guard가 막는다(test_models.py).",
        limit="실제 A/B provider 교체 실측은 실 provider가 필요해 미실행이다.",
    ),
    SourceQuestion(
        key="continuity",
        section="Continuity",
        question="Brain이 없어도 SSAK-AI의 경험과 Decision History가 유지되는가?",
        answer="yes_with_limits",
        basis="store가 canonical record로 유지되고 rebuild_index·verify_digests로 재구성된다. migration dry-run은 source를 읽기 전용으로만 열어 보존을 확인한다.",
        limit="실사용 vault DB·vector index 대상 dry-run은 별도 실행 항목이다.",
    ),
    SourceQuestion(
        key="brain_boundary",
        section="Brain Boundary",
        question="Body가 두 번째 Semantic Brain이 되지는 않았는가?",
        answer="yes",
        basis="COMMIT은 readiness만 검사하고 semantic judge를 호출하지 않으며(LLM 호출 0), Governance는 요청의 구조·권한·위험만 판정한다. Body 기계 집계와 의미 해석 주체가 분리되어 있다.",
        limit="의미 해석의 author는 Primary 또는 human-assisted 경로뿐이며, 그 경계는 learning 시험으로 고정했다.",
    ),
    SourceQuestion(
        key="context",
        section="Context",
        question="Context를 재구성하는가, 단순 누적하는가?",
        answer="yes",
        basis="ContextBuilder가 매 episode 재구성하고, 무관한 과거 기록은 여유 budget이 있어도 기본 Context로 주입되지 않는다. 확장은 handle 단위이며 권한·digest·만료를 재확인한다.",
        limit="실제 provider context window에서의 축소·불완전 처리 확인은 P11 이월.",
    ),
    SourceQuestion(
        key="experience",
        section="Experience",
        question="Brain Judgment와 SSAK-AI Experience가 분리되어 있는가?",
        answer="yes",
        basis="Brain Output은 Experience가 아니며, OPERATIONAL_ONLY/EXPERIENCE/DEFERRED 선별과 세 평가(Outcome/Decision/Execution)가 분리된다. 선별 이유·근거·producer·정책 version이 남고 어느 경우도 원본을 지우지 않는다.",
        limit="PENDING/UNKNOWN을 성공으로 학습하지 않고, 후속 관찰은 supplement로 append한다.",
    ),
    SourceQuestion(
        key="learning",
        section="Learning",
        question="Experience가 실제 Future Behavior를 바꿀 수 있는가?",
        answer="yes_with_limits",
        basis="후보→ValidationReport→PolicyActivation→다음 task의 실제 선택→outcome이 BehaviorChangeTrace로 연결되고, FINAL split에서 retry 39→15·success 비열등을 관찰했다.",
        limit="deterministic fixture 결과이며 live pilot은 NOT_RUN(exit 2). 소표본(18 task)이라 일반 성능 보장이 아니다.",
    ),
    SourceQuestion(
        key="governance",
        section="Governance",
        question="COMMIT은 readiness만 확인하는가?",
        answer="yes",
        basis="9 checks가 PASS/FAIL/UNKNOWN/N_A와 reference를 가지며, provider spy로 semantic LLM 호출 0을 확인했다. 의미적 결론 문구만 바꾼 fixture에서도 판정이 흔들리지 않는다.",
        limit="guard가 실제 executor에서 강제되는지 여부는 action 계층 시험과 T07 증거로 확인한다.",
    ),
    SourceQuestion(
        key="risk",
        section="Risk",
        question="위험을 무조건 회피하지 않고 reshape 가능한가?",
        answer="yes",
        basis="RESHAPE는 기존 grant 안에서 isolated scope·checkpoint·verification으로 위험을 줄이고, 고위험이라는 이유만으로 자동 human escalation하지 않는다.",
        limit="human-only action은 reshape로 우회할 수 없다(보호 권한 시험).",
    ),
    SourceQuestion(
        key="unknown",
        section="Unknown",
        question="UNKNOWN 상태를 유지할 수 있는가?",
        answer="yes",
        basis="ACCEPTABLE/MATERIAL/BLOCKING Unknown을 구분하고, ACCEPTABLE Unknown 하나로 NOT_READY가 되지 않는다. BLOCKING은 관련 action만 차단한다.",
        limit="원인 UNKNOWN인 실패도 남은 unknown을 명시하고 기록을 닫을 수 있다.",
    ),
    SourceQuestion(
        key="history",
        section="History",
        question="과거 Decision과 Experience를 덮어쓰지 않는가?",
        answer="yes",
        basis="reopen은 최소 범위 append이고 원래 DecisionTrace는 불변이다. 재해석·교정은 새 version record이며 기존 core digest가 동일함을 시험으로 고정했다.",
        limit="migration은 source를 `mode=ro`로만 열고, destructive in-place 변환은 실행하지 않는다(사람 결정 이월).",
    ),
    SourceQuestion(
        key="human",
        section="Human",
        question="Human Partner가 최종 Constitutional Authority인가?",
        answer="yes_with_limits",
        basis="헌법 변경은 CONSTITUTION_CHANGE_PROPOSAL로만 제안 가능하고, ACTIVE 전환은 사람 승인·dispatch port·canonical project id가 모두 있어야 한다. OFF가 기본이고 fail-closed다.",
        limit="승인 발급 주체·보호 hook의 실제 연결(T01b)과 Human Partner 표면(P11)은 미완이다.",
    ),
    SourceQuestion(
        key="complexity",
        section="Complexity",
        question="Evidence 없이 복잡성이 증가하지 않았는가?",
        answer="yes_with_limits",
        basis="성장 mechanism 6종을 한 번에 하나씩 ablation했고 전부 MEASURED이며, 쓰이지 않은 mechanism은 NOT_RUN으로 no-op 비교를 증거에서 제외한다. 개선이 없으면 그대로 기록한다.",
        limit="live 성능 증거가 없으므로 learned policy를 Core로 승격하지 않았다. 현재 위치는 experimental/conditional 단계다.",
    ),
)


# --------------------------------------------------------------------------------------
# 원문 §52 Constitution Drift 질문
# --------------------------------------------------------------------------------------

_DRIFT_QUESTIONS: Final[tuple[DriftQuestion, ...]] = (
    DriftQuestion(
        key="body_semantic_brain",
        question="Does this make Body a semantic Brain?",
        triggered=False,
        basis="COMMIT semantic judge 0(provider 호출 spy), Governance의 advisory_notes 비사용 시험, Body 기계 집계와 의미 해석 분리.",
        note="의미 해석은 Primary/human-assisted author만 허용된다.",
    ),
    DriftQuestion(
        key="brain_replaceability",
        question="Does this reduce Brain replaceability?",
        triggered=False,
        basis="cognitive 패키지의 도구·UI import 금지 guard, fixture 도구·executor는 engine/growth_fixture_tools.py adapter로 분리.",
        note="guard가 실패하면 시험 2건이 즉시 깨진다.",
    ),
    DriftQuestion(
        key="history_dependence",
        question="Does this make memory dependent on conversation history?",
        triggered=False,
        basis="Context는 재구성되고 L1/L2/L3 handle 참조로만 주입된다. 무관 기록 미유입 시험(test_context.py).",
        note="대화 전문을 Brain memory로 넣는 경로는 만들지 않았다.",
    ),
    DriftQuestion(
        key="experience_dictates",
        question="Does this allow experience to dictate conclusions?",
        triggered=False,
        basis="Experience는 advisory이며 applicability MISMATCH면 자동 적용되지 않는다. 승격은 별도 validation report가 필요하다.",
        note="한 실패·한 해석만으로 policy가 바뀌지 않는다(T10-A).",
    ),
    DriftQuestion(
        key="human_authority_bypass",
        question="Does this bypass Human Constitutional Authority?",
        triggered=False,
        basis="ACTIVE 전환은 사람 승인 필수, human-only boundary는 reshape로 우회 불가, 헌법 변경은 제안만 가능.",
        note="승인 발급·검증의 실제 표면 연결은 T01b 이월이다.",
    ),
    DriftQuestion(
        key="unbounded_loops",
        question="Does this create unbounded cognitive loops?",
        triggered=False,
        basis="material cognitive delta stop, expansion budget 소진 시 BLOCKED/DEFER, 유한 SSE(limit 후 done), 성장 runner는 고정 task 수.",
        note="stop은 READY로 승격되지 않는다(T08-D).",
    ),
    DriftQuestion(
        key="commit_semantic",
        question="Does this make COMMIT re-evaluate semantic correctness?",
        triggered=False,
        basis="readiness 입력만 사용하며 결론 문구를 바꾼 fixture에서도 판정이 동일하다. 판정 입력은 type·args·권한·risk·unknown뿐이다.",
        note="의미 판단이 더 필요하면 Primary로 돌려보낸다.",
    ),
    DriftQuestion(
        key="complexity_without_value",
        question="Does this add complexity without measured value?",
        triggered=False,
        basis="6 ablation 전부 MEASURED, 미사용 mechanism은 NOT_RUN으로 제외, 값이 없으면 개선 없음을 그대로 기록.",
        note="live 성능 증거가 없어 Core 승격은 보류 상태다.",
    ),
    DriftQuestion(
        key="prevents_learning",
        question="Does this prevent future learning?",
        triggered=False,
        basis="성장 사슬(후보→검증→활성화→실제 선택 변화)이 FINAL split에서 동작하고 rollback/CAS 계약이 있다.",
        note="운영 target이 하나뿐이라는 범위 제한은 남아 있다(T10-E).",
    ),
    DriftQuestion(
        key="erases_history",
        question="Does this erase cognitive history?",
        triggered=False,
        basis="append-only reopen, 재해석 versioning, migration source read-only, rollback rehearsal은 dry-run 출력을 보존.",
        note="destructive in-place 변환은 실행하지 않는다.",
    ),
)


# --------------------------------------------------------------------------------------
# 검사
# --------------------------------------------------------------------------------------

_CARD_PATTERN: Final[re.Pattern[str]] = re.compile(r"^- \[[ x]\] \*\*(T\d+[a-z]?)\b", re.MULTILINE)
_LINK_PATTERN: Final[re.Pattern[str]] = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_MARKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"<!--\s*measured:([a-z_]+)=(-?\d+)\s*-->")


def _display(path: Path) -> str:
    """가능하면 저장소 기준 상대 경로로 보여준다(밖의 경로는 그대로)."""

    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _resolve(relative: str, *, base: Path = DOCS_ROOT) -> Path:
    """매핑·문서 안의 경로를 실제 파일 경로로 해석한다.

    `evidence/T05_governance.md`처럼 docs 기준 상대 경로와 `../cognitive_surface.py`처럼
    패키지 밖을 가리키는 경로를 모두 처리한다.
    """

    value = relative.strip()
    if value.startswith("evidence/"):
        return (REPO_ROOT / base / value).resolve()
    if value.startswith("../"):
        return (REPO_ROOT / "src" / "antigravity_k" / "engine" / value[3:]).resolve()
    if value.startswith("docs/"):
        return (REPO_ROOT / value).resolve()
    if value.startswith("test"):
        return (REPO_ROOT / "tests" / "cognitive" / value).resolve()
    if value.endswith(".md"):
        return (REPO_ROOT / base / "evidence" / value).resolve()
    if value.endswith(".py"):
        return (REPO_ROOT / "src" / "antigravity_k" / "engine" / "cognitive" / value).resolve()
    return (REPO_ROOT / base / value).resolve()


def collect_test_count(path: Path) -> int | None:
    """pytest 수집 개수를 센다. 수집 실패는 None(호출자가 실패로 처리)."""

    if not path.exists():
        return None
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(path), "-q", "--collect-only", "-p", "no:randomly"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    match = re.search(r"(\d+)\s+tests? collected", result.stdout + result.stderr)
    if match is None:
        return None
    return int(match.group(1))


def check_artifacts(principles: tuple[Principle, ...]) -> CheckResult:
    missing: list[str] = []
    total = 0
    for principle in principles:
        for relative in (*principle.evidence, *principle.tests, *principle.modules):
            total += 1
            if not _resolve(relative).exists():
                missing.append(f"P{principle.number}:{relative}")
    if missing:
        return CheckResult(
            name="artifacts_exist",
            passed=False,
            detail=f"매핑이 인용한 artifact가 없다: {', '.join(sorted(missing))}",
            observed=total,
        )
    return CheckResult(
        name="artifacts_exist",
        passed=True,
        detail=f"{total}개 artifact 참조가 모두 실재한다",
        observed=total,
    )


def check_doc_links() -> CheckResult:
    """docs/ssak-ai-core 안의 상대 link가 모두 해석되는지 확인한다."""

    broken: list[str] = []
    checked = 0
    for document in sorted(DOCS_ROOT.rglob("*.md")):
        text = document.read_text(encoding="utf-8")
        for target in _LINK_PATTERN.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            cleaned = target.split("#", maxsplit=1)[0]
            if not cleaned:
                continue
            checked += 1
            if not (document.parent / cleaned).resolve().exists():
                broken.append(f"{_display(document)} → {target}")
    if broken:
        return CheckResult(
            name="doc_links_resolve",
            passed=False,
            detail=f"깨진 상대 link: {'; '.join(sorted(broken))}",
            observed=checked,
        )
    return CheckResult(
        name="doc_links_resolve",
        passed=True,
        detail=f"상대 link {checked}건이 모두 해석된다",
        observed=checked,
    )


def check_checklist_coverage(principles: tuple[Principle, ...]) -> CheckResult:
    checklist_ids = tuple(dict.fromkeys(_CARD_PATTERN.findall(CHECKLIST.read_text(encoding="utf-8"))))
    mapped = {card for principle in principles for card in principle.cards}
    unmapped = sorted(set(checklist_ids) - mapped)
    unknown_cards = sorted(mapped - set(checklist_ids))
    if unmapped or unknown_cards:
        parts: list[str] = []
        if unmapped:
            parts.append(f"원칙 매핑이 없는 인수 항목: {', '.join(unmapped)}")
        if unknown_cards:
            parts.append(f"체크리스트에 없는 카드 ID: {', '.join(unknown_cards)}")
        return CheckResult(
            name="checklist_coverage",
            passed=False,
            detail=" / ".join(parts),
            observed=len(checklist_ids),
        )
    return CheckResult(
        name="checklist_coverage",
        passed=True,
        detail=f"인수 항목 {len(checklist_ids)}개가 모두 최소 한 원칙에 매핑된다",
        observed=len(checklist_ids),
    )


def check_evidence_referenced(principles: tuple[Principle, ...]) -> CheckResult:
    """evidence/ 의 모든 문서가 실제로 인용되는지(고아 증거 방지), 인용된 증거가 있는지 본다."""

    on_disk = {p.name for p in sorted(EVIDENCE_DIR.glob("*.md"))}
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in sorted(DOCS_ROOT.rglob("*.md")) if p != REVIEW_DOC)
    orphans = sorted(name for name in on_disk if name not in corpus)
    mapped = {name for principle in principles for name in principle.evidence if "/" not in name}
    unknown = sorted(name for name in mapped if name not in on_disk)
    if orphans or unknown:
        parts: list[str] = []
        if orphans:
            parts.append(f"어디에서도 인용되지 않는 증거: {', '.join(orphans)}")
        if unknown:
            parts.append(f"실재하지 않는 증거 파일: {', '.join(unknown)}")
        return CheckResult(
            name="evidence_referenced",
            passed=False,
            detail=" / ".join(parts),
            observed=len(on_disk),
        )
    return CheckResult(
        name="evidence_referenced",
        passed=True,
        detail=f"증거 문서 {len(on_disk)}건이 모두 인용되고, 인용된 증거가 모두 실재한다",
        observed=len(on_disk),
    )


# 문서가 문장 안에서 인용하는 저장소 경로. glob·생략(…) 은 시험이 아니라 패턴이므로 해석하지 않는다.
_CITATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w./-])((?:tests|scripts|src|dashboard|tools|config|data)/[A-Za-z0-9_./\-]+"
    r"\.(?:py|md|json|jsonl|yaml|yml|ts|tsx|sh|txt|toml))"
)
_CITATION_ELISION: Final[tuple[str, ...]] = ("*", "?", "<", ">", "...", "…")
# 탐지력 하한 — 인용 0건은 "모두 추적된다" 가 아니라 "문서를 못 봤다" 일 수 있다.
_MIN_CITATIONS: Final[int] = 1
_WHY_CITATIONS: Final[str] = (
    "2026-09-24 기준 관측: 문서가 지목한 경로 인용이 270건이다. 하한 1 은 작아 보이지만 재는 것이 ‘얼마나 많이 "
    "봤나’ 가 아니라 ‘아무것도 못 보고 초록을 냈나’ 다 — 스캔이 깨지거나 문서 뿌리가 사라지면 관측이 0 이 되고, "
    "그때 ‘모두 실재·추적된다’ 가 ‘한 번도 안 봤다’ 와 구별된다. 부분 범위 호출은 이 하한을 소유하지 않는다"
    "(그 범위를 정한 호출자가 소유한다)."
)


@dataclass(frozen=True, slots=True)
class CitationException:
    """문서가 인용하지만 **추적되지 않는** 경로 — 이유·소유자·재검토 기한을 함께 둔다.

    면죄부가 되지 않도록 등록은 양방향이다: 등록된 경로가 추적되면(또는 추적되는 파일로 해석되면) 낡은
    등록으로 실패하고, 기한이 지나도 실패한다.
    """

    path: str
    owner: str
    reason: str
    review_by: str


# 등록부. 여기 없는 경로를 문서가 인용하는데 실재하지 않거나 추적되지 않으면 검사가 실패한다.
_CITATION_EXCEPTIONS: Final[tuple[CitationException, ...]] = (
    CitationException(
        path="docs/ssak-ai-core/evidence/benchmark_spec.md",
        owner="integration",
        reason="아직 만들지 않은 목표 산출물 — IMPLEMENTATION_ROADMAP 이 '신규 산출물의 목표'라고 명시한다",
        review_by="2026-12-31",
    ),
    CitationException(
        path="src/innocent.md",
        owner="protection",
        reason="T01b 우회 경로 설명의 **예시 링크 대상**이며 실재 경로가 아니다(symlink 예시)",
        review_by="2026-12-31",
    ),
    CitationException(
        path="tests/test_aa_purge_probe.py",
        owner="cognitive-core",
        reason="순서 오염 재현용 임시 진단 — 명령 기록만 남기고 파일은 삭제하는 것이 의도다",
        review_by="2026-12-31",
    ),
    CitationException(
        path="docs/qa/2026-09-16-followup/nx10/fsync/rehearse_flush.sh",
        owner="nx10-qa",
        reason="다른 레인의 미추적 QA 산출물 — 이 카드가 커밋 여부를 결정하지 않는다(digest 고정 대상)",
        review_by="2026-12-31",
    ),
    CitationException(
        path="docs/qa/2026-09-16-followup/nx10/fsync/test_flush_budget_contract.py",
        owner="nx10-qa",
        reason="승격본의 staged 쌍둥이 — nx10 QA 레인 산출물이라 커밋 여부는 그 레인의 결정이다",
        review_by="2026-12-31",
    ),
    CitationException(
        path="docs/qa/2026-09-16-followup/nx10/fsync2/test_view_freshness_contract.py",
        owner="nx10-qa",
        reason="아직 승격되지 않은 F2 쌍둥이 — nx10 QA 레인 산출물이라 커밋 여부는 그 레인의 결정이다",
        review_by="2026-12-31",
    ),
)


def _tracked_paths() -> set[str] | None:
    """git 이 추적하는 경로 집합. 저장소가 아니거나 git 이 없으면 None(칩목)."""

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return {item.decode("utf-8", "replace") for item in result.stdout.split(b"\0") if item}


def _resolve_citation(citation: str) -> Path | None:
    """문서의 인용을 실제 파일로 해석한다(저장소 관행의 축약 표기를 허용).

    예: `tools/ssak_bundle_store.py` → `src/antigravity_k/tools/ssak_bundle_store.py`.
    해석되지 않으면 None — 호출자가 실패로 처리한다.
    """

    candidates = [REPO_ROOT / citation]
    if not citation.startswith(("src/", "tests/", "docs/")):
        candidates.append(REPO_ROOT / "src" / "antigravity_k" / citation)
    candidates.append(REPO_ROOT / "tests" / "cognitive" / citation)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def iter_citations(root: Path | None = None) -> Iterator[tuple[Path, str]]:
    """문서가 지목한 경로 인용을 하나씩 낸다 — **세는 자리와 판정하는 자리가 같은 순회를 쓴다**.

    두 번 구현하면 하한이 재는 수와 검사가 보는 수가 갈라진다(그러면 하한이 다른 것을 재게 된다).
    """

    for doc in sorted((root or DOCS_ROOT).rglob("*.md")):
        text = doc.read_text(encoding="utf-8")
        for citation in sorted(set(_CITATION_PATTERN.findall(text))):
            if any(elision in citation for elision in _CITATION_ELISION):
                continue
            yield doc, citation


def count_citations(root: Path | None = None) -> int:
    """인용 수 — 이 리뷰의 하한이 재는 관측값이다(스캔이 깨지면 0 이 되고, 그때 하한이 문다)."""

    return sum(1 for _ in iter_citations(root))


def coverage_floors(root: Path | None = None) -> list[Floor]:
    """이 리뷰의 탐지력 하한 — **카나리아와 원장이 읽는 자리**다(값 + 근거).

    첫 구현은 이 하한을 검사 함수 안에만 두었고, 그래서 어떤 하한 목록에도 안 실렸다: 카나리아가 눈멀게 한
    사본으로 시험하지도, 원장이 표에 올리지도 못했다(“표 밖은 침묵”). 이제 `_MIN_CITATIONS` 는 이름 있는
    하한으로 나가고, 리뷰는 카나리아 roster 에 `review` 로 들어간다.
    """

    return [Floor("인용", count_citations(root), _MIN_CITATIONS, why=_WHY_CITATIONS)]


def check_citation_tracking(docs_root: Path | None = None, *, on: str | None = None) -> CheckResult:
    """문서가 인용한 저장소 경로가 **실재하고 git 에 추적되는지** 본다.

    실재만 보는 검사(`check_artifacts`)로는 부족하다: 이 체크아웃을 잃으면 사라지는 근거가 통과한다 —
    실제로 `tests/test_cognitive_surface_api.py` 가 T11 증거로 인용되고도 추적되지 않은 적이 있다.
    해석되지 않거나 추적되지 않는 인용은 등록부(`_CITATION_EXCEPTIONS`)에 이유와 기한이 있어야 한다.
    """

    root = docs_root or DOCS_ROOT
    tracked = _tracked_paths()
    if tracked is None:
        return CheckResult(
            name="citation_tracking",
            passed=False,
            detail="git 을 쓸 수 없어 인용이 추적되는지 확인하지 못했다 — 확인 불가를 통과로 쓰지 않는다",
        )
    today = date.fromisoformat(on) if on else date.today()
    registered = {item.path: item for item in _CITATION_EXCEPTIONS}
    unresolved: list[str] = []
    untracked: list[str] = []
    total = 0
    for doc, citation in iter_citations(root):
        total += 1
        resolved = _resolve_citation(citation)
        if resolved is None:
            if citation not in registered:
                unresolved.append(f"{_display(doc)}:{citation}")
            continue
        if resolved.relative_to(REPO_ROOT).as_posix() in tracked:
            continue
        if citation not in registered:
            untracked.append(f"{_display(doc)}:{citation}")

    stale: list[str] = []
    overdue: list[str] = []
    for item in _CITATION_EXCEPTIONS:
        resolved = _resolve_citation(item.path)
        if resolved is not None and resolved.relative_to(REPO_ROOT).as_posix() in tracked:
            stale.append(f"{item.path}(이미 추적된다 — 등록이 필요 없다)")
        elif date.fromisoformat(item.review_by) < today:
            overdue.append(f"{item.path}(재검토 기한 {item.review_by} 경과)")

    problems: list[str] = []
    # 탐지력 하한: 인용이 0건이면 "모두 실재·추적" 이 아니라 **아무것도 못 본 것**일 수 있다.
    # 하한은 **저장소 기본 범위**에만 적용한다 — 부분 범위를 넘기면 그 범위를 정한 호출자가 하한을 소유한다.
    if docs_root is None and total < _MIN_CITATIONS:
        problems.append(
            f"인용이 {total}건뿐이다(저장소 전체 하한 {_MIN_CITATIONS}) — 문서를 읽지 못했거나 패턴이 깨졌을 수 있다"
        )
    if unresolved:
        problems.append(f"해석되지 않는 인용 {len(unresolved)}건 — 등록이 필요하다: {', '.join(unresolved)}")
    if untracked:
        problems.append(f"추적되지 않는 인용 {len(untracked)}건: {', '.join(untracked)}")
    if stale:
        problems.append(f"낡은 등록 {len(stale)}건: {', '.join(stale)}")
    if overdue:
        problems.append(f"재검토 기한이 지난 등록 {len(overdue)}건: {', '.join(overdue)}")
    if problems:
        return CheckResult(
            name="citation_tracking",
            passed=False,
            detail=" / ".join(problems),
            observed=total,
        )
    return CheckResult(
        name="citation_tracking",
        passed=True,
        detail=(f"인용 {total}건이 모두 실재·추적되고, 등록 {len(_CITATION_EXCEPTIONS)}건은 이유와 기한이 있다"),
        observed=total,
    )


def harness_problems(report: dict[str, object], *, name: str, floors: tuple[tuple[str, int], ...]) -> list[str]:
    """harness JSON 의 자기시험·탐지력 하한을 공통 문장으로 — 부재·실패·미달을 모두 실패로 만든다.

    하한 label 은 그 harness 의 JSON 이 `coverage` 안에 싣는 키다(예: `pins` · `runs` · `scanned`).
    """

    raw_probe = report.get("probe")
    probe = (
        Probe(
            cases=_as_int(raw_probe.get("cases")),
            failures=tuple(str(item) for item in _as_list(raw_probe.get("failures"))),
        )
        if isinstance(raw_probe, dict)
        else None
    )
    problems = list(probe_problems(probe, name=name))
    # 하한은 **기록된 근거와 함께** 있어야 한다 — 값만 있으면 나중에 그것을 내려도 되는지 아무도 판단할 수 없다.
    # 기록이 있으면 그 근거를 그대로 인용해 판정하고, 없으면 coverage 의 관측값으로 최소 하한을 적용한다.
    recorded: dict[str, dict[str, object]] = {
        str(item.get("label")): item for item in _as_list(report.get("floors")) if isinstance(item, dict)
    }
    for label, minimum in floors:
        item = recorded.get(label)
        if item is None:
            problems.append(f"{name} 하한 '{label}' 의 근거 기록이 없다 — `floors` 에 관측·최소·근거를 남겨야 한다")
            continue
        if not str(item.get("why", "")).strip():
            problems.append(f"{name} 하한 '{label}' 에 근거(`why`)가 비었다 — 값만 남기면 재판단할 수 없다")
        problems.extend(
            floor_problems(
                [
                    Floor(
                        str(item.get("label")),
                        _as_int(item.get("observed")),
                        _as_int(item.get("minimum")),
                        why=str(item.get("why", "")),
                    )
                ]
            )
        )
    return problems


def read_digest_drift() -> dict[str, object] | None:
    """artifact 를 읽는다. 없거나 깨졌으면 None(호출자가 실패로 처리)."""

    if not DIGEST_DRIFT_ARTIFACT.exists():
        return None
    try:
        return json.loads(DIGEST_DRIFT_ARTIFACT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def measure_digest_drift() -> dict[str, object] | None:
    """`digest_drift.py --emit-json` 으로 지금 값을 다시 잰다(저장본이 썩지 않게).

    종료 코드가 0 이 아니어도 **JSON 이 읽히면 그대로 쓴다**: 그 경로는 판정과 진단을 함께 내므로, 여기서
    None 으로 바꾸면 "왜 이 층이 실패했는지" 가 이음매에서 사라진다. 대신 종료 코드를 보고에 실어 검사가
    모순(보고는 통과인데 스스로 실패했다고 말함)을 잡게 한다.
    """

    result = subprocess.run(
        [sys.executable, str(DIGEST_DRIFT_SCRIPT), "--emit-json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(report, dict):
        return None
    report["exit_code"] = result.returncode
    return report


def _as_int(value: object) -> int:
    """JSON 에서 온 값을 int 로 — 수치가 아니면 0(판정은 호출자가 한다)."""

    return value if isinstance(value, int) else 0


def check_digest_report(stored: dict[str, object] | None, fresh: dict[str, object] | None) -> CheckResult:
    """증거가 못 박은 digest 의 현재 일치 여부가 **측정 artifact 로 최신으로** 남아 있는가.

    파일이 바뀌면 그 증거는 지나간 revision 을 가리키게 된다. 그것을 문서만 읽어 추정하지 않도록
    측정해 두고, 이 검사가 저장본과 방금 잰 값을 대조한다 — 저장본이 낡으면 실패한다.
    """

    if stored is None:
        return CheckResult(
            name="digest_report",
            passed=False,
            detail=(
                f"{_display(DIGEST_DRIFT_ARTIFACT)} 가 없거나 읽히지 않는다 — "
                "scripts/digest_drift.py 를 먼저 돌려야 한다"
            ),
        )
    if fresh is None:
        return CheckResult(
            name="digest_report",
            passed=False,
            detail="digest 를 다시 재지 못했다(scripts/digest_drift.py 가 실패했다) — 확인 불가를 통과로 쓰지 않는다",
        )
    keys = ("counts", "docs", "pins", "floors")
    stale = [key for key in keys if stored.get(key) != fresh.get(key)]
    counts = _as_dict(fresh.get("counts"))
    broken = _as_int(counts.get("missing"))
    stale_reverification = _as_int(counts.get("stale_reverification"))
    problems: list[str] = harness_problems(fresh, name="digest_drift", floors=(("pin", 1), ("pin 을 박은 문서", 1)))
    if stale:
        problems.append(f"artifact 가 최신이 아니다({', '.join(stale)} 불일치) — digest_drift.py 를 다시 돌려야 한다")
    if broken:
        problems.append(f"파일이 없는데 digest 를 못 박은 항목 {broken}건")
    if stale_reverification:
        problems.append(f"재확인 뒤에 파일이 또 바뀌어 무효가 된 재확인 {stale_reverification}건")
    problems.extend(exit_code_problems(fresh, name="digest_drift", already=problems))
    if problems:
        return CheckResult(
            name="digest_report",
            passed=False,
            detail=" / ".join(problems),
            observed=_as_int(counts.get("drift")),
        )
    return CheckResult(
        name="digest_report",
        passed=True,
        detail=(
            f"digest pin {len(_as_list(fresh.get('pins')))}개 — 그대로 {_as_int(counts.get('match'))} · "
            f"재확인 {_as_int(counts.get('reverified'))} · 미확인 움직임 {_as_int(counts.get('drift'))} · "
            f"자기시험 {_as_int(_as_dict(fresh.get('probe')).get('cases'))}건 통과"
        ),
        observed=_as_int(counts.get("reverified")),
    )


def digest_measured(drift: dict[str, object]) -> dict[str, int]:
    """digest 측정에서 리뷰 마커로 고정할 값."""

    counts = _as_dict(drift.get("counts"))
    return {
        "digest_pinned": len(_as_list(drift.get("pins"))),
        "digest_reverified": _as_int(counts.get("reverified")),
        "digest_drifted": _as_int(counts.get("drift")),
        "digest_stale": _as_int(counts.get("stale_reverification")),
        "digest_missing": _as_int(counts.get("missing")),
    }


def measure_canary() -> dict[str, object] | None:
    """카나리아를 돌려 JSON 을 받는다 — 여섯 harness 의 하한이 눈멀게 한 사본을 막는지 본다.

    종료 코드가 0 이 아니어도 **JSON 이 읽히면 그대로 쓴다**: 카나리아는 장식 하한을 찾으면 exit 1 과 함께
    진단을 stdout 에 내므로, 여기서 None 으로 바꾸면 "어느 harness 의 하한이 못 물었는지" 라는 진단이
    판정과 만나는 이음매에서 사라진다. 대신 종료 코드를 보고에 실어 검사가 모순(보고는 전부 통과인데
    스스로 실패했다고 말함)을 잡게 한다.
    """

    result = subprocess.run(
        [sys.executable, str(CANARY_SCRIPT), "--emit-json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(report, dict):
        return None
    report["exit_code"] = result.returncode
    return report


def check_harness_canary(report: dict[str, object] | None) -> CheckResult:
    """탐지력 하한이 **지금 저장소에서 실제로 무는가** — 하한이 장식이면 기록도 장식이다.

    정상 측정을 막지 않고(`healthy`), 눈멀게 한 사본(`observed=0`)은 막으며(`bites`), 실패 문장이 기록된
    근거를 함께 낸다(`carries_reason`). 이 셋 중 하나라도 빠진 harness 는 통과시키지 않는다.
    """

    if report is None:
        return CheckResult(
            name="harness_canary",
            passed=False,
            detail=f"{_display(CANARY_SCRIPT)} 를 돌리지 못했다 — 하한이 무는지 확인하지 않은 실행은 통과시키지 않는다",
        )
    harnesses = [item for item in _as_list(report.get("harnesses")) if isinstance(item, dict)]
    counts = _as_dict(report.get("counts"))
    blind = [str(item.get("name")) for item in harnesses if not item.get("bites")]
    unjustified = [str(item.get("name")) for item in harnesses if not item.get("carries_reason")]
    unhealthy = [str(item.get("name")) for item in harnesses if not item.get("healthy")]
    seen_ok = sum(1 for item in harnesses if item.get("ok"))
    problems: list[str] = []
    if "exit_code" not in report:
        problems.append("카나리아 종료 코드 없이 온 보고다 — 스스로 실패했는지 알 수 없는 보고는 판정이 아니다")
    elif _as_int(report.get("exit_code")) != 0 and not (blind or unjustified or unhealthy):
        problems.append(
            f"카나리아가 exit {_as_int(report.get('exit_code'))} 로 스스로 실패했다고 말했는데 보고는 전부 통과라고 한다(모순)"
        )
    if not harnesses:
        problems.append("카나리아가 harness 를 하나도 보지 않았다")
    if blind:
        problems.append(f"하한이 눈멀게 한 사본을 막지 못한 harness(장식이다): {', '.join(blind)}")
    if unjustified:
        problems.append(f"실패 문장에 하한 근거를 싣지 않은 harness: {', '.join(unjustified)}")
    if unhealthy:
        problems.append(f"하한이 정상 측정을 막은 harness: {', '.join(unhealthy)}")
    if counts and _as_int(counts.get("ok")) != seen_ok:
        problems.append(
            f"합계가 항목과 다르다(ok {_as_int(counts.get('ok'))} ≠ 항목 {seen_ok}) — 보고를 그대로 믿을 수 없다"
        )
    exit_note = f" · 카나리아 exit {_as_int(report.get('exit_code'))}" if "exit_code" in report else ""
    if problems:
        return CheckResult(
            name="harness_canary",
            passed=False,
            detail=" / ".join(problems) + exit_note,
            observed=len(harnesses),
        )
    return CheckResult(
        name="harness_canary",
        passed=True,
        detail=(
            f"harness {len(harnesses)}개 하한이 실제로 문다 — 정상 통과·눈멀게 한 사본 차단·근거 동봉 "
            f"(ok {_as_int(counts.get('ok'))})"
        ),
        observed=len(harnesses),
    )


def canary_measured(report: dict[str, object]) -> dict[str, int]:
    """카나리아에서 마커로 고정할 값."""

    counts = _as_dict(report.get("counts"))
    return {
        "canary_harnesses": _as_int(counts.get("harnesses")),
        "canary_ok": _as_int(counts.get("ok")),
    }


def measure_floor_ledger() -> dict[str, object] | None:
    """하한 원장을 돌려 JSON 을 받는다 — 카나리아와 **같은 이음매 규칙**(exit≠0 이어도 JSON 이 읽히면 그대로 쓴다)."""

    if not LEDGER_SCRIPT.exists():
        return None
    result = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--emit-json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(report, dict):
        return None
    report["exit_code"] = result.returncode
    return report


def check_floor_ledger(report: dict[str, object] | None) -> CheckResult:
    """하한 원장이 **스스로 말한 것과 같은 것을 말하는가** — 표가 자기 합계와 어긋나면 읽는 사람이 잘못된 수를 믿는다.

    원장은 하한을 한 자리에 모으는 층이므로, 여기서 물을 수 있는 것은 “하한이 있는가” 가 아니라 **보고의 정합성**이다:
    층별 하한 합계 = 헤더 합계 · 승인을 못 읽은 층이 없음 · 고아 기록 수 = 헤더 수 · 하한에 근거가 있음 ·
    표 밖 **면제**(선언)가 기록이 승인한 수와 같고 **재검토 창**도 기록과 같음(창을 넓히는 것도 결정이므로 승인된 창과
    재는 자가 갈라지면 안 된다) · 원장이 자기 판정(`verdict`)과 종료 코드에서 모순되지 않음.
    표 밖 **배선**도 같은 자리에서 본다: “배선됐다” 는 수와 “어느 층의 하한인지 이어졌다” 는 지도가 갈라지면(이어지지
    않은 이름이 생기면) 면제가 층이 되는 순간을 잇지 못하고 — 그 사실을 통과 문장이 감춘다(이번 회차의 결함이 그 모양이다:
    하한 **라벨**로 이으려 한 첫 구현이 자기시험만 통과하고 실제 저장소에서는 한 번도 물지 않았다).
    기한 이동 이력은 **보고만** 한다(그 이력이 자기 기한과 맞는지는 원장이 묻고, 어긋나면 기록 문제로 실려 위의
    “통과라는데 기록 문제가 있다” 가 문다) — 리뷰가 수를 옮겨 적는 자리와 판정하는 자리를 가르는 규칙은 원장과 같다.
    """

    if report is None:
        return CheckResult(
            name="floor_ledger",
            passed=False,
            detail=f"{_display(LEDGER_SCRIPT)} 를 돌리지 못했다 — 하한을 한 자리에서 못 본 실행은 통과시키지 않는다",
        )
    layers = [item for item in _as_list(report.get("layers")) if isinstance(item, dict)]
    counts = _as_dict(report.get("counts"))
    coverage = _as_dict(report.get("coverage"))
    orphans = _as_list(report.get("orphans"))
    floors = [item for item in _as_list(report.get("floors")) if isinstance(item, dict)]
    summed = sum(len(_as_list(layer.get("floors"))) for layer in layers)
    unapproved = [str(layer.get("name")) for layer in layers if str(layer.get("approval_text")) == UNREAD_APPROVAL]
    baseless = [str(floor.get("label")) for floor in floors if not str(floor.get("why", "")).strip()]
    record = _as_dict(report.get("record"))
    exempted = _as_dict(record.get("outside"))
    # 표 밖 배선 — 이름 → 그 하한을 드는 층(라벨은 사람이 쓴 이름이라 이름으로는 잇지 못한다): 승격을 잇는 유일한 자리다.
    outside_report = _as_dict(report.get("outside"))
    wiring = _as_dict(outside_report.get("wiring"))
    wired = _as_int(outside_report.get("wired"))
    record_problems = [str(item) for item in _as_list(record.get("problems"))]
    problems: list[str] = []
    exit_code = _as_int(report.get("exit_code"))
    verdict = str(report.get("verdict"))
    if verdict == "PASS" and not record.get("present"):
        problems.append(
            "원장이 통과라고 하는데 **하한 기록이 없다** — 사람이 승인한 목록이 없으면 하한을 내려도 되는지 물을 자리가 없다"
        )
    if verdict == "PASS" and record_problems:
        problems.append("원장이 통과라고 하는데 기록 문제가 함께 실렸다(모순): " + " / ".join(record_problems[:2]))
    if verdict != "PASS":
        problems.append(
            f"원장이 스스로 {verdict} 라고 말했다: {' / '.join(str(item) for item in _as_list(report.get('problems'))[:2])}"
        )
    if exit_code != 0 and verdict == "PASS":
        problems.append(f"원장이 exit {exit_code} 로 스스로 실패했다고 말했는데 보고는 PASS 라고 한다(모순)")
    if not layers:
        problems.append("원장이 층을 하나도 보지 않았다(빈 표는 ‘빠진 하한 없음’ 과 구별되지 않는다)")
    if _as_int(counts.get("floors")) != summed:
        problems.append(
            f"표의 하한 합계가 항목과 다르다(헤더 {_as_int(counts.get('floors'))} ≠ 항목 합 {summed}) — "
            "읽는 사람이 잘못된 수를 믿게 된다"
        )
    if unapproved:
        problems.append(f"승인을 못 읽은 층이 있는데 통과라고 한다: {', '.join(unapproved)}")
    if _as_int(counts.get("orphans")) != len(orphans):
        problems.append(f"고아 기록 수가 목록과 다르다({_as_int(counts.get('orphans'))} ≠ {len(orphans)})")
    if baseless:
        problems.append(f"근거 없는 하한을 표에 싣고도 통과했다: {', '.join(baseless)}")
    if _as_int(counts.get("wired_layers")) != len(wiring):
        problems.append(
            f"배선 지도가 헤더 수와 다르다({_as_int(counts.get('wired_layers'))} ≠ {len(wiring)}) — "
            "“몇 개가 배선됐나” 와 “어느 층의 하한인가” 가 다른 수를 말한다"
        )
    if wired != len(wiring):
        problems.append(
            f"표가 하한으로 아는 이름({wired}개) 중 **어느 층의 하한인지 이어진** 이름이 {len(wiring)}개다 — "
            "이어지지 않은 이름은 승격을 잇지 못한다(그래서 라벨이 아니라 배선으로 잇는다)"
        )
    stray = sorted({str(layer) for layer in wiring.values()} - {str(layer.get("name")) for layer in layers})
    if stray:
        problems.append(f"배선이 표에 없는 층을 가리킨다: {', '.join(stray)} — 그 이름은 어느 층의 하한도 아니다")
    if verdict == "PASS" and _as_int(exempted.get("declared")) != _as_int(exempted.get("recorded")):
        problems.append(
            f"원장이 통과라고 하는데 면제가 기록과 다르다(선언 {_as_int(exempted.get('declared'))} ≠ "
            f"기록 {_as_int(exempted.get('recorded'))}) — 승인되지 않은 면제가 있다는 뜻이다"
        )
    if verdict == "PASS" and _as_int(exempted.get("window_days")) != _as_int(exempted.get("recorded_window_days")):
        problems.append(
            f"원장이 통과라고 하는데 재검토 창이 기록과 다르다(지금 {_as_int(exempted.get('window_days'))}일 ≠ "
            f"기록 {_as_int(exempted.get('recorded_window_days'))}일) — 면제의 기한을 재는 자와 승인된 창이 다르다"
        )
    if _as_int(coverage.get("min_floors")) > _as_int(counts.get("canvas")):
        problems.append(
            f"원장이 본 하한({_as_int(counts.get('canvas'))}개)이 자기 하한({_as_int(coverage.get('min_floors'))}개) 아래다"
        )
    if problems:
        return CheckResult(name="floor_ledger", passed=False, detail=" / ".join(problems), observed=len(layers))
    return CheckResult(
        name="floor_ledger",
        passed=True,
        detail=(
            f"층 {len(layers)}개 · 하한 {summed}개가 한 표에 있고, 각 층의 승인(누가 언제)이 실려 있다 — "
            f"하한 기록 {record.get('recorded_on')} 승인({record.get('floors')}개 · 판단 이동 내려감 {record.get('lowered')} · "
            f"층 이동 {len(_as_list(record.get('vanished_layers'))) + len(_as_list(record.get('added_layers')))}"
            f"(이름 변경 후보 {len(_as_list(record.get('renamed_layers')))}) · "
            f"관측 이동 {len(_as_list(record.get('moves')))}보고) · "
            f"표 밖 배선 {len(wiring)}개(어느 층의 하한인지 이어진 이름 — 승격을 잇는 자리다) · "
            f"면제 기록 {_as_int(exempted.get('recorded'))}개(선언 {_as_int(exempted.get('declared'))}개 · "
            f"창 {_as_int(exempted.get('recorded_window_days'))}일) · 면제의 판단 이동 0(검토 없이 미룸 "
            f"{len(_as_list(exempted.get('bare_deferred')))} · 기한 미룸 {len(_as_list(exempted.get('deferred')))} · "
            f"이름만 바뀐 듯한 면제 {len(_as_list(exempted.get('renamed')))} · 기한 당김 "
            f"{len(_as_list(exempted.get('pulled')))}보고 · 확인일 갱신 {len(_as_list(exempted.get('reviewed')))}보고 · "
            f"기록된 기한 이동 {len(_as_list(exempted.get('deadline_moves')))} · 기록된 승격 "
            f"{len(_as_list(exempted.get('promoted')))}) — 재검토는 `--review` 가 기한 순서로, 승격은 `--promote` 가 남은 일을 낸다"
        ),
        observed=summed,
    )


def ledger_measured(report: dict[str, object] | None) -> dict[str, int]:
    """원장에서 마커로 고정할 값 — 표가 사라지거나 하한이 줄면 문서가 먼저 멈춘다.

    스캔 규모(후보·선언·배선)도 여기서 고정한다: 후보가 줄면(임계값이 사라지거나 스캔이 눈머는 순간) 문서가 먼저 멈춰
    사람이 “사라진 하한이 정상적인 리팩터링인가” 를 묻게 된다 — 그 전에는 조용히 지나가는 자리였다(배선 수가 줄면
    표가 하한으로 아는 이름이 어느 층의 하한인지 잇지 못하게 된 것이고, 그러면 승격 감지가 다시 눈먼다).
    """

    if report is None:
        return {}
    counts = _as_dict(report.get("counts"))
    return {
        "ledger_layers": _as_int(counts.get("layers")),
        "ledger_floors": _as_int(counts.get("floors")),
        "ledger_candidates": _as_int(counts.get("outside_scanned")),
        "ledger_declared": _as_int(counts.get("outside_declared")),
        "ledger_wired": _as_int(counts.get("wired_layers")),
        "ledger_recorded_floors": _as_int(counts.get("recorded_floors")),
    }


def measure_red_rehearsal() -> dict[str, object] | None:
    """red 리허설을 돌려 JSON 을 받는다 — 카나리아와 **같은 이음매 규칙**을 쓴다.

    종료 코드가 0 이 아니어도 JSON 이 읽히면 그대로 쓰고(심은 위반을 못 본 층의 이름을 잃지 않는다), 종료 코드를
    보고에 실어 검사가 모순을 잡게 한다. 돌리지 못했을 때만 None 이다.
    """

    if not REHEARSAL_SCRIPT.exists():
        return None
    result = subprocess.run(
        [sys.executable, str(REHEARSAL_SCRIPT), "--emit-json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(report, dict):
        return None
    report["exit_code"] = result.returncode
    return report


def check_red_rehearsal(report: dict[str, object] | None) -> CheckResult:
    """“위반 0건” 이 **’다 봤는데 깨끗하다’** 인지 **’한 번도 red 를 낸 적이 없다’** 인지 — 심어서 확인했는가.

    자기시험은 판독 규칙을, 하한은 “볼 수 있는가” 를 지킨다. 리허설은 그 둘이 만나도 남는 것을 본다: 심은 위반을
    보고 **exit 1 을 내는가**(`seen`·`dirty_exit`·`named`·`spoken`) · **경계 사례를 위반으로 보지 않는가**(`flagged` —
    넓게 잡은 탐지는 탐지력이 아니라 오탐이고, 그러면 사람이 그 감사를 끄게 된다) · 같은 자리에 허용 형태를 넣으면
    **초록인가**(`clean_exit` — 이게 없으면 “새 파일이 생겨서 빨간” 과 구분할 수 없다) · **아무것도 없는 트리를
    통과시키지 않는가**(`blind_exit`). 종료 코드 없는 보고·모순·합계 불일치는 카나리아와 같은 규칙으로 실패다.
    """

    if report is None:
        return CheckResult(
            name="red_rehearsal",
            passed=False,
            detail=(
                f"{_display(REHEARSAL_SCRIPT)} 를 돌리지 못했다 — ‘위반 0건’ 이 관찰이 아니라 미관찰인 실행은 "
                "통과시키지 않는다"
            ),
        )
    layers = [item for item in _as_list(report.get("layers")) if isinstance(item, dict)]
    counts = _as_dict(report.get("counts"))
    floors = [record for record in _as_list(report.get("floors")) if isinstance(record, dict)]
    declared = _as_dict(report.get("declared"))
    unseen = [str(item.get("layer")) for item in layers if _as_int(item.get("seen")) < 1]
    quiet = [str(item.get("layer")) for item in layers if _as_int(item.get("dirty_exit")) != 1]
    unnamed = [
        str(item.get("layer"))
        for item in layers
        if _as_int(item.get("seen")) >= 1 and not (item.get("named") and item.get("spoken"))
    ]
    crashed = [str(item.get("layer")) for item in layers if item.get("crashed")]
    control_red = [str(item.get("layer")) for item in layers if item.get("clean_exit") not in (None, 0)]
    control_missing = [str(item.get("layer")) for item in layers if item.get("clean_exit") is None]
    blind_pass = [str(item.get("layer")) for item in layers if _as_int(item.get("blind_exit")) == 0]
    overbroad = [
        f"{item.get('layer')}({', '.join(str(name) for name in _as_list(item.get('flagged')))})"
        for item in layers
        if _as_list(item.get("flagged"))
    ]
    unguarded = [str(item.get("layer")) for item in layers if _as_int(item.get("boundaries")) < 1]
    seen_ok = sum(1 for item in layers if item.get("ok"))
    problems: list[str] = []
    if "exit_code" not in report:
        problems.append("리허설 종료 코드 없이 온 보고다 — 스스로 실패했는지 알 수 없는 보고는 판정이 아니다")
    elif _as_int(report.get("exit_code")) != 0 and not any(
        (unseen, quiet, unnamed, crashed, control_red, control_missing, blind_pass, overbroad, unguarded)
    ):
        problems.append(
            f"리허설이 exit {_as_int(report.get('exit_code'))} 로 스스로 실패했다고 말했는데 보고는 전부 통과라고 한다(모순)"
        )
    if not layers:
        problems.append("리허설이 층을 하나도 심지 않았다")
    if not declared:
        problems.append("리허설되지 않는 층의 이유(`declared`)가 비어 있다 — 이유 없는 생략은 생략이 아니다")
    problems.extend(probe_problems(_probe_from(_as_dict(report.get("probe"))), name="red_rehearsal"))
    if not floors:
        problems.append("리허설이 하한을 기록하지 않았다")
    for record in floors:
        if not str(record.get("why", "")).strip():
            problems.append(f"리허설 하한 {record.get('label')} 에 근거(`why`)가 없다")
    if quiet:
        problems.append(f"심은 위반을 보고도 red 를 내지 못한 층: {', '.join(quiet)}")
    if unseen:
        problems.append(f"심은 위반을 한 건도 보지 못한 층: {', '.join(unseen)}")
    if unnamed:
        problems.append(f"위반을 봤지만 심은 파일을 지목하지 않은 층: {', '.join(unnamed)}")
    if control_missing:
        problems.append(f"대조군(허용 형태)을 돌리지 않은 층: {', '.join(control_missing)}")
    if control_red:
        problems.append(
            f"허용 형태를 위반으로 본 층(오탐 — 그 리허설은 심은 위반을 증명하지 못한다): {', '.join(control_red)}"
        )
    if blind_pass:
        problems.append(f"아무것도 없는 트리를 통과시킨 층: {', '.join(blind_pass)}")
    if unguarded:
        problems.append(
            f"경계 사례가 하나도 없는 층(오탐을 볼 수 없다 — 경계를 넓게 잡아도 그 사실이 안 보인다): {', '.join(unguarded)}"
        )
    if overbroad:
        problems.append(f"경계 사례를 위반으로 본 층(오탐 — 넓게 잡은 탐지는 탐지력이 아니다): {', '.join(overbroad)}")
    if crashed:
        problems.append(f"사고로 죽은 층: {', '.join(crashed)}")
    if counts and _as_int(counts.get("ok")) != seen_ok:
        problems.append(
            f"합계가 항목과 다르다(ok {_as_int(counts.get('ok'))} ≠ 항목 {seen_ok}) — 보고를 그대로 믿을 수 없다"
        )
    if problems:
        return CheckResult(
            name="red_rehearsal",
            passed=False,
            detail="; ".join(problems),
            observed=len(layers),
        )
    return CheckResult(
        name="red_rehearsal",
        passed=True,
        detail=(
            f"층 {len(layers)}개에 **진짜 파일로 위반을 심어** red 를 재현했다 — 심은 트리 exit 1·지목, "
            f"경계 사례 {_as_int(counts.get('boundaries'))}개 오탐 0, 대조군(허용 형태) 초록, "
            f"빈 트리 차단(ok {_as_int(counts.get('ok'))})"
        ),
        observed=len(layers),
    )


def rehearsal_measured(report: dict[str, object]) -> dict[str, int]:
    """리허설에서 마커로 고정할 값."""

    counts = _as_dict(report.get("counts"))
    return {
        "rehearsal_layers": _as_int(counts.get("layers")),
        "rehearsal_ok": _as_int(counts.get("ok")),
    }


def load_evidence_gate() -> ModuleType | None:
    """증거 게이트 module 을 읽는다 — 없거나 불러오지 못하면 None(호출자가 실패로 처리).

    **게이트를 실행하지 않는다.** 게이트의 stage 중 하나가 이 리뷰이므로, 실행하면 서로를 불러 끝나지 않는다;
    리뷰가 볼 것은 게이트의 판정이 아니라 **게이트의 명세**(roster·자기시험·하한)다.
    """

    if not EVIDENCE_GATE_SCRIPT.exists():
        return None
    spec = importlib.util.spec_from_file_location("review_evidence_gate", EVIDENCE_GATE_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - 불러오지 못한 게이트는 통과가 아니라 실패다(이유는 검사가 말한다)
        return None
    return module


def measure_evidence_gate(module: ModuleType | None) -> dict[str, object] | None:
    """게이트의 명세를 읽어 온다 — stage roster · tier · 자기시험 · 하한(측정은 하지 않는다)."""

    if module is None:
        return None
    stages = tuple(module.STAGES)
    probe = module._probe_or_failure()  # noqa: SLF001 - 자기시험이 예외로 죽어도 판정으로 바꾸는 자리
    return {
        "stages": [
            {"name": stage.name, "tier": stage.tier, "script": stage.script, "args": list(stage.args)}
            for stage in stages
        ],
        "names": [stage.name for stage in stages],
        "tiers": list(module.TIERS),
        "fast": [stage.name for stage in module.stages_for(module.TIER_FAST)],
        "probe": probe.as_mapping(),
        "floors": module.floor_records(module.coverage_floors(stages)),
        "baseline": _baseline_state(module.BASELINE),
    }


def _baseline_state(path: Path) -> dict[str, object]:
    """기준 파일의 상태 — **있는데 못 읽는 것**과 “아직 없는 것” 을 구분해 돌려준다."""

    state: dict[str, object] = {
        "path": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
        "exists": path.exists(),
        "layers": 0,
        "recorded_on": "",
        "method": "",
        "readable": False,
    }
    if not path.exists():
        return state
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return state
    if not isinstance(payload, dict):
        return state
    layers = payload.get("layers")
    state["readable"] = isinstance(layers, dict) and bool(layers)
    state["layers"] = len(layers) if isinstance(layers, dict) else 0
    state["recorded_on"] = str(payload.get("recorded_on", ""))
    state["method"] = str(payload.get("method", ""))
    return state


def check_evidence_gate(report: dict[str, object] | None) -> CheckResult:
    """여섯 층이 **한 번에 도는 명령으로 묶여 있는가**(`scripts/evidence_gate.py`).

    harness 가 각자 게이트를 갖는 것과 그것을 도는 자리는 다르다. 여기서 보는 것은 게이트의 명세다:

      * 게이트가 불려오고, **stage 가 하나도 없지 않고**, 요구된 이름이 전부 들어 있는가.
      * 각 stage 의 스크립트가 실재하고, tier 가 아는 값이며, `fast` 가 비어 있지 않은가.
      * 게이트의 **자기시험이 있고 통과하는가**(합성 결과로 판정 규칙 — 종류 구분·tier 필터·roster 정합·수치 추출 — 을
        매 실행 다시 물어본다). 자기시험이 없거나 실패하면 절반의 명단은 명단이 아니다.
      * 하한이 기록돼 있고 **근거(`why`)가 적혀 있는가**.
      * **기준 파일이 있는가** — 게이트의 추이는 “어제보다 얇아졌는가” 를 말하는데, 기준이 없으면 그 질문은
        매번 “기준 없음” 으로 끝난다. 기준은 `--record-baseline --method` 로만 갱슰되고(무엇을 보고 승인했는지
        없이는 기준이 아니다) 사람이 커밋하는 자리다.
    """

    if report is None:
        return CheckResult(
            name="evidence_gate",
            passed=False,
            detail=(
                f"{EVIDENCE_GATE_SCRIPT.name} 가 없거나 불려오지 않는다 — 층마다 있는 게이트를 도는 명령이 없다면 "
                "그 게이트는 사람의 기억으로만 돌아간다"
            ),
        )
    stages = _as_list(report.get("stages"))
    names = [str(name) for name in _as_list(report.get("names"))]
    probe = _as_dict(report.get("probe"))
    floors = [record for record in _as_list(report.get("floors")) if isinstance(record, dict)]
    problems: list[str] = []
    if not stages:
        problems.append("stage 가 하나도 없다")
    missing_scripts = [
        str(entry.get("script"))
        for entry in stages
        if isinstance(entry, dict) and not (REPO_ROOT / "scripts" / str(entry.get("script"))).exists()
    ]
    if missing_scripts:
        problems.append(f"stage 의 스크립트가 없다: {missing_scripts}")
    unknown_tiers = [
        str(entry.get("tier"))
        for entry in stages
        if isinstance(entry, dict) and entry.get("tier") not in _as_list(report.get("tiers"))
    ]
    if unknown_tiers:
        problems.append(f"모르는 tier 를 쓰는 stage: {sorted(set(unknown_tiers))}")
    fast = [str(name) for name in _as_list(report.get("fast"))]
    if not fast:
        problems.append("fast tier 가 비어 있다 — 기본 실행이 아무 층도 돌지 않는다")
    if not names:
        problems.append("stage 이름이 비어 있다")
    problems.extend(probe_problems(_probe_from(probe), name="evidence_gate"))
    if not floors:
        problems.append("하한이 기록돼 있지 않다")
    for record in floors:
        if not str(record.get("why", "")).strip():
            problems.append(f"하한 {record.get('label')} 에 근거(`why`)가 없다")
    baseline = _as_dict(report.get("baseline"))
    if not baseline.get("exists"):
        problems.append(
            "비교할 기준 파일이 없다 — 기준 없는 게이트는 '어제보다 얇아졌는가' 를 매번 모른다고만 말한다"
            " (`--record-baseline --method` 로 기록하고 커밋한다)"
        )
    elif not baseline.get("readable"):
        problems.append(f"기준 파일을 읽지 못한다: {baseline.get('path')} — 깨진 기준을 '기준 없음' 으로 삼키지 않는다")
    else:
        if not str(baseline.get("method", "")).strip():
            problems.append("기준 파일에 `method` 가 없다 — 무엇을 보고 승인했는지 남기지 않은 기준은 근거가 아니다")
        if not str(baseline.get("recorded_on", "")).strip():
            problems.append("기준 파일에 `recorded_on` 이 없다 — 언제 승인한 상태인지 알 수 없다")
    if problems:
        return CheckResult(
            name="evidence_gate",
            passed=False,
            detail="; ".join(problems),
            observed={"stages": len(stages), "fast": len(fast)},
        )
    return CheckResult(
        name="evidence_gate",
        passed=True,
        detail=(
            f"stage {len(stages)}개(전부 스크립트 실재·하한 근거 기록)를 한 번에 도는 명령이 있다 — "
            f"fast {len(fast)}개 · 자기시험 {_as_int(probe.get('cases'))}건 통과 · "
            f"기준 {baseline.get('layers')}개 층({baseline.get('recorded_on')} 승인)"
        ),
        observed={"stages": len(stages), "fast": len(fast)},
    )


def exit_code_problems(report: dict[str, object], *, name: str, already: list[str]) -> list[str]:
    """machine-readable 실행의 종료 코드를 판정으로 읽는다 — **모순과 부재를 모두 실패로** 본다.

    JSON 을 내는 경로는 이제 판정(종료 코드)과 진단(JSON)을 함께 낸다(그 전에는 `--emit-json` 이 결과와
    무관하게 exit 0 을 냈다). 그 출력을 읽는 쪽이 지켜야 할 두 가지:

      * **종료 코드가 없는 보고는 판정이 아니다** — 스스로 실패했는지 알 수 없으면 통과로 쓰지 않는다.
      * **모순** — 보고서는 문제가 없다는데 실행이 스스로 실패했다고 말하면 둘 중 하나는 거짓이다.
        (`already` 가 비어 있지 않으면 모순이 아니라 같은 결함의 두 얼굴이므로 중복해서 세지 않는다.)
    """

    if "exit_code" not in report:
        return [f"{name} 보고에 종료 코드가 없다 — 스스로 실패했는지 알 수 없는 보고는 판정이 아니다"]
    code = _as_int(report.get("exit_code"))
    if code != 0 and not already:
        return [f"{name} 가 exit {code} 로 스스로 실패했다고 말했는데 보고서는 문제가 없다고 한다(모순)"]
    return []


def _probe_from(mapping: dict[str, object]) -> Probe | None:
    """JSON 으로 온 자기시험 결과를 `Probe` 로 되살린다(없으면 None → 부재로 실패)."""

    cases = mapping.get("cases")
    failures = _as_list(mapping.get("failures"))
    if not isinstance(cases, int):
        return None
    return Probe(cases=cases, failures=tuple(str(failure) for failure in failures))


def evidence_gate_measured(report: dict[str, object] | None) -> dict[str, int]:
    """게이트에서 마커로 고정할 값 — stage roster 수(명단이 줄면 문서 마커가 어긋난다)."""

    if report is None:
        return {}
    return {"evidence_gate_stages": len(_as_list(report.get("stages")))}


def read_state_claims_artifact() -> dict[str, object] | None:
    """감사가 남긴 artifact — 하한과 그 근거를 담은 기록. 없거나 깨졌으면 None(호출자가 실패로 처리)."""

    if not STATE_CLAIMS_ARTIFACT.exists():
        return None
    try:
        return json.loads(STATE_CLAIMS_ARTIFACT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def measure_state_claims() -> dict[str, object] | None:
    """상태 주장 감사를 돌려 JSON 을 받는다 — 몇 초 걸린다(시험을 실제로 돌린다).

    `measure_digest_drift`·`measure_canary` 와 같은 규칙: 종료 코드가 0 이 아니어도 **JSON 이 읽히면 그대로
    쓰고** 종료 코드를 보고에 실어 모순을 검사가 잡게 한다(진단을 이음매에서 뭉개지 않는다).
    """

    result = subprocess.run(
        [sys.executable, str(STATE_CLAIMS_SCRIPT), "--emit-json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(report, dict):
        return None
    report["exit_code"] = result.returncode
    return report


def check_state_claims(stored: dict[str, object] | None, report: dict[str, object] | None) -> CheckResult:
    """증거 문서의 **현재 상태 주장**이 방금 돌린 시험과 일치하는가 + 하한의 근거가 기록돼 있는가.

    스냅샷(시점 기록)은 낡아도 역사지만, “이 시험은 실패한다” 는 지금 트리에 대한 주장이라 낡으면 틀린 문장이다.
    낡은 주장은 정정 표기를 붙여 해결한다(지우지 않는다).

    감사자의 **탐지력 하한**도 함께 본다 — 하한이 없거나, 기록된 artifact 가 방금 잰 값과 다르거나, 하한의
    근거(`why`)가 비어 있으면 실패다. 값만 남고 근거가 사라지면 나중에 누구도 그 값을 내려도 되는지 판단할 수 없다.
    """

    if report is None:
        return CheckResult(
            name="state_claims",
            passed=False,
            detail=f"{_display(STATE_CLAIMS_SCRIPT)} 를 돌리지 못했다 — 상태 주장을 판정할 수 없다",
        )
    if stored is None:
        return CheckResult(
            name="state_claims",
            passed=False,
            detail=(
                f"{_display(STATE_CLAIMS_ARTIFACT)} 가 없거나 읽히지 않는다 — "
                "감사자가 하한 근거를 기록하지 않은 실행은 증거로 옮기지 않는다"
            ),
        )
    recorded_keys = ("counts", "coverage", "floors", "claims")
    outdated = [key for key in recorded_keys if stored.get(key) != report.get(key)]
    floors = [item for item in _as_list(report.get("floors")) if isinstance(item, dict)]
    counts = _as_dict(report.get("counts"))
    coverage = _as_dict(report.get("coverage"))
    probe = _as_dict(report.get("probe"))
    stale = _as_int(counts.get("stale"))
    unknown = _as_int(counts.get("unknown"))
    mentions = _as_int(coverage.get("mentions"))
    problems: list[str] = []
    if outdated:
        problems.append(
            f"하한 근거 artifact 가 최신이 아니다({', '.join(outdated)} 불일치) — "
            "scripts/audit_state_claims.py 를 다시 돌려 근거와 관측을 함께 갱신해야 한다"
        )
    if not floors:
        problems.append("탐지력 하한이 artifact 에 없다 — 하한 없는 감사는 ‘주장 0건’ 으로 조용히 통과할 수 있다")
    without_reason = [str(item.get("label")) for item in floors if not str(item.get("why", "")).strip()]
    if without_reason:
        problems.append(
            f"근거(`why`) 없는 하한: {', '.join(without_reason)} — 값만 남기면 나중에 내려도 되는지 판단할 수 없다"
        )
    if probe and not probe.get("ok"):
        problems.append(f"감사 자기시험이 실패했다(판독 규칙이 깨졌다): {probe.get('failures')}")
    if not probe:
        problems.append("자기시험 결과가 없다 — 감사가 자기 판독력을 확인하지 않았다")
    # 하한 판정은 **감사가 기록한 근거**를 그대로 써서 낸다 — 값만 옮겨 적으면 근거가 메시지에서 사라진다.
    for item in floors:
        problems.extend(
            floor_problems(
                [
                    Floor(
                        str(item.get("label")),
                        _as_int(item.get("observed")),
                        _as_int(item.get("minimum")),
                        why=str(item.get("why", "")),
                    )
                ]
            )
        )
    if stale:
        offenders = [
            f"{item.get('doc')}:{item.get('line')}"
            for item in _as_list(report.get("claims"))
            if isinstance(item, dict) and item.get("status") == "stale"
        ]
        problems.append(f"지금 트리와 어긋나는 상태 주장 {stale}건(정정 표기 없음): {', '.join(offenders)}")
    if unknown:
        problems.append(f"상태를 판정하지 못한 주장 {unknown}건")
    problems.extend(exit_code_problems(report, name="audit_state_claims", already=problems))
    if problems:
        return CheckResult(
            name="state_claims",
            passed=False,
            detail=" / ".join(problems),
            observed=stale,
        )
    return CheckResult(
        name="state_claims",
        passed=True,
        detail=(
            f"상태 주장 {_as_int(counts.get('claims'))}건 — 그대로 {_as_int(counts.get('ok'))} · "
            f"정정 붙임 {_as_int(counts.get('fixed'))} · 낡음 {stale} · "
            f"자기시험 {_as_int(probe.get('cases'))}건 통과(증거 문서 {_as_int(coverage.get('docs'))}개 "
            f"· node 지목 산문 {mentions}줄) · "
            + " · ".join(
                f"하한 {item.get('label')} {item.get('observed')}≥{item.get('minimum')}(여유 {item.get('margin')})"
                for item in floors
            )
        ),
        observed=_as_int(counts.get("fixed")),
    )


def state_claim_measured(report: dict[str, object]) -> dict[str, int]:
    """상태 주장 감사에서 마커로 고정할 값."""

    counts = _as_dict(report.get("counts"))
    coverage = _as_dict(report.get("coverage"))
    probe = _as_dict(report.get("probe"))
    return {
        "state_claims": _as_int(counts.get("claims")),
        "state_claims_fixed": _as_int(counts.get("fixed")),
        "state_claims_stale": _as_int(counts.get("stale")),
        "state_claim_mentions": _as_int(coverage.get("mentions")),
        "state_claim_probe_cases": _as_int(probe.get("cases")),
    }


def check_review_document(principles: tuple[Principle, ...]) -> CheckResult:
    """리뷰 문서가 24원칙·§63·§52를 다루고 매핑 artifact 경로를 담고 있는지 확인한다."""

    if not REVIEW_DOC.exists():
        return CheckResult(
            name="review_document",
            passed=False,
            detail=f"{REVIEW_DOC} 가 없다 — 최종 리뷰 문서를 작성해야 한다",
        )
    text = REVIEW_DOC.read_text(encoding="utf-8")
    missing: list[str] = []
    for principle in principles:
        if f"**P{principle.number}**" not in text:
            missing.append(f"P{principle.number}")
    for question in _SOURCE_QUESTIONS:
        if f"**Q-{question.key}**" not in text:
            missing.append(f"Q-{question.key}")
    for drift in _DRIFT_QUESTIONS:
        if f"**D-{drift.key}**" not in text:
            missing.append(f"D-{drift.key}")
    for principle in principles:
        for relative in (*principle.evidence, *principle.tests, *principle.modules):
            if relative not in text:
                missing.append(f"P{principle.number}:{relative}")
    if missing:
        return CheckResult(
            name="review_document",
            passed=False,
            detail=f"리뷰 문서에 없는 항목/artifact: {', '.join(sorted(set(missing)))}",
            observed=len(missing),
        )
    return CheckResult(
        name="review_document",
        passed=True,
        detail="리뷰 문서가 24원칙·§63·§52와 매핑 artifact를 모두 담는다",
    )


def check_measured_markers(measured: dict[str, int]) -> CheckResult:
    """리뷰 문서의 measured 마커가 실제 값과 일치하는지 확인한다."""

    if not REVIEW_DOC.exists():
        return CheckResult(name="measured_markers", passed=False, detail=f"{REVIEW_DOC} 가 없다")
    text = REVIEW_DOC.read_text(encoding="utf-8")
    declared = {key: int(value) for key, value in _MARKER_PATTERN.findall(text)}
    problems: list[str] = []
    for key, value in sorted(measured.items()):
        if key not in declared:
            problems.append(f"{key} 마커가 없다(기대 {value})")
        elif declared[key] != value:
            problems.append(f"{key} 마커 {declared[key]} ≠ 실제 {value}")
    for key in sorted(declared):
        if key not in measured:
            problems.append(f"{key} 마커는 검사되지 않은 값이다")
    if problems:
        return CheckResult(
            name="measured_markers",
            passed=False,
            detail="; ".join(problems),
            observed=dict(sorted(declared.items())),
        )
    return CheckResult(
        name="measured_markers",
        passed=True,
        detail=f"{len(measured)}개 measured 마커가 실제 측정값과 일치한다",
        observed=dict(sorted(measured.items())),
    )


def _as_list(value: object) -> list[object]:
    """JSON 값이 list 일 때만 돌려준다(아니면 빈 목록)."""

    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, object]:
    """JSON 값이 dict 일 때만 돌려준다(아니면 빈 mapping)."""

    return value if isinstance(value, dict) else {}


def read_regression_ledger() -> dict[str, object] | None:
    """전량 회귀 원장 JSON 을 읽는다(없거나 깨졌으면 None)."""

    if not REGRESSION_LEDGER.is_file():
        return None
    try:
        payload = json.loads(REGRESSION_LEDGER.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def check_regression_ledger(ledger: dict[str, object] | None) -> CheckResult:
    """회귀 원장이 **scope 별로 두 회차**를 갖고, 결정적 실패에 모두 소유자가 붙었는지 본다.

    한 회차뿐인 scope 는 "결정적"과 "seed 민감"을 구분할 수 없으므로 그 자체가 실패다.
    """

    if ledger is None:
        return CheckResult(
            name="regression_ledger",
            passed=False,
            detail=f"{_display(REGRESSION_LEDGER)} 가 없거나 읽히지 않는다 — scripts/regression_ledger.py",
        )

    entries = _as_list(ledger.get("runs"))
    scopes = _as_dict(ledger.get("scopes"))
    incomplete = _as_list(ledger.get("incomplete_scopes"))
    deterministic = _as_list(ledger.get("deterministic"))
    owners = _as_dict(ledger.get("owners"))
    unowned = _as_list(ledger.get("unowned"))
    drift = _as_list(ledger.get("drift"))

    problems: list[str] = harness_problems(ledger, name="regression_ledger", floors=(("회차", 1), ("scope", 1)))
    if not scopes:
        problems.append("scope 가 없다 — 무엇을 재는지 이름이 없는 원장은 인용할 수 없다")
    if incomplete:
        problems.append("두 회차(서로 다른 seed)가 없는 scope: " + ", ".join(str(scope) for scope in incomplete))
    if unowned:
        problems.append(f"소유자 없는 결정적 실패 {len(unowned)}건: {', '.join(str(node) for node in unowned)}")
    if {str(node) for node in deterministic} != set(owners):
        missing = sorted({str(node) for node in deterministic} - set(owners))
        problems.append(f"결정적 실패 중 오너가 안 붙은 항목: {missing}")

    if problems:
        return CheckResult(
            name="regression_ledger",
            passed=False,
            detail=" / ".join(problems),
            observed=len(entries),
        )
    return CheckResult(
        name="regression_ledger",
        passed=True,
        detail=(
            f"scope {len(scopes)}개 · 회차 {len(entries)}개 · 결정적 실패 {len(deterministic)}건 전부 "
            f"소유자 있음 · variant 민감 {len(drift)}건"
        ),
        observed=len(deterministic),
    )


def regression_measured(ledger: dict[str, object]) -> dict[str, int]:
    """원장에서 리뷰 마커로 고정할 값(scope·회차·결정적·variant 민감·무소유)."""

    return {
        "regression_scopes": len(_as_dict(ledger.get("scopes"))),
        "regression_runs": len(_as_list(ledger.get("runs"))),
        "regression_deterministic": len(_as_list(ledger.get("deterministic"))),
        "regression_drift": len(_as_list(ledger.get("drift"))),
        "regression_unowned": len(_as_list(ledger.get("unowned"))),
    }


def check_constitution_source() -> CheckResult:
    """헌법 24원칙·§63·§52가 원문에 그대로 있는지(개수 기준) 확인한다."""

    constitution = CONSTITUTION.read_text(encoding="utf-8")
    principles = len(re.findall(r"^## Constitutional Principle \d+ —", constitution, re.MULTILINE))
    master = (DOCS_ROOT / "MASTER_PROMPT_V2_SOURCE.md").read_text(encoding="utf-8")
    question_block = master.split("# 63. 최종 Architecture Review 질문")[1].split("# 64.")[0]
    source_questions = len(re.findall(r"^### [\w ]+$", question_block, re.MULTILINE))
    policy = (DOCS_ROOT / "SELF_IMPROVEMENT_POLICY.md").read_text(encoding="utf-8")
    drift_block = policy.split("# 52. Constitution Drift Detection")[1].split("# 56.")[0]
    drift_questions = len(re.findall(r"^\w[^\n]*\?$", drift_block, re.MULTILINE))
    problems: list[str] = []
    if principles != len(_PRINCIPLES):
        problems.append(f"헌법 원칙 {principles}개 ≠ 매핑 {len(_PRINCIPLES)}개")
    if source_questions != len(_SOURCE_QUESTIONS):
        problems.append(f"§63 질문 {source_questions}개 ≠ 매핑 {len(_SOURCE_QUESTIONS)}개")
    if drift_questions != len(_DRIFT_QUESTIONS):
        problems.append(f"§52 drift 질문 {drift_questions}개 ≠ 매핑 {len(_DRIFT_QUESTIONS)}개")
    if problems:
        return CheckResult(name="source_alignment", passed=False, detail="; ".join(problems))
    return CheckResult(
        name="source_alignment",
        passed=True,
        detail=f"헌법 {principles}원칙 · §63 {source_questions}질문 · §52 {drift_questions}질문과 매핑이 일치",
        observed=principles,
    )


def measure() -> ReviewMeasurement:
    """매핑 검사와 문서 정합성 검사를 실행한다."""

    principles = _PRINCIPLES
    statuses = [p.status for p in principles]
    measured: dict[str, int] = {
        "principles": len(principles),
        "principles_covered": sum(1 for s in statuses if s == "covered"),
        "principles_partial": sum(1 for s in statuses if s == "partial"),
        "principles_gap": sum(1 for s in statuses if s == "gap"),
        "source_questions": len(_SOURCE_QUESTIONS),
        "drift_questions": len(_DRIFT_QUESTIONS),
        "drift_triggered": sum(1 for d in _DRIFT_QUESTIONS if d.triggered),
        "evidence_docs": len(list(EVIDENCE_DIR.glob("*.md"))),
    }
    checks: list[CheckResult] = [
        check_constitution_source(),
        check_artifacts(principles),
        check_doc_links(),
        check_checklist_coverage(principles),
        check_evidence_referenced(principles),
        check_citation_tracking(),
    ]
    cognitive = collect_test_count(REPO_ROOT / "tests" / "cognitive")
    if cognitive is None:
        checks.append(
            CheckResult(
                name="test_collection",
                passed=False,
                detail="tests/cognitive 수집 개수를 얻지 못했다",
            )
        )
    else:
        measured["cognitive_tests"] = cognitive
        checks.append(
            CheckResult(
                name="test_collection",
                passed=True,
                detail=f"tests/cognitive 수집 {cognitive}건",
                observed=cognitive,
            )
        )
    ledger = read_regression_ledger()
    checks.append(check_regression_ledger(ledger))
    if ledger is not None:
        measured.update(regression_measured(ledger))
    drift = measure_digest_drift()
    checks.append(check_digest_report(read_digest_drift(), drift))
    if drift is not None:
        measured.update(digest_measured(drift))
    state_claims = measure_state_claims()
    checks.append(check_state_claims(read_state_claims_artifact(), state_claims))
    if state_claims is not None:
        measured.update(state_claim_measured(state_claims))
    canary = measure_canary()
    checks.append(check_harness_canary(canary))
    if canary is not None:
        measured.update(canary_measured(canary))
    ledger_report = measure_floor_ledger()
    checks.append(check_floor_ledger(ledger_report))
    measured.update(ledger_measured(ledger_report))
    rehearsal = measure_red_rehearsal()
    checks.append(check_red_rehearsal(rehearsal))
    if rehearsal is not None:
        measured.update(rehearsal_measured(rehearsal))
    evidence_gate = measure_evidence_gate(load_evidence_gate())
    checks.append(check_evidence_gate(evidence_gate))
    measured.update(evidence_gate_measured(evidence_gate))
    checks.append(check_review_document(principles))
    checks.append(check_measured_markers(measured))
    return ReviewMeasurement(
        principles=principles,
        source_questions=_SOURCE_QUESTIONS,
        drift_questions=_DRIFT_QUESTIONS,
        checks=tuple(checks),
        measured=measured,
    )


def failure_lines(measurement: ReviewMeasurement) -> list[str]:
    """실패한 검사를 **이름과 이유로** 남기는 문장 — `--quiet` 도 이 문장은 숨기지 않는다.

    여섯 층을 한 번에 도는 게이트(`scripts/evidence_gate.py`)가 이 스크립트의 출력에서 실패 이유를 읽는다.
    조용한 실행이 `exit 1` 만 남기면, 어느 층이 얖은지 알아내려고 그 층을 다시 돌려야 한다.
    """

    return [f"[FAIL] {check.name}: {check.detail}" for check in measurement.checks if not check.passed]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="architecture_review",
        description="T14 final architecture review — constitution/§63/§52 mapping vs evidence",
    )
    parser.add_argument("--output", type=Path, default=None, help="결과 JSON artifact 경로")
    parser.add_argument("--quiet", action="store_true", help="표를 출력하지 않는다")
    args = parser.parse_args(argv)

    measurement = measure()
    if not args.quiet:
        header = f"{'check':22s} {'result':6s} detail"
        print(header)
        print("-" * len(header))
        for check in measurement.checks:
            print(f"{check.name:22s} {'PASS' if check.passed else 'FAIL':6s} {check.detail}")
        print()
        print(
            f"원칙 {measurement.measured['principles']}개: covered {measurement.measured['principles_covered']}"
            f" · partial {measurement.measured['principles_partial']}"
            f" · gap {measurement.measured['principles_gap']}"
        )
        print(
            f"§63 질문 {measurement.measured['source_questions']}개 · "
            f"§52 drift 질문 {measurement.measured['drift_questions']}개(triggered {measurement.measured['drift_triggered']})"
        )
        print(f"verdict passed={measurement.passed}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(measurement.as_mapping(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.output}")
    for line in failure_lines(measurement):
        print(line, file=sys.stderr)
    return EXIT_OK if measurement.passed else EXIT_FAILED


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
