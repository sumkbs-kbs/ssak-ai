"""번들 검색 artifact 의 배치·갱신·rollback (task 15).

이 모듈이 지키는 문장은 넷이다.

1. **어느 bytes 를 실행하는지 모르면 실행하지 않는다.** 해석 순서는 명시 설정 → 사용자 저장소의
   현재 버전 → 설치 패키지 리소스이고, 셋 다 없으면 `problem` 을 남기고 시작하지 않는다(task 12 의
   fail-closed 와 같은 규칙).
2. **바이트는 제자리에서 바뀌지 않는다.** 버전마다 자기 디렉터리를 갖고, "현재 버전"은 작은 포인터
   파일(`CURRENT.json`)로만 가리킨다. 그래서 실행 중인 child 의 파일을 덮어쓰는 일이 **구조적으로**
   불가능하다(교체는 `os.replace` 한 번, 즉 원자적이다).
3. **검증이 통과한 것만 교체한다.** 매니페스트 sha256 일치 → 호스트 platform/arch 일치 → 스테이징한
   바이트를 실제로 한 번 실행(`--version`)해 보는 selftest. 셋 중 하나라도 실패하면 아무것도 바꾸지
   않는다(잘린 다운로드·다른 아키텍처·신뢰 밖 매니페스트가 모두 여기서 멈춘다).
4. **이전 버전을 지우지 않는다.** 교체 후에도 직전 버전 디렉터리를 남기고 `rollback()` 이 포인터를
   되돌린다 — 갱신이 잘못된 것으로 판명될 때 되돌릴 곳이 있어야 한다.

갱신은 **두 단계**다: `stage_update()` 가 검증·스테이징만 하고, `commit_update()` 가 포인터를 바꾼다.
그 사이에 프로세스가 죽으면 이전 버전이 그대로 현재 버전으로 남는다(그 사실을 시험으로 고정한다).
살아 있는 child 가 있으면 기본값은 **교체 보류**다 — "다음 안전 시점"에 `commit_update()` 를 부르면 된다.
"""

from __future__ import annotations

import json
import os
import platform as platform_module
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from antigravity_k.tools.ssak_search_runtime import (
    ArtifactVerdict,
    verify_bundled_artifact,
)
from antigravity_k.tools.ssak_search_trust import extra_trusted_roots, is_trusted_artifact_path

#: 설치 패키지 안의 기본 배치(task 11 의 `bin/ssak-mcp` + `release/ssak-search-manifest.json` 규약).
PACKAGE_BUNDLE_RELATIVE = Path("vendor") / "ssak_search"
BINARY_NAME = "ssak-mcp"
MANIFEST_RELATIVE = Path("release") / "ssak-search-manifest.json"

#: 사용자 저장소(갱신된 버전이 사는 곳). `~/.antigravity-k` 는 이미 신뢰 루트다(task 13).
STORE_RELATIVE = Path("ssak_search")
VERSIONS_DIRNAME = "versions"
POINTER_NAME = "CURRENT.json"

#: 테스트·클린룸 검증용 오버라이드. 비어 있으면 각각 패키지 리소스·사용자 저장소를 쓴다.
BUNDLE_DIR_ENV = "AGK_SSAK_BUNDLE_DIR"
STORE_DIR_ENV = "AGK_SSAK_STORE_DIR"

#: 스테이징된 바이트를 실제로 한 번 실행해 보는 selftest 의 상한(초).
SELFTEST_TIMEOUT_SECONDS = 30.0

#: 해석 출처 — 상태 화면과 증거가 "어디서 온 바이트인가"를 말할 수 있어야 한다.
SOURCE_EXPLICIT = "explicit"
SOURCE_STORE = "store"
SOURCE_PACKAGE = "package"

