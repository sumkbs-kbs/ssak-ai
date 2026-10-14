"""FastAPI application factory, middleware, and lifespan for the Ssak-Ai API."""

import asyncio
import json
import logging
import os
import re
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast, override

import anyio
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import Scope

from antigravity_k.api.sse_revocation import SSERevocationMiddleware

_ = load_dotenv()  # .env 로드 — config import 전에 실행되어야 함

from antigravity_k.config import config
from antigravity_k.tools.egress_policy import validate_httpx_request_async

logger = logging.getLogger("antigravity_k.api.server")

from contextlib import asynccontextmanager

# ---------------------------------------------------------------------------
# Rate limiter (slowapi) — single shared Limiter instance.
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan.

    Args:
        app (FastAPI): FastAPI app.

    """
    from antigravity_k.api.startup_security import validate_startup_security

    validate_startup_security(
        host=config.server.host,
        environment=os.environ.get("AGK_ENV", "development"),
        access_pin=config.security.access_pin,
        pin_hash_file=Path(config.security.pin_hash_file),
    )

    # Startup — Sidabari 패턴 기반 서브시스템 초기화
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    # CR-14 F-45: hermetic e2e 는 공유 `vault_data/hooks`(15MB·동시 기록자)를 피해야 한다.
    # 기본값은 기존과 같다(`<project_root>/vault_data`). `AGK_HOOK_VAULT_DIR` 이 있으면
    # HookEventBus·AuditDb 만 그 아래로 돌린다 — 출하 경로를 바꾸지 않는 격리 구멍이다.
    vault_data_dir = os.environ.get("AGK_HOOK_VAULT_DIR") or os.path.join(project_root, "vault_data")

    # 0) 시작 시 config 검증 (fail-fast, 작업 D) — 잘못된 설정을 런타임 전에 발견
    try:
        problems = config.validate()
        if problems:
            logger.warning("[Startup] 설정 검증 %d개 문제 — 계속 시작하지만 확인 필요:", len(problems))
            for p in problems:
                logger.warning("  ⚠️  %s", p)
    except Exception:
        logger.exception("[Startup] config 검증 중 예외 (non-critical)")

    # 1) HookEventBus 초기화 (파일 기반 실시간 이벤트 IPC)
    try:
        from antigravity_k.engine.hook_event_bus import init_hook_event_bus

        _ = init_hook_event_bus(vault_data_dir)
        logger.info("[Startup] HookEventBus initialized")
    except Exception:
        logger.exception("[Startup] HookEventBus init skipped")

    # 2) AuditDb 초기화 (SQLite 감사 로그)
    try:
        from antigravity_k.engine.audit_db import init_audit_db

        _ = init_audit_db(vault_data_dir)
        logger.info("[Startup] AuditDb initialized")
    except Exception:
        logger.exception("[Startup] AuditDb init skipped")

    # 3) PanelActivityTracker 초기화 (에이전트 활동 추적)
    try:
        from antigravity_k.engine.panel_activity_tracker import (
            init_panel_activity_tracker,
        )

        _ = init_panel_activity_tracker()
        logger.info("[Startup] PanelActivityTracker initialized")
    except Exception:
        logger.exception("[Startup] PanelActivityTracker init skipped")

    # 4) EventBus ↔ HookEventBus 듀얼 싱크 브릿지
    try:
        from antigravity_k.engine.event_bus import bridge_to_hook_event_bus

        bridge_to_hook_event_bus(project_root=project_root)
        logger.info("[Startup] EventBus dual-sync bridge established")
    except Exception:
        logger.exception("[Startup] EventBus bridge skipped")

    # 5) RAG 자동 인덱싱 (기존)
    try:
        from antigravity_k.engine.rag_indexer import RAGIndexer

        def _run_index() -> None:
            try:
                indexer = RAGIndexer(project_root=project_root)
                count = indexer.index_project()
                logger.info("[RAG] Background indexing complete: %s files indexed", count)
            except Exception:
                logger.exception("[RAG] Background indexing failed")

        active_indexer = getattr(app.state, "rag_index_thread", None)
        if not isinstance(active_indexer, threading.Thread) or not active_indexer.is_alive():
            index_thread = threading.Thread(
                target=_run_index,
                name="antigravity-rag-index",
                daemon=True,
            )
            app.state.rag_index_thread = index_thread
            index_thread.start()
            logger.info("[RAG] Background indexing started")
        else:
            logger.info("[RAG] Background indexing already running")
    except Exception:
        logger.exception("[RAG] Auto-index startup skipped")

    # 6) IDE Server (code-server Web IDE)
    try:
        from antigravity_k.engine.ide_server import IDEServer

        ide_server = IDEServer(port=8080, workspace_dir=project_root)
        ide_server.start()
        app.state.ide_server = ide_server
        logger.info("[Startup] IDE Server initialized on port 8080")
    except Exception:
        logger.exception("[Startup] IDE Server init skipped")

    # 7) API Cache 주기적 cleanup (5분 간격)
    _cache_cleanup_task: asyncio.Task[None] | None = None

    try:
        from antigravity_k.engine.api_cache import api_cache

        async def _cache_cleanup_loop():
            while True:
                await asyncio.sleep(300)  # 5분
                try:
                    removed = await api_cache.clear_expired()
                    if removed:
                        logger.debug("[Cache] Periodic cleanup: %d expired entries removed", removed)
                except Exception:
                    logger.debug("[Cache] Cleanup error (non-critical)", exc_info=True)

        _cache_cleanup_task = asyncio.create_task(_cache_cleanup_loop())
        logger.info("[Startup] API Cache periodic cleanup started (interval=300s)")
    except Exception:
        logger.exception("[Startup] API Cache cleanup init skipped")

    _scheduled_job_task: asyncio.Task[None] | None = None

    try:

        async def _scheduled_job_loop() -> None:
            while True:
                await anyio.sleep(15)
                try:
                    from antigravity_k.api.dependencies import get_scheduled_job_service

                    service = get_scheduled_job_service()
                    _ = await asyncio.to_thread(service.tick)
                except Exception:
                    logger.exception("[Jobs] Scheduled job tick failed")

        _scheduled_job_task = asyncio.create_task(_scheduled_job_loop())
        logger.info("[Startup] Scheduled job loop started (interval=15s)")
    except Exception:
        logger.exception("[Startup] Scheduled job loop init skipped")

    from antigravity_k.api.dependencies import bootstrap_cognitive_active

    bootstrap_cognitive_active(app)
    yield

    # Cancel cache cleanup
    if _cache_cleanup_task is not None and not _cache_cleanup_task.done():
        _ = _cache_cleanup_task.cancel()
    if _scheduled_job_task is not None and not _scheduled_job_task.done():
        _ = _scheduled_job_task.cancel()
    # Shutdown
    logger.info("Server shutting down — cancelling application background tasks...")
    background_tasks = cast(
        set[asyncio.Task[object]],
        getattr(app.state, "background_tasks", cast(set[asyncio.Task[object]], set())),
    )
    tasks: list[asyncio.Task[object]] = [task for task in background_tasks if not task.done()]
    for task in tasks:
        _ = task.cancel()
    if tasks:
        _ = await asyncio.gather(*tasks, return_exceptions=True)

    # 번들 검색 child 종료 — 호스트가 소유한 child 는 호스트가 닫는다.
    # 아직 만든 적이 없으면 아무것도 하지 않는다(종료 경로에서 새 child 를 만들지 않는다).
    try:
        from antigravity_k.tools.ssak_search_runtime import shutdown_ssak_search_runtime

        search_shutdown = shutdown_ssak_search_runtime()
        if search_shutdown is not None:
            logger.info(
                "[Shutdown] bundled search child: state=%s child_pids=%s clean=%s",
                search_shutdown.get("state"),
                search_shutdown.get("child_pids"),
                search_shutdown.get("shutdown_clean"),
            )
    except Exception:
        logger.exception("[Shutdown] bundled search child shutdown skipped")

    # 브라우저 세션 종료 — 호스트가 소유한 세션은 호스트가 닫는다(task 16).
    # 아직 만든 적이 없으면 아무것도 하지 않는다(종료 경로에서 새로 만들지 않는다).
    try:
        from antigravity_k.tools.browser_session_owner import shutdown_browser_sessions

        browser_shutdown = shutdown_browser_sessions()
        if browser_shutdown is not None:
            logger.info(
                "[Shutdown] browser sessions: closed=%s max_active=%s",
                browser_shutdown.get("closed"),
                browser_shutdown.get("max_active_sessions"),
            )
    except Exception:
        logger.exception("[Shutdown] browser session shutdown skipped")

    # Sidabari 서브시스템 정리
    try:
        from antigravity_k.engine.hook_event_bus import get_hook_event_bus

        get_hook_event_bus().shutdown()
    except Exception:
        logger.exception("Unhandled exception")
        pass

    try:
        from antigravity_k.engine.audit_db import get_audit_db

        get_audit_db().close()
    except Exception:
        logger.exception("Unhandled exception")
        pass

    try:
        if hasattr(app.state, "ide_server"):
            _ = app.state.ide_server.stop()
    except Exception:
        logger.exception("Unhandled exception")
        pass

    logger.info("Shutdown complete: %s tasks cancelled.", len(tasks))


from antigravity_k import __version__

app = FastAPI(
    title="Ssak-Ai API",
    description=(
        "OpenAI-compatible API for Ssak-Ai Local Engine — "
        "로컬 AI 엔지니어링 에이전트. 채팅, 웹 검색, 파일 조작, "
        "코드 생성/분석, Git 연동, 워크스페이스 관리 등 다양한 작업을 지원합니다.\n\n"
        "## 주요 기능\n"
        "- **채팅/LLM 추론**: OpenAI 호환 `/v1/chat/completions` 엔드포인트\n"
        "- **웹 검색**: 다중 엔진(SearxNG, Jina, DuckDuckGo) 기반 실시간 검색\n"
        "- **파일 시스템**: 워크스페이스 파일 읽기/쓰기/검색/관리\n"
        "- **Git**: status, diff, commit, branch 등 전체 Git 워크플로우\n"
        "- **에이전트**: 자율 태스크 실행, 도구 호출, 진화 학습\n"
        "- **실시간**: WebSocket 기반 이벤트 스트리밍 및 터미널\n\n"
        "## 인증\n"
        "보호된 엔드포인트는 `Authorization: Bearer <token>` 또는 "
        "`X-Access-Pin` 헤더로 인증합니다. `/api/auth/login`에서 토큰 발급 가능.\n"
        "공개 엔드포인트: `/health`, `/docs`, `/openapi.json`, `/metrics`"
    ),
    version=__version__,
    lifespan=lifespan,
    contact={
        "name": "Ssak-Ai Team",
        "url": "https://github.com/ssak-comp/Ssak-Ai",
        "email": "team@ssak-ai.dev",
    },
    license_info={
        "name": "MIT",
        "identifier": "MIT",
    },
    servers=[
        {"url": "http://localhost:8000", "description": "로컬 개발 서버"},
        {"url": "https://api.ssak-ai.dev", "description": "프로덕션 서버"},
    ],
    externalDocs={
        "description": "온보딩 가이드",
        "url": "https://github.com/ssak-comp/Ssak-Ai/blob/main/ONBOARDING.md",
    },
    # 태그 메타데이터 — Swagger UI에서 그룹 설명 표시
    openapi_tags=[
        {"name": "chat", "description": "채팅 및 LLM 추론 엔드포인트 (OpenAI 호환)"},
        {"name": "auth", "description": "인증 및 토큰 관리"},
        {"name": "system", "description": "시스템 상태, 모드 전환, 설정 관리"},
        {"name": "events", "description": "실시간 이벤트 스트리밍 (WebSocket)"},
        {"name": "agent_tools", "description": "에이전트 도구 실행 및 관리"},
        {"name": "agent_activity", "description": "에이전트 활동 로그 및 모니터링"},
        {"name": "workspaces", "description": "워크스페이스 및 프로젝트 관리"},
        {"name": "approval", "description": "에이전트 작업 승인 관리"},
        {"name": "filesystem", "description": "파일 시스템 읽기/쓰기/검색"},
        {"name": "git", "description": "Git 저장소 상태 및 작업"},
        {"name": "code", "description": "코드 분석 및 인라인 제안"},
        {"name": "legacy", "description": "이전 버전 호환 라우트"},
    ],
    # Swagger UI 접두사
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "docExpansion": "list",  # 모든 엔드포인트 펼쳐서 표시
        "defaultModelsExpandDepth": -1,  # 스키마 모델 접기
        "tryItOutEnabled": True,  # Try it out 기본 활성화
        "filter": True,  # 필터 검색창 표시
        "syntaxHighlight.theme": "monokai",
        "displayRequestDuration": True,  # 요청 시간 표시
    },
)

# CORS origins from config or environment (AGK_CORS_ORIGINS)
# Comma-separated list of allowed origins. Default: dashboard dev server + production
_cors_env = os.environ.get("AGK_CORS_ORIGINS", "")
if _cors_env:
    cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    cors_origins = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5174",
        "http://localhost:4178",  # Vite preview server
        "http://localhost:8000",  # Production uvicorn
        "http://localhost:8012",  # Test / E2E uvicorn
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:4178",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8012",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# slowapi state + middleware registration
# ---------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    cast(Callable[[Request, Exception], Response | Awaitable[Response]], _rate_limit_exceeded_handler),
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Inject security headers on every response.

    The CSP allows the CDN-hosted scripts and inline React style attributes the
    dashboard depends on, but blocks inline scripts, ``javascript:`` navigation,
    and external frame ancestors. This is defense-in-depth alongside DOMPurify
    sanitization of agent output in the frontend.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"
    # CSP: allow self + the specific CDNs the React dashboard uses. Inline
    # styles remain until component styles move behind a build-time CSP nonce.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' "
        "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' "
        "https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' ws: wss: http: https:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response


# ---------------------------------------------------------------------------
# Public paths that do NOT require authentication.
# Kept as a set for O(1) lookups in the hot path.
# ---------------------------------------------------------------------------
_PUBLIC_EXACT_PATHS = frozenset(
    {
        "/api/auth/login",
        "/api/auth/token",
        "/api/auth/status",  # SEC-01: UI 표시용 — 사전인증 상태 조회 (credential 노출 없음)
        "/api/ready",  # OBS-01: orchestration readiness probe (dependency 상태만 노출)
        "/api/remote/pairing/complete",
        "/api/remote/pairing/relay",
        "/api/remote/pairing/relay/poll",
        "/health",
        "/v1/health",
        "/api/health/deep",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

# Path prefixes that require authentication.
_PROTECTED_PREFIXES = ("/api/", "/v1/", "/ws/", "/ide/")


def _is_protected_path(path: str) -> bool:
    """Return True if the request path requires authentication.

    A path is protected if it falls under one of the protected prefixes
    (``/api/``, ``/v1/``, ``/ws/``, ``/ide/``) and is not in the explicit
    public allowlist.
    """
    if path in _PUBLIC_EXACT_PATHS:
        return False
    return path.startswith(_PROTECTED_PREFIXES)


def _metric_path(request: Request) -> str:
    """Return a bounded-cardinality route label for an HTTP request."""
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return re.sub(r"/(?:[0-9]+|[0-9a-f]{8,})(?=/|$)", "/:id", request.url.path)


# NX-05 잔여 — 이미 열려 있는 SSE 스트림의 폐기. **가장 먼저 등록**해 미들웨어 스택의 안쪽에
# 둔다(Starlette 은 나중에 추가한 것이 바깥이다): 라우트가 만든 StreamingResponse 를 직접
# 감싸므로 인증·메트릭 미들웨어가 중간에 끼워 넣는 래핑에 의존하지 않는다.
# 판정은 이 미들웨어가 스스로 한다(요청의 bearer 를 매 주기 재검증) — 인증 미들웨어 순서와 무관하다.
app.add_middleware(SSERevocationMiddleware)


@app.middleware("http")
async def verify_access_token(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Authenticate requests to protected paths via bearer token (or legacy PIN).

    Coverage is widened from the previous ``/api/``-only guard to also include
    ``/v1/*`` (LLM inference), ``/ws/*`` (terminal/events), and ``/ide/*``.
    Health checks, docs, and the login endpoint remain public.

    Credentials are accepted in two forms:
      1. ``Authorization: Bearer <jwt>``  — primary, issued by /api/auth/login.
      2. ``X-Access-Pin`` header / ``ag_access_pin`` cookie — legacy fallback
         for existing dashboard clients during the migration window. Compared
         constant-time via PBKDF2 verification.
    """
    # CORS preflight (OPTIONS) requests must bypass auth so that the
    # CORSMiddleware can handle them with proper CORS headers.
    if request.method == "OPTIONS":
        return await call_next(request)

    if _is_protected_path(request.url.path):
        from antigravity_k.api.auth_routes import authenticate_request

        if not authenticate_request(request):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing credentials", "ok": False},
            )
    return await call_next(request)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Collect RED (Rate, Errors, Duration) metrics for every HTTP request.

    Records request count (by method/path/status), latency histogram, and an
    in-flight gauge. Runs after auth so that 401 responses are also counted.
    """
    from antigravity_k.engine.metrics import (
        request_counter,
        request_latency,
        requests_in_flight,
    )

    # Short-circuit: skip collection for the metrics endpoint itself to avoid
    # a feedback loop (scraping /metrics would increment its own counters).
    if request.url.path == "/metrics":
        return await call_next(request)

    requests_in_flight().inc()
    start = asyncio.get_event_loop().time()
    status_code = "500"
    try:
        response = await call_next(request)
        status_code = str(response.status_code)
        return response
    finally:
        elapsed = asyncio.get_event_loop().time() - start
        requests_in_flight().dec()
        # Prefer the resolved route template; only fall back to a bounded
        # identifier scrubber for unmatched or mounted paths.
        path = _metric_path(request)
        request_counter().labels(method=request.method, path=path, status=status_code).inc()
        request_latency().labels(method=request.method, path=path).observe(elapsed)


from antigravity_k.api.auth_routes import router as auth_router
from antigravity_k.api.routes import api_router

app.include_router(auth_router)
app.include_router(api_router)


# ---------------------------------------------------------------------------
# OpenAPI OAuth2 Security Scheme — Swagger Authorize 버튼 활성화
# ---------------------------------------------------------------------------
from fastapi.openapi.utils import get_openapi  # noqa: E402


def _custom_openapi():
    """Generate OpenAPI schema with OAuth2 password flow security scheme.

    Swagger UI의 Authorize 버튼에 OAuth2 password flow를 등록하여
    사용자가 브라우저에서 바로 PIN을 입력하고 API를 테스트할 수 있게 합니다.
    실제 인증은 ``verify_access_token`` 미들웨어에서 처리하며,
    여기서는 OpenAPI 메타데이터만 추가합니다.
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=str(app.version),
        openapi_version=app.openapi_version,
        description=app.description,
        terms_of_service=app.terms_of_service,
        contact=app.contact,
        license_info=app.license_info,
        routes=app.routes,
        tags=app.openapi_tags,
        servers=app.servers,
    )

    # OAuth2 Password Flow 등록 — Swagger Authorize 버튼용
    openapi_schema.setdefault("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2Password": {
            "type": "oauth2",
            "flows": {
                "password": {
                    "tokenUrl": "/api/auth/token",
                    "scopes": {},
                }
            },
            "description": (
                "액세스 PIN을 **username** 필드에 입력하세요. "
                "(password 필드는 비워둬도 됩니다.) "
                "토큰이 자동 발급되어 모든 요청에 포함됩니다."
            ),
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "발급받은 JWT 토큰을 그대로 입력하세요. "
                "토큰은 POST /api/auth/login 또는 POST /api/auth/token 에서 발급받을 수 있습니다."
            ),
        },
    }
    openapi_schema["security"] = [{"OAuth2Password": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


setattr(app, "openapi", _custom_openapi)

# Prometheus metrics endpoint (public — Prometheus scrapers need access).
# We expose a plain GET route at exactly /metrics (the ASGI mount from
# make_asgi_app only serves /metrics/ with a trailing slash, which Prometheus
# does not send by default).
from antigravity_k.engine.metrics import render_metrics  # noqa: E402


@app.get(
    "/metrics",
    include_in_schema=False,  # Prometheus scraper 전용 — Swagger UI 비노출
)
def metrics_endpoint() -> Response:
    """Prometheus exposition endpoint."""
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")


# ---------------------------------------------------------------------------
# OBS-01 — readiness probe: 실제 필수 dependency를 검사한다 (/health와 구분).
# ---------------------------------------------------------------------------
from antigravity_k.engine.operational_metrics import compute_readiness  # noqa: E402


@app.get(
    "/api/ready",
    include_in_schema=False,
)
def readiness_endpoint() -> Response:
    """Readiness probe — task DB/registry/writable storage/model manager 검사.

    NX-06 판정 계약(deps: `deploy/k8s/deployment.yaml` 와 같은 표를 쓴다):

      ==========  ==================================================  ========
      status      조건                                                 HTTP
      ==========  ==================================================  ========
      ready       required·optional 모두 ready                         200 (수용)
      degraded    required 전부 ready + optional ≥1 실패                200 (수용)
      not_ready   required 검사가 하나라도 ready 가 아님                 503 (거부)
      ==========  ==================================================  ========

    degraded 를 수용하는 이유는 신규 설치의 정상 상태(활성 프로젝트 없음, 모델 미로드)
    때문이다 — 거부하면 서비스가 영원히 열리지 않는다. required 실패는 degraded 여부와
    무관하게 503 이며, orchestration 이 EndpointSlice 에서 제외한다.

    인증이 면제된 공개 경로다(probe 는 credential 을 갖지 않는다). 노출 내용은
    검사 이름·상태·경로 수준의 진단이며 secret 을 담지 않는다.
    """
    report = compute_readiness()
    status_code = 503 if report.get("traffic") == "reject" else 200
    return Response(
        content=json.dumps(report, ensure_ascii=False), status_code=status_code, media_type="application/json"
    )


# ---------------------------------------------------------------------------
# Correlation-ID middleware + global exception handler registration.
# ---------------------------------------------------------------------------
import uuid  # noqa: E402

from antigravity_k.api.error_handler import (  # noqa: E402
    correlation_id_var,
    global_exception_handler,
    http_exception_handler,
    session_persistence_exception_handler,
    validation_exception_handler,
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Assign or propagate a correlation id for every request.

    Reads an inbound ``X-Request-Id`` header if present (so callers can trace
    a request across services), otherwise generates one. The id is stored in a
    ``ContextVar`` so log records can include it, and echoed back in the
    ``X-Request-Id`` response header.

    OBS-01: 요청 시작/종료를 operation 범위 구조화 로그로 남긴다 —
    구조화 로그 한 줄로 method/path/status/latency/correlation을 추적한다.
    실행 컨텍스트(project/task/conversation)는 바인딩되는 대로
    ``log_operation_event``가 자동 주입한다.
    """
    cid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    token = correlation_id_var.set(cid)
    from antigravity_k.engine.operational_metrics import log_operation_event

    start = asyncio.get_event_loop().time()
    log_operation_event(
        "http.request.started",
        method=request.method,
        path=request.url.path,
    )
    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = cid
        log_operation_event(
            "http.request.completed",
            outcome="ok",
            duration_ms=(asyncio.get_event_loop().time() - start) * 1000,
            status=response.status_code,
            method=request.method,
            path=request.url.path,
        )
        return response
    except Exception as exc:
        log_operation_event(
            "http.request.failed",
            outcome="error",
            duration_ms=(asyncio.get_event_loop().time() - start) * 1000,
            error_code=type(exc).__name__,
            method=request.method,
            path=request.url.path,
        )
        raise
    finally:
        correlation_id_var.reset(token)


# Register structured exception handlers so errors never leak internal details.
from fastapi import HTTPException  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
# CR-02: 세션 저장 실패는 409(stale)/503(persistence)으로 명시한다.
from antigravity_k.engine.session_manager import SessionPersistenceError  # noqa: E402

app.add_exception_handler(SessionPersistenceError, session_persistence_exception_handler)
# CR-04: shell 실행 경계 거부(403 ASK/DENY, 503 sandbox, 504 timeout)는 전용
# 핸들러로 처리한다 — base Exception 핸들러는 응답 전송 후 재raise하므로
# 정상 응답을 보장하지 못한다.
from antigravity_k.api.contracts.shell import ShellBoundaryError  # noqa: E402

app.add_exception_handler(ShellBoundaryError, global_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

import httpx
from fastapi.responses import StreamingResponse


@app.api_route(
    "/ide/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def reverse_proxy_ide(request: Request, path: str):
    """code-server (Web IDE)에 대한 리버스 프록시.

    주의: 완벽한 VS Code 구동을 위해서는 WebSocket 프록싱이 필요하며,
    현 구현은 기초적인 HTTP 프록싱만 제공합니다. 실사용 시 Nginx 등을 권장합니다.
    """
    ide_host = "http://127.0.0.1:8080"
    url = f"{ide_host}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    # httpx를 이용해 트래픽 포워딩
    async with httpx.AsyncClient(event_hooks={"request": [validate_httpx_request_async]}) as client:
        # 헤더 조작 시 Host 헤더 등이 충돌할 수 있으므로 필터링 필요
        req_headers = dict(request.headers)
        _ = req_headers.pop("host", None)

        rp_req = client.build_request(
            request.method,
            url,
            headers=req_headers,
            content=await request.body(),
        )
        try:
            rp_resp = await client.send(rp_req, stream=True)
            return StreamingResponse(
                rp_resp.aiter_raw(),
                status_code=rp_resp.status_code,
                headers=dict(rp_resp.headers),
            )
        except httpx.RequestError as exc:
            return JSONResponse(
                status_code=502,
                content={"detail": "IDE Server Proxy Error", "error": str(exc)},
            )


# --- STATIC FILES FOR DASHBOARD ---
dashboard_path = Path(__file__).resolve().parents[1] / "dashboard_dist"
if dashboard_path.is_dir():

    class _DashboardStaticFiles(StaticFiles):
        @override
        async def get_response(self, path: str, scope: Scope) -> Response:
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404 and "." not in Path(path).name:
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", _DashboardStaticFiles(directory=dashboard_path, html=True), name="dashboard")
else:
    logger.warning(
        "Dashboard build not found at %s. Please run npm run build in dashboard/",
        dashboard_path,
    )

if __name__ == "__main__":
    import uvicorn

    from antigravity_k.api.startup_security import validate_startup_security

    validate_startup_security(
        host=config.server.host,
        environment=os.environ.get("AGK_ENV", "development"),
        access_pin=config.security.access_pin,
        pin_hash_file=Path(config.security.pin_hash_file),
    )
    uvicorn.run(
        "antigravity_k.api.server:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
        reload_dirs=["src", "config.yaml"],
    )
