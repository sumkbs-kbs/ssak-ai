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
  4. **red 재현 둘** — 이 층은 두 종류의 결함을 막아야 한다:
     · “빠진 배포판”: 같은 wheel 사본에서 module 하나를 빼고 `RECORD` 를 다시 써서 **유효하지만 불완전한**
       wheel 을 만든 뒤 같은 검증기에 건다. 그 검증기가 통과시키면 이 층은 아무것도 막지 못한다.
     · “빠진 sdist”: sdist 사본에서 파일 하나를 빼고 **같은 왕복**을 돌린다. 왕복이 그 빠짐을 지목하지 못하면
       왕복 관찰(exit 0 · 빠짐 0)이 “보고 0” 인지 “아무것도 못 보고 0” 인지 가릴 수 없다.
     빌드는 한 번만 한다(두 번 빌드하면 서로 다른 순간을 가리킨다).
  5. **자기시험** — 판정 규칙(빌드 실패·산출물 수·PASS 문장·왕복 누락·왕복 red 미탐지·red 미탐지·사고)을 합성 관찰로 매 실행 다시 묻는다.

**탐지력 하한**도 함께 낸다(`Floor` — 값과 근거): 배포 산출물 2(wheel+sdist) · 저장소 밖 PASS 2 · **비교한 파일**(왕복
비교가 몇 파일에서 이뤄졌나 — 목록 읽기가 깨져 **0개를 비교하고 “차이 없음”** 으로 통과하는 순간을 잡는다). 하한이
장식인지도 자기시험이 본다(관측 0 은 실패).

```sh
.venv/bin/python scripts/release_artifacts.py            # 빌드 + 검증 + red 재현(수십 초)
.venv/bin/python scripts/release_artifacts.py --emit-json # 게이트 stage 가 읽는다(판정은 종료 코드)
.venv/bin/python scripts/release_artifacts.py --self-test # 자기시험만(빌드하지 않는다)
```
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCRIPTS_DIR: Final[Path] = REPO_ROOT / "scripts"
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
    extra: tuple[str, ...]
    rehearsal_exit: int | None
    rehearsal_missing: tuple[str, ...]
    rehearsal_compared: int
    tamper_exit: int | None
    tamper_removed: str
    inputs_line: bool
    crashed: bool
    seconds: float
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
            "extra": list(self.extra),
            "rehearsal_exit": self.rehearsal_exit,
            "rehearsal_missing": list(self.rehearsal_missing),
            "rehearsal_compared": self.rehearsal_compared,
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
    if record.tamper_exit is None:
        problems.append("red 재현(빠진 배포판)을 돌리지 않았다 — 이 검증이 무는지 확인하지 않은 실행은 통과가 아니다")
    elif record.tamper_exit == EXIT_OK:
        problems.append(
            f"**빠진 배포판을 통과시켰다**({record.tamper_removed} 를 뺀 wheel) — 이 검증은 아무것도 막지 못한다"
        )
    return tuple(problems)


def coverage_floors(record: Observation | None = None) -> list[Floor]:
    """탐지력 하한 — 산출물 수와 실제로 써 본 산출물 수(값 + 근거)."""

    observed_artifacts = len(record.artifacts) if record is not None else _MIN_ARTIFACTS
    observed_passed = len(record.passed) if record is not None else _MIN_PASSED
    observed_compared = record.compared if record is not None else _MIN_COMPARED
    return [
        Floor("배포 산출물", observed_artifacts, _MIN_ARTIFACTS, why=_WHY_ARTIFACTS),
        Floor("저장소 밖 PASS", observed_passed, _MIN_PASSED, why=_WHY_PASSED),
        Floor("비교한 파일", observed_compared, _MIN_COMPARED, why=_WHY_COMPARED),
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


def run(cmd: list[str], *, cwd: Path | None = None, seconds_budget: float | None = None) -> tuple[int, str]:
    """독립 process 로 돌리고 (종료 코드, 출력) 을 돌려준다."""

    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=seconds_budget,
    )
    return result.returncode, result.stdout + result.stderr


def build(dist_dir: Path) -> tuple[int, str]:
    """wheel + sdist 를 만든다(저장소 밖 자리에)."""

    return run(["uv", "build", "--no-sources", "--out-dir", str(dist_dir)])


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


def compare_wheels(direct: Path, rebuilt: Path) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    """트리에서 만든 wheel 과 sdist 에서 다시 만든 wheel 을 견준다 — (빠진 것, 더 있는 것, 비교한 파일 수)."""

    left = set(wheel_names(direct))
    right = set(wheel_names(rebuilt))
    return tuple(sorted(left - right)), tuple(sorted(right - left)), len(left | right)


def roundtrip(sdist: Path, direct_wheel: Path, work: Path) -> tuple[int | None, tuple[str, ...], tuple[str, ...], int]:
    """sdist 를 풀어 그 안에서 wheel 을 다시 만들고 파일 목록을 견준다 — sdist 설치 경로의 결함을 드러낸다."""

    if not sdist.is_file() or not direct_wheel.is_file():
        return None, (), (), 0
    root = unpack_sdist(sdist, work)
    out = work / "roundtrip"
    out.mkdir(parents=True, exist_ok=True)
    exit_code, _ = run(["uv", "build", "--no-sources", "--wheel", "--out-dir", str(out)], cwd=root)
    rebuilt = sorted(out.glob("antigravity_k-*.whl"))
    if not rebuilt:
        return exit_code, (), (), 0
    missing, extra, compared = compare_wheels(direct_wheel, rebuilt[-1])
    return exit_code, missing, extra, compared