#: 갱신이 거절되는 이유(문자열은 로그·증거에 그대로 실린다).
CODE_SHA_MISMATCH = "BUNDLE_SHA_MISMATCH"
CODE_WRONG_ARCH = "BUNDLE_WRONG_ARCH"
CODE_UNTRUSTED = "BUNDLE_UNTRUSTED_SOURCE"
CODE_SELFTEST_FAILED = "BUNDLE_SELFTEST_FAILED"
CODE_MISSING = "BUNDLE_SOURCE_MISSING"


def _env_path(name: str, default: Path) -> Path:
    raw = str(os.environ.get(name, "") or "").strip()
    return Path(raw).expanduser() if raw else default


def package_bundle_dir() -> Path:
    """설치 패키지가 들고 있는 번들 디렉터리(기본 배치)."""
    default = Path(__file__).resolve().parent.parent / PACKAGE_BUNDLE_RELATIVE
    return _env_path(BUNDLE_DIR_ENV, default)


def store_root() -> Path:
    """사용자 저장소 루트(갱신된 버전들의 부모)."""
    return _env_path(STORE_DIR_ENV, Path.home() / ".antigravity-k" / STORE_RELATIVE)


@dataclass(frozen=True)
class BundleLayout:
    """실행 가능한 번들 한 벌 — 바이너리와 그 바이트를 기술한 매니페스트."""

    root: Path
    binary: Path
    manifest: Path | None
    source: str
    version: str | None = None


@dataclass(frozen=True)
class BundleResolution:
    """해석 결과. `reason` 은 실패했을 때 **사용자에게 보여줄 한 줄**이다."""

    layout: BundleLayout | None
    reason: str | None = None

    @property
    def found(self) -> bool:
        return self.layout is not None


def _layout_at(root: Path, source: str, version: str | None = None) -> BundleLayout | None:
    binary = root / "bin" / BINARY_NAME
    if not binary.is_file():
        return None
    manifest = root / MANIFEST_RELATIVE
    return BundleLayout(
        root=root,
        binary=binary,
        manifest=manifest if manifest.is_file() else None,
        source=source,
        version=version,
    )


def _pointer_file(root: Path | None = None) -> Path:
    return (root or store_root()) / POINTER_NAME


def read_pointer(root: Path | None = None) -> dict[str, object] | None:
    """현재 버전 포인터(`CURRENT.json`). 손상됐으면 `None` — 추측하지 않는다."""
    pointer = _pointer_file(root)
    if not pointer.is_file():
        return None
    try:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return cast("dict[str, object]", payload) if isinstance(payload, dict) else None


def current_version_dir(root: Path | None = None) -> Path | None:
    """포인터가 가리키는 버전 디렉터리(없거나 손상됐으면 `None`)."""
    payload = read_pointer(root)
    if payload is None:
        return None
    version = str(payload.get("version", "") or "").strip()
    if not version:
        return None
    candidate = (root or store_root()) / VERSIONS_DIRNAME / version
    return candidate if (candidate / "bin" / BINARY_NAME).is_file() else None


def store_bundle(root: Path | None = None) -> BundleLayout | None:
    """사용자 저장소의 현재 버전(갱신이 있었다면 여기서 실행된다)."""
    directory = current_version_dir(root)
    if directory is None:
        return None
    version = directory.name
    return _layout_at(directory, SOURCE_STORE, version)


def packaged_bundle() -> BundleLayout | None:
    """설치 패키지가 들고 있는 번들(있으면 기본 실행 대상)."""
    return _layout_at(package_bundle_dir(), SOURCE_PACKAGE)


