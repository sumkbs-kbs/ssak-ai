#!/usr/bin/env python
"""측정 harness 공통 계약 — **harness 자신이 눈이 멀지 않았는지** 확인하는 두 장치.

측정 harness 의 실패는 두 종류다. 하나는 **빨간 것을 못 보는 것**(위반 0건으로 통과), 다른 하나는
**아무것도 못 보는 것**(스캔 대상 0개 · pin 0개 · 회차 0개인데 “위반 없음”이라 보고)이다. 뒤엣것이 더 위험하다 —
초록으로 보이지만 그 초록은 증거가 아니다. 이 module 은 그 둘을 기계로 구분한다.

  * ``Probe``/``Cases`` — **자기시험.** 매 실행마다 harness 의 판독 규칙을 합성 입력으로 다시 물어본다.
    어휘·패턴·판정 규칙을 지우거나 망가뜨리면 그 실행이 즉시 실패한다(“위반 0건”으로 조용히 통과하지 않는다).
  * ``Floor`` — **탐지력 하한.** harness 가 봐야 할 대상의 수(스캔한 파일 · 읽은 pin · 회차)를 세고
    하한보다 적으면 실패한다. 하한을 내리는 것은 **근거와 함께 사람이 하는 결정**이다.

```sh
.venv/bin/python scripts/<harness>.py --self-test   # 자기시험만(측정 대상은 건드리지 않는다)
```
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1


@dataclass(frozen=True, slots=True)
class Probe:
    """자기시험 결과 — 재판정한 항목 수와 실패한 항목."""

    cases: int
    failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """재판정 항목이 하나도 없으면 검사하지 않은 것이다 — 통과로 세지 않는다."""

        return not self.failures and self.cases > 0

    def as_mapping(self) -> dict[str, object]:
        return {"cases": self.cases, "failures": list(self.failures), "ok": self.ok}


class Cases:
    """자기시험 항목을 모으는 builder — 실패를 모으되 실행을 멈추지 않는다(한 번에 다 보고한다)."""

    __slots__ = ("_cases", "_failures")

    def __init__(self) -> None:
        self._cases = 0
        self._failures: list[str] = []

    def check(self, label: str, condition: bool) -> None:
        """조건이 참이어야 하는 항목."""

        self._cases += 1
        if not condition:
            self._failures.append(label)

    def equal(self, label: str, actual: object, expected: object) -> None:
        """두 값이 같아야 하는 항목 — 틀리면 실제·기대를 함께 남긴다."""

        self._cases += 1
        if actual != expected:
            self._failures.append(f"{label}: {actual!r} ≠ {expected!r}")

    def covers(self, label: str, required: Iterable[str], available: Iterable[str]) -> None:
        """요구 목록이 전부 살아 있어야 하는 항목 — **지워진 항목**은 순회로는 안 보인다."""

        self._cases += 1
        have = set(available)
        missing = [item for item in required if item not in have]
        if missing:
            self._failures.append(f"{label}가 사라졌다: {missing}")

    def probe(self) -> Probe:
        return Probe(cases=self._cases, failures=tuple(self._failures))


@dataclass(frozen=True, slots=True)
class Floor:
    """탐지력 하한 — 본 대상 수와 최소값. 미달이면 그 이유를 문장으로 낸다."""

    label: str
    observed: int
    minimum: int

    def problem(self) -> str | None:
        if self.observed >= self.minimum:
            return None
        return (
            f"{self.label} {self.observed}개 < 하한 {self.minimum} — "
            "찾은 것이 없다기보다 **볼 수 없는 상태**일 수 있다."
        )

    def as_mapping(self) -> dict[str, object]:
        return {"label": self.label, "observed": self.observed, "minimum": self.minimum}


def probe_problems(probe: Probe | None, *, name: str) -> list[str]:
    """자기시험 결과를 게이트 문장으로 — 부재와 실패를 모두 실패로 만든다."""

    if probe is None:
        return [f"{name} 자기시험 결과가 없다 — 자기 판독력을 확인하지 않은 실행은 통과시키지 않는다"]
    if not probe.ok:
        if not probe.failures:
            return [f"{name} 자기시험이 항목 0건이다 — 검사하지 않은 것을 통과로 세지 않는다"]
        return [f"{name} 자기시험 실패(판독 규칙이 깨졌다): " + "; ".join(probe.failures)]
    return []


def floor_problems(floors: Iterable[Floor]) -> list[str]:
    """하한 미달을 게이트 문장으로."""

    return [problem for floor in floors if (problem := floor.problem()) is not None]


def describe_self_test(name: str, probe: Probe) -> str:
    """자기시험 한 줄 보고 — 사람이 읽는 자리."""

    state = "통과" if probe.ok else "실패: " + "; ".join(probe.failures)
    return f"[self-probe] {name} {probe.cases}건 재판정 — {state}"
