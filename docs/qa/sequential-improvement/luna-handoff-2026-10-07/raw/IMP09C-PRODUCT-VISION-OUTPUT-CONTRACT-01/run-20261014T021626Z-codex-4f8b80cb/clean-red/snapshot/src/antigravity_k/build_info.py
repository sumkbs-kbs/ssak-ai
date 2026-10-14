"""CR-10: 런타임 빌드 provenance — 실제로 실행 중인 배포의 식별자.

BUILD 지표는 하드코딩된 문자열이 아니라 **지금 떠 있는 프로세스가 어느 빌드인지**를
말해야 한다. 값은 릴리스 파이프라인이 주입하는 환경 변수에서 온다.

- ``AGK_BUILD_ID``      — git SHA 등 빌드 식별자
- ``AGK_BUILT_AT``      — 빌드 시각(ISO 8601)
- ``AGK_BUILD_CHANNEL`` — 배포 채널(dev/rc/stable 등)

기록되지 않은 값은 ``None``으로 반환한다. 빈 문자열이나 추측값으로 채우지 않는다 —
UI가 UNKNOWN을 표시할 수 있어야 하기 때문이다. 버전의 단일 원본은
``antigravity_k.__version__``이며 ``pyproject.toml``이 이 값을 참조한다.
"""

from __future__ import annotations

import os

from antigravity_k import __version__

ENV_BUILD_ID = "AGK_BUILD_ID"
ENV_BUILT_AT = "AGK_BUILT_AT"
ENV_BUILD_CHANNEL = "AGK_BUILD_CHANNEL"

BuildInfo = dict[str, str | None]


def _clean(value: str | None) -> str | None:
    """빈 문자열/공백만 있는 환경 변수를 ``None``(미기록)으로 정규화한다."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def get_build_info() -> BuildInfo:
    """현재 프로세스가 실행 중인 빌드의 provenance를 반환한다.

    Returns:
        ``{"version", "build_id", "built_at", "channel"}``. ``version``만 항상 값이
        있고 나머지는 기록되지 않았으면 ``None``이다.
    """
    return {
        "version": __version__,
        "build_id": _clean(os.environ.get(ENV_BUILD_ID)),
        "built_at": _clean(os.environ.get(ENV_BUILT_AT)),
        "channel": _clean(os.environ.get(ENV_BUILD_CHANNEL)),
    }
