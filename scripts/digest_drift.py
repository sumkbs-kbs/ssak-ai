#!/usr/bin/env python
"""증거 문서가 못 박은 sha256 이 **아직 그 파일인지** 측정해 artifact 로 남긴다.

증거 문서는 인용한 파일의 digest 를 함께 적는다(예: `models.py (sha256 65abe58b…)`). 그 digest 는
"내가 이 파일을 봤다"는 시점의 기록이다. 파일이 나중에 바뀌면 그 증거는 **지나간 revision 을 가리키게
되는데**, 문서만 읽어서는 알 수 없다 — 그래서 추정하지 않고 측정한다.

이 스크립트가 만들지 않는 것: "digest 를 현재 값으로 갱신"은 **하지 않는다**. 갱신은 그 증거를 다시
확인했다는 주장이 되는데, 그것은 사람이 해야 할 일이다. 여기서는 어느 pin 이 아직 서 있고 어느 pin 이
움직였는지만 남긴다.

```sh
.venv/bin/python scripts/digest_drift.py                       # 측정 + artifact 갱신 + 요약
.venv/bin/python scripts/digest_drift.py --gate                # artifact 가 최신인지 + 깨진 pin 이 없는지
.venv/bin/python scripts/digest_drift.py --emit-json           # stdout 으로만 측정 결과(리뷰 검사용)
```
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

EXIT_OK: Final[int] = 0
EXIT_GATE: Final[int] = 1

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DOCS_ROOT: Final[Path] = Path("docs/ssak-ai-core")

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

ARTIFACT: Final[Path] = DOCS_ROOT / "evidence" / "digest_drift.json"
REVERIFIED: Final[Path] = DOCS_ROOT / "evidence" / "digest_reverification.json"

# 문서가 문장에서 인용하는 경로 + 그 뒤에 붙은 digest. 경로 뒤 40자 안에서 `sha256` 표기를 찾는다.
_PIN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"((?:tests|scripts|src|docs|dashboard|tools|config|data)/[A-Za-z0-9_./\-]+"
    r"\.(?:py|md|json|jsonl|yaml|yml|ts|tsx|sh|txt|toml))"
    r"[^\n]{0,40}?sha256[ =:`]*([0-9a-f]{8,64})"
)

STATUS_MATCH: Final[str] = "match"
STATUS_DRIFT: Final[str] = "drift"
STATUS_REVERIFIED: Final[str] = "reverified"
STATUS_STALE: Final[str] = "stale_reverification"
STATUS_MISSING: Final[str] = "missing"

STATUSES: Final[tuple[str, ...]] = (
    STATUS_MATCH,
    STATUS_REVERIFIED,
    STATUS_DRIFT,
    STATUS_STALE,
    STATUS_MISSING,
)

# 자기시험이 요구하는 상태 — 순회만으로는 **지워진 상태 이름**이 안 보이므로 따로 고정한다.
_REQUIRED_STATUSES: Final[tuple[str, ...]] = (
    STATUS_MATCH,
    STATUS_REVERIFIED,
    STATUS_DRIFT,
    STATUS_STALE,
    STATUS_MISSING,
)
# 탐지력 하한 — 문서가 pin 을 하나도 안 만들면 “pin 0 · 움직임 0” 으로 조용히 통과한다.
_MIN_PINS: Final[int] = 1
_MIN_PINNED_DOCS: Final[int] = 1
_WHY_PINS: Final[str] = (
    "2026-09-23 기준 관측: 증거 문서 13개가 파일에 digest 를 박아 pin 50개(그대로 28 · 재확인 22). "
    "하한을 1로 둔 것은 ‘얼마나 많이 보나’ 가 아니라 ‘패턴이 죽어 0이 됐나’ 를 잡기 위해서다."
)
_WHY_DOCS: Final[str] = (
    "2026-09-23 기준 관측: pin 을 박은 문서 13개. 문서 집합이 통째로 안 읽히면 ‘움직임 0’ 으로 보이므로 그 순간을 잡는다."
)


@dataclass(frozen=True, slots=True)
class Reverification:
    """사람이 그 증거를 다시 확인한 기록 — 확인 시점의 digest 와 방법.

    기록 자체가 “그 뒤로 안 바뀌었다” 를 뜻하지는 않는다. 그 파일이 다시 바뀌면 이 기록은 **무효**가
    되고(`stale_reverification`), 그 사실이 게이트를 실패시킨다.
    """

    doc: str
    path: str
    verified_digest: str
    verified_on: str
    method: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "doc": self.doc,
            "path": self.path,
            "verified_digest": self.verified_digest,
            "verified_on": self.verified_on,
            "method": self.method,
        }


@dataclass(frozen=True, slots=True)
class Pin:
    """증거 문서 하나가 파일 하나에 못 박은 digest."""

    doc: str
    path: str
    recorded: str
    actual: str
    status: str
    reverified_on: str = ""

    def as_mapping(self) -> dict[str, str]:
        return {
            "doc": self.doc,
            "path": self.path,
            "recorded": self.recorded,
            "actual": self.actual,
            "status": self.status,
            "reverified_on": self.reverified_on,
        }


@dataclass(frozen=True, slots=True)
class Drift:
    """측정 결과 전체 — artifact 와 stdout JSON 의 내용."""

    pins: tuple[Pin, ...]
    source_head: str

    @property
    def counts(self) -> dict[str, int]:
        counts = dict.fromkeys(STATUSES, 0)
        for pin in self.pins:
            counts[pin.status] += 1
        return counts

    @property
    def docs(self) -> dict[str, dict[str, int]]:
        per_doc: dict[str, dict[str, int]] = {}
        for pin in self.pins:
            bucket = per_doc.setdefault(pin.doc, dict.fromkeys(STATUSES, 0))
            bucket[pin.status] += 1
        return per_doc

    def as_mapping(self) -> dict[str, object]:
        return {
            "command": ["python", "scripts/digest_drift.py"],
            "source_head": self.source_head,
            "counts": self.counts,
            "docs": self.docs,
            "pins": [pin.as_mapping() for pin in self.pins],
        }

    def compared(self) -> dict[str, object]:
        """artifact 최신성 비교에 쓰는 부분 — 시점(source_head)은 비교하지 않는다.

        하한(`floors`)도 비교 대상이다: 하한 값이나 그 근거를 바꾸고 artifact 를 다시 만들지 않으면,
        저장본은 예전 기준을 계속 주장하게 된다.
        """

        return {
            "counts": self.counts,
            "docs": self.docs,
            "pins": [pin.as_mapping() for pin in self.pins],
            "floors": floor_records(coverage_floors(self)),
        }


def display(path: Path) -> str:
    """가능하면 저장소 기준 상대 경로로 보여준다."""

    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve_citation(citation: str) -> Path | None:
    """문서의 인용을 실제 파일로 해석한다(저장소 관행의 축약 표기를 허용한다).

    예: `tools/ssak_bundle_store.py` → `src/antigravity_k/tools/ssak_bundle_store.py`.
    """

    candidates = [REPO_ROOT / citation]
    if not citation.startswith(("src/", "tests/", "docs/")):
        candidates.append(REPO_ROOT / "src" / "antigravity_k" / citation)
    candidates.append(REPO_ROOT / "tests" / "cognitive" / citation)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def source_head() -> str:
    """측정 시점의 HEAD(짧은 sha). 비교에는 쓰지 않고 기록용이다."""

    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def load_reverifications(path: Path | None = None) -> dict[tuple[str, str], Reverification]:
    """재확인 기록 — 없으면 빈 표(기록이 없다는 것이 곧 ‘재확인 안 됨’이다)."""

    target = path or REVERIFIED
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    records: dict[tuple[str, str], Reverification] = {}
    for item in payload.get("entries", []):
        record = Reverification(
            doc=str(item.get("doc", "")),
            path=str(item.get("path", "")),
            verified_digest=str(item.get("verified_digest", "")),
            verified_on=str(item.get("verified_on", "")),
            method=str(item.get("method", "")),
        )
        records[(record.doc, record.path)] = record
    return records


def classify(recorded: str, actual: str, reverified: Reverification | None) -> str:
    """pin 하나의 상태 — 재확인 기록은 “그 뒤로 안 바뀌었다” 를 뜻하지 않는다."""

    if actual.startswith(recorded):
        return STATUS_MATCH
    if reverified is None:
        return STATUS_DRIFT
    return STATUS_REVERIFIED if reverified.verified_digest == actual else STATUS_STALE


def measure(docs_root: Path | None = None, reverifications: Path | None = None) -> Drift:
    """문서의 모든 digest pin 을 실제 파일·재확인 기록과 대조한다."""

    root = docs_root or DOCS_ROOT
    records = load_reverifications(reverifications)
    pins: list[Pin] = []
    seen: set[tuple[str, str]] = set()
    for doc in sorted(root.rglob("*.md")):
        text = doc.read_text(encoding="utf-8")
        for citation, recorded in sorted(set(_PIN_PATTERN.findall(text))):
            key = (doc.name, citation)
            if key in seen:
                continue
            seen.add(key)
            target = resolve_citation(citation)
            if target is None:
                pins.append(Pin(doc=doc.name, path=citation, recorded=recorded, actual="", status=STATUS_MISSING))
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            record = records.get(key)
            status = classify(recorded, actual, record)
            pins.append(
                Pin(
                    doc=doc.name,
                    path=citation,
                    recorded=recorded,
                    actual=actual,
                    status=status,
                    reverified_on=record.verified_on if record and status == STATUS_REVERIFIED else "",
                )
            )
    return Drift(pins=tuple(pins), source_head=source_head())


def describe(drift: Drift, probe: Probe | None = None) -> str:
    """사람이 읽는 요약 — 어떤 pin 이 움직였고, 어느 것이 재확인됐는지."""

    counts = drift.counts
    lines = [
        describe_self_test("digest_drift", probe if probe is not None else self_probe()),
        f"[digest-drift] pin {len(drift.pins)}개 · 그대로 {counts[STATUS_MATCH]} · "
        f"재확인 {counts[STATUS_REVERIFIED]} · 움직임(미확인) {counts[STATUS_DRIFT]} · "
        f"재확인 무효 {counts[STATUS_STALE]} · 깨짐 {counts[STATUS_MISSING]} "
        f"(source head {drift.source_head})",
    ]
    markers = {
        STATUS_DRIFT: "DRIFT   ",
        STATUS_STALE: "STALE   ",
        STATUS_MISSING: "BROKEN  ",
        STATUS_REVERIFIED: "REVERIFY",
    }
    for pin in drift.pins:
        if pin.status == STATUS_MATCH:
            continue
        note = f" · 재확인 {pin.reverified_on}" if pin.reverified_on else ""
        lines.append(
            f"  {markers[pin.status]} {pin.doc} · {pin.path} · 기록 {pin.recorded[:16]} ≠ "
            f"현재 {(pin.actual[:16] or '(파일 없음)')}{note}"
        )
    lines.append(
        "* 움직임은 “그 파일이 그 뒤에 바뀌었다”는 뜻이다. 재확인 기록은 그 시점에 내용을 다시 봤다는 것이고, "
        "그 뒤에 파일이 또 바뀌면 무효(STALE)가 된다 — 재생성만으로는 재확인이 아니다."
    )
    return "\n".join(lines)


_PROBE_PINNED: Final[str] = "근거: scripts/digest_drift.py (sha256 abcdef0123456789) 를 쓴다."
_PROBE_UNPINNED: Final[str] = "이 문장은 sha256 abcdef0123456789 만 적고 경로가 없다."


def self_probe() -> Probe:
    """매 실행 자기시험 — 경로+digest 판독·상태 판정·경로 해석을 합성 입력으로 다시 물어본다."""

    cases = Cases()
    cases.covers("상태 이름", _REQUIRED_STATUSES, STATUSES)
    cases.equal("경로+digest 판독", len(_PIN_PATTERN.findall(_PROBE_PINNED)), 1)
    cases.equal("경로 없는 sha256 은 pin 이 아니다", len(_PIN_PATTERN.findall(_PROBE_UNPINNED)), 0)
    cases.check("실제 경로를 해석한다", resolve_citation("scripts/digest_drift.py") is not None)
    cases.check("없는 경로는 None", resolve_citation("scripts/definitely_not_here_9f3a.py") is None)

    record = Reverification(
        doc="T00_probe.md",
        path="scripts/digest_drift.py",
        verified_digest="f" * 64,
        verified_on="2026-09-23",
        method="probe",
    )
    cases.equal("그대로(기록이 앞자리)", classify("abc", "abcdef", None), STATUS_MATCH)
    cases.equal("재확인 없이 바뀜", classify("abc", "xyz", None), STATUS_DRIFT)
    cases.equal("재확인이 지금 내용과 같다", classify("abc", "f" * 64, record), STATUS_REVERIFIED)
    cases.equal("재확인 뒤 또 바뀜", classify("abc", "e" * 64, record), STATUS_STALE)
    return cases.probe()


def coverage_floors(drift: Drift) -> list[Floor]:
    """이번 측정이 실제로 무엇을 봤는지 — pin 0개는 “움직임 0” 이 아니라 “못 봄” 일 수 있다."""

    return [
        Floor("pin", len(drift.pins), _MIN_PINS, why=_WHY_PINS),
        Floor("pin 을 박은 문서", len(drift.docs), _MIN_PINNED_DOCS, why=_WHY_DOCS),
    ]


def load_stored(artifact: Path) -> dict[str, object] | None:
    if not artifact.exists():
        return None
    try:
        return json.loads(artifact.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def gate_failures(drift: Drift, artifact: Path, probe: Probe | None = None) -> list[str]:
    """게이트: 자기시험·탐지력 + artifact 최신성 + 깨진 pin(파일이 없는 주장)이 없는가."""

    problems: list[str] = probe_problems(probe if probe is not None else self_probe(), name="digest_drift")
    problems.extend(floor_problems(coverage_floors(drift)))
    stored = load_stored(artifact)
    if stored is None:
        problems.append(f"{display(artifact)} 가 없거나 읽히지 않는다 — 먼저 scripts/digest_drift.py 를 돌려야 한다")
    else:
        compare_keys = ("counts", "docs", "pins", "floors")
        outdated = [key for key in compare_keys if stored.get(key) != drift.compared()[key]]
        if outdated:
            problems.append(
                f"artifact 가 최신이 아니다({', '.join(outdated)} 불일치) — 파일이 바뀌었으면 다시 측정해야 한다"
            )
    broken = [pin for pin in drift.pins if pin.status == STATUS_MISSING]
    if broken:
        problems.append("파일이 없는데 digest 를 못 박은 항목: " + ", ".join(f"{pin.doc}:{pin.path}" for pin in broken))
    stale = [pin for pin in drift.pins if pin.status == STATUS_STALE]
    if stale:
        problems.append(
            "재확인 뒤에 파일이 또 바뀌어 그 재확인이 무효인 항목: "
            + ", ".join(f"{pin.doc}:{pin.path}" for pin in stale)
        )
    return problems


def write_reverification(
    doc_name: str,
    drift: Drift,
    *,
    method: str,
    on: str,
    path: Path | None = None,
) -> tuple[int, str]:
    """한 문서의 **움직인 pin 전부**를 재확인으로 기록한다.

    확인하지 않은 pin 을 기록하지 않도록, 그 문서에서 지금 움직인 pin 만 대상으로 한다(움직인 것이
    없으면 할 일이 없다). 기록은 확인 시점의 digest 를 박고, 그 뒤에 파일이 또 바뀌면 무효가 된다.
    """

    target = path or REVERIFIED
    moved = [pin for pin in drift.pins if pin.doc == doc_name and pin.actual]
    fresh = [pin for pin in moved if pin.status != STATUS_MATCH]
    if not fresh:
        return EXIT_OK, f"{doc_name}: 지금 움직인 pin 이 없다 — 기록할 것이 없다(낡은 재확인을 만들지 않는다)"

    payload: dict[str, object] = {"entries": []}
    if target.exists():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"entries": []}
    raw = payload.get("entries")
    existing: list[object] = raw if isinstance(raw, list) else []
    replaced = {pin.path for pin in fresh}
    kept: list[dict[str, str]] = [
        dict(item)
        for item in existing
        if isinstance(item, dict) and not (item.get("doc") == doc_name and item.get("path") in replaced)
    ]
    for pin in fresh:
        kept.append(
            Reverification(
                doc=pin.doc,
                path=pin.path,
                verified_digest=pin.actual,
                verified_on=on,
                method=method,
            ).as_mapping()
        )
    kept.sort(key=lambda item: (str(item.get("doc", "")), str(item.get("path", ""))))
    payload["entries"] = kept
    payload["command"] = ["python", "scripts/digest_drift.py", "--record", doc_name]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return EXIT_OK, f"{doc_name}: {len(fresh)}개 pin 을 재확인으로 기록했다 ({display(target)})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="증거가 못 박은 sha256 의 현재 일치 여부를 측정한다")  # noqa: E501
    parser.add_argument("--gate", action="store_true", help="artifact 최신성과 깨진 pin 을 실패로 만든다")
    parser.add_argument(
        "--emit-json",
        action="store_true",
        help="artifact 를 건드리지 않고 측정 결과만 stdout 으로 낸다(리뷰 검사가 읽는다)",
    )
    parser.add_argument(
        "--record",
        metavar="DOC",
        default=None,
        help="이 증거 문서의 지금 움직인 pin 을 재확인으로 기록한다(사람이 내용을 본 뒤에만)",
    )
    parser.add_argument("--method", default="", help="--record 와 함께: 무엇을 해서 확인했는가")
    parser.add_argument("--on", default=None, help="--record 와 함께: 확인 날짜(기본 오늘)")
    parser.add_argument("--artifact", type=Path, default=ARTIFACT, help="측정 artifact 경로")
    parser.add_argument("--reverification", type=Path, default=REVERIFIED, help="재확인 기록 경로")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다(측정·기록 없음)")
    args = parser.parse_args(argv)

    if args.self_test:
        probe = self_probe()
        print(describe_self_test("digest_drift", probe))
        return EXIT_OK if probe.ok else EXIT_GATE

    drift = measure(reverifications=args.reverification)
    probe = self_probe()
    payload = {
        **drift.as_mapping(),
        "probe": probe.as_mapping(),
        "floors": floor_records(coverage_floors(drift)),
        "coverage": {
            "pins": len(drift.pins),
            "docs": len(drift.docs),
            "min_pins": _MIN_PINS,
            "min_docs": _MIN_PINNED_DOCS,
        },
    }
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK

    if args.record:
        if not args.method.strip():
            print(
                "[FAIL] --record 에는 --method 가 필요하다 — 무엇을 확인했는지 없이는 재확인이 아니다", file=sys.stderr
            )
            return EXIT_GATE
        if not any(pin.doc == args.record for pin in drift.pins):
            print(f"[FAIL] {args.record} 는 digest 를 못 박은 문서가 아니다(이름 확인)", file=sys.stderr)
            return EXIT_GATE
        code, message = write_reverification(
            args.record,
            drift,
            method=args.method.strip(),
            on=args.on or date.today().isoformat(),
            path=args.reverification,
        )
        print(message)
        return code

    if args.gate:
        problems = gate_failures(drift, args.artifact)
        for problem in problems:
            print(f"[FAIL] {problem}", file=sys.stderr)
        return EXIT_GATE if problems else EXIT_OK

    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(describe(drift))
    print(f"\n측정 artifact: {display(args.artifact)}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
