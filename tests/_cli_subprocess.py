"""테스트 서브프로세스용 인터프리터 선택 헬퍼.

Phase 12에서 확인된 문제: `pytest`가 프로젝트 venv 밖의 인터프리터(miniforge,
macOS CLT 등)로 실행되면 `sys.executable`이 `antigravity_k`가 설치되지 않은
파이썬을 가리켜 subprocess 기반 CLI/서버 스모크 테스트가 전부 실패한다.

이 헬퍼는 다음 순서로 서브프로세스에 사용할 인터프리터를 고른다:

1. ``AGK_TEST_PYTHON`` 환경변수 (명시적 지정 — CI에서 사용 가능)
2. 활성 venv의 ``sys.executable``이 패키지를 임포트하면 그 환경 재사용
3. ``uv run`` 가능 여부 (프로젝트 환경이 필요한 경우)
4. ``sys.executable``이 실제로 ``antigravity_k``를 임포트할 수 있는지 확인 후 사용
5. 모두 실패하면 프로젝트 ``.venv/bin/python``이 존재할 때 사용
6. 그래도 없으면 ``sys.executable`` (기존 동작 — 실패하더라도 기존과 동일)

함수는 (argv 접두어, 환경 덮어쓰기) 튜플을 반환한다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 서브프로세스에 필요한 최소 모듈 — CLI 임포트 비용이 있는 패키지 루트만 확인
_PROBE_MODULE = "antigravity_k"


@lru_cache(maxsize=1)
def _sys_executable_can_import_package() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {_PROBE_MODULE}"],
            capture_output=True,
            check=False,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@lru_cache(maxsize=1)
def _has_uv() -> bool:
    return shutil.which("uv") is not None


def resolve_interpreter(*, project: bool = False) -> tuple[list[str], dict[str, str]]:
    """서브프로세스 실행용 (argv 접두어, env 덮어쓰기) 반환.

    Args:
        project: True면 uv run에 ``--project``를 명시해 cwd가 프로젝트 밖이어도
            (예: tmp_path에서 실행하는 테스트) 프로젝트 환경을 강제한다.

    Returns:
        argv_prefix: 명령 앞에 붙일 토큰 (예: ["uv", "run", "python"] 또는 [python])
        env_overrides: subprocess env에 덮어쓸 값 (예: {"VIRTUAL_ENV": ...})

    """
    explicit = os.environ.get("AGK_TEST_PYTHON")
    if explicit and Path(explicit).exists():
        return [explicit], {}

    if sys.prefix != sys.base_prefix and _sys_executable_can_import_package():
        return [sys.executable], {}

    if _has_uv():
        # uv run은 프로젝트 pyproject/uv.lock 기준 환경을 보장한다.
        # --project로 cwd와 무관하게 프로젝트 환경을 고정하고, --no-sync로
        # 테스트 중 의존성 재설치를 방지한다.
        prefix = ["uv", "run", "--no-sync"]
        if project:
            prefix += ["--project", str(PROJECT_ROOT)]
        return [*prefix, "python"], {}

    if _sys_executable_can_import_package():
        return [sys.executable], {}

    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return [str(venv_python)], {}

    return [sys.executable], {}


def python_invocation(*, project: bool = False) -> list[str]:
    """`python -m ...` 형태의 명령 접두어만 필요한 경우."""
    argv_prefix, _ = resolve_interpreter(project=project)
    return argv_prefix
