"""SEC-01 테스트 하네스 — 인증 정책의 명시적 dev 익명 허용 env 세팅.

SEC-01 이전에는 테스트가 서버의 취약 분기("plaintext PIN 부재 시 loopback 익명
허용")에 암묵적으로 의존했다. 정책이 fail-closed로 바뀌면서 익명 허용은
``AGK_SEC_DEV_NO_PIN_ALLOW`` 명시 설정이 필요하다 — 테스트도 동일한 명시적
계약을 따른다 (production 코드와 같은 문을 통과).

자격증명 격리:
  - ``AGK_SEC_ACCESS_PIN``/``AGK_SEC_PIN_HASH_FILE``/``AGK_SEC_TOKEN_SECRET_FILE``을
    세션 임시 디렉터리로 향하게 하여, 개발자 로컬 ``data/auth_hash``가 테스트
    실행 중 스캔되지 않게 한다 (결정론적 상태).
  - hash 파일을 만들지 않으면 정책은 credential 전무 상태가 되고, dev-allow env와
    결합해 기존 테스트가 기대하던 "익명 허용" 동작이 재현된다.

개별 인증 테스트(test_auth.py, test_auth_policy_truth_table.py)는 이 fixture가
설정한 값을 monkeypatch로 덮어쓸 수 있다 — fixture는 세션 시작 시 1회 적용이며
테스트가 끝나면 원래 환경으로 복원한다.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_login_security_state() -> Iterator[None]:
    """테스트 경계마다 **프로세스 전역 로그인 보안 상태 2종**을 비운다 (CR-14 F-20).

    로그인 경로에는 두 개의 전역 상태 기계가 있고, 둘 다 키가 "호출자 IP" — TestClient 는
    **항상 같은 주소**라 한 pytest 프로세스 안의 앞선 테스트가 뒤 테스트의 결과를 바꾼다:

      1. ``auth_routes._limiter`` (slowapi ``5/minute``) → 초과 시 **429**.
      2. ``credential_gate`` 실패 burst/sustained 임계 → **lockout 403**.

    실측(같은 코드·같은 명령, **순서만 다름**, deps=dev+rag):

        pytest tests/test_sec03_ws_origin_ticket.py::TestWsGateIntegration   -> 7 passed
        pytest <로그인 5회 태우는 파일> tests/...::TestWsGateIntegration      -> 5 failed (429)
        pytest tests/test_auth.py tests/test_auth_policy_truth_table.py      -> 1 failed (403)

    세 번째가 두 번째 기계의 증거다: ``test_auth.py::test_login_rate_limited`` 는 실패 7회를
    만들고, 그 실패가 credential gate 의 lockout 을 켜면 뒤 파일의 정상 로그인이 403이 된다.
    흥미로운 점은 **두 기계가 서로를 가려 왔다는 것**이다 — 레이트리밋 카운터가 먼저 차서
    429로 끝나면 실패가 7회까지 쌓이지 않아 lockout 이 켜지지 않는다. 즉 지금까지의 초록은
    "버그가 없어서"가 아니라 "한 누수가 다른 누수를 가려서"였다.

    기존 대응은 개별 테스트 안의 우회였다(``test_auth_policy_truth_table.py`` 의
    "429면 카운터 리셋 후 1회 재시도" — 그런데 실제로 도착한 것은 429가 아니라 403이라
    그 우회로는 막지 못한다). 격리는 하네스의 책임이므로 여기서 루트로 처리하고,
    제품의 제한 자체는 그대로다 — ``test_auth.py::test_login_rate_limited`` 는 한 테스트
    안에서 7회를 시도하므로 이 fixture 의 영향을 받지 않는다.
    """
    from antigravity_k.api.auth_routes import _limiter
    from antigravity_k.security.credential_gate import reset_credential_gate

    _limiter.reset()
    reset_credential_gate()
    yield


@pytest.fixture(autouse=True)
def _reset_bound_execution_context() -> Iterator[None]:
    """테스트 경계마다 ARC-01 바인딩된 실행 컨텍스트를 해제한다.

    ``resolve_project_execution_context(bind=True)`` (chat/task route)는 실서버에서
    요청별 contextvar 분리로 누수가 없지만, 테스트는 같은 스레드에서 연속 실행되므로
    바인딩이 다음 테스트로 새어 나가 ``effective_project_root()`` 기반 경로 검사
    (WS-02 sandbox)를 오염시킨다. 시작·종료 양쪽에서 리셋해 테스트 순서 무관성을 보장.
    """
    from antigravity_k.api.project_binding import reset_bound_request_execution_context

    reset_bound_request_execution_context()
    yield
    reset_bound_request_execution_context()


@pytest.fixture(scope="session", autouse=True)
def _isolate_default_session_storage() -> Iterator[None]:
    """세션 전체: 인자를 생략한 ``SessionManager()``가 사용자 홈을 쓰지 않게 격리한다.

    CR-02 이전에는 ``EngineContext``/``OrchestratorAgent``를 session_manager 없이
    만드는 테스트가 실제 ``~/.antigravity/sessions``에 세션 파일을 썼다(회귀 실행마다
    파일 증가). 기본 루트를 세션 임시 디렉터리로 돌려 사용자 데이터를 보호한다.
    """
    import antigravity_k.engine.session_manager as session_manager_mod

    tmpdir = Path(tempfile.mkdtemp(prefix="agk-default-sessions-"))
    patcher = pytest.MonkeyPatch()
    patcher.setattr(session_manager_mod, "default_session_base_dir", lambda: str(tmpdir))
    yield
    patcher.undo()


@pytest.fixture(scope="session", autouse=True)
def _isolate_default_benchmark_db() -> Iterator[None]:
    """세션 전체: 인자를 생략한 ``BenchmarkHarness()``가 **저장소 추적 파일**을 쓰지 않게 격리한다.

    CR-14 F-02: API 런타임은 ``AgentRuntime(task_outcome_recorder=benchmark_harness.record_task_outcome)``
    로 모든 작업 완료를 기록한다. 기본 경로가 CWD 상대 ``data/benchmark_results.json``(추적 파일)
    이라, 작업을 실행하는 테스트가 하나라도 있으면 **검증 실행이 후보 트리를 바꿨다** —
    CR-13 R03 드리프트의 뿌리이자 게이트 코드 지문이 실행마다 이동한 원인이다.

    기본 경로를 세션 임시 디렉터리로 돌린다. 프로덕션 기본값은 그대로이고(추적 파일은 계속
    누적 결과 DB 다), 테스트만 저장소 밖에서 돈다 — CR-02 D-07 과 같은 방식이다.
    """
    import antigravity_k.engine.benchmark_harness as benchmark_harness_mod

    tmpdir = Path(tempfile.mkdtemp(prefix="agk-default-benchmark-"))
    patcher = pytest.MonkeyPatch()
    patcher.setattr(
        benchmark_harness_mod,
        "default_benchmark_db_path",
        lambda: tmpdir / "benchmark_results.json",
    )
    yield
    patcher.undo()


@pytest.fixture(scope="session", autouse=True)
def _isolate_default_usage_db() -> Iterator[None]:
    """세션 전체: 인자를 생략한 사용량 추적이 **저장소 추적 파일**을 쓰지 않게 격리한다.

    CR-14 F-08: API 런타임은 ``UsageTracker(db_path=default_usage_db_path())`` 로 ModelManager 를
    만들고, ``record()`` 는 ``auto_save_interval``(기본 50)건마다 ``_save()`` 를 호출한다.
    기본 경로가 추적 파일 ``data/token_usage.json`` 이라, 사용량을 50건 이상 기록하는 테스트
    조합 하나면 **검증 실행이 후보 트리를 바꿨다**(실측: ``M data/token_usage.json``) —
    F-02(benchmark_harness)와 같은 결함의 두 번째 경로다.

    F-02 와 같은 방식으로 기본 경로를 세션 임시 디렉터리로 돌린다. 프로덕션 기본값은 그대로다.
    """
    import antigravity_k.engine.usage_tracker as usage_tracker_mod

    tmpdir = Path(tempfile.mkdtemp(prefix="agk-default-usage-"))
    patcher = pytest.MonkeyPatch()
    patcher.setattr(
        usage_tracker_mod,
        "default_usage_db_path",
        lambda: tmpdir / "token_usage.json",
    )
    yield
    patcher.undo()


@pytest.fixture(scope="session", autouse=True)
def _sec01_test_auth_harness() -> Iterator[None]:
    """세션 전체: SEC-01 명시적 dev 익명 허용 + 자격증명 격리."""
    from antigravity_k.config import config

    orig = {
        "access_pin": os.environ.get("AGK_SEC_ACCESS_PIN"),
        "pin_hash_file": os.environ.get("AGK_SEC_PIN_HASH_FILE"),
        "token_secret_file": os.environ.get("AGK_SEC_TOKEN_SECRET_FILE"),
        "dev_allow": os.environ.get("AGK_SEC_DEV_NO_PIN_ALLOW"),
    }
    tmpdir = Path(tempfile.mkdtemp(prefix="sec01-auth-"))

    os.environ["AGK_SEC_DEV_NO_PIN_ALLOW"] = "1"
    os.environ["AGK_SEC_ACCESS_PIN"] = ""
    os.environ["AGK_SEC_PIN_HASH_FILE"] = str(tmpdir / "auth_hash")
    os.environ["AGK_SEC_TOKEN_SECRET_FILE"] = str(tmpdir / "token_secret")

    # 이미 임포트된 config 인스턴스에도 반영 (BaseSettings는 env를 생성 시 읽음).
    config.security.access_pin = ""
    config.security.pin_hash_file = str(tmpdir / "auth_hash")
    config.security.token_secret_file = str(tmpdir / "token_secret")

    # auth_routes 모듈 상태 재초기화 — 새 자격증명 경로로 부트스트랩.
    import antigravity_k.api.auth_routes as auth_routes_mod

    auth_routes_mod._token_service = None
    auth_routes_mod._pin_hash = None
    auth_routes_mod.init_auth_state()

    # WS-01 계약: chat/task route는 project_id 또는 session active-project
    # binding을 요구한다. 기본 세션("default")을 레지스트리의 active project에
    # binding해 두면 라우트 테스트가 실제 사용자 플로우(프로젝트 연 뒤 대화)
    # 와 동일한 상태에서 실행된다. binding이 없던 테스트는 WS-01 게이트에서
    # MissingExecutionContextError로 실패했었다 (2026-09-07 정리).
    from antigravity_k.api.project_binding import bind_session_active_project
    from antigravity_k.engine.project_registry import get_project_registry

    try:
        registry = get_project_registry()
        active = registry.get_active_project()
        bind_session_active_project("", active.id)
        # Hermetic 게이트 환경(uv run --isolated --frozen)은 패키지를
        # non-editable로 설치해 PROJECT_ROOT가 site-packages를 가리킨다 —
        # allowed-base가 binding한 실제 프로젝트와 어긋해 임의 checkout에서
        # ProjectRootInvalidError가 난다. binding 대상 경로를 명시적으로
        # 허용해 어떤 checkout/설치 방식에서도 동일하게 동작시킨다.
        record = registry.get_project(active.id)
        if record is not None:
            bound_root = str(Path(record.path).expanduser().resolve())
            existing = os.environ.get("AGK_ALLOWED_ROOTS", "")
            roots = [r for r in existing.split(os.pathsep) if r]
            roots.append(bound_root)
            os.environ["AGK_ALLOWED_ROOTS"] = os.pathsep.join(dict.fromkeys(roots))
    except Exception:
        pass  # registry 부트 실패 시에도 기존 테스트 동작은 유지

    yield

    for key, value in orig.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    # config 인스턴스는 프로세스 종료와 함께 버려지므로 복원 불필요.
    auth_routes_mod._token_service = None
    auth_routes_mod._pin_hash = None


@pytest.fixture(scope="session", autouse=True)
def _isolate_ssak_bundle_locations() -> Iterator[None]:
    """세션 전체: 번들 검색 artifact 의 **배치 위치**를 임시 디렉터리로 돌린다.

    왜 필요한가(task 15): 이제 설치 패키지가 번들을 들고 있고, 갱신된 버전은 사용자 저장소
    (`~/.antigravity-k/ssak_search`)에 산다. 격리가 없으면 다음 두 가지가 실제로 일어난다.

    - 개발 트리에 vendored 바이트(64MB)가 있으면 `search.ssak.enabled=true` 인 시험이 **그 실물**을
      실행한다(느리고, 시험 의도와 무관한 계약까지 함께 재게 된다).
    - `~/.antigravity-k` 는 이미 신뢰 루트라, 개발자가 굴린 갱신 버전이 시험 결과를 바꾼다 — 시험이
      공유 체크아웃/사용자 상태에 따라 달라지는 것은 task 14 에서 `.env` 로 실제로 겪은 실패다.

    실물 경로를 재는 시험은 `AGK_SSAK_BUNDLE_DIR`/`AGK_SSAK_STORE_DIR` 를 직접 지정한다.
    """
    import tempfile

    tmpdir = Path(tempfile.mkdtemp(prefix="ssak-bundle-"))
    orig = {key: os.environ.get(key) for key in ("AGK_SSAK_BUNDLE_DIR", "AGK_SSAK_STORE_DIR")}
    os.environ["AGK_SSAK_BUNDLE_DIR"] = str(tmpdir / "package-bundle")
    os.environ["AGK_SSAK_STORE_DIR"] = str(tmpdir / "store")
    yield
    for key, value in orig.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_browser_session_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """시험마다 브라우저 세션 소유자와 **호스트 전역 원장**을 버린다(task 16 · task 16 후속).

    소유자와 그 원장은 호스트 전역이다. 한 시험이 브라우저를 열고 닫지 않으면, 다음 시험이 같은
    owner 로 `begin()` 을 부를 때 "이미 네 세션이 있다"로 **재사용**되고 아무것도 실행하지 않는다 —
    실제로 그렇게 8개 시험이 깨졌다(단독으로 돌리면 통과해서 더 찾기 어려웠다).

    task 16 후속으로 그 원장은 **파일**이 됐다(프로세스 경계 너머 상한). 시험이 그것을 그대로
    쓰면 개발자의 `~/.antigravity-k` 를 오염시키고, 시험끼리도 서로의 자리를 센다 — 그래서
    시험마다 빈 디렉터리로 격리한다(번들 격리와 같은 규칙).
    """
    from antigravity_k.tools.browser_session_owner import reset_browser_session_owner

    monkeypatch.setenv("AGK_BROWSER_SESSION_STATE", str(tmp_path / "browser_sessions" / "sessions.json"))
    reset_browser_session_owner()
    yield
    reset_browser_session_owner()


@pytest.fixture(autouse=True)
def _isolate_browser_task_journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """시험마다 브라우저 작업 저널을 빈 파일로 격리한다(task 20).

    저널의 기본 경로는 `~/.antigravity-k/browser_tasks.jsonl` 이다. 시험이 그대로 쓰면 개발자의
    실제 기록에 "이미 본 요청" 이 남아 다음 실행이 **중복으로 판정**되고, 시험끼리도 서로의 결말을
    물려받는다(그러면 통과가 이 시험의 결과가 아니게 된다) — task 16 후속의 원장과 같은 규칙이다.
    """
    monkeypatch.setenv("AGK_BROWSER_TASK_JOURNAL", str(tmp_path / "browser_tasks" / "tasks.jsonl"))
    yield


@pytest.fixture(autouse=True)
def _reset_browser_approval_state() -> Iterator[None]:
    """시험마다 브라우저 승인 원장·비밀 보관소·일반 승인 관리자를 비운다(task 18).

    셋 다 **프로세스 전역**이다. 하나라도 남으면 다음 시험이 남의 승인 토큰이나 "항상 허용"
    부여를 물려받아, 통과가 이 시험의 결과가 아니게 된다(그리고 승인은 남으면 안 되는 상태다).
    """
    from antigravity_k.engine.approval_manager import reset_approval_manager
    from antigravity_k.tools.browser_approval import reset_browser_approval

    reset_browser_approval()
    reset_approval_manager()
    yield
    reset_browser_approval()
    reset_approval_manager()
