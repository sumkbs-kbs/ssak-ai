"""번들 artifact 의 **신뢰 경로** 규칙 (task 13 에서 도입, task 15 에서 분리).

왜 따로 있는가: 이 규칙을 provider(설정·라우팅)와 bundle store(설치·갱신)가 **둘 다** 쓴다. 한 곳에
두고 양쪽이 import 하면 규칙이 갈라지지 않고, provider ↔ store 순환 import 도 생기지 않는다
(basedpyright 가 순환을 오류로 잡아 실제로 드러났다).

규칙 자체는 하나다: 어떤 경로가 **신뢰 루트 안**에 있어야 실행하거나 받아들인다. 그래야 "사용자가
지정한 아무 파일이나 실행" / "임의로 받은 매니페스트를 신뢰" 두 실패 모드가 막힌다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

#: 운영자/시험이 추가하는 신뢰 루트 목록(운영체제 경로 구분자로 나열).
TRUSTED_ROOTS_ENV = "AGK_SEARCH_TRUSTED_ROOTS"


def extra_trusted_roots(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """`AGK_SEARCH_TRUSTED_ROOTS` (os.pathsep 구분). 운영자/시험이 추가하는 루트."""
    source = env if env is not None else os.environ
    raw = str(source.get(TRUSTED_ROOTS_ENV, "") or "")
    return tuple(part.strip() for part in raw.split(os.pathsep) if part.strip())


def trusted_roots(extra: Sequence[str] = ()) -> tuple[Path, ...]:
    """artifact 가 있을 수 있는 루트들: 설치된 패키지 루트 · 사용자 데이터 디렉터리 · 명시 루트."""
    roots: list[Path] = []
    for candidate in (
        Path(__file__).resolve().parents[3],  # 설치/개발 트리 루트(tools/ 아래 두 단계 위와 같은 깊이)
        Path.home() / ".antigravity-k",
        *(Path(item) for item in extra),
    ):
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:  # pragma: no cover — 해석 불가 경로는 신뢰하지 않는다
            continue
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def is_trusted_artifact_path(path: str | os.PathLike[str] | None, extra: Sequence[str] = ()) -> bool:
    """`path`(심볼릭 링크 해석 후)가 신뢰된 루트 안에 있는가."""
    if path is None:
        return False
    try:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            return False
        resolved = candidate.resolve()
    except OSError:  # pragma: no cover
        return False
    for root in trusted_roots(extra):
        if resolved == root or root in resolved.parents:
            return True
    return False


__all__ = [
    "TRUSTED_ROOTS_ENV",
    "extra_trusted_roots",
    "is_trusted_artifact_path",
    "trusted_roots",
]