def resolve_bundle(
    artifact_path: str | os.PathLike[str] | None = None,
    manifest_path: str | os.PathLike[str] | None = None,
) -> BundleResolution:
    """실행할 번들을 정한다: 명시 → 사용자 저장소 → 설치 패키지.

    명시 경로가 **있는데 문제가 있으면** 조용히 다른 것으로 내려가지 않는다 — 사용자가 지정한
    bytes 를 실행하지 않으면서 다른 bytes 를 실행하는 것이 가장 나쁜 결과이기 때문이다.
    """
    if artifact_path:
        binary = Path(artifact_path).expanduser()
        if not binary.is_file():
            return BundleResolution(None, f"artifact_path does not exist: {binary}")
        explicit_manifest = (
            Path(manifest_path).expanduser()
            if manifest_path
            else (
                binary.parent.parent / MANIFEST_RELATIVE
                if (binary.parent.parent / MANIFEST_RELATIVE).is_file()
                else None
            )
        )
        return BundleResolution(
            BundleLayout(
                root=binary.parent.parent,
                binary=binary,
                manifest=explicit_manifest,
                source=SOURCE_EXPLICIT,
            )
        )

    stored = store_bundle()
    if stored is not None:
        return BundleResolution(stored)

    packaged = packaged_bundle()
    if packaged is not None:
        return BundleResolution(packaged)

    return BundleResolution(
        None,
        "no bundled search artifact is available "
        f"(checked the installed package at {package_bundle_dir()} and the update store at {store_root()})",
    )


# ── 호스트 적합성 ────────────────────────────────────────────────────────────


def host_platform() -> str:
    return "darwin" if sys.platform == "darwin" else ("win32" if os.name == "nt" else "linux")


def host_arch() -> str:
    machine = platform_module.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86_64", "amd64"}:
        return "x64"
    return machine


def _manifest_section(manifest: Path) -> Mapping[str, object] | None:
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    section = cast(Mapping[str, object], payload).get("artifact")
    return cast("Mapping[str, object]", section) if isinstance(section, Mapping) else None


def describe_manifest(manifest: Path) -> dict[str, object]:
    """매니페스트의 artifact 절을 읽는다(없으면 빈 dict)."""
    section = _manifest_section(manifest)
    return dict(section) if section else {}


@dataclass
class StageResult:
    """스테이징 결과. `ok=False` 면 **아무것도 바꾸지 않았다**."""

    ok: bool
    code: str | None = None
    detail: str = ""
    version: str | None = None
    staged_dir: Path | None = None
    verdict: ArtifactVerdict | None = None
    selftest_output: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "code": self.code,
            "detail": self.detail,
            "version": self.version,
            "staged_dir": str(self.staged_dir) if self.staged_dir else None,
            "sha256": self.verdict.sha256 if self.verdict else None,
            "selftest_output": self.selftest_output,
        }


