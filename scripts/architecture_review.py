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
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

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

    problems: list[str] = []
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
    checks.append(check_review_document(principles))
    checks.append(check_measured_markers(measured))
    return ReviewMeasurement(
        principles=principles,
        source_questions=_SOURCE_QUESTIONS,
        drift_questions=_DRIFT_QUESTIONS,
        checks=tuple(checks),
        measured=measured,
    )


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
    return EXIT_OK if measurement.passed else EXIT_FAILED


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