def drop_member(source: Path, target: Path, *, remove: str) -> Path:
    """sdist 사본에서 파일 하나를 뺀다 — 소비자가 받는 압축본에 파일이 빠진 상태를 그대로 만든다.

    나머지 member 는 손대지 않고 그대로 옮긴다(경로 모양이 바뀌면 재현이 아니라 다른 물건이 된다).
    """

    with tarfile.open(source) as archive:
        members = archive.getmembers()
        if not any(member.name == remove or member.name.endswith(f"/{remove}") for member in members):
            raise ValueError(f"{remove} 가 {source.name} 안에 없다 — 빼려는 파일이 그 압축본에 없다")
        with tarfile.open(target, "w:gz") as out:
            for member in members:
                if member.name == remove or member.name.endswith(f"/{remove}"):
                    continue
                payload = archive.extractfile(member) if member.isfile() else None
                out.addfile(member, payload)
    return target


def rehearse_dropped_sdist(sdist: Path, direct_wheel: Path, work: Path) -> tuple[int | None, tuple[str, ...], int]:
    """sdist 에서 파일 하나를 빼고 **같은 왕복**을 돌린다 — 왕복이 그 빠짐을 지목하지 못하면 이 층은 무력하다.

    관찰(왕복 exit 0 · 빠짐 0)만으로는 “왕복이 아무것도 보지 못해서 0” 인지 “보고 0” 인지 갈리지 않는다.
    """

    if not sdist.is_file() or not direct_wheel.is_file():
        return None, (), 0
    corner = work / "roundtrip-rehearsal"
    corner.mkdir(parents=True, exist_ok=True)
    drop_member(sdist, corner / sdist.name, remove=TAMPER_TARGET)
    exit_code, missing, _extra, compared = roundtrip(corner / sdist.name, direct_wheel, corner)
    return exit_code, missing, compared


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
    """빌드 → 저장소 밖 검증 → red 재현을 한 번의 실행으로 한다."""

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
            roundtrip_exit, missing, extra, compared = roundtrip(sdist, wheel, temporary)
            rehearsal_exit, rehearsal_missing, rehearsal_compared = rehearse_dropped_sdist(sdist, wheel, temporary)
        else:
            roundtrip_exit, missing, extra, compared = None, (), (), 0
            rehearsal_exit, rehearsal_missing, rehearsal_compared = None, (), 0
        tamper_exit, removed = rehearse_missing_module(artifacts, target, temporary)
        crashed = CRASH_MARKER in (build_out + verify_out)
        return Observation(
            build_exit=build_exit,
            artifacts=artifacts,
            verify_exit=verify_exit,
            passed=passed_kinds(verify_out),
            roundtrip_exit=roundtrip_exit,
            compared=compared,
            missing=missing,
            extra=extra,
            rehearsal_exit=rehearsal_exit,
            rehearsal_missing=rehearsal_missing,
            rehearsal_compared=rehearsal_compared,
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
            "extra": (),
            "rehearsal_exit": EXIT_OK,
            "rehearsal_missing": (TAMPER_TARGET,),
            "rehearsal_compared": 664,
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
            extra=payload["extra"],  # type: ignore[arg-type]
            rehearsal_exit=payload["rehearsal_exit"],  # type: ignore[arg-type]
            rehearsal_missing=payload["rehearsal_missing"],  # type: ignore[arg-type]
            rehearsal_compared=int(payload["rehearsal_compared"]),  # type: ignore[call-overload]
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
    cases.check("red 재현을 안 돌리면 통과가 아니다", not record(tamper_exit=None).ok)
    cases.check(
        "빠진 배포판을 통과시키면 통과가 아니다(이 층의 red)",
        not record(tamper_exit=EXIT_OK).ok
        and "빠진 배포판을 통과시켰다" in " ".join(record(tamper_exit=EXIT_OK).problems),
    )
    cases.check("사고로 죽은 실행은 통과가 아니다", not record(note="하위 process 가 죽었다").ok)

    floors = coverage_floors()
    cases.check("하한이 셋이다(산출물·PASS·비교한 파일)", len(floors) == 3)
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
            "extra": list(record.extra),
            "rehearsal_exit": record.rehearsal_exit,
            "rehearsal_missing": list(record.rehearsal_missing),
        },
        "tamper": {
            "removed": record.tamper_removed,
            "exit": record.tamper_exit,
            "detected": record.detected,
        },
        "probe": probe.as_mapping(),
        "floors": floor_records(coverage_floors(record)),
        "coverage": {"artifacts": artifacts, "verified": len(record.passed), "compared": record.compared},
        "counts": {
            "artifacts": artifacts,
            "verified": len(record.passed),
            "compared": record.compared,
            "missing": len(record.missing),
            "roundtrip_bites": 1 if TAMPER_TARGET in record.rehearsal_missing else 0,
            "tamper_detected": 1 if record.detected else 0,
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
        f"파일 {record.compared}개 비교 · 빠짐 {len(record.missing)} · 더 있음 {len(record.extra)}"
        if record.roundtrip_exit is not None
        else "돌리지 않았다"
    )
    lines.append(f"  roundtrip exit {record.roundtrip_exit} · {roundtrip_note}")
    rehearsal_note = (
        "sdist 에서 파일을 빼니 왕복이 지목했다" if TAMPER_TARGET in record.rehearsal_missing else "**빼도 못 봤다**"
    )
    lines.append(f"  재현      sdist 왕복({TAMPER_TARGET} 제거) exit {record.rehearsal_exit} — {rehearsal_note}")
    lines.append(
        f"  red       빠진 배포판({record.tamper_removed} 제거) exit {record.tamper_exit} — "
        f"{'막았다' if record.detected else '**못 막았다**'}"
    )
    lines.append(f"  소요      {record.seconds:.1f}초 · 자기시험 {probe.cases}건 재판정")
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