def pin_sha256() -> str | None:
    """설치본이 고정한 번들 sha256(`PINNED.json`). 없으면 `None`."""
    pin_file = package_bundle_dir() / "PINNED.json"
    if not pin_file.is_file():
        return None
    try:
        payload = json.loads(pin_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    artifact = cast(Mapping[str, object], payload).get("artifact")
    if not isinstance(artifact, Mapping):
        return None
    sha = cast(Mapping[str, object], artifact).get("sha256")
    return str(sha) if isinstance(sha, str) and sha else None


def _is_trusted_manifest(manifest: Path, *, sha256: str | None) -> bool:
    """갱신 매니페스트를 받아들일 수 있는가.

    두 가지 중 하나면 받아들인다.

    - 매니페스트가 **신뢰 루트 안**에 있다(운영자가 놓은 스테이징 디렉터리·설치 트리·사용자 저장소,
      또는 `AGK_SEARCH_TRUSTED_ROOTS` 로 명시한 곳).
    - 매니페스트가 기술한 sha256 이 **설치본의 핀과 같다** — 고정된 릴리스의 복구·재설치는 어디서
      가져와도 같은 바이트이므로 허용한다.

    둘 다 아니면 거절한다: 임의의 다운로드한 매니페스트를 실행 파일의 권위로 받아들이는 것이
    이 규칙이 막으려는 실패 모드다(“임의 최신 다운로드 금지”).
    """
    if sha256 and sha256 == pin_sha256():
        return True
    return is_trusted_artifact_path(manifest, extra_trusted_roots())


def _child_running() -> list[int]:
    """살아 있는 번들 child pid(있으면 교체를 보류한다). 런타임이 없으면 빈 목록."""
    try:
        from antigravity_k.tools.ssak_search_runtime import get_ssak_search_runtime

        runtime = get_ssak_search_runtime()
    except Exception:  # noqa: BLE001 — 저장소 조작이 런타임 사정으로 죽으면 안 된다
        return []
    if runtime is None:
        return []
    try:
        return list(runtime.child_pids())
    except Exception:  # noqa: BLE001
        return []


def _selftest(binary: Path) -> tuple[bool, str]:
    """스테이징한 바이트를 실제로 한 번 실행한다(`--version`).

    왜 필요한가: sha256 일치는 "매니페스트가 기술한 그 파일"까지만 말한다. 잘린 파일·실행 불가
    파일·다른 바이너리 이름을 씌운 경우는 **실행해 봐야** 드러난다. 실패하면 그 버전은 승격되지 않는다.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — 실행할 bytes 를 우리가 검증한 뒤 실행한다
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=SELFTEST_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"selftest could not run: {type(exc).__name__}: {exc}"
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    first = output[0] if output else ""
    if completed.returncode != 0:
        return False, f"selftest exit={completed.returncode} output={first!r}"
    return True, first


def stage_update(
    source_binary: str | os.PathLike[str],
    source_manifest: str | os.PathLike[str] | None,
    *,
    root: Path | None = None,
    expected_version: str | None = None,
) -> StageResult:
    """갱신 후보를 검증하고 스테이징한다(**포인터는 아직 바꾸지 않는다**).

    순서: 매니페스트 신뢰 루트 확인 → sha256 일치 → 호스트 platform/arch 일치 → selftest → 스테이징.
    어느 단계에서든 실패하면 저장소는 손대지 않은 상태로 남는다.
    """
    store = root or store_root()
    binary = Path(source_binary).expanduser()
    if not binary.is_file():
        return StageResult(False, CODE_MISSING, f"update source does not exist: {binary}")

    manifest = Path(source_manifest).expanduser() if source_manifest else None
    if manifest is None or not manifest.is_file():
        return StageResult(
            False, CODE_MISSING, "an update must be accompanied by its manifest — refusing to run unpinned bytes"
        )
    # 매니페스트가 기술한 해시를 먼저 읽어 "핀과 같은가"를 볼 수 있게 한다(읽을 수 없으면 검증기가 거절한다).
    declared_sha = str(describe_manifest(manifest).get("sha256", "") or "") or None
    if not _is_trusted_manifest(manifest, sha256=declared_sha):
        return StageResult(
            False,
            CODE_UNTRUSTED,
            f"update manifest is neither inside the trusted roots nor the pinned release: {manifest}",
        )

    verdict = verify_bundled_artifact(binary, manifest)
    if not verdict.ok:
        return StageResult(False, CODE_SHA_MISMATCH, verdict.detail, verdict=verdict)

    section = describe_manifest(manifest)
    recorded_platform = str(section.get("platform", "") or "")
    recorded_arch = str(section.get("arch", "") or "")
    if recorded_platform and recorded_platform != host_platform():
        return StageResult(
            False,
            CODE_WRONG_ARCH,
            f"artifact is for platform {recorded_platform}, this host is {host_platform()}",
            verdict=verdict,
        )
    if recorded_arch and recorded_arch != host_arch():
        return StageResult(
            False,
            CODE_WRONG_ARCH,
            f"artifact is for arch {recorded_arch}, this host is {host_arch()}",
            verdict=verdict,
        )

    ok, selftest_output = _selftest(binary)
    if not ok:
        return StageResult(False, CODE_SELFTEST_FAILED, selftest_output, verdict=verdict)

    version = (expected_version or str(verdict.sha256 or "")[:16]).strip()
    if not version:
        return StageResult(False, CODE_SHA_MISMATCH, "artifact has no sha256 to version by", verdict=verdict)

    versions = store / VERSIONS_DIRNAME
    versions.mkdir(parents=True, exist_ok=True)
    final_dir = versions / version
    if (final_dir / "bin" / BINARY_NAME).is_file():
        # 같은 버전이 이미 있다 — 바이트를 다시 쓰지 않는다(제자리 교체 금지).
        return StageResult(
            True, None, f"version {version} is already staged", version=version, staged_dir=final_dir, verdict=verdict
        )

    staging = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=str(versions)))
    try:
        target_binary = staging / "bin" / BINARY_NAME
        target_binary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, target_binary)
        target_binary.chmod(0o755)
        (staging / MANIFEST_RELATIVE).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest, staging / MANIFEST_RELATIVE)
        (staging / "STAGED.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "sha256": verdict.sha256,
                    "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "selftest": selftest_output,
                    "source_manifest": str(manifest),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        # 디렉터리 rename 은 원자적이다 — 완성된 버전 디렉터리만 보이게 한다.
        os.replace(staging, final_dir)
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        return StageResult(False, CODE_SELFTEST_FAILED, f"staging failed: {exc}", verdict=verdict)
    return StageResult(
        True,
        None,
        f"staged version {version} (selftest: {selftest_output})",
        version=version,
        staged_dir=final_dir,
        verdict=verdict,
    )


@dataclass
class CommitResult:
    """포인터 교체 결과. `deferred=True` 면 **바꾸지 않고 미뤘다**(다음 안전 시점에 다시 부른다)."""

    committed: bool
    deferred: bool = False
    detail: str = ""
    version: str | None = None
    previous_version: str | None = None
    running_children: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "committed": self.committed,
            "deferred": self.deferred,
            "detail": self.detail,
            "version": self.version,
            "previous_version": self.previous_version,
            "running_children": list(self.running_children),
        }


def commit_update(staged: StageResult, *, root: Path | None = None, allow_live_swap: bool = False) -> CommitResult:
    """스테이징된 버전으로 포인터를 **원자적으로** 바꾼다(이전 버전은 남는다).

    살아 있는 child 가 있으면 기본은 보류다: 실행 중인 검색이 있는 상태에서 버전을 갈아끼우면 그 다음
    child 가 갑자기 다른 바이트가 된다. `allow_live_swap=True` 는 그 사실을 아는 호출자(예: 다음
    기동 전 정리 단계)만 쓴다.
    """
    if not staged.ok or not staged.version:
        return CommitResult(False, detail=staged.detail or "nothing was staged")
    store = root or store_root()
    version_dir = store / VERSIONS_DIRNAME / staged.version
    if not (version_dir / "bin" / BINARY_NAME).is_file():
        return CommitResult(False, detail=f"staged version disappeared: {version_dir}")

    children = _child_running()
    if children and not allow_live_swap:
        return CommitResult(
            False,
            deferred=True,
            detail="a search child is running; the swap waits for the next safe point",
            version=staged.version,
            running_children=children,
        )

    pointer = _pointer_file(store)
    previous = read_pointer(store) or {}
    previous_version = str(previous.get("version", "") or "") or None
    if previous_version == staged.version:
        return CommitResult(
            True,
            detail=f"version {staged.version} is already current",
            version=staged.version,
            previous_version=previous_version,
        )

    payload = {
        "version": staged.version,
        "sha256": staged.verdict.sha256 if staged.verdict else None,
        "previous_version": previous_version,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    store.mkdir(parents=True, exist_ok=True)
    tmp = pointer.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 원자적 교체: 작은 포인터 파일 하나만 바꾼다(바이너리는 절대 건드리지 않는다).
    os.replace(tmp, pointer)
    return CommitResult(
        True,
        detail=f"current version is now {staged.version} (previous: {previous_version or 'none'})",
        version=staged.version,
        previous_version=previous_version,
    )


def update_bundle(
    source_binary: str | os.PathLike[str],
    source_manifest: str | os.PathLike[str] | None,
    *,
    root: Path | None = None,
    allow_live_swap: bool = False,
) -> tuple[StageResult, CommitResult]:
    """stage → commit 을 한 번에. 실패하면 저장소는 그대로다(이전 버전이 계속 현재 버전)."""
    staged = stage_update(source_binary, source_manifest, root=root)
    if not staged.ok:
        return staged, CommitResult(False, detail="staging failed, nothing was changed")
    return staged, commit_update(staged, root=root, allow_live_swap=allow_live_swap)


@dataclass
class RollbackResult:
    ok: bool
    detail: str = ""
    version: str | None = None
    restored_from: str | None = None
    missing: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "detail": self.detail,
            "version": self.version,
            "restored_from": self.restored_from,
            "missing": self.missing,
        }


def rollback(root: Path | None = None, *, allow_live_swap: bool = False) -> RollbackResult:
    """직전 버전으로 되돌린다(그 버전이 보관돼 있을 때만).

    되돌릴 곳이 없으면 **성공이라고 말하지 않는다** — `missing=True` 로 사실을 알린다.
    """
    store = root or store_root()
    payload = read_pointer(store)
    if payload is None:
        return RollbackResult(
            False, "no update has ever been installed, so there is nothing to roll back to", missing=True
        )
    current = str(payload.get("version", "") or "") or None
    previous = str(payload.get("previous_version", "") or "") or None
    if not previous:
        return RollbackResult(
            False, "the current version has no previous version on record", version=current, missing=True
        )
    previous_dir = store / VERSIONS_DIRNAME / previous
    if not (previous_dir / "bin" / BINARY_NAME).is_file():
        return RollbackResult(
            False, f"the previous version is no longer on disk: {previous_dir}", version=current, missing=True
        )

    children = _child_running()
    if children and not allow_live_swap:
        return RollbackResult(
            False, f"a search child is running ({children}); rollback waits for the next safe point", version=current
        )

    pointer = _pointer_file(store)
    tmp = pointer.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "version": previous,
                "sha256": read_version_sha(store, previous),
                "previous_version": current,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "rolled_back_from": current,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, pointer)
    return RollbackResult(True, f"rolled back from {current} to {previous}", version=previous, restored_from=current)


def read_version_sha(root: Path, version: str) -> str | None:
    """버전 디렉터리의 STAGED.json 에서 sha256 을 읽는다(없으면 매니페스트에서)."""
    staged = root / VERSIONS_DIRNAME / version / "STAGED.json"
    if staged.is_file():
        try:
            payload = json.loads(staged.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, Mapping):
            sha = cast(Mapping[str, object], payload).get("sha256")
            if isinstance(sha, str) and sha:
                return sha
    manifest = root / VERSIONS_DIRNAME / version / MANIFEST_RELATIVE
    section = describe_manifest(manifest) if manifest.is_file() else {}
    recorded = section.get("sha256")
    return str(recorded) if isinstance(recorded, str) and recorded else None


def bundle_status(root: Path | None = None) -> dict[str, object]:
    """상태 화면·검증 스크립트가 쓰는 한 눈 요약(현재 버전·출처·보관된 버전들)."""
    store = root or store_root()
    packaged = packaged_bundle()
    stored = store_bundle(store)
    resolution = resolve_bundle()
    versions_dir = store / VERSIONS_DIRNAME
    available = sorted(d.name for d in versions_dir.iterdir() if d.is_dir()) if versions_dir.is_dir() else []
    pointer = read_pointer(store)
    return {
        "store_root": str(store),
        "package_dir": str(package_bundle_dir()),
        "packaged_present": packaged is not None,
        "packaged_version": str(packaged.version) if packaged and packaged.version else None,
        "current_source": resolution.layout.source if resolution.layout else None,
        "current_version": stored.version if stored else None,
        "previous_version": str(pointer.get("previous_version", "") or "") or None if pointer else None,
        "available_versions": available,
        "resolution_problem": resolution.reason,
    }
