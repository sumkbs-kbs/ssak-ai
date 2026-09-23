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
from pathlib import Path
from typing import Final

EXIT_OK: Final[int] = 0
EXIT_GATE: Final[int] = 1

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DOCS_ROOT: Final[Path] = Path("docs/ssak-ai-core")
ARTIFACT: Final[Path] = DOCS_ROOT / "evidence" / "digest_drift.json"

# 문서가 문장에서 인용하는 경로 + 그 뒤에 붙은 digest. 경로 뒤 40자 안에서 `sha256` 표기를 찾는다.
_PIN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"((?:tests|scripts|src|docs|dashboard|tools|config|data)/[A-Za-z0-9_./\-]+"
    r"\.(?:py|md|json|jsonl|yaml|yml|ts|tsx|sh|txt|toml))"
    r"[^\n]{0,40}?sha256[ =:`]*([0-9a-f]{8,64})"
)

STATUS_MATCH: Final[str] = "match"
STATUS_DRIFT: Final[str] = "drift"
STATUS_MISSING: Final[str] = "missing"


@dataclass(frozen=True, slots=True)
class Pin:
    """증거 문서 하나가 파일 하나에 못 박은 digest."""

    doc: str
    path: str
    recorded: str
    actual: str
    status: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "doc": self.doc,
            "path": self.path,
            "recorded": self.recorded,
            "actual": self.actual,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class Drift:
    """측정 결과 전체 — artifact 와 stdout JSON 의 내용."""

    pins: tuple[Pin, ...]
    source_head: str

    @property
    def counts(self) -> dict[str, int]:
        counts = {STATUS_MATCH: 0, STATUS_DRIFT: 0, STATUS_MISSING: 0}
        for pin in self.pins:
            counts[pin.status] += 1
        return counts

    @property
    def docs(self) -> dict[str, dict[str, int]]:
        per_doc: dict[str, dict[str, int]] = {}
        for pin in self.pins:
            bucket = per_doc.setdefault(pin.doc, {STATUS_MATCH: 0, STATUS_DRIFT: 0, STATUS_MISSING: 0})
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
        """artifact 최신성 비교에 쓰는 부분 — 시점(source_head)은 비교하지 않는다."""

        return {"counts": self.counts, "docs": self.docs, "pins": [pin.as_mapping() for pin in self.pins]}


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


def measure(docs_root: Path | None = None) -> Drift:
    """문서의 모든 digest pin 을 실제 파일과 대조한다."""

    root = docs_root or DOCS_ROOT
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
            status = STATUS_MATCH if actual.startswith(recorded) else STATUS_DRIFT
            pins.append(Pin(doc=doc.name, path=citation, recorded=recorded, actual=actual, status=status))
    return Drift(pins=tuple(pins), source_head=source_head())


def describe(drift: Drift) -> str:
    """사람이 읽는 요약 — 어떤 문서의 어떤 pin 이 움직였는지."""

    counts = drift.counts
    lines = [
        f"[digest-drift] pin {len(drift.pins)}개 · 그대로 {counts[STATUS_MATCH]} · "
        f"움직임 {counts[STATUS_DRIFT]} · 깨짐 {counts[STATUS_MISSING]} (source head {drift.source_head})",
    ]
    for pin in drift.pins:
        if pin.status == STATUS_MATCH:
            continue
        marker = "DRIFT  " if pin.status == STATUS_DRIFT else "BROKEN "
        lines.append(
            f"  {marker}{pin.doc} · {pin.path} · 기록 {pin.recorded[:16]} ≠ 현재 {(pin.actual[:16] or '(파일 없음)')}"
        )
    lines.append(
        "* 움직임은 “그 파일이 그 뒤에 바뀌었다”는 뜻이다 — 증거가 현재 내용에 대해 다시 확인되지 않았다. "
        "digest 를 갱신하는 것은 그 재확인이 아니다."
    )
    return "\n".join(lines)


def load_stored(artifact: Path) -> dict[str, object] | None:
    if not artifact.exists():
        return None
    try:
        return json.loads(artifact.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def gate_failures(drift: Drift, artifact: Path) -> list[str]:
    """게이트: artifact 가 최신인가 + 깨진 pin(파일이 없는 주장)이 없는가."""

    problems: list[str] = []
    stored = load_stored(artifact)
    if stored is None:
        problems.append(f"{display(artifact)} 가 없거나 읽히지 않는다 — 먼저 scripts/digest_drift.py 를 돌려야 한다")
    else:
        compare_keys = ("counts", "docs", "pins")
        stale = [key for key in compare_keys if stored.get(key) != drift.compared()[key]]
        if stale:
            problems.append(
                f"artifact 가 최신이 아니다({', '.join(stale)} 불일치) — 파일이 바뀌었으면 다시 측정해야 한다"
            )
    broken = [pin for pin in drift.pins if pin.status == STATUS_MISSING]
    if broken:
        problems.append("파일이 없는데 digest 를 못 박은 항목: " + ", ".join(f"{pin.doc}:{pin.path}" for pin in broken))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="증거가 못 박은 sha256 의 현재 일치 여부를 측정한다")
    parser.add_argument("--gate", action="store_true", help="artifact 최신성과 깨진 pin 을 실패로 만든다")
    parser.add_argument(
        "--emit-json",
        action="store_true",
        help="artifact 를 건드리지 않고 측정 결과만 stdout 으로 낸다(리뷰 검사가 읽는다)",
    )
    parser.add_argument("--artifact", type=Path, default=ARTIFACT, help="측정 artifact 경로")
    args = parser.parse_args(argv)

    drift = measure()
    if args.emit_json:
        print(json.dumps(drift.as_mapping(), ensure_ascii=False, indent=2))
        return EXIT_OK

    if args.gate:
        problems = gate_failures(drift, args.artifact)
        for problem in problems:
            print(f"[FAIL] {problem}", file=sys.stderr)
        return EXIT_GATE if problems else EXIT_OK

    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(drift.as_mapping(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(describe(drift))
    print(f"\n측정 artifact: {display(args.artifact)}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
