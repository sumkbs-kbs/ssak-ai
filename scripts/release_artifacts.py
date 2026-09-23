#!/usr/bin/env python
"""배포 산출물 계약 — **wheel/sdist 를 실제로 만들어 저장소 밖에서 소비해 보고**, 그 검증이 정말 무는지까지 본다.

T14 는 `test / lint / type / build` 를 요구하는데 `build` 만 **NOT_RUN** 으로 남아 있었다(“릴리스 CI 소관이라 이
체크아웃에서 실행하지 않았다”). 그 문장은 위험 하나를 숨긴다 — 이 체크아웃에서 배포판을 한 번도 만들어 본 적이 없다는
것. 소비자가 받는 물건과 저장소 트리는 다를 수 있고(빠진 파일), 그 차이는 설치된 곳에서만 보인다.

이 도구가 그 물음을 네 단계로 닫는다:

  1. **빌드** — `uv build --no-sources` 로 wheel 과 sdist 를 만든다. 하나라도 없으면 실패다(계약은 둘이다).
  2. **저장소 밖 소비** — 기존 검증기(`scripts/verify_release_artifacts.sh`)가 신규 venv 에 설치해 저장소 트리 없이
     CLI·모듈·API·auth 를 돌린다. 그 판정을 **종료 코드와 산출물별 PASS 문장**으로 읽는다.
  3. **sdist 왕복** — sdist 를 풀어 **그 안에서** wheel 을 다시 빌드한 뒤, 트리에서 만든 wheel 과 **파일 목록을 견준다**.
     `MANIFEST`/package-data 에서 빠진 파일은 sdist 설치 경로에서만 드러난다 — wheel 만 검증하면 그 결함은 안 보인다.
  4. **배포판 vs 추적 트리** — 소비자가 받는 wheel 이 **커밋된 코드를 모두 담고 있는가**. `uv build` 는 wheel 을
     sdist 에서 만들므로(로그: “Building wheel from source distribution…”) sdist 가 잃은 파일은 소비자에게도 없다 —
     `git ls-files` 로 추적 파일을 세어 빠진 것이 있으면 **이름으로 실패**시키고, 미추적 로컬 파일·빌드 생성물은 **보고만** 한다.
  5. **red 재현 셋** — 이 층은 세 종류의 결함을 막아야 한다:
     · “빠진 배포판”: 같은 wheel 사본에서 module 하나를 빼고 `RECORD` 를 다시 써서 **유효하지만 불완전한**
       wheel 을 만든 뒤 같은 검증기에 건다. 그 검증기가 통과시키면 이 층은 아무것도 막지 못한다.
     · “빠진 sdist”: sdist 사본에서 파일 하나를 빼고 **같은 왕복**을 돌린다. 왕복이 그 빠짐을 지목하지 못하면
       왕복 관찰(exit 0 · 빠짐 0)이 “보고 0” 인지 “아무것도 못 보고 0” 인지 가릴 수 없다.
     · “잃어버린 추적 파일”: **작은 실물 프로젝트**(git·uv 로 실제 빌드)에서 추적 파일 하나를 sdist 에서 빼고 같은 눈으로 본다.
       대조군은 같은 프로젝트에서 그 한 줄만 뺀 것 — 심은 이름을 지목하고 대조군이 조용해야 이 눈이 무는 것이다.
     판정(검증·왕복·추적 대조)은 **한 빌드**를 가리킨다. 재현 계약만 같은 pin 으로 **한 번 더** 만든다(아래 6).
  6. **재현 빌드 동일성** — `SOURCE_DATE_EPOCH` 를 고정하고 **같은 트리로 한 번 더** 만들어 바이트를 견준다. “어제 만든 것과
     오늘 만든 것이 같은 물건인가” 는 공급망 신뢰의 전제이고, 이 층이 검증한 물건이 재현 불가능하면 그 검증은 그날의 사본에만
     해당한다. 판정은 산출물마다 다르다:
     · **wheel — 계약.** 항목마다 pin 시각을 쓰는 backend(vendored `wheel` 의 `Wheelfile`)라 같은 pin 이면 같은 바이트여야 한다.
     · **sdist — 예외, 그러나 만료되는 예외.** 현 backend(setuptools)의 sdist 경로는 `SOURCE_DATE_EPOCH` 를 **읽지 않는다**:
       실제 파일은 디스크 mtime, 생성 항목(`PKG-INFO`·`setup.cfg`·디렉터리)과 gzip 헤더는 벽시계를 쓴다. 그래서 관측은
       “항상 다름” 이다 — 이 층은 그것을 **이름 붙여 기록**하되 좁게 잡는다: 차이가 디렉터리·backend 생성물에만 있으면 허용,
       **트리에 있는 실제 파일**이 달라지면 결함, 파일 **목록**이 흔들리면 결함, 그리고 sdist 가 **같아지면** 예외가 만료된
       것이므로 실패시킨다(낡은 예외는 결함을 가리는 면죄부가 된다). 근거 문장이 낡았는지도 본다(항목 중 pin 을 따르는 수).
  7. **민감도 실물 재현** — “동일” 관찰은 비교가 눈이 있다는 증거 없이는 공허하다. 작은 **setuptools** 프로젝트(우리 배포 경로와
     같은 backend)를 실제로 세 번 빌드한다: 같은 pin 두 번(**대조군** — 같아야 한다) · 다른 pin 한 번(달라야 한다 — 그래서
     “같음” 이 공허하지 않다) · 그리고 그 미니 sdist 도 우리 sdist 와 같은 모양으로 달라지는가(그러면 이 차이는 **backend
     속성**이고 우리 repo 탓이 아니다).
  8. **배포 경로가 정말 pin 을 거는가** — 이 층이 “재현된다” 고 말해도 배포하는 쪽이 pin 을 안 걸면 그 보장은 이론이다.
     그래서 CI 의 build job 이 **같은 값**을 거는지 읽어서 확인한다(없거나 다르면 실패).
  9. **자기시험** — 판정 규칙(빌드 실패·산출물 수·PASS 문장·왕복 누락·추적 파일 누락·재현 불일치·예외 만료·민감도 실종·CI pin 누락·
     왕복 red 미탐지·red 미탐지·사고)을 매 실행 다시 묻는다.

**탐지력 하한**도 함께 낸다(`Floor` — 값과 근거): 배포 산출물 2(wheel+sdist) · 저장소 밖 PASS 2 · **비교한 파일**(왕복
비교가 몇 파일에서 이뤄졌나) · **배포판에 실린 추적 파일**(추적 대조가 **0개를 보고 “빠짐 없음”** 으로 통과하는 순간을 잡는다) ·
**재현 비교한 산출물**(재현 비교가 0건이면 “동일” 이 아니라 **아무것도 안 본 것**이다). 하한이 장식인지도 자기시험이 본다(관측 0 은 실패).

```sh
.venv/bin/python scripts/release_artifacts.py            # 빌드 + 검증 + red 재현(수십 초)
.venv/bin/python scripts/release_artifacts.py --emit-json # 게이트 stage 가 읽는다(판정은 종료 코드)
.venv/bin/python scripts/release_artifacts.py --self-test # 자기시험만(빌드하지 않는다)
```
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCRIPTS_DIR: Final[Path] = REPO_ROOT / "scripts"
# sdist 안 최상위 디렉터리 이름(`antigravity_k-0.1.0/…`) — 트리 경로로 되돌릴 때 한 칸 벗긴다.
_ARCHIVE_ROOT: Final[re.Pattern[str]] = re.compile(r"^[^/]+/")
VERIFIER: Final[Path] = SCRIPTS_DIR / "verify_release_artifacts.sh"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from harness_contract import (  # noqa: E402
    Cases,
    Floor,
    Probe,
    describe_self_test,
    floor_problems,
    floor_records,
    probe_problems,
)

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
CRASH_MARKER: Final[str] = "Traceback (most recent call last)"

ARTIFACT_KINDS: Final[tuple[str, ...]] = ("wheel", "sdist")
TAMPER_TARGET: Final[str] = "antigravity_k/engine/release_sbom.py"
# sdist 안에서 **내용을 바꿔** 왕복이 그 변화를 보는지 확인한다(빠진 파일만으로는 ‘이름’ 만 보는 눈을 증명하지 못한다).
REWRITE_TARGET: Final[str] = "antigravity_k/engine/artifact_provenance.py"
REWRITE_APPENDIX: Final[str] = "\n# 왕복 내용 재현 — sdist 안에서만 다른 바이트\n"

# 내용 대조용 작은 프로젝트 — 빌드가 **내용을 바꿔 싣는** 경우를 실제 setuptools 로 재현한다.
TRANSFORM_MINI: Final[str] = "transform-mini"
TRANSFORM_TARGET: Final[str] = "mini/kept.py"
TRANSFORM_BODY: Final[str] = "kept = 9  # build transform\n"

# 재현 빌드 — 같은 입력이면 같은 바이트인가. 값 자체에는 의미가 없다: 의미가 있는 것은 **모든 빌드가 같은 값**을 본다는
# 것뿐이다(시계에서 읽으면 그 순간에 따라 바이트가 달라진다 — 재현이 목적에 반한다). CI build job 도 같은 값을 건다.
REPRO_PIN: Final[int] = 1_758_600_000  # 2025-09-23T04:00:00Z
REPRO_ALT_PIN: Final[int] = REPRO_PIN + 86_400  # 다른 pin — 비교가 이 바이트를 보는지 확인용
CI_WORKFLOW: Final[Path] = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CI_BUILD_JOB: Final[str] = "build"
CI_BUILD_TOKEN: Final[str] = "uv build"

# sdist 예외의 근거 — backend 는 이 값을 읽지 않는다. 이 문장이 관측과 어긋나면(항목이 pin 을 따르기 시작하면) 낡은 근거다.
SDIST_LIMITATION_WHY: Final[str] = (
    "현 backend(setuptools)의 sdist 경로는 `SOURCE_DATE_EPOCH` 를 읽지 않는다 — 실제 파일은 디스크 mtime, "
    "생성 항목(PKG-INFO·setup.cfg·디렉터리)과 gzip 헤더는 벽시계를 쓴다(항목 중 pin 시각을 가진 것 0개로 관측). "
    "wheel 은 vendored `wheel` 의 `Wheelfile` 이 이 값을 읽어 재현된다."
)
_MIN_CONTENT: Final[int] = 600
_WHY_CONTENT: Final[str] = (
    "2026-09-23 기준 관측: 배포 wheel 의 패키지 파일 658개가 **디스크 트리 바이트와 전부 일치**했다(다름 0). "
    "하한 600은 경로 매핑이 바뀌어 **0개를 비교하고 ‘차이 없음’** 으로 통과하는 순간을 잡는다 — "
    "비교한 것이 없으면 내용 대조는 증거가 아니다."
)
_MIN_IDENTITIES: Final[int] = 2
_WHY_IDENTITIES: Final[str] = (
    "2026-09-23 기준 관측: 같은 pin 두 번 빌드에서 wheel 664/664 항목이 pin 시각 · sdist 0/1205 · 비교한 산출물 2종. "
    "하한 2는 **재현 비교가 0~1건에서 ‘차이 없음’ 으로 통과하는 순간**을 잡는다 — 비교한 산출물이 없으면 ‘동일하다’ 는 관측이 아니다."
)

_MIN_ARTIFACTS: Final[int] = 2
_WHY_ARTIFACTS: Final[str] = (
    "2026-09-23 기준 관측: `uv build --no-sources` 가 wheel(33.2MB)·sdist(34.1MB) 를 만든다. "
    "하한 2는 계약 그 자체다 — 하나만 만들고 통과하면 “배포 가능” 이 아니다(sdist 소비자와 wheel 소비자가 다르다)."
)
_MIN_PASSED: Final[int] = 2
_WHY_PASSED: Final[str] = (
    "2026-09-23 기준 관측: 저장소 밖 신규 venv 설치 뒤 wheel·sdist 둘 다 CLI/모듈/API/auth 를 통과했다. "
    "하한 2는 “설치가 됐다” 가 아니라 “설치한 것을 실제로 써 봤다” 를 요구한다 — 설치 성공만 보면 빈 배포판도 통과한다."
)
_MIN_COMPARED: Final[int] = 100
_WHY_COMPARED: Final[str] = (
    "2026-09-23 기준 관측: 트리에서 만든 wheel 안 항목 664개(cognitive core·surface·dashboard bundle 포함). "
    "하한 100은 **목록 읽기가 깨져 0~소수에서 ‘차이 없음’ 으로 통과하는 순간**을 잡는 안전선이다 — "
    "비교한 것이 없으면 왕복 검증은 증거가 아니다."
)

# 배포판이 담아야 할 뿌리 — pyproject.toml 의 `packages = [\"src/antigravity_k\"]`.
PACKAGE_SRC: Final[str] = "src/antigravity_k"
PACKAGE_NAME: Final[str] = "antigravity_k"
_MIN_TRACKED: Final[int] = 600
_WHY_TRACKED: Final[str] = (
    "2026-09-23 기준 관측: git 추적 파일 656개가 **모두** 배포 wheel 안에 있다(빠짐 0). 하한 600은 "
    "`git ls-files` 가 실패하거나(`returncode≠0`) 뿌리 경로가 바뀌어 **0개를 보고 ‘빠짐 없음’** 으로 통과하는 순간을 잡는다 — "
    "추적 대조가 0을 보면 그 초록은 판정이 아니다."
)

# 작은 재현 프로젝트 — 배포판에서 사라진 추적 파일을 이 눈이 보는지 실제 빌드로 확인한다(합성 기록이 아니다).
MINI_PACKAGE: Final[str] = "minipkg"
MINI_DROPPED: Final[str] = "minipkg/dropped.py"

# 재현 민감도용 작은 프로젝트 — **우리 배포 경로와 같은 backend(setuptools)** 여야 sdist 관찰이 backend 속성인지 우리 탓인지 갈린다.
REPRO_MINI: Final[str] = "repro-mini"
REPRO_MINI_PACKAGE: Final[str] = "mini"
REPRO_MINI_ALT: Final[int] = REPRO_ALT_PIN
_SKIP_PARTS: Final[frozenset[str]] = frozenset({"__pycache__", ".git", ".venv"})


@dataclass(frozen=True, slots=True)
class TreeCoverage:
    """배포판과 **git 추적 트리** 의 차이 — 소비자가 받는 물건이 커밋한 코드를 담고 있는가.

    `uv build` 는 wheel 을 **sdist 에서** 만든다(uv 로그: “Building wheel from source distribution…”). 그래서 sdist 에서
    빠진 **추적** 파일은 배포판에서도 빠지고, 소비자에게 그 module 은 없다(로컬 트리에서는 import 된다).
    반대 방향 — 추적되지 않는 로컬 파일 — 은 배포판에 없는 것이 **정상**이므로 보고만 한다.
    """

    expected: tuple[str, ...]
    missing: tuple[str, ...]
    generated: tuple[str, ...]
    local_only: tuple[str, ...]

    def as_mapping(self) -> dict[str, object]:
        return {
            "expected": len(self.expected),
            "missing": list(self.missing),
            "generated": list(self.generated),
            "local_only": list(self.local_only),
        }


@dataclass(frozen=True, slots=True)
class Identity:
    """산출물 하나의 재현 관찰 — 같은 pin 으로 두 번 만든 두 파일이 **같은 바이트**인가.

    `identical` 은 파일 전체의 sha256 으로 판정한다. 다를 때 `differs`·`appeared` 가 **무엇이** 달라졌는지 이름으로
    말한다 — 이름 없는 불일치는 사람이 고칠 수 없다.
    """

    kind: str
    first: str
    second: str
    members: int
    pinned_members: int
    appeared: tuple[str, ...]
    differs: tuple[str, ...]
    allowed_differs: tuple[str, ...]
    real_differs: tuple[str, ...]

    @property
    def identical(self) -> bool:
        return self.first == self.second

    @property
    def bytes_only(self) -> bool:
        """항목은 모두 같은데 바이트가 다르다 — 압축·헤더가 흔들렸다(실린 파일이 바뀐 것은 아니다).

        이 구분이 없으면 “다르다” 가 “무엇이 다른지 모른다” 로 읽힌다 — 예: gzip 헤더의 시각(소비에는 무관).
        """

        return not self.identical and not self.differs and not self.appeared

    def as_mapping(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "bytes_only": self.bytes_only,
            "first": self.first,
            "second": self.second,
            "identical": self.identical,
            "members": self.members,
            "pinned_members": self.pinned_members,
            "appeared": list(self.appeared),
            "differs": list(self.differs),
            "allowed_differs": list(self.allowed_differs),
            "real_differs": list(self.real_differs),
        }


@dataclass(frozen=True, slots=True)
class Sensitivity:
    """이 비교가 **이 바이트를 본다** 는 증거 — 작은 실물 프로젝트를 세 번 빌드해 확인한다(합성 기록이 아니다).

    `sdist_backend_only` 가 참이라는 것이 우리 sdist 예외의 **두 번째 사례**다: 같은 backend 의 미니 프로젝트도 sdist 가
    달라지고 그 차이가 생성 항목뿐이라면, 우리 sdist 의 차이는 **우리 repo 탓이 아니라 backend 속성**이다.
    """

    control_equal: bool
    pin_moves_bytes: bool
    sdist_differs: tuple[str, ...]
    sdist_backend_only: bool
    exits: tuple[int, ...]

    def as_mapping(self) -> dict[str, object]:
        return {
            "control_equal": self.control_equal,
            "pin_moves_bytes": self.pin_moves_bytes,
            "sdist_differs": list(self.sdist_differs),
            "sdist_backend_only": self.sdist_backend_only,
            "exits": list(self.exits),
        }


@dataclass(frozen=True, slots=True)
class Reproducibility:
    """재현 계약 — pin 을 걸고 두 번 만든 결과·그 비교의 민감도·배포 경로가 같은 pin 을 거는가."""

    identities: tuple[Identity, ...]
    second_build_exit: int | None
    sensitivity: Sensitivity
    ci_pinned: bool
    ci_pin_value: str
    seconds: float
    ci_note: str = ""
    # ‘실제 파일’ 을 가리는 자(git 추적 목록)가 작동했는가 — 못 읽었으면 예외 분류가 성립하지 않는다.
    tracked_readable: bool = True

    @property
    def sdist_identity(self) -> Identity | None:
        return next((item for item in self.identities if item.kind == "sdist"), None)

    def as_mapping(self) -> dict[str, object]:
        return {
            "pin": REPRO_PIN,
            "identities": [item.as_mapping() for item in self.identities],
            "second_build_exit": self.second_build_exit,
            "sensitivity": self.sensitivity.as_mapping(),
            "ci_pinned": self.ci_pinned,
            "ci_pin_value": self.ci_pin_value,
            "ci_note": self.ci_note,
            "tracked_readable": self.tracked_readable,
            "seconds": round(self.seconds, 1),
        }


@dataclass(frozen=True, slots=True)
class Artifact:
    """산출물 하나 — 종류·이름·크기·sha256."""

    kind: str
    name: str
    bytes: int
    sha256: str

    def as_mapping(self) -> dict[str, object]:
        return {"kind": self.kind, "name": self.name, "bytes": self.bytes, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class Observation:
    """이번 실행의 관찰 — 빌드·검증·red 재현."""

    build_exit: int | None
    artifacts: tuple[Artifact, ...]
    verify_exit: int | None
    passed: tuple[str, ...]
    roundtrip_exit: int | None
    compared: int
    missing: tuple[str, ...]
    differing: tuple[str, ...]
    extra: tuple[str, ...]
    rehearsal_exit: int | None
    rehearsal_missing: tuple[str, ...]
    rehearsal_differing: tuple[str, ...]
    rehearsal_compared: int
    tree: TreeCoverage
    content: ContentCheck
    tree_rehearsal_control: tuple[str, ...]
    tree_rehearsal_defect: tuple[str, ...]
    reproducibility: Reproducibility
    tamper_exit: int | None
    tamper_removed: str
    inputs_line: bool
    crashed: bool
    seconds: float
    # 재현 재료를 만들지 못했을 때의 까닭 — “못 돌렸다” 와 “못 봤다” 를 가른다.
    rehearsal_note: str = ""
    note: str = ""

    @property
    def detected(self) -> bool:
        """검증기가 ‘빠진 배포판’ 을 막았는가 — 이 층의 red 재현."""

        return self.tamper_exit is not None and self.tamper_exit != 0

    @property
    def problems(self) -> tuple[str, ...]:
        return observation_problems(self)

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_mapping(self) -> dict[str, object]:
        return {
            "build_exit": self.build_exit,
            "artifacts": [item.as_mapping() for item in self.artifacts],
            "verify_exit": self.verify_exit,
            "passed": list(self.passed),
            "roundtrip_exit": self.roundtrip_exit,
            "compared": self.compared,
            "missing": list(self.missing),
            "differing": list(self.differing),
            "extra": list(self.extra),
            "rehearsal_exit": self.rehearsal_exit,
            "rehearsal_missing": list(self.rehearsal_missing),
            "rehearsal_differing": list(self.rehearsal_differing),
            "rehearsal_compared": self.rehearsal_compared,
            "rehearsal_note": self.rehearsal_note,
            "tree": self.tree.as_mapping(),
            "content": self.content.as_mapping(),
            "tree_rehearsal_control": list(self.tree_rehearsal_control),
            "tree_rehearsal_defect": list(self.tree_rehearsal_defect),
            "reproducibility": self.reproducibility.as_mapping(),
            "tamper_exit": self.tamper_exit,
            "tamper_removed": self.tamper_removed,
            "tamper_detected": self.detected,
            "inputs_line": self.inputs_line,
            "crashed": self.crashed,
            "seconds": round(self.seconds, 1),
            "note": self.note,
            "ok": self.ok,
            "problems": list(self.problems),
        }


def observation_problems(record: Observation) -> tuple[str, ...]:
    """관찰 하나를 판정으로 바꾼다 — 빌드·소비·red 재현을 모두 요구한다."""

    problems: list[str] = []
    if record.note:
        problems.append(f"배포 산출물 검사를 돌리다 사고가 났다: {record.note} — 사고는 판정이 아니다")
    if record.build_exit != EXIT_OK:
        problems.append(f"빌드가 exit {record.build_exit} 다 — 배포판이 만들어지지 않았다")
    kinds = {item.kind for item in record.artifacts}
    if record.build_exit == EXIT_OK and kinds != set(ARTIFACT_KINDS):
        problems.append(f"산출물이 계약과 다르다: {sorted(kinds) or '없음'} ≠ {sorted(ARTIFACT_KINDS)}")
    if record.verify_exit != EXIT_OK:
        problems.append(
            f"저장소 밖 설치·소비 검증이 exit {record.verify_exit} 다 — 배포판을 소비자가 쓸 수 있는지 모른다"
        )
    elif len(record.passed) < len(ARTIFACT_KINDS):
        problems.append(
            f"산출물별 PASS 문장이 {len(record.passed)}개뿐이다({', '.join(record.passed) or '없음'}) — "
            "설치만 되고 써 보지 않았을 수 있다"
        )
    if not record.inputs_line:
        problems.append("검증 보고에 `ARTIFACT-INPUTS` 가 없다 — 무엇을 검증했는지 말하지 않는 보고는 판정이 아니다")
    if record.roundtrip_exit is None:
        problems.append("sdist 왕복을 돌리지 않았다 — sdist 설치 경로에서 파일이 빠지는 결함은 wheel 검증에 안 보인다")
    elif record.roundtrip_exit != EXIT_OK:
        problems.append(
            f"sdist 로 다시 빌드되지 않는다(exit {record.roundtrip_exit}) — sdist 를 받은 소비자는 그걸로 설치할 수 없다"
        )
    if record.missing:
        shown = ", ".join(record.missing[:3])
        more = f" 외 {len(record.missing) - 3}개" if len(record.missing) > 3 else ""
        problems.append(
            f"sdist→wheel 에서 **파일 {len(record.missing)}개가 빠졌다**: {shown}{more} — "
            "`MANIFEST`/package-data 에서 빠진 파일은 sdist 설치 경로에서만 드러난다"
        )
    if record.differing:
        shown = ", ".join(record.differing[:3])
        more = f" 외 {len(record.differing) - 3}개" if len(record.differing) > 3 else ""
        problems.append(
            f"sdist→wheel 에서 **파일 {len(record.differing)}개의 내용이 다르다**: {shown}{more} — "
            "이름이 같아도 바이트가 다르면 소비자가 받는 코드가 다르다(잘림·변형·빈 파일이 이 자리를 지나간다)"
        )
    if record.tree.missing:
        shown = ", ".join(record.tree.missing[:3])
        more = f" 외 {len(record.tree.missing) - 3}개" if len(record.tree.missing) > 3 else ""
        problems.append(
            f"배포판에 없는 **추적 파일 {len(record.tree.missing)}개**: {shown}{more} — "
            "`uv build` 는 wheel 을 sdist 에서 만들므로 sdist 가 잃은 파일은 소비자에게도 없다(로컬에서는 import 된다)"
        )
    if not record.tree_rehearsal_defect:
        problems.append(
            "추적 파일을 sdist 에서 뺀 실물 재현에서 이 눈이 아무것도 지목하지 못했다 — "
            "배포판에서 사라진 module 을 소비자보다 먼저 보지 못한다"
        )
    elif MINI_DROPPED not in record.tree_rehearsal_defect:
        problems.append(
            f"실물 재현이 심은 이름({MINI_DROPPED})이 아니라 {', '.join(record.tree_rehearsal_defect[:3])} 를 지목했다 — "
            "심은 것과 다른 것을 보면 그 눈이 무엇을 보는지 알 수 없다"
        )
    if record.tree_rehearsal_control:
        problems.append(
            f"대조군(정상 프로젝트)에서 빼짐을 지목했다: {', '.join(record.tree_rehearsal_control[:3])} — "
            "넓게 잡은 눈은 탐지력이 아니다(그러면 사람이 이 검사를 끄게 된다)"
        )
    if record.rehearsal_note:
        problems.append(
            f"왕복 재현 재료를 만들지 못했다: {record.rehearsal_note} — "
            "재료가 사라진 것을 모른 채 “탐지력 없음” 만 말하는 층은 사람이 믿을 수 없다"
        )
    if record.rehearsal_exit is None:
        problems.append(
            "왕복의 red 재현(sdist 에서 파일 빼기)을 돌리지 않았다 — 왕복이 무는지 확인하지 않은 실행은 통과가 아니다"
        )
    elif record.rehearsal_exit != EXIT_OK:
        problems.append(
            f"왕복 red 재현에서 재빌드가 실패했다(exit {record.rehearsal_exit}) — "
            "파일을 뺀 것이 빌드 자체를 깨뜨렸다면 그건 왕복의 판정력이 아니다"
        )
    elif TAMPER_TARGET not in record.rehearsal_missing:
        problems.append(
            f"sdist 에서 {TAMPER_TARGET} 를 빼도 왕복이 ‘차이 없음’ 이라고 말했다(비교 {record.rehearsal_compared}개) — "
            "이 층은 sdist 결함을 막지 못한다(이게 이 층의 red다)"
        )
    if REWRITE_TARGET not in record.rehearsal_differing:
        problems.append(
            f"sdist 안에서 {REWRITE_TARGET} 의 내용을 바꿔도 왕복이 ‘이름은 같은데 바이트가 다르다’ 고 말하지 못했다 — "
            "이름만 보는 왕복은 잘린 파일·변형된 파일을 통과시킨다"
        )
    problems.extend(content_problems(record.content))
    problems.extend(reproducibility_problems(record.reproducibility))
    if record.tamper_exit is None:
        problems.append("red 재현(빠진 배포판)을 돌리지 않았다 — 이 검증이 무는지 확인하지 않은 실행은 통과가 아니다")
    elif record.tamper_exit == EXIT_OK:
        problems.append(
            f"**빠진 배포판을 통과시켰다**({record.tamper_removed} 를 뺀 wheel) — 이 검증은 아무것도 막지 못한다"
        )
    return tuple(problems)


def content_problems(check: ContentCheck) -> tuple[str, ...]:
    """내용 대조를 판정으로 — 실린 파일의 **바이트** 가 빌드가 본 트리와 같아야 한다."""

    problems: list[str] = []
    if check.differ:
        shown = ", ".join(check.differ[:3])
        more = f" 외 {len(check.differ) - 3}개" if len(check.differ) > 3 else ""
        problems.append(
            f"배포판 파일 {len(check.differ)}개의 **내용**이 빌드가 본 트리와 다르다: {shown}{more} — "
            "이름이 같으므로 목록 대조로는 보이지 않는다(소비자가 받는 코드가 저장소와 다르다)"
        )
    if check.rehearsal_note:
        problems.append(f"내용 재현 재료를 만들지 못했다: {check.rehearsal_note} — 못 돌린 재현은 증거가 아니다")
    elif not check.rehearsal_defect:
        problems.append(
            "빌드가 내용을 바꿔 싣는 실물 프로젝트에서 이 눈이 아무것도 지목하지 못했다 — "
            "배포판 내용이 트리와 달라지는 것을 소비자보다 먼저 보지 못한다"
        )
    elif TRANSFORM_TARGET not in check.rehearsal_defect:
        problems.append(
            f"실물 재현이 심은 이름({TRANSFORM_TARGET})이 아니라 {', '.join(check.rehearsal_defect[:3])} 를 지목했다 — "
            "심은 것과 다른 것을 보면 그 눈이 무엇을 보는지 알 수 없다"
        )
    if check.rehearsal_control:
        problems.append(
            f"대조군(변환 없는 같은 프로젝트)에서 내용 차이를 지목했다: {', '.join(check.rehearsal_control[:3])} — "
            "넓게 잡은 눈은 탐지력이 아니다"
        )
    return tuple(problems)


def repro_sensitivity_bites(repro: Reproducibility) -> bool:
    """민감도 재현이 무는가(대조군 동일 + pin 이 바이트를 움직임) — 수치용."""

    return repro.sensitivity.control_equal and repro.sensitivity.pin_moves_bytes


def reproducibility_problems(repro: Reproducibility) -> tuple[str, ...]:
    """재현 계약을 판정으로 — 산출물마다 다르고, 예외는 좁고 **만료된다**."""

    problems: list[str] = []
    if repro.second_build_exit is None:
        problems.append(
            "재현 비교를 위한 두 번째 빌드를 돌리지 않았다 — “회차마다 같은 물건인가” 를 보지 않은 실행은 통과가 아니다"
        )
    elif repro.second_build_exit != EXIT_OK:
        problems.append(
            f"두 번째 빌드가 exit {repro.second_build_exit} 다 — 같은 트리가 두 번 만들어지지 않으면 재현을 논할 수 없다"
        )
    kinds = {item.kind for item in repro.identities}
    if kinds != set(ARTIFACT_KINDS):
        problems.append(
            f"재현 비교가 산출물 {sorted(kinds) or '없음'} 에서만 이뤄졌다 — 계약은 {sorted(ARTIFACT_KINDS)} 둘이다"
        )
    for item in repro.identities:
        if item.appeared:
            shown = ", ".join(item.appeared[:3])
            more = f" 외 {len(item.appeared) - 3}개" if len(item.appeared) > 3 else ""
            problems.append(
                f"{item.kind} 의 파일 목록이 두 빌드에서 다르다({len(item.appeared)}개: {shown}{more}) — "
                "흔들리는 목록은 재현이 아니다(무엇이 실릴지가 빌드 순간에 달렸다)"
            )
        if item.real_differs:
            shown = ", ".join(item.real_differs[:3])
            more = f" 외 {len(item.real_differs) - 3}개" if len(item.real_differs) > 3 else ""
            problems.append(
                f"{item.kind} 에서 **트리에 있는 파일 {len(item.real_differs)}개가 두 빌드에서 달라졌다**: {shown}{more} — "
                "빌드가 배포판에 회차마다 다른 상태를 싣는다(디렉터리·생성물이 아니라 실제 파일이다)"
            )
        if item.kind == "wheel" and not item.identical:
            why = (
                "항목 차이 없음 — 압축·헤더가 흔들렸다"
                if item.bytes_only
                else f"차이 {len(item.differs)}항목(실제 파일 {len(item.real_differs)})·목록 차이 {len(item.appeared)}"
            )
            problems.append(
                f"wheel 이 같은 pin 으로도 다른 바이트다({item.first[:12]} ≠ {item.second[:12]} · {why}) — "
                "소비자가 받는 물건이 빌드 순간에 따라 달라진다(재현 계약의 대상이다)"
            )
    if not repro.tracked_readable:
        problems.append(
            "git 추적 목록을 읽지 못했다 — 무엇이 실제 파일이고 무엇이 빌드 생성물인지 가릴 수 없으므로 이 예외 분류는 성립하지 않는다"
        )
    sdist = repro.sdist_identity
    if sdist is None:
        problems.append("sdist 재현 관찰이 없다 — 이 계약에서 가장 먼저 의심해야 할 산출물을 보지 않았다")
    elif sdist.identical:
        problems.append(
            "이제 sdist 도 재현된다 — 기록된 예외와 문서·근거 문장을 **지워라**: 낡은 예외는 다음 결함을 가리는 면죄부가 된다"
        )
    elif sdist.pinned_members:
        problems.append(
            f"sdist 항목 중 pin 시각을 가진 것이 {sdist.pinned_members}개다(관측은 0개) — 근거 문장이 낡았다: {SDIST_LIMITATION_WHY}"
        )
    sens = repro.sensitivity
    if any(code != EXIT_OK for code in sens.exits) or len(sens.exits) != 3:
        problems.append(
            f"민감도 재현의 빌드가 셋이 아니거나 실패했다(exit {list(sens.exits)}) — 못 돌린 재현은 증거가 아니다"
        )
    elif not sens.control_equal:
        problems.append(
            "같은 pin 으로 만든 미니 wheel 이 서로 다르다 — 이 환경의 wheel 경로가 비결정이므로 우리 wheel 의 ‘동일’ 도 믿을 수 없다"
        )
    elif not sens.pin_moves_bytes:
        problems.append(
            "다른 pin 으로 만든 미니 wheel 이 같은 바이트다 — 이 비교가 바이트를 보지 못하거나, 시각이 산출물에 전혀 실리지 않는다"
            "(둘 중 무엇인지 이 실행은 말하지 못한다) → 눈이 있다는 증거가 없다"
        )
    if not sens.sdist_differs:
        problems.append(
            "미니 setuptools 프로젝트의 sdist 는 두 빌드가 같았다 — 그러면 우리 sdist 의 차이는 backend 속성이 아니라 **우리 repo 탓**이다"
        )
    elif not sens.sdist_backend_only:
        problems.append(
            "미니 sdist 의 차이가 생성 항목 밖(실제 파일·목록)에 있다 — 그 차이를 backend 예외로 덮을 수 없다"
        )
    if not repro.ci_pinned:
        detail = (
            f"({repro.ci_note})" if repro.ci_note else f"(CI 에 적힌 값: {repro.ci_pin_value or '없음'} ≠ {REPRO_PIN})"
        )
        problems.append(
            f"배포 경로가 같은 pin 을 걸지 않는다 {detail} — 이 층이 검증한 물건과 배포되는 물건이 다르면 “재현된다” 는 이론이다"
        )
    return tuple(problems)


def coverage_floors(record: Observation | None = None) -> list[Floor]:
    """탐지력 하한 — 산출물 수와 실제로 써 본 산출물 수(값 + 근거)."""

    observed_artifacts = len(record.artifacts) if record is not None else _MIN_ARTIFACTS
    observed_passed = len(record.passed) if record is not None else _MIN_PASSED
    observed_compared = record.compared if record is not None else _MIN_COMPARED
    observed_tracked = len(record.tree.expected) if record is not None else _MIN_TRACKED
    observed_identities = len(record.reproducibility.identities) if record is not None else _MIN_IDENTITIES
    observed_content = record.content.compared if record is not None else _MIN_CONTENT
    return [
        Floor("배포 산출물", observed_artifacts, _MIN_ARTIFACTS, why=_WHY_ARTIFACTS),
        Floor("저장소 밖 PASS", observed_passed, _MIN_PASSED, why=_WHY_PASSED),
        Floor("비교한 파일", observed_compared, _MIN_COMPARED, why=_WHY_COMPARED),
        Floor("배포판에 실린 추적 파일", observed_tracked, _MIN_TRACKED, why=_WHY_TRACKED),
        Floor("재현 비교한 산출물", observed_identities, _MIN_IDENTITIES, why=_WHY_IDENTITIES),
        Floor("내용을 견준 패키지 파일", observed_content, _MIN_CONTENT, why=_WHY_CONTENT),
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_artifacts(dist_dir: Path) -> tuple[Artifact, ...]:
    """산출물 두 종류를 찾는다 — 이름·크기·sha256 을 함께 남긴다(무엇을 검증했는지)."""

    found: list[Artifact] = []
    for kind, pattern in (("wheel", "antigravity_k-*.whl"), ("sdist", "antigravity_k-*.tar.gz")):
        candidates = sorted(dist_dir.glob(pattern))
        if not candidates:
            continue
        path = candidates[-1]
        found.append(Artifact(kind=kind, name=path.name, bytes=path.stat().st_size, sha256=_sha256(path)))
    return tuple(found)


def build_env(pin: int = REPRO_PIN) -> dict[str, str]:
    """빌드 환경 — `SOURCE_DATE_EPOCH` 를 고정한다(이 층이 돌리는 **모든** 빌드에 같은 값).

    판정한 물건과 재현 계약이 같은 물건이어야 하기 때문이다. pin 을 안 건 빌드를 검증해 놓고 “재현된다” 고 말하면
    그 문장은 이론이다.
    """

    return {**os.environ, "SOURCE_DATE_EPOCH": str(pin)}


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    seconds_budget: float | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    """독립 process 로 돌리고 (종료 코드, 출력) 을 돌려준다."""

    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=seconds_budget,
        env=env,
    )
    return result.returncode, result.stdout + result.stderr


def build(dist_dir: Path, *, pin: int = REPRO_PIN) -> tuple[int, str]:
    """wheel + sdist 를 만든다(저장소 밖 자리에). `SOURCE_DATE_EPOCH` 를 고정해 넘긴다."""

    return run(["uv", "build", "--no-sources", "--out-dir", str(dist_dir)], env=build_env(pin))


def verify(dist_dir: Path) -> tuple[int, str]:
    """저장소 밖 신규 venv 설치·소비 검증 — 기존 검증기가 판정한다."""

    return run(["bash", str(VERIFIER), "--dist-dir", str(dist_dir), "--skip-build"])


def unpack_sdist(sdist: Path, work: Path) -> Path:
    """sdist 를 풀어 **그 안의 프로젝트 뿌리**를 돌려준다 — 소비자가 받는 바로 그 바이트에서 빌드하기 위해서다."""

    target = work / "sdist-tree"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with tarfile.open(sdist) as archive:
        archive.extractall(target, filter="data")
    roots = sorted(path.parent for path in target.rglob("pyproject.toml"))
    if not roots:
        raise ValueError(f"{sdist.name} 안에 pyproject.toml 이 없다 — 빌드할 트리를 찾지 못했다")
    return roots[0]


def wheel_names(path: Path) -> tuple[str, ...]:
    """wheel 안 파일 목록 — 중복을 제거하고 정렬해 두 목록을 견줄 수 있게 한다."""

    with zipfile.ZipFile(path) as archive:
        return tuple(sorted(set(archive.namelist())))


@dataclass(frozen=True, slots=True)
class WheelDiff:
    """같은 트리에서 나온 두 wheel 의 차이 — **이름과 내용 모두** 견준다.

    이름만 견주면 잘렸거나 내용이 바뀐 파일이 통과한다 — 왕복은 *무엇이 실렸는가* 뿐 아니라 *어떤 바이트로 실렸는가* 를 물어야 한다.
    """

    missing: tuple[str, ...]
    differing: tuple[str, ...]
    extra: tuple[str, ...]
    compared: int

    def as_mapping(self) -> dict[str, object]:
        return {
            "missing": list(self.missing),
            "differing": list(self.differing),
            "extra": list(self.extra),
            "compared": self.compared,
        }


def wheel_payloads(path: Path) -> dict[str, str]:
    """wheel 안 항목의 **내용** 지문 — 이름이 같고 내용이 다른 파일을 가리는 데 쓴다."""

    with zipfile.ZipFile(path) as archive:
        return {
            info.filename: hashlib.sha256(archive.read(info.filename)).hexdigest()
            for info in archive.infolist()
            if not info.filename.endswith("/")
        }


def compare_wheels(direct: Path, rebuilt: Path) -> WheelDiff:
    """트리에서 만든 wheel 과 sdist 에서 다시 만든 wheel 을 견준다 — 이름 **과 내용** 을 함께 본다."""

    left_names = set(wheel_names(direct))
    right_names = set(wheel_names(rebuilt))
    left = wheel_payloads(direct)
    right = wheel_payloads(rebuilt)
    shared = set(left) & set(right)
    return WheelDiff(
        missing=tuple(sorted(left_names - right_names)),
        differing=tuple(sorted(name for name in shared if left[name] != right[name])),
        extra=tuple(sorted(right_names - left_names)),
        compared=len(left_names | right_names),
    )


def roundtrip(sdist: Path, direct_wheel: Path, work: Path) -> tuple[int | None, WheelDiff]:
    """sdist 를 풀어 그 안에서 wheel 을 다시 만들고 견준다 — sdist 설치 경로의 결함을 드러낸다."""

    empty = WheelDiff((), (), (), 0)
    if not sdist.is_file() or not direct_wheel.is_file():
        return None, empty
    root = unpack_sdist(sdist, work)
    out = work / "roundtrip"
    out.mkdir(parents=True, exist_ok=True)
    exit_code, _ = run(["uv", "build", "--no-sources", "--wheel", "--out-dir", str(out)], cwd=root, env=build_env())
    rebuilt = sorted(out.glob("antigravity_k-*.whl"))
    if not rebuilt:
        return exit_code, empty
    return exit_code, compare_wheels(direct_wheel, rebuilt[-1])


def damage_sdist(source: Path, target: Path, *, remove: str, rewrite: str = "", appendix: str = "") -> Path:
    """sdist 사본을 **망가뜨린다** — 파일 하나를 빼고(빠진 것), 다른 하나의 내용을 바꾼다(내용이 다른 것).

    나머지 member 는 손대지 않고 그대로 옮긴다(경로 모양이 바뀌면 재현이 아니라 다른 물건이 된다). 한 번의 사본으로
    두 결함을 함께 심어 왕복 빌드를 두 번 돌리지 않는다.
    """

    with tarfile.open(source) as archive:
        members = archive.getmembers()

        def matches(name: str, needle: str) -> bool:
            return name == needle or name.endswith(f"/{needle}")

        if not any(matches(member.name, remove) for member in members):
            raise ValueError(f"{remove} 가 {source.name} 안에 없다 — 빼려는 파일이 그 압축본에 없다")
        if rewrite and not any(matches(member.name, rewrite) for member in members):
            raise ValueError(f"{rewrite} 가 {source.name} 안에 없다 — 내용을 바꿀 파일이 그 압축본에 없다")
        with tarfile.open(target, "w:gz") as out:
            for member in members:
                if matches(member.name, remove):
                    continue
                stream = archive.extractfile(member) if member.isfile() else None
                if stream is not None and rewrite and matches(member.name, rewrite):
                    body = stream.read() + appendix.encode("utf-8")
                    changed = tarfile.TarInfo(member.name)
                    changed.size = len(body)
                    changed.mtime = member.mtime
                    changed.mode, changed.uid, changed.gid = member.mode, member.uid, member.gid
                    changed.uname, changed.gname = member.uname, member.gname
                    out.addfile(changed, io.BytesIO(body))
                    continue
                out.addfile(member, stream)
    return target


def drop_member(source: Path, target: Path, *, remove: str) -> Path:
    """sdist 사본에서 파일 하나를 뺀다 — 내용 재현 없이 빠짐만 심는 자리(기존 호출자를 위해 남긴다)."""

    return damage_sdist(source, target, remove=remove)


@dataclass(frozen=True, slots=True)
class SdistRehearsal:
    """망가뜨린 sdist 로 돌린 왕복의 결과.

    재료가 없어 **못 돌렸으면** 그 까닭(`note`)을 남긴다 — 못 돌림을 “못 봤다” 로 합치면 재현 재료가 사라진 날
    이 층이 사라진 것을 모른 채 “탐지력이 없다” 고만 말한다.
    """

    exit_code: int | None
    missing: tuple[str, ...]
    differing: tuple[str, ...]
    compared: int
    note: str = ""


def rehearse_dropped_sdist(sdist: Path, direct_wheel: Path, work: Path) -> SdistRehearsal:
    """sdist 를 망가뜨려(파일 하나 빠짐 + 다른 하나 내용 바뀜) **같은 왕복**을 돌린다.

    관찰(왕복 exit 0 · 차이 0)만으로는 “왕복이 아무것도 보지 못해서 0” 인지 “보고 0” 인지 갈리지 않는다. 빠진 파일은
    **목록**에서, 내용을 바꾼 파일은 **바이트**에서 드러나야 한다 — 한쪽만 보는 눈은 다른 쪽 결함을 통과시킨다.
    """

    if not sdist.is_file() or not direct_wheel.is_file():
        return SdistRehearsal(None, (), (), 0, note="빌드 산출물이 없어 재현 재료를 만들지 못했다")
    corner = work / "roundtrip-rehearsal"
    corner.mkdir(parents=True, exist_ok=True)
    try:
        damage_sdist(
            sdist, corner / sdist.name, remove=TAMPER_TARGET, rewrite=REWRITE_TARGET, appendix=REWRITE_APPENDIX
        )
    except ValueError as exc:
        # 재료가 사라졌다(파일명 변경·패키징 제외) — 사고가 아니라 **못 돌림** 이므로 판정으로 남긴다.
        return SdistRehearsal(None, (), (), 0, note=str(exc))
    exit_code, diff = roundtrip(corner / sdist.name, direct_wheel, corner)
    return SdistRehearsal(exit_code, diff.missing, diff.differing, diff.compared)


def _wheel_name(path: Path, package_dir: Path, package_name: str) -> str:
    """저장소 경로를 wheel 안 이름으로 옮긴다(`src/antigravity_k/a/b.py` → `antigravity_k/a/b.py`)."""

    return f"{package_name}/{path.relative_to(package_dir).as_posix()}"


def tree_coverage(wheel: Path, *, package_dir: Path, package_name: str, repo: Path) -> TreeCoverage:
    """배포 wheel 과 **git 추적 트리** 를 견준다 — 추적 파일이 배포판에 없으면 그게 결함이다.

    `--others` 로 세지 않는 이유: 로컬의 미추적 파일은 배포판에 없는 것이 **정상**이고(그게 배포판의 정의다),
    그것을 실패로 만들면 이 층은 늘 빨개져 무시된다. 대신 그 목록을 **보고**해 "로컬에서는 되는데 설치하면 없다" 를
    미리 말한다.
    """

    if not wheel.is_file() or not package_dir.is_dir():
        return TreeCoverage((), (), (), ())
    members = set(wheel_names(wheel))
    listing = subprocess.run(
        ["git", "ls-files", "--", str(package_dir.relative_to(repo))],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if listing.returncode != EXIT_OK:
        # 0개를 보고 “빠짐 없음” 으로 통과하지 않는다 — 하한이 문다.
        return TreeCoverage((), (), (), ())
    tracked = tuple(
        sorted(
            _wheel_name(repo / line, package_dir, package_name) for line in listing.stdout.splitlines() if line.strip()
        )
    )
    tracked_set = set(tracked)
    missing = tuple(name for name in tracked if name not in members)
    generated = tuple(
        sorted(name for name in members if name.startswith(f"{package_name}/") and name not in tracked_set)
    )
    local_only: list[str] = []
    for path in sorted(package_dir.rglob("*")):
        relative = path.relative_to(package_dir)
        if not path.is_file() or _SKIP_PARTS & set(relative.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        name = _wheel_name(path, package_dir, package_name)
        if name not in tracked_set and name not in members:
            local_only.append(name)
    return TreeCoverage(expected=tracked, missing=missing, generated=generated, local_only=tuple(local_only))


def _write_mini_project(project: Path, *, drop_from_sdist: bool) -> None:
    """재현용 작은 추적 프로젝트 — 파일 하나를 sdist 에서 빼면 그 파일이 배포판에서도 사라진다."""

    package = project / MINI_PACKAGE
    package.mkdir(parents=True, exist_ok=True)
    exclude = f'\n[tool.hatch.build.targets.sdist]\nexclude = ["{MINI_DROPPED}"]\n' if drop_from_sdist else ""
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
        '\n[project]\nname = "minipkg"\nversion = "0.1.0"\n'
        f'\n[tool.hatch.build.targets.wheel]\npackages = ["{MINI_PACKAGE}"]\n{exclude}',
        encoding="utf-8",
    )
    (package / "__init__.py").write_text("value = 1\n", encoding="utf-8")
    (package / "kept.py").write_text("kept = 1\n", encoding="utf-8")
    (package / "dropped.py").write_text("dropped = 1\n", encoding="utf-8")
    identity = ["-c", "user.email=release-contract@localhost", "-c", "user.name=release contract"]
    run(["git", "init", "-q", "."], cwd=project)
    run(["git", "add", "-A"], cwd=project)
    run(["git", *identity, "commit", "-qm", "mini"], cwd=project)


def rehearse_tree_loss(work: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """**실물 빌드** 로 이 눈이 무는지 본다 — 같은 작은 프로젝트 둘(정상 · sdist 에서 파일을 뺀 것).

    돌려주는 것: `(대조군이 지목한 것, 심은 프로젝트가 지목한 것)`. 심은 이름만 지목되고 대조군이 비어야 통과다 —
    합성 기록이 아니라 실제 `git`·`uv build` 로 돌리므로 “이 눈이 진짜 파일에서 작동하는가” 가 이 재현의 대상이다.
    """

    results: list[tuple[str, ...]] = []
    for label, drop in (("control", False), ("defect", True)):
        project = work / f"tree-rehearsal-{label}"
        project.mkdir(parents=True, exist_ok=True)
        _write_mini_project(project, drop_from_sdist=drop)
        dist = project / "dist"
        run(["uv", "build", "--no-sources", "--out-dir", str(dist)], cwd=project, env=build_env())
        wheels = sorted(dist.glob("*.whl"))
        if not wheels:
            results.append(())
            continue
        coverage = tree_coverage(
            wheels[-1], package_dir=project / MINI_PACKAGE, package_name=MINI_PACKAGE, repo=project
        )
        results.append(coverage.missing)
    return results[0], results[1]


def _zip_stamp(date_time: tuple[int, int, int, int, int, int]) -> int:
    """zip 항목의 시각을 초로 — pin 시각을 쓰는 항목을 세기 위해서다."""

    return int(dt.datetime(*date_time, tzinfo=dt.timezone.utc).timestamp())


def _member_rows(kind: str, path: Path) -> dict[str, tuple[object, ...]]:
    """산출물 항목별 행 — 이름 → (메타·내용 지문, 디렉터리 여부). 두 빌드의 차이를 **이름으로** 말하기 위해서다."""

    if kind == "wheel":
        with zipfile.ZipFile(path) as archive:
            return {
                info.filename: (
                    info.date_time,
                    info.CRC,
                    info.file_size,
                    hashlib.sha256(archive.read(info.filename)).hexdigest(),
                    False,
                )
                for info in archive.infolist()
            }
    with tarfile.open(path) as archive:
        rows: dict[str, tuple[object, ...]] = {}
        for member in archive.getmembers():
            stream = archive.extractfile(member) if member.isfile() else None
            digest = hashlib.sha256(stream.read()).hexdigest() if stream is not None else ""
            rows[member.name] = (
                member.mtime,
                member.mode,
                member.uid,
                member.gid,
                member.size,
                digest,
                member.isdir(),
            )
        return rows


def _member_name(member: str, *, kind: str) -> str:
    """아카이브 항목 이름을 **트리 경로** 로 옮긴다 — 실제 파일인지 가리는 데 쓴다(`src/…` 는 호출자가 붙인다)."""

    if kind == "wheel":
        return member.split("/", 1)[1] if "/" in member else ""
    return _ARCHIVE_ROOT.sub("", member)


def _pinned_members(kind: str, path: Path) -> int:
    """항목 중 재현 pin 시각을 가진 것 수 — 이 산출물이 pin 을 보는가(0 이면 안 본다).

    근거 문장과 관측을 견주는 수다. 근거(`SDIST_LIMITATION_WHY`)는 “sdist 는 pin 을 읽지 않는다” 고 말하는데,
    그 수가 0 이 아니게 되면 그 문장은 낡은 것이다.
    """

    if kind == "wheel":
        with zipfile.ZipFile(path) as archive:
            return sum(1 for info in archive.infolist() if _zip_stamp(info.date_time) == REPRO_PIN)
    with tarfile.open(path) as archive:
        return sum(1 for member in archive.getmembers() if int(member.mtime) == REPRO_PIN)


def compare_artifacts(kind: str, first: Path, second: Path, *, is_tree_file: Callable[[str], bool]) -> Identity:
    """같은 pin 으로 만든 두 산출물을 견준다 — 같으면 그 사실, 다르면 **무엇이** 다른지(이름으로).

    허용되는 차이는 좁다: 디렉터리와 backend 생성물(**커밋되지 않은** 이름)의 **메타·내용** 차이뿐이다.
    커밋된 파일의 차이와 **목록의 차이**(한쪽에만 있는 항목)는 결함이다 — 흔들리는 목록은 재현이 아니다.
    """

    rows_first = _member_rows(kind, first)
    rows_second = _member_rows(kind, second)
    appeared = tuple(sorted(set(rows_first) ^ set(rows_second)))
    differs = tuple(
        sorted(name for name in set(rows_first) & set(rows_second) if rows_first[name] != rows_second[name])
    )
    allowed: list[str] = []
    real: list[str] = []
    for name in differs:
        directory = bool(rows_first[name][-1])
        if directory or not is_tree_file(_member_name(name, kind=kind)):
            allowed.append(name)
        else:
            real.append(name)
    return Identity(
        kind=kind,
        first=_sha256(first),
        second=_sha256(second),
        members=len(rows_first),
        pinned_members=_pinned_members(kind, first),
        appeared=appeared,
        differs=differs,
        allowed_differs=tuple(allowed),
        real_differs=tuple(real),
    )


def tracked_paths(repo: Path) -> frozenset[str] | None:
    """git 이 아는 파일들 — ‘실제 파일’ 의 기준.

    파일 시스템으로 판정하면 안 된다: 빌드 자신이 트리에 생성물을 **남기기** 때문이다(`src/antigravity_k.egg-info/` 는
    `.gitignore` 대상이고 배포판에도 실린다). 그걸 실제 파일로 오인하면 이 층은 자기 빌드가 남긴 찌꺼기마다 빨개진다.
    """

    listing = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=False)
    if listing.returncode != EXIT_OK:
        return None
    return frozenset(line for line in listing.stdout.splitlines() if line.strip())


def _tree_oracle(kind: str, *, tracked: frozenset[str] | None, package_src: str = PACKAGE_SRC) -> Callable[[str], bool]:
    """아카이브 항목 이름 → 그 이름이 **커밋된 실제 파일** 인가(디렉터리·생성물과 가르는 자).

    추적 목록을 못 읽으면 **엄격한 쪽**(전부 실제 파일)으로 판정하고, 그 사실은 따로 문제로 남긴다 —
    못 읽은 목록을 “생성물이 많네” 로 삼키면 실제 결함이 조용히 예외에 섮인다.
    """

    if tracked is None:
        return lambda name: bool(name)
    prefix = "" if kind == "sdist" else f"{package_src}/"
    return lambda name: bool(name) and f"{prefix}{name}" in tracked


def _one_artifact(dist_dir: Path, kind: str) -> Path | None:
    """산출물 하나를 고른다(`find_artifacts` 와 같은 규칙 — 마지막 것이 이번 빌드다)."""

    pattern = "antigravity_k-*.whl" if kind == "wheel" else "antigravity_k-*.tar.gz"
    candidates = sorted(dist_dir.glob(pattern))
    return candidates[-1] if candidates else None


def _same_bytes(left: Path, right: Path) -> bool:
    """두 파일이 같은 바이트인가 — 둘 중 하나라도 없으면 같다고 말하지 않는다."""

    return left.is_file() and right.is_file() and _sha256(left) == _sha256(right)


def _write_repro_project(project: Path) -> None:
    """재현 민감도용 작은 프로젝트 — **우리 배포 경로와 같은 backend(setuptools)** 여야 sdist 차이가 누구 탓인지 갈린다."""

    package = project / REPRO_MINI_PACKAGE
    package.mkdir(parents=True, exist_ok=True)
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=77.0.0", "wheel"]\nbuild-backend = "setuptools.build_meta"\n'
        '\n[project]\nname = "repro-mini"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (package / "__init__.py").write_text("value = 1\n", encoding="utf-8")
    (package / "kept.py").write_text("kept = 1\n", encoding="utf-8")
    # git 저장소로 만든다 — ‘실제 파일’ 의 기준이 우리 배포 경로와 **같아야** 미니 관찰을 우리 sdist 에 쓸 수 있다.
    identity = ["-c", "user.email=release-contract@localhost", "-c", "user.name=release contract"]
    run(["git", "init", "-q", "."], cwd=project)
    run(["git", "add", "-A"], cwd=project)
    run(["git", *identity, "commit", "-qm", "repro mini"], cwd=project)


def repro_sensitivity(work: Path) -> Sensitivity:
    """작은 실물 프로젝트를 **세 번** 빌드해 이 비교가 눈이 있는지 본다(합성 기록이 아니다).

    · 같은 pin 두 번 → wheel 이 같아야 한다. 다르면 이 환경의 wheel 경로가 비결정이고, 우리 wheel 의 “동일” 도 못 믿는다.
    · 다른 pin 한 번 → wheel 이 달라야 한다. 그래서 “같음” 이 공허하지 않다(비교가 이 바이트를 본다는 증거).
    · 미니 sdist 도 달라지고 그 차이가 생성 항목뿐인가 → 우리 sdist 예외의 **두 번째 사례**(backend 속성).
    """

    project = work / REPRO_MINI
    project.mkdir(parents=True, exist_ok=True)
    _write_repro_project(project)
    # 산출물 자리는 프로젝트 **밖** 이다 — 안에 두면 setuptools 가 그 디렉터리를 package 로 발견해 빌드가 죽는다.
    out = work / "repro-mini-dist"
    wheels: list[Path] = []
    sdists: list[Path] = []
    exits: list[int] = []
    for label, pin in (("control", REPRO_PIN), ("same", REPRO_PIN), ("other", REPRO_MINI_ALT)):
        target = out / label
        target.mkdir(parents=True, exist_ok=True)
        exit_code, _ = run(["uv", "build", "--no-sources", "--out-dir", str(target)], cwd=project, env=build_env(pin))
        exits.append(exit_code)
        wheels.append(_last(target, "*.whl"))
        sdists.append(_last(target, "*.tar.gz"))
    control_equal = _same_bytes(wheels[0], wheels[1])
    pin_moves_bytes = wheels[0].is_file() and wheels[2].is_file() and not _same_bytes(wheels[0], wheels[2])
    differs: tuple[str, ...] = ()
    backend_only = False
    if sdists[0].is_file() and sdists[1].is_file():
        identity = compare_artifacts(
            "sdist",
            sdists[0],
            sdists[1],
            is_tree_file=_tree_oracle("sdist", tracked=tracked_paths(project)),
        )
        differs = identity.differs + identity.appeared
        backend_only = not identity.real_differs and not identity.appeared and bool(identity.differs)
    return Sensitivity(
        control_equal=control_equal,
        pin_moves_bytes=pin_moves_bytes,
        sdist_differs=differs,
        sdist_backend_only=backend_only,
        exits=tuple(exits),
    )


def _last(directory: Path, pattern: str) -> Path:
    """디렉터리에서 마지막 산출물 — 없으면 존재하지 않는 자리(호출자가 `is_file()` 로 가린다)."""

    candidates = sorted(directory.glob(pattern))
    return candidates[-1] if candidates else directory / f"__missing__{pattern}"


def ci_pin_check() -> tuple[bool, str, str]:
    """배포 경로(CI build job)가 **같은 pin** 을 거는가 — (걸었나, 값, 못 본 이유).

    이 층이 “재현된다” 고 말해도 배포하는 쪽이 pin 을 안 걸면 그 보장은 이론이다. job 이 사라지거나 이름이 바뀌면
    조용히 통과하지 않고 **못 봤다** 고 말한다.
    """

    try:
        text = CI_WORKFLOW.read_text(encoding="utf-8")
    except OSError as exc:
        return False, "", f"`{CI_WORKFLOW.name}` 을 읽지 못했다: {exc}"
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.rstrip() == f"  {CI_BUILD_JOB}:"), None)
    if start is None:
        return False, "", f"`{CI_WORKFLOW.name}` 에 `{CI_BUILD_JOB}` job 이 없다"
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith("   "):
            break
        body.append(line)
    block = "\n".join(body)
    if CI_BUILD_TOKEN not in block:
        return False, "", f"`{CI_BUILD_JOB}` job 안에 `{CI_BUILD_TOKEN}` 단계가 없다(배포 경로가 바뀌었나)"
    found = re.search(r"SOURCE_DATE_EPOCH:\s*['\"]?(\d+)", block)
    if found is None:
        return False, "", f"`{CI_BUILD_JOB}` job 이 `SOURCE_DATE_EPOCH` 를 걸지 않는다"
    value = found.group(1)
    return value == str(REPRO_PIN), value, ""


def reproducibility(dist_dir: Path, *, work: Path) -> Reproducibility:
    """같은 pin 으로 **한 번 더** 만들어 견준다 — 소비자가 받는 물건이 회차마다 같은가.

    판정(검증·왕복·추적 대조)은 첫 빌드 하나를 가리키고, 이 함수만 두 번째 빌드를 만든다.
    """

    started = time.monotonic()
    second = work / "second-build"
    second.mkdir(parents=True, exist_ok=True)
    exit_code, _ = build(second, pin=REPRO_PIN)
    tracked = tracked_paths(REPO_ROOT)
    identities: list[Identity] = []
    for kind in ARTIFACT_KINDS:
        left = _one_artifact(dist_dir, kind)
        right = _one_artifact(second, kind)
        if left is None or right is None:
            continue
        identities.append(compare_artifacts(kind, left, right, is_tree_file=_tree_oracle(kind, tracked=tracked)))
    pinned, value, note = ci_pin_check()
    return Reproducibility(
        identities=tuple(identities),
        second_build_exit=exit_code,
        sensitivity=repro_sensitivity(work),
        ci_pinned=pinned,
        ci_pin_value=value,
        seconds=time.monotonic() - started,
        ci_note=note,
        tracked_readable=tracked is not None,
    )


@dataclass(frozen=True, slots=True)
class ContentCheck:
    """배포판에 실린 **바이트** 가 빌드가 본 트리와 같은가 — 이름이 같아도 내용이 다를 수 있다.

    이 확인이 없으면 잘렸거나 내용이 바뀐 파일이 통과한다(“실렸다” 와 “제대로 실렸다” 는 다르다).
    """

    compared: int
    differ: tuple[str, ...]
    absent: tuple[str, ...]
    rehearsal_control: tuple[str, ...]
    rehearsal_defect: tuple[str, ...]
    rehearsal_note: str = ""

    def as_mapping(self) -> dict[str, object]:
        return {
            "compared": self.compared,
            "differ": list(self.differ),
            "absent": list(self.absent),
            "rehearsal_control": list(self.rehearsal_control),
            "rehearsal_defect": list(self.rehearsal_defect),
            "rehearsal_note": self.rehearsal_note,
        }


def content_check(wheel: Path, *, tree_root: Path | None = None, package_name: str = PACKAGE_NAME) -> ContentCheck:
    """배포 wheel 의 패키지 파일 내용을 **디스크 트리** 와 견준다 — 빌드가 본 바이트가 그대로 실렸는가.

    디스크와 견주는 까닭: 빌드가 본 것도 이 트리다(다른 레인의 미커밋 편집까지 포함해). 커밋된 내용과 견주면 그 편집이
    오탐이 되고, 이 층은 늘 빨개져 무시된다. 배포판에만 있는 이름(생성물·`dist-info`)은 **견줄 수 없다** 로 보고한다.
    """

    root = (tree_root or (REPO_ROOT / PACKAGE_SRC)).resolve()
    if not wheel.is_file() or not root.is_dir():
        return ContentCheck(0, (), (), (), ())
    prefix = f"{package_name}/"
    compared = 0
    differ: list[str] = []
    absent: list[str] = []
    for name, digest in sorted(wheel_payloads(wheel).items()):
        path = root / name[len(prefix) :] if name.startswith(prefix) else None
        if path is None or not path.is_file():
            absent.append(name)
            continue
        compared += 1
        if _sha256(path) != digest:
            differ.append(name)
    return ContentCheck(compared, tuple(differ), tuple(absent), (), ())


def _write_transform_project(project: Path, *, transform: bool) -> None:
    """빌드가 내용을 바꿔 싣는 미니 프로젝트 — `setup.py` 의 `build_py` 가 파일 하나를 다시 쓴다."""

    package = project / "mini"
    package.mkdir(parents=True, exist_ok=True)
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=77.0.0", "wheel"]\nbuild-backend = "setuptools.build_meta"\n'
        '\n[project]\nname = "transform-mini"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (package / "__init__.py").write_text("value = 1\n", encoding="utf-8")
    (package / "kept.py").write_text("kept = 1\n", encoding="utf-8")
    if transform:
        (project / "setup.py").write_text(
            "from pathlib import Path\n\n"
            "from setuptools import setup\n"
            "from setuptools.command.build_py import build_py as _build_py\n\n\n"
            "class build_py(_build_py):\n"
            '    """빌드가 내용을 바꿔 싣는 경우 — 흔한 패턴이다(버전 주입·주석 제거·라이선스 헤더)."""\n\n'
            "    def run(self) -> None:\n"
            "        super().run()\n"
            f"        (Path(self.build_lib) / '{TRANSFORM_TARGET}').write_text({TRANSFORM_BODY!r})\n\n\n"
            'setup(cmdclass={"build_py": build_py})\n',
            encoding="utf-8",
        )


def rehearse_content_transform(work: Path) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """**실물 빌드** 로 이 눈이 무는지 본다 — 빌드가 내용을 바꿔 싣는 프로젝트와 그 대조군(변환만 뺀 것).

    그런 빌드에서 “배포판 내용 ≠ 트리 내용” 은 일어나지만 **우리 계약은 그것을 허용하지 않는다**(소비자가 받는 코드가
    저장소와 달라진다). 그래서 이 눈이 그 파일을 이름으로 지목해야 하고, 대조군은 조용해야 한다.
    """

    results: list[tuple[str, ...]] = []
    note = ""
    for label, transform in (("control", False), ("defect", True)):
        project = work / f"{TRANSFORM_MINI}-{label}"
        project.mkdir(parents=True, exist_ok=True)
        _write_transform_project(project, transform=transform)
        # 산출물 자리는 프로젝트 **밖** 이다 — 안에 두면 setuptools 가 그 디렉터리를 package 로 발견해 빌드가 죽는다.
        out = work / f"{TRANSFORM_MINI}-{label}-dist"
        out.mkdir(parents=True, exist_ok=True)
        exit_code, output = run(
            ["uv", "build", "--no-sources", "--wheel", "--out-dir", str(out)], cwd=project, env=build_env()
        )
        wheels = sorted(out.glob("*.whl"))
        if exit_code != EXIT_OK or not wheels:
            note = f"{label} 프로젝트의 wheel 이 만들어지지 않았다(exit {exit_code})"
            results.append(())
            continue
        results.append(content_check(wheels[-1], tree_root=project / "mini", package_name="mini").differ)
    return results[0], results[1], note


def passed_kinds(output: str) -> tuple[str, ...]:
    """`ARTIFACT-RESULT` 줄에서 **PASS 한 산출물 종류**를 읽는다(산문이 아니라 구조를 읽는다)."""

    found: list[str] = []
    for line in output.splitlines():
        if not line.startswith("ARTIFACT-RESULT:"):
            continue
        try:
            payload = json.loads(line.split(":", 1)[1].strip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("status") == "PASS":
            found.append(str(payload.get("kind")))
    return tuple(found)


def tamper_wheel(source: Path, target: Path, *, remove: str) -> Path:
    """wheel 사본에서 module 하나를 빼고 `RECORD` 를 다시 쓴다 — **유효하지만 불완전한** 배포판을 만든다.

    RECORD 를 그대로 두면 그 wheel 은 형식적으로 깨진 것이라, “설치가 거부된 것” 과 “설치됐지만 쓸 수 없는 것” 을
    구분할 수 없다. 이 도구가 재현하려는 것은 뒤엣것이다(빠진 파일은 설치를 막지 않는다).
    """

    with zipfile.ZipFile(source) as handle:
        items = [(info, handle.read(info.filename)) for info in handle.infolist()]
    names = {info.filename for info, _ in items}
    if remove not in names:
        raise ValueError(f"{remove} 가 {source.name} 안에 없다 — 재현할 대상을 정할 수 없다")
    record_name = next((name for name in sorted(names) if name.endswith(".dist-info/RECORD")), "")
    if not record_name:
        raise ValueError(f"{source.name} 에 RECORD 가 없다")
    kept = [(info, data) for info, data in items if info.filename != remove]
    lines: list[str] = []
    for info, data in kept:
        if info.filename == record_name:
            continue
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        lines.append(f"{info.filename},sha256={digest},{len(data)}")
    lines.append(f"{record_name},,")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for info, data in kept:
            payload = ("\n".join(lines) + "\n").encode("utf-8") if info.filename == record_name else data
            out.writestr(info, payload)
    return target


def rehearse_missing_module(artifacts: tuple[Artifact, ...], dist_dir: Path, work: Path) -> tuple[int | None, str]:
    """‘빠진 배포판’ 을 만들어 같은 검증기에 건다 — 검증기가 막지 못하면 이 층은 무력하다."""

    wheel = next((dist_dir / item.name for item in artifacts if item.kind == "wheel"), None)
    sdist = next((dist_dir / item.name for item in artifacts if item.kind == "sdist"), None)
    if wheel is None or sdist is None or not wheel.is_file() or not sdist.is_file():
        return None, TAMPER_TARGET
    tampered_dir = work / "tampered"
    tampered_dir.mkdir(parents=True, exist_ok=True)
    tamper_wheel(wheel, tampered_dir / wheel.name, remove=TAMPER_TARGET)
    shutil.copy2(sdist, tampered_dir / sdist.name)
    # 검증기는 두 종류가 다 있어야 시작하므로, **깨진 wheel + 정상 sdist** 를 함께 넘긴다.
    tamper_exit, _ = verify(tampered_dir)
    return tamper_exit, TAMPER_TARGET


def measure(*, dist_dir: Path | None = None, work: Path | None = None, keep: bool = False) -> Observation:
    """빌드 → 저장소 밖 검증 → red 재현 → 재현 빌드 비교를 한 번의 실행으로 한다.

    판정(검증·왕복·추적 대조·빨간 재현)은 첫 빌드 하나를 가리키고, 재현 계약만 두 번째 빌드를 만든다.
    """

    started = time.monotonic()
    temporary = Path(tempfile.mkdtemp(prefix="agk-release-")) if work is None else Path(work)
    target = Path(dist_dir) if dist_dir is not None else temporary / "dist"
    target.mkdir(parents=True, exist_ok=True)
    try:
        build_exit, build_out = build(target)
        artifacts = find_artifacts(target)
        verify_exit, verify_out = verify(target) if artifacts else (None, "")
        wheel = next((target / item.name for item in artifacts if item.kind == "wheel"), None)
        sdist = next((target / item.name for item in artifacts if item.kind == "sdist"), None)
        if wheel is not None and sdist is not None:
            roundtrip_exit, diff = roundtrip(sdist, wheel, temporary)
            rehearsal = rehearse_dropped_sdist(sdist, wheel, temporary)
        else:
            roundtrip_exit, diff = None, WheelDiff((), (), (), 0)
            rehearsal = SdistRehearsal(None, (), (), 0, note="빌드 산출물이 없어 재현 재료를 만들지 못했다")
        tree = (
            tree_coverage(wheel, package_dir=REPO_ROOT / PACKAGE_SRC, package_name=PACKAGE_NAME, repo=REPO_ROOT)
            if wheel is not None
            else TreeCoverage((), (), (), ())
        )
        tree_control, tree_defect = rehearse_tree_loss(temporary)
        shipped = content_check(wheel) if wheel is not None else ContentCheck(0, (), (), (), ())
        transform_control, transform_defect, transform_note = rehearse_content_transform(temporary)
        content = ContentCheck(
            compared=shipped.compared,
            differ=shipped.differ,
            absent=shipped.absent,
            rehearsal_control=transform_control,
            rehearsal_defect=transform_defect,
            rehearsal_note=transform_note,
        )
        repro = reproducibility(target, work=temporary)
        tamper_exit, removed = rehearse_missing_module(artifacts, target, temporary)
        crashed = CRASH_MARKER in (build_out + verify_out)
        return Observation(
            build_exit=build_exit,
            artifacts=artifacts,
            verify_exit=verify_exit,
            passed=passed_kinds(verify_out),
            roundtrip_exit=roundtrip_exit,
            compared=diff.compared,
            missing=diff.missing,
            differing=diff.differing,
            extra=diff.extra,
            rehearsal_exit=rehearsal.exit_code,
            rehearsal_missing=rehearsal.missing,
            rehearsal_differing=rehearsal.differing,
            rehearsal_compared=rehearsal.compared,
            rehearsal_note=rehearsal.note,
            tree=tree,
            content=content,
            tree_rehearsal_control=tree_control,
            tree_rehearsal_defect=tree_defect,
            reproducibility=repro,
            tamper_exit=tamper_exit,
            tamper_removed=removed,
            inputs_line="ARTIFACT-INPUTS" in verify_out,
            crashed=crashed,
            seconds=time.monotonic() - started,
            note="하위 process 가 traceback 으로 죽었다" if crashed else "",
        )
    finally:
        if dist_dir is None and not keep:
            shutil.rmtree(temporary, ignore_errors=True)


def self_probe(*, probe_ok: bool = True) -> Probe:
    """판정 규칙을 합성 관찰로 다시 물어본다 — 빌드는 하지 않는다."""

    cases = Cases()

    good_wheel = Identity(
        kind="wheel",
        first="a" * 16,
        second="a" * 16,
        members=664,
        pinned_members=664,
        appeared=(),
        differs=(),
        allowed_differs=(),
        real_differs=(),
    )
    generated = "antigravity_k-0.1.0/PKG-INFO"
    real_file = "antigravity_k-0.1.0/src/antigravity_k/__init__.py"

    def sdist_of(**overrides: object) -> Identity:
        payload: dict[str, object] = {
            "kind": "sdist",
            "first": "b" * 16,
            "second": "c" * 16,
            "members": 1205,
            "pinned_members": 0,
            "appeared": (),
            "differs": (generated,),
            "allowed_differs": (generated,),
            "real_differs": (),
        }
        payload.update(overrides)
        return Identity(**payload)  # type: ignore[arg-type]

    good_sensitivity = Sensitivity(
        control_equal=True,
        pin_moves_bytes=True,
        sdist_differs=("repro-mini-0.1.0/PKG-INFO",),
        sdist_backend_only=True,
        exits=(EXIT_OK, EXIT_OK, EXIT_OK),
    )

    def repro_of(**overrides: object) -> Reproducibility:
        payload: dict[str, object] = {
            "identities": (good_wheel, sdist_of()),
            "second_build_exit": EXIT_OK,
            "sensitivity": good_sensitivity,
            "ci_pinned": True,
            "ci_pin_value": str(REPRO_PIN),
            "seconds": 12.0,
            "ci_note": "",
            "tracked_readable": True,
        }
        payload.update(overrides)
        return Reproducibility(**payload)  # type: ignore[arg-type]

    def record(**overrides: object) -> Observation:
        base: dict[str, object] = {
            "build_exit": EXIT_OK,
            "artifacts": (
                Artifact("wheel", "antigravity_k-0.1.0-py3-none-any.whl", 100, "a"),
                Artifact("sdist", "antigravity_k-0.1.0.tar.gz", 120, "b"),
            ),
            "verify_exit": EXIT_OK,
            "passed": ARTIFACT_KINDS,
            "roundtrip_exit": EXIT_OK,
            "compared": 664,
            "missing": (),
            "differing": (),
            "extra": (),
            "rehearsal_exit": EXIT_OK,
            "rehearsal_missing": (TAMPER_TARGET,),
            "rehearsal_differing": (REWRITE_TARGET,),
            "rehearsal_compared": 664,
            "content": ContentCheck(658, (), ("antigravity_k.dist-info/METADATA",), (), (TRANSFORM_TARGET,)),
            "tree": TreeCoverage(
                expected=tuple(f"antigravity_k/f{i}.py" for i in range(656)),
                missing=(),
                generated=("antigravity_k/vendor/ssak_search/bin/ssak-mcp",),
                local_only=("antigravity_k/local_scratch.py",),
            ),
            "tree_rehearsal_control": (),
            "tree_rehearsal_defect": (MINI_DROPPED,),
            "reproducibility": repro_of(),
            "tamper_exit": EXIT_FAIL,
            "tamper_removed": TAMPER_TARGET,
            "inputs_line": True,
            "crashed": False,
            "seconds": 24.0,
            "note": "",
        }
        payload: dict[str, object] = {**base, **overrides}
        return Observation(
            build_exit=payload["build_exit"],  # type: ignore[arg-type]
            artifacts=payload["artifacts"],  # type: ignore[arg-type]
            verify_exit=payload["verify_exit"],  # type: ignore[arg-type]
            passed=payload["passed"],  # type: ignore[arg-type]
            roundtrip_exit=payload["roundtrip_exit"],  # type: ignore[arg-type]
            compared=int(payload["compared"]),  # type: ignore[call-overload]
            missing=payload["missing"],  # type: ignore[arg-type]
            differing=payload["differing"],  # type: ignore[arg-type]
            extra=payload["extra"],  # type: ignore[arg-type]
            rehearsal_exit=payload["rehearsal_exit"],  # type: ignore[arg-type]
            rehearsal_missing=payload["rehearsal_missing"],  # type: ignore[arg-type]
            rehearsal_differing=payload["rehearsal_differing"],  # type: ignore[arg-type]
            rehearsal_compared=int(payload["rehearsal_compared"]),  # type: ignore[call-overload]
            tree=payload["tree"],  # type: ignore[arg-type]
            content=payload["content"],  # type: ignore[arg-type]
            tree_rehearsal_control=payload["tree_rehearsal_control"],  # type: ignore[arg-type]
            tree_rehearsal_defect=payload["tree_rehearsal_defect"],  # type: ignore[arg-type]
            reproducibility=payload["reproducibility"],  # type: ignore[arg-type]
            tamper_exit=payload["tamper_exit"],  # type: ignore[arg-type]
            tamper_removed=str(payload["tamper_removed"]),
            inputs_line=bool(payload["inputs_line"]),
            crashed=bool(payload["crashed"]),
            seconds=float(payload["seconds"]),  # type: ignore[arg-type]
            note=str(payload["note"]),
        )

    cases.check("빌드·소비·red 재현을 모두 본 관찰은 통과다", record().ok)
    cases.check("빌드가 실패하면 통과가 아니다", not record(build_exit=EXIT_FAIL).ok)
    cases.check("산출물이 하나뿐이면 통과가 아니다", not record(artifacts=(Artifact("wheel", "w.whl", 1, "a"),)).ok)
    cases.check("저장소 밖 검증이 실패하면 통과가 아니다", not record(verify_exit=EXIT_FAIL).ok)
    cases.check("PASS 문장이 하나뿐이면 통과가 아니다", not record(passed=("wheel",)).ok)
    cases.check("`ARTIFACT-INPUTS` 없는 보고는 통과가 아니다", not record(inputs_line=False).ok)
    cases.check("왕복을 안 돌리면 통과가 아니다", not record(roundtrip_exit=None).ok)
    cases.check("sdist 로 다시 빌드되지 않으면 통과가 아니다", not record(roundtrip_exit=EXIT_FAIL).ok)
    cases.check(
        "왕복에서 파일이 빠지면 통과가 아니다(이름을 남긴다)",
        not record(missing=("antigravity_k/dashboard_dist/index.html",)).ok
        and "dashboard_dist/index.html"
        in " ".join(record(missing=("antigravity_k/dashboard_dist/index.html",)).problems),
    )
    cases.check("더 있는 파일은 실패가 아니다(보고만 한다)", record(extra=("antigravity_k/extra.py",)).ok)
    changed = ("antigravity_k/engine/release_sbom.py",)
    cases.check(
        "내용이 다른 파일이 있으면 통과가 아니다(이름이 같아도 소비자는 다른 코드를 받는다)",
        not record(differing=changed).ok and "개의 내용이 다르다" in " ".join(record(differing=changed).problems),
    )
    cases.check(
        "왕복이 내용 변화를 못 보면 통과가 아니다(이름만 보는 눈)",
        not record(rehearsal_differing=()).ok and REWRITE_TARGET in " ".join(record(rehearsal_differing=()).problems),
    )
    cases.check("배포판 내용이 트리와 같으면 통과다", record().ok)
    cases.check(
        "배포판 내용이 트리와 다르면 통과가 아니다(이름을 남긴다)",
        not record(content=ContentCheck(658, ("antigravity_k/a.py",), (), (), (TRANSFORM_TARGET,))).ok,
    )
    cases.check(
        "내용 실물 재현이 심은 이름을 못 지목하면 통과가 아니다",
        not record(content=ContentCheck(658, (), (), (), ())).ok,
    )
    cases.check(
        "내용 실물 재현이 다른 이름을 지목하면 통과가 아니다",
        not record(content=ContentCheck(658, (), (), (), ("mini/other.py",))).ok,
    )
    cases.check(
        "내용 대조군에서 지목하면 통과가 아니다(넓게 잡은 눈)",
        not record(content=ContentCheck(658, (), (), ("mini/kept.py",), (TRANSFORM_TARGET,))).ok,
    )
    cases.check(
        "내용을 0개 비교하면 하한이 문다(경로 매핑이 바뀌어 ‘차이 없음’ 으로 통과하는 순간)",
        bool(floor_problems(coverage_floors(record(content=ContentCheck(0, (), (), (), (TRANSFORM_TARGET,)))))),
    )
    lost = TreeCoverage(expected=("antigravity_k/a.py",), missing=("antigravity_k/a.py",), generated=(), local_only=())
    cases.check(
        "배포판에 없는 추적 파일이 있으면 통과가 아니다(이름을 남긴다)",
        not record(tree=lost).ok and "antigravity_k/a.py" in " ".join(record(tree=lost).problems),
    )
    cases.check(
        "추적되지 않는 로컬 파일은 실패가 아니다(보고만 한다)",
        record(tree=TreeCoverage(expected=("a",), missing=(), generated=("b",), local_only=("c",))).ok,
    )
    cases.check(
        "실물 재현이 심은 이름을 못 지목하면 통과가 아니다",
        not record(tree_rehearsal_defect=()).ok,
    )
    cases.check(
        "실물 재현이 다른 이름을 지목하면 통과가 아니다(심은 것과 다른 것을 봤다)",
        not record(tree_rehearsal_defect=("minipkg/something_else.py",)).ok,
    )
    cases.check(
        "대조군에서 빼짐을 지목하면 통과가 아니다(넓게 잡은 눈)",
        not record(tree_rehearsal_control=("minipkg/kept.py",)).ok,
    )
    cases.check(
        "추적 파일이 0개면 하한이 문다(경로 뿌리가 바뀌면 조용히 통과하는 순간)",
        bool(floor_problems(coverage_floors(record(tree=TreeCoverage((), (), (), ()))))),
    )
    cases.check("왕복 red 재현을 안 돌리면 통과가 아니다", not record(rehearsal_exit=None).ok)
    cases.check("왕복 red 재현의 재빌드가 실패하면 통과가 아니다", not record(rehearsal_exit=EXIT_FAIL).ok)
    cases.check(
        "sdist 에서 뺀 파일을 왕복이 못 보면 통과가 아니다(이 층의 red — 이름을 남긴다)",
        not record(rehearsal_missing=()).ok and TAMPER_TARGET in " ".join(record(rehearsal_missing=()).problems),
    )
    cases.check(
        "비교한 파일이 0이면 하한이 문다(목록 읽기가 깨져 통과하는 순간)",
        bool(floor_problems(coverage_floors(record(compared=0)))),
    )
    cases.check(
        "재현 비교가 0건이면 하한이 문다(‘동일’ 이 아니라 아무것도 안 본 것)",
        bool(floor_problems(coverage_floors(record(reproducibility=repro_of(identities=()))))),
    )
    cases.check("red 재현을 안 돌리면 통과가 아니다", not record(tamper_exit=None).ok)
    cases.check(
        "빠진 배포판을 통과시키면 통과가 아니다(이 층의 red)",
        not record(tamper_exit=EXIT_OK).ok
        and "빠진 배포판을 통과시켰다" in " ".join(record(tamper_exit=EXIT_OK).problems),
    )
    cases.check("사고로 죽은 실행은 통과가 아니다", not record(note="하위 process 가 죽었다").ok)

    cases.check("재현 계약을 본 관찰은 통과다(wheel 동일·sdist 예외 좁게)", record(reproducibility=repro_of()).ok)
    header_only = sdist_of(differs=(), allowed_differs=())
    cases.check(
        "항목이 같은데 바이트만 다르면 그 까닭을 이름으로 말한다(압축·헤더)",
        header_only.bytes_only and not sdist_of().bytes_only,
    )
    cases.check(
        "sdist 의 압축·헤더 차이는 기록된 한계 안이다(항목이 흔들린 것은 아니다)",
        record(reproducibility=repro_of(identities=(good_wheel, header_only))).ok,
    )
    header_only_wheel = Identity("wheel", "a", "d", 664, 664, (), (), (), ())
    cases.check(
        "wheel 이 압축·헤더만 달라도 실패이며 그 까닭을 말한다",
        not record(reproducibility=repro_of(identities=(header_only_wheel, sdist_of()))).ok
        and "압축·헤더가 흔들렸다"
        in " ".join(reproducibility_problems(repro_of(identities=(header_only_wheel, sdist_of())))),
    )
    cases.check(
        "두 번째 빌드를 안 돌리면 통과가 아니다",
        not record(reproducibility=repro_of(second_build_exit=None)).ok,
    )
    cases.check(
        "두 번째 빌드가 실패하면 통과가 아니다",
        not record(reproducibility=repro_of(second_build_exit=EXIT_FAIL)).ok,
    )
    torn = Identity(
        kind="wheel",
        first="a" * 16,
        second="d" * 16,
        members=664,
        pinned_members=664,
        appeared=(),
        differs=("antigravity_k/engine/x.py",),
        allowed_differs=(),
        real_differs=("antigravity_k/engine/x.py",),
    )
    cases.check(
        "wheel 이 같은 pin 으로도 다르면 통과가 아니다(이름을 남긴다)",
        not record(reproducibility=repro_of(identities=(torn, sdist_of()))).ok
        and "wheel 이 같은 pin 으로도 다른 바이트다"
        in " ".join(record(reproducibility=repro_of(identities=(torn, sdist_of()))).problems),
    )
    cases.check(
        "재현 비교가 산출물 하나뿐이면 통과가 아니다",
        not record(reproducibility=repro_of(identities=(good_wheel,))).ok,
    )
    cases.check(
        "sdist 가 같아지면 예외가 만료된 것이다(통과가 아니다)",
        not record(reproducibility=repro_of(identities=(good_wheel, sdist_of(second="b" * 16)))).ok
        and "이제 sdist 도 재현된다"
        in " ".join(record(reproducibility=repro_of(identities=(good_wheel, sdist_of(second="b" * 16)))).problems),
    )
    real_loss = sdist_of(differs=(real_file,), allowed_differs=(), real_differs=(real_file,))
    cases.check(
        "sdist 의 실제 파일이 달라지면 통과가 아니다(이름을 남긴다)",
        not record(reproducibility=repro_of(identities=(good_wheel, real_loss))).ok
        and "__init__.py" in " ".join(record(reproducibility=repro_of(identities=(good_wheel, real_loss))).problems),
    )
    cases.check(
        "sdist 의 파일 목록이 흔들리면 통과가 아니다",
        not record(
            reproducibility=repro_of(identities=(good_wheel, sdist_of(appeared=("antigravity_k-0.1.0/extra.py",))))
        ).ok,
    )
    cases.check(
        "sdist 가 pin 을 따르기 시작하면 근거가 낡은 것이다(통과가 아니다)",
        not record(reproducibility=repro_of(identities=(good_wheel, sdist_of(pinned_members=3)))).ok,
    )
    cases.check(
        "대조군 미니 wheel 이 다르면 통과가 아니다",
        not record(
            reproducibility=repro_of(sensitivity=Sensitivity(False, True, ("x",), True, (EXIT_OK, EXIT_OK, EXIT_OK)))
        ).ok,
    )
    cases.check(
        "pin 이 바이트를 못 움직이면 비교가 눈이 없다(통과가 아니다)",
        not record(
            reproducibility=repro_of(sensitivity=Sensitivity(True, False, ("x",), True, (EXIT_OK, EXIT_OK, EXIT_OK)))
        ).ok,
    )
    cases.check(
        "미니 sdist 가 같으면 우리 sdist 차이는 우리 탓이다(통과가 아니다)",
        not record(
            reproducibility=repro_of(sensitivity=Sensitivity(True, True, (), False, (EXIT_OK, EXIT_OK, EXIT_OK)))
        ).ok,
    )
    cases.check(
        "미니 sdist 차이가 생성 항목 밖이면 통과가 아니다",
        not record(
            reproducibility=repro_of(
                sensitivity=Sensitivity(True, True, ("mini/kept.py",), False, (EXIT_OK, EXIT_OK, EXIT_OK))
            )
        ).ok,
    )
    cases.check(
        "민감도 빌드가 실패하면 통과가 아니다",
        not record(
            reproducibility=repro_of(sensitivity=Sensitivity(True, True, ("x",), True, (EXIT_OK, EXIT_FAIL, EXIT_OK)))
        ).ok,
    )
    cases.check(
        "배포 경로가 pin 을 안 걸면 통과가 아니다(이유를 남긴다)",
        not record(reproducibility=repro_of(ci_pinned=False, ci_pin_value="", ci_note="걸지 않는다")).ok
        and "배포 경로가 같은 pin 을 걸지 않는다"
        in " ".join(record(reproducibility=repro_of(ci_pinned=False, ci_note="걸지 않는다")).problems),
    )
    cases.check(
        "배포 경로의 pin 값이 다르면 통과가 아니다",
        not record(reproducibility=repro_of(ci_pinned=False, ci_pin_value="0")).ok,
    )
    cases.check(
        "추적 목록을 못 읽으면 예외 분류를 하지 않는다(통과가 아니다)",
        not record(reproducibility=repro_of(tracked_readable=False)).ok,
    )
    cases.check("빌드 환경이 pin 을 넣는다", build_env()["SOURCE_DATE_EPOCH"] == str(REPRO_PIN))
    cases.check(
        "다른 pin 도 만들 수 있다(민감도 재현)", build_env(REPRO_MINI_ALT)["SOURCE_DATE_EPOCH"] == str(REPRO_MINI_ALT)
    )
    ci_pinned, _ci_value, ci_note = ci_pin_check()
    cases.check("CI pin 검사는 못 본 경우에도 이유를 말한다", ci_pinned or bool(ci_note))

    floors = coverage_floors()
    cases.check("하한이 여섯이다(산출물·PASS·비교한 파일·실린 추적 파일·재현 비교·내용 비교)", len(floors) == 6)
    cases.check("하한에 근거가 기록돼 있다", all(floor.why.strip() for floor in floors))
    cases.check("하한이 지금 관측을 넘지 않는다", not floor_problems(floors))
    cases.check(
        "눈멀게 한 하한(관측 0)은 문다",
        bool(floor_problems([Floor("배포 산출물", 0, _MIN_ARTIFACTS, why="근거")])),
    )
    cases.check("검증기 스크립트가 실재한다", VERIFIER.is_file())
    cases.check("재현 대상이 wheel 안 경로다(절대 경로가 아니다)", not Path(TAMPER_TARGET).is_absolute())
    cases.check(
        "PASS 문장 파서가 oxymoron 을 만들지 않는다",
        passed_kinds('ARTIFACT-RESULT: {"kind":"wheel","status":"FAIL"}') == (),
    )
    cases.check(
        "PASS 문장 파서가 실제 형태를 읽는다",
        passed_kinds('ARTIFACT-RESULT: {"kind":"wheel","status":"PASS","artifact":"a.whl"}') == ("wheel",),
    )
    cases.check("자기시험 자체가 예외로 죽지 않았다", probe_ok)
    return cases.probe()


def _probe_or_failure() -> Probe:
    """자기시험이 예외로 죽으면 그 사실을 **실패**로 바꾼다(사고는 판정이 아니다)."""

    try:
        return self_probe()
    except Exception as exc:  # noqa: BLE001
        return Probe(cases=0, failures=(f"자기시험이 예외로 죽었다: {type(exc).__name__}: {exc}",))


def as_mapping(record: Observation, probe: Probe) -> dict[str, object]:
    artifacts = len(record.artifacts)
    return {
        "command": ["python", "scripts/release_artifacts.py"],
        "build": {"exit": record.build_exit},
        "artifacts": [item.as_mapping() for item in record.artifacts],
        "verify": {"exit": record.verify_exit, "passed": list(record.passed)},
        "roundtrip": {
            "exit": record.roundtrip_exit,
            "compared": record.compared,
            "missing": list(record.missing),
            "differing": list(record.differing),
            "extra": list(record.extra),
            "rehearsal_exit": record.rehearsal_exit,
            "rehearsal_missing": list(record.rehearsal_missing),
            "rehearsal_differing": list(record.rehearsal_differing),
        },
        "content": record.content.as_mapping(),
        "tree": {
            **record.tree.as_mapping(),
            "rehearsal_control": list(record.tree_rehearsal_control),
            "rehearsal_defect": list(record.tree_rehearsal_defect),
        },
        "tamper": {
            "removed": record.tamper_removed,
            "exit": record.tamper_exit,
            "detected": record.detected,
        },
        "reproducibility": record.reproducibility.as_mapping(),
        "probe": probe.as_mapping(),
        "floors": floor_records(coverage_floors(record)),
        "coverage": {"artifacts": artifacts, "verified": len(record.passed), "compared": record.compared},
        "counts": {
            "artifacts": artifacts,
            "verified": len(record.passed),
            "compared": record.compared,
            "missing": len(record.missing),
            "differing": len(record.differing),
            "roundtrip_bites": 1 if TAMPER_TARGET in record.rehearsal_missing else 0,
            "roundtrip_content_bites": 1 if REWRITE_TARGET in record.rehearsal_differing else 0,
            "content_compared": record.content.compared,
            "content_differ": len(record.content.differ),
            "content_absent": len(record.content.absent),
            "content_rehearsal_bites": 1 if TRANSFORM_TARGET in record.content.rehearsal_defect else 0,
            "tracked_shipped": len(record.tree.expected) - len(record.tree.missing),
            "tracked_missing": len(record.tree.missing),
            "generated": len(record.tree.generated),
            "local_only": len(record.tree.local_only),
            "tree_rehearsal_bites": 1 if MINI_DROPPED in record.tree_rehearsal_defect else 0,
            "tamper_detected": 1 if record.detected else 0,
            "identity_compared": len(record.reproducibility.identities),
            "identity_identical": sum(1 for item in record.reproducibility.identities if item.identical),
            "identity_allowed_differs": sum(len(item.allowed_differs) for item in record.reproducibility.identities),
            "identity_real_differs": sum(len(item.real_differs) for item in record.reproducibility.identities),
            "identity_appeared": sum(len(item.appeared) for item in record.reproducibility.identities),
            "pinned_members": sum(item.pinned_members for item in record.reproducibility.identities),
            "sensitivity_bites": 1 if repro_sensitivity_bites(record.reproducibility) else 0,
            "ci_pinned": 1 if record.reproducibility.ci_pinned else 0,
            "seconds": round(record.seconds, 1),
        },
        "verdict": "PASS" if record.ok else "FAIL",
        "problems": list(record.problems),
    }


def describe(record: Observation, probe: Probe) -> str:
    lines = ["[release] 배포 산출물 계약 — wheel/sdist 를 만들어 저장소 밖에서 써 보고, 빠진 배포판도 만들어 본다"]
    for item in record.artifacts:
        lines.append(
            f"  artifact  {item.kind:5s} {item.name} · {item.bytes / 1_048_576:.1f}MB · sha256 {item.sha256[:12]}"
        )
    lines.append(f"  build     exit {record.build_exit}")
    lines.append(f"  verify    exit {record.verify_exit} · PASS {', '.join(record.passed) or '없음'}")
    roundtrip_note = (
        f"파일 {record.compared}개 비교 · 빠짐 {len(record.missing)} · 내용 다름 {len(record.differing)}"
        f" · 더 있음 {len(record.extra)}"
        if record.roundtrip_exit is not None
        else "돌리지 않았다"
    )
    lines.append(f"  roundtrip exit {record.roundtrip_exit} · {roundtrip_note}")
    missing_note = (
        "sdist 에서 파일을 빼니 왕복이 지목했다" if TAMPER_TARGET in record.rehearsal_missing else "**빼도 못 봤다**"
    )
    rewrite_note = (
        "내용을 바꾸니 바이트 차이로 지목했다" if REWRITE_TARGET in record.rehearsal_differing else "**바꿔도 못 봤다**"
    )
    lines.append(
        f"  재현      sdist 왕복({TAMPER_TARGET} 제거 · {REWRITE_TARGET} 내용 변환) exit {record.rehearsal_exit} — "
        f"{missing_note} · {rewrite_note}"
    )
    content = record.content
    content_note = (
        f"패키지 파일 {content.compared}개 내용 비교 · 다름 {len(content.differ)} · 견줄 수 없음 {len(content.absent)}"
        if content.compared
        else "**내용을 견주지 못했다**"
    )
    lines.append(f"  내용      트리 대조 {content_note}")
    lines.append(
        f"  내용재현  빌드가 내용을 바꾸는 실물 프로젝트 — 심은 파일을 "
        f"{'지목했다' if TRANSFORM_TARGET in content.rehearsal_defect else '못 봤다'} · "
        f"대조군 오탐 {len(content.rehearsal_control)}건"
    )
    tree_note = (
        f"추적 {len(record.tree.expected)}개 중 빠짐 {len(record.tree.missing)} · 배포판 생성물 {len(record.tree.generated)} · "
        f"트리에만(미추적) {len(record.tree.local_only)}"
        if record.tree.expected
        else "**추적 파일을 보지 못했다**"
    )
    lines.append(f"  tree      {tree_note}")
    lines.append(
        f"  재현      작은 프로젝트 실물 빌드 — 심은 파일을 {'지목했다' if MINI_DROPPED in record.tree_rehearsal_defect else '못 봤다'} · "
        f"대조군 오탐 {len(record.tree_rehearsal_control)}건"
    )
    lines.append(
        f"  red       빠진 배포판({record.tamper_removed} 제거) exit {record.tamper_exit} — "
        f"{'막았다' if record.detected else '**못 막았다**'}"
    )
    repro = record.reproducibility
    for identity in repro.identities:
        state = "동일" if identity.identical else "다름"
        detail = (
            f"항목 {identity.members}개 중 pin {identity.pinned_members}개 · 차이 {len(identity.differs)}"
            f"(허용 {len(identity.allowed_differs)}·실제 파일 {len(identity.real_differs)})"
            f" · 목록 차이 {len(identity.appeared)}" + (" · 압축·헤더만" if identity.bytes_only else "")
        )
        lines.append(f"  재현      {identity.kind:5s} {state} {detail}")
    sens = repro.sensitivity
    lines.append(
        f"  민감도    pin {REPRO_PIN} · 두 번째 빌드 exit {repro.second_build_exit} — "
        f"미니 setuptools: 같은 pin {'동일' if sens.control_equal else '**다름**'} · "
        f"다른 pin {'다름' if sens.pin_moves_bytes else '**같음**'} · "
        f"미니 sdist 차이 {len(sens.sdist_differs)}개({'생성 항목뿐' if sens.sdist_backend_only else '**생성 항목 밖**'})"
    )
    lines.append(
        f"  배포경로  CI `{CI_BUILD_JOB}` job pin {repro.ci_pin_value or '없음'}"
        + (" — 같은 값" if repro.ci_pinned else f" — **불일치** {repro.ci_note}")
    )
    lines.append(
        f"  소요      {record.seconds:.1f}초(재현 {repro.seconds:.1f}초 포함) · 자기시험 {probe.cases}건 재판정"
    )
    for problem in record.problems:
        lines.append(f"    - {problem}")
    lines.append(
        "* 이 도구가 없으면 `build` 는 NOT_RUN 으로 남고, 소비자가 받는 물건과 저장소 트리의 차이는 아무도 못 본다."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="release_artifacts",
        description="배포 산출물(wheel/sdist) 계약 — 빌드·저장소 밖 소비·빠진 배포판 재현",
    )
    parser.add_argument("--gate", action="store_true", help="하나라도 어긋나면 exit 1")
    parser.add_argument("--emit-json", action="store_true", help="결과를 stdout JSON 으로 낸다(게이트 stage 가 읽는다)")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다(빌드하지 않는다)")
    parser.add_argument("--dist-dir", type=Path, default=None, help="산출물 자리(기본: 임시 디렉터리)")
    parser.add_argument("--keep", action="store_true", help="임시 산출물을 지우지 않는다(사람이 열어 볼 때)")
    args = parser.parse_args(argv)

    probe = _probe_or_failure()
    if args.self_test:
        print(describe_self_test("release_artifacts", probe))
        return EXIT_OK if probe.ok else EXIT_FAIL

    record = measure(dist_dir=args.dist_dir, keep=args.keep)
    problems = list(record.problems)
    problems.extend(probe_problems(probe, name="release_artifacts"))
    problems.extend(floor_problems(coverage_floors(record)))
    if args.emit_json:
        print(json.dumps(as_mapping(record, probe), ensure_ascii=False, indent=2))
        # JSON 을 내는 실행도 **판정을 종료 코드로** 말한다 — 진단은 stdout 에 그대로 남는다.
        return EXIT_FAIL if problems else EXIT_OK
    print(describe(record, probe))
    if not args.gate:
        return EXIT_OK if record.ok else EXIT_FAIL
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_FAIL if problems else EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
