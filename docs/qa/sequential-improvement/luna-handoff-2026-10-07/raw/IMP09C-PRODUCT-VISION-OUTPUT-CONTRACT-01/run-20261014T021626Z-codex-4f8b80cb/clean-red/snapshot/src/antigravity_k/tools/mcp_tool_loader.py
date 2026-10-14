"""Mcp Tool Loader module."""

import asyncio
import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Callable, ClassVar, cast, final, override

from mcp.client.session import ClientSession

from antigravity_k.engine.mcp_capability import MCPCapabilityAdvisor
from antigravity_k.engine.mcp_health_cache import mcp_health_cache

from .base_tool import BaseTool, RiskLevel, ToolCategory
from .mcp_session_manager import MCPSessionManager
from .mcp_tool_result import MCPToolOutcome, build_outcome, error_outcome

if TYPE_CHECKING:  # 실제 import 는 관리형 경로를 쓸 때만 한다(순환 방지 + 기동 비용)
    from .ssak_search_runtime import SsakSearchRuntime
from .system_tools import ReadFileTool, ReplaceFileContentTool, RunBashCommandTool

logger = logging.getLogger(__name__)


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [str(item) for item in items]


def _optional_string_dict(value: object) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[object, object], value)
    return {str(key): str(item) for key, item in mapping.items()}


def _as_float(value: object, default: float) -> float:
    return float(value) if isinstance(value, (int, float, str)) else default


def _active_policy_denial(name: str, server_name: str) -> str | None:
    """요청 단위 ToolPolicy 를 조회해 이 MCP 호출의 허용 여부를 판정한다.

    규칙은 엔진 한 곳(`tool_executor.mcp_server_policy_denial`)에만 있다 — 여기서
    다시 구현하면 두 벌로 갈라져 한쪽만 고쳐지는 우회가 생긴다.
    """
    try:
        # 도구 계층 → 엔진 정책 모듈(잎) 방향 import: tool_executor 를 끌어오면 순환이 된다.
        from antigravity_k.engine.tool_policy import mcp_server_policy_denial
    except Exception:  # noqa: BLE001 — 정책 레이어가 없는 경량 실행(스크립트/CLI)에서는 통과
        logger.debug("tool policy layer unavailable; MCP policy self-check skipped", exc_info=True)
        return None
    return mcp_server_policy_denial(name, server_name)


def _schema_problem(schema: object) -> str | None:
    """서버가 준 `inputSchema` 가 호출 가능한 형태인지 판정한다(스펙 위반은 오류).

    종전에는 `inputSchema` 가 없으면 `{}` 로 대체해 **스키마 불일치를 숨기고** 도구를
    등록했다 — 호스트의 사전 검증(required)도 무력해졌다. 여기서는 보수적으로 판정한다:
    실제 서버들이 `{}`(인자 없음)와 `{"type": "object"}` 를 모두 보내므로 명백한
    위반(누락·비객체·type != object·required/properties 타입 불일치)만 오류로 본다.
    """
    if schema is None:
        return "inputSchema 가 없다"
    if not isinstance(schema, Mapping):
        return f"inputSchema 가 객체가 아니다({type(schema).__name__})"
    mapping = cast(Mapping[str, object], schema)
    declared_type = mapping.get("type")
    if declared_type is not None and declared_type != "object":
        return f"inputSchema type 이 'object' 가 아니다({declared_type!r})"
    required = mapping.get("required")
    if required is not None and not (
        isinstance(required, list) and all(isinstance(item, str) for item in cast(list[object], required))
    ):
        return "inputSchema required 가 문자열 목록이 아니다"
    properties = mapping.get("properties")
    if properties is not None and not isinstance(properties, Mapping):
        return "inputSchema properties 가 객체가 아니다"
    return None


@final
class MCPTool(BaseTool):
    """MCP(Model Context Protocol) 리소스를 래핑하는 도구.

    실제 MCP 서버의 엔드포인트나 리소스를 호출하여 결과를 반환합니다.
    """

    def __init__(
        self,
        name: str,
        description: str,
        schema: dict[str, object],
        mcp_client: ClientSession | None = None,
        server_name: str = "",
        transport: str = "stdio",
        annotations: Mapping[str, object] | None = None,
        server_policy: Mapping[str, object] | None = None,
        session_loop: asyncio.AbstractEventLoop | None = None,
        caller: Callable[[str, Mapping[str, object]], MCPToolOutcome] | None = None,
        runtime_note: str = "",
    ):
        """Initialize the MCPTool.

        Args:
            name (str): str name.
            description (str): str description.
            schema (dict[str, Any]): dict[str, Any] schema.
            mcp_client (ClientSession): ClientSession mcp client.
            server_name (str): str server name.
            transport (str): str transport.
            annotations (Mapping[str, Any] | None): Mapping[str, Any] | None annotations.
            server_policy (Mapping[str, Any] | None): Mapping[str, Any] | None server policy.
            session_loop (asyncio.AbstractEventLoop | None): 세션을 만든 이벤트 루프.
                anyio 스트림은 이 루프에 묶여 있어 다른 루프에서 부르면 응답이 오지 않는다.
            caller (Callable[[str, Mapping[str, Any]], MCPToolOutcome] | None): 세션 대신
                호출을 넘길 관리형 런타임(예: `SsakSearchRuntime.call_tool`). 런타임이 child 와
                전용 루프를 소유하므로 이 도구는 세션/루프를 만지지 않는다.
            runtime_note (str): 관리형 런타임 도구임을 메타데이터에 남기는 짧은 설명.

        """
        self._caller = caller
        self._runtime_note = runtime_note
        self._name = name
        self._description = description
        self._schema = schema
        self._mcp_client = mcp_client
        self._server_name = server_name
        self._transport = transport
        self._session_loop = session_loop
        self._annotations = dict(annotations or {})
        self._server_policy = dict(server_policy or {})
        self.category = ToolCategory.DATA
        self.risk_level = _risk_from_annotations(self._annotations)
        self.icon = "🔌"
        self.tags = [tag for tag in ["mcp", server_name, transport] if tag]

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return self._name

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return self._description

    @property
    @override
    def parameters_schema(self) -> dict[str, object]:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> object:
        """도구를 실행하고 typed 결과를 반환한다.

        반환값은 `MCPToolOutcome`(str 하위)이라 문자열 소비자는 본문을 그대로 받고,
        호스트는 `is_error`·`structured_content`·`blocks`·`partial` 을 직접 읽는다.
        """
        logger.info("Executing MCP Tool '%s' with args: %s", self._name, kwargs)

        # 요청 단위 정책을 도구에서도 재확인한다(승인 실행 경로는 ToolExecutor.execute 의
        # 정책 검사를 지나가지 않는다 — MCP 서버 허용 목록 우회 금지).
        denial = _active_policy_denial(self._name, self._server_name)
        if denial is not None:
            logger.warning("MCP tool '%s' blocked by request tool policy: %s", self._name, denial)
            return error_outcome(
                f"MCP tool '{self._name}' is blocked for this request. [BLOCKED] {denial}",
                server_name=self._server_name,
                tool_name=self._name,
                transport=self._transport,
                error_code="POLICY_DENIED",
            )

        if self._caller is None and self._mcp_client is None:
            return error_outcome(
                f"MCP tool '{self._name}' has neither a session nor a managed runtime",
                server_name=self._server_name,
                tool_name=self._name,
                transport=self._transport,
                error_code="NO_TRANSPORT",
            )

        if self._caller is not None:
            # 관리형 런타임 경로: child 와 전용 루프는 런타임이 소유한다(이 도구는 이벤트 루프를
            # 만지지 않는다 — 세션 자체가 없다).
            try:
                return self._caller(self._name, dict(kwargs))
            except Exception as exc:  # noqa: BLE001 — 런타임 실패도 typed 오류로 보존한다
                logger.exception("Managed MCP tool '%s' call failed", self._name)
                return error_outcome(
                    f"MCP tool '{self._name}' on server '{self._server_name}' call failed: {exc}",
                    server_name=self._server_name,
                    tool_name=self._name,
                    transport=self._transport,
                    error_code="RUNTIME_ERROR",
                )

        loop_problem = self._prepare_call_loop()
        if isinstance(loop_problem, str):
            return error_outcome(
                f"MCP tool '{self._name}' on server '{self._server_name}' could not be called: {loop_problem}",
                server_name=self._server_name,
                tool_name=self._name,
                transport=self._transport,
                error_code="CALL_LOOP_UNAVAILABLE",
            )
        loop = loop_problem

        # 관리형 런타임 경로가 아니면 세션 경로다 — 위 NO_TRANSPORT 검사가 둘 다 None 인 경우를
        # 이미 돌려보냈지만, 타입 좁히기를 위해 여기서 한 번 더 명시한다(동작 변화 없음).
        client = self._mcp_client
        if client is None:  # pragma: no cover — 위 검사가 먼저 잡는다
            return error_outcome(
                f"MCP tool '{self._name}' has neither a session nor a managed runtime",
                server_name=self._server_name,
                tool_name=self._name,
                transport=self._transport,
                error_code="NO_TRANSPORT",
            )

        try:
            result = loop.run_until_complete(client.call_tool(self._name, arguments=kwargs))
        except Exception as exc:  # noqa: BLE001 — 전송/프로토콜 실패도 typed 오류로 보존한다
            logger.exception("MCP tool '%s' call failed", self._name)
            return error_outcome(
                f"MCP tool '{self._name}' on server '{self._server_name}' call failed: {exc}",
                server_name=self._server_name,
                tool_name=self._name,
                transport=self._transport,
                error_code="TRANSPORT_ERROR",
            )

        outcome = build_outcome(
            result,
            server_name=self._server_name,
            tool_name=self._name,
            transport=self._transport,
        )
        if outcome.is_error:
            logger.warning(
                "MCP tool '%s' returned isError=true (%s) — 호스트는 이를 성공으로 집계하지 않는다.",
                self._name,
                outcome.error_code or "no-code",
            )
        return outcome

    def _prepare_call_loop(self) -> asyncio.AbstractEventLoop | str:
        """호출을 돌릴 이벤트 루프를 고르거나, 불가능하면 사람이 읽는 이유를 돌려준다.

        ① 세션을 만든 루프를 알면 **그 루프에서** 실행한다. anyio 스트림은 생성 루프에
           묶여 있어 다른 루프(예: `asyncio.to_thread` 작업 스레드가 새로 만든 루프)에서
           부르면 응답이 영원히 오지 않는다 — 실측 hang 이 그랬다.
        ② 그 루프가 이미 어딘가에서 돌고 있으면 `run_until_complete` 는 예외를 던지거나
           끝나지 않는다. 멈추는 대신 typed 오류로 즉시 돌려준다(호스트를 볼모로 잡지 않는다).
        ③ 루프를 모르는 경우(테스트가 클라이언트를 직접 주입한 경우)만 종전처럼 현재
           스레드의 루프를 쓴다.
        """
        loop = self._session_loop
        if loop is None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        if loop.is_running():
            return (
                f"its session event loop is already running in another thread "
                f"(server '{self._server_name}'); MCP calls must run on the loop that owns the session"
            )
        return loop

    @override
    def to_metadata(self) -> dict[str, object]:
        """To Metadata.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        metadata = super().to_metadata()
        mcp_metadata: dict[str, object] = {
            "server": self._server_name,
            "transport": self._transport,
            "annotations": self._annotations,
            "trust_level": self._server_policy.get("trust_level", "experimental"),
            "remote": self._transport in {"http", "streamable-http", "sse"},
            "authenticated": bool(self._server_policy.get("authenticated")),
            "timeout_ms": self._server_policy.get("timeout_ms"),
        }
        if self._runtime_note:
            # 관리형 런타임 도구에만 붙인다 — 세션 기반 도구의 메타데이터 표면은 그대로 둔다.
            mcp_metadata["managed_runtime"] = self._runtime_note
        metadata["mcp"] = mcp_metadata
        return metadata


@final
class MCPToolLoader:
    """설정된 MCP 서버들로부터 도구 목록을 가져와서 BaseTool 객체 리스트로 변환하는 로더.

    Phase 1 D11: MCPServerRegistry를 통해 스킬이 등록한 MCP 서버도 로드.
    """

    def __init__(
        self,
        config_path: str | None = ".mcp.json",
        include_system_tools: bool = True,
        load_skill_servers: bool = True,
        project_root: str | None = None,
    ):
        """Initialize the MCPToolLoader.

        Args:
            config_path (str | None): str | None config path.
            include_system_tools (bool): bool include system tools.
            load_skill_servers (bool): Phase 1 D11 — 스킬이 등록한 MCP 서버도 로드할지 여부.
            project_root (str | None): Phase 1 D11 — 프로젝트 루트 (스킬 메타데이터 스캔용).

        """
        self.config_path = config_path
        self.include_system_tools = include_system_tools
        self.load_skill_servers = load_skill_servers
        self.project_root = project_root or os.getcwd()
        self.tools: list[BaseTool] = []
        self.session_manager = MCPSessionManager()
        # 스키마 계약 위반으로 **등록하지 않은** 도구 기록(서버는 살아 있어도 그 도구는 못 쓴다).
        self.schema_errors: list[dict[str, str]] = []

    def load_bundled_search_tools(self, runtime: "SsakSearchRuntime") -> list[BaseTool]:
        """관리형 런타임이 소유한 번들 검색 child 의 도구를 등록한다.

        세션의 소유자는 런타임 하나다(전용 루프). 이 로더는 목록만 받아 도구를 만들고, 호출은
        `runtime.call_tool` 로 넘긴다 — 그래서 child 의 stdin/stdout 을 읽는 곳이 둘이 되지 않는다.
        실패(미준비·스키마 위반)는 `schema_errors` 와 health cache 에 남긴다.
        """
        from .ssak_search_runtime import SsakSearchRuntime

        if not isinstance(runtime, SsakSearchRuntime):  # pragma: no cover — 배선 실수 방지
            raise TypeError("load_bundled_search_tools expects a SsakSearchRuntime")
        server_name = runtime.config.server_name
        transport = "bundled_stdio"
        listings = runtime.list_tools()
        if not listings:
            reason = "child advertised no tools (not ready, or the artifact was rejected)"
            self.schema_errors.append({"server": server_name, "tool": "", "reason": reason})
            mcp_health_cache.record_failure(
                server_name,
                str(runtime.status().get("last_error") or reason),
                transport=transport,
                source="bundled-runtime",
                command=str(runtime.config.launch_command or ""),
            )
            return []
        registered: list[BaseTool] = []
        names: list[str] = []
        for entry in listings:
            name = str(entry.get("name") or "")
            schema = entry.get("inputSchema")
            problem = _schema_problem(schema) if name else "tool advertises no name"
            if problem is not None:
                logger.error("Skipping managed search tool '%s': %s", name or "(unnamed)", problem)
                self.schema_errors.append({"server": server_name, "tool": name, "reason": problem})
                continue
            tool = MCPTool(
                name=name,
                description=str(entry.get("description") or ""),
                schema=cast(dict[str, object], schema),
                server_name=server_name,
                transport=transport,
                caller=runtime.call_tool,
                runtime_note=f"managed by {type(runtime).__name__} (one child per host)",
            )
            self.tools.append(tool)
            registered.append(tool)
            names.append(name)
            logger.info("Registered managed search tool: %s from %s", name, server_name)
        mcp_health_cache.record_success(
            server_name,
            transport=transport,
            tools=names,
            source="bundled-runtime",
            command=str(runtime.config.launch_command or ""),
        )
        return registered

    def load_tools(self) -> list[BaseTool]:
        """MCP 서버와 통신하여 사용 가능한 도구 목록을 조회하고 로드합니다.

        동기 방식으로 호출되며, 내부는 asyncio.run으로 비동기 초기화를 래핑합니다.
        Phase 1 D11: MCPServerRegistry의 스킬 등록 서버를 추가로 로드합니다.
        """
        logger.info("Loading tools from MCP servers...")

        # 시스템(Local) 도구 등록
        if self.include_system_tools:
            self.tools.extend([ReadFileTool(), ReplaceFileContentTool(), RunBashCommandTool()])

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Phase 1 D11: 표준 .mcp.json에서 서버 로드
        if self.config_path and os.path.exists(self.config_path):
            loop.run_until_complete(self._load_mcp_servers(self.config_path))
        else:
            logger.warning(
                "MCP config not found at %s. Skipping dynamic MCP servers.",
                self.config_path,
            )

        # Phase 1 D11: 스킬이 등록한 MCP 서버 로드
        if self.load_skill_servers:
            loop.run_until_complete(self._load_skill_mcp_servers())

        return self.tools

    async def _load_mcp_servers(self, config_path: str):
        read_text = await asyncio.to_thread(Path(config_path).read_text, encoding="utf-8")
        load_json = cast(Callable[[str], object], json.loads)
        config = cast(dict[str, object], load_json(read_text))

        mcp_servers = cast(dict[str, dict[str, object]], config.get("mcpServers", {}))
        await self._connect_and_load_servers(mcp_servers, config_path)

    async def _load_skill_mcp_servers(self):
        """Phase 1 D11: MCPServerRegistry에서 스킬 등록 MCP 서버를 로드합니다."""
        try:
            registry = MCPServerRegistry()
            skill_servers = registry.get_skill_mcp_servers()

            if not skill_servers:
                return

            logger.info(
                "[MCPToolLoader] Loading %s skill-registered MCP servers...",
                len(skill_servers),
            )

            # 스킬 등록 서버를 .mcp.json 형식의 dict로 변환
            mcp_servers: dict[str, dict[str, object]] = {}
            for sid, cfg in skill_servers.items():
                server_config: dict[str, object] = {
                    "command": str(cfg.get("command", "")),
                    "args": _string_list(cfg.get("args", [])),
                }
                if cfg.get("env"):
                    server_config["env"] = dict(cast(Mapping[str, object], cfg["env"]))
                mcp_servers[sid] = server_config

            await self._connect_and_load_servers(mcp_servers, "skill-registry")

        except ImportError:
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
        except Exception:
            logger.exception("[MCPToolLoader] Failed to load skill MCP servers")

    async def _connect_and_load_servers(
        self,
        mcp_servers: dict[str, dict[str, object]],
        source: str,
    ):
        """MCP 서버 목록을 연결하고 도구를 로드합니다.

        Phase 1 D11: _load_mcp_servers와 _load_skill_mcp_servers에서 공통 사용.

        Args:
            mcp_servers: 서버 이름 → 설정 매핑
            source: 로그용 출처 식별자 (파일 경로 또는 "skill-registry")
        """
        advisor = MCPCapabilityAdvisor()
        audit = advisor.audit_config({"mcpServers": mcp_servers}, source=source)
        blocked_servers = {finding.server for finding in audit.findings if finding.severity == "error"}

        for finding in audit.findings:
            log_message = f"MCP audit [{finding.severity}] {finding.server}: {finding.message} {finding.recommendation}"
            if finding.severity == "error":
                logger.error(log_message)
            elif finding.severity == "warning":
                logger.warning(log_message)
            else:
                logger.info(log_message)

        for server_name, server_config in mcp_servers.items():
            if server_name in blocked_servers:
                logger.error("Skipping MCP server '%s' due to audit errors.", server_name)
                block_msgs = [
                    finding.message
                    for finding in audit.findings
                    if finding.server == server_name and finding.severity == "error"
                ]
                mcp_health_cache.record_blocked(
                    server_name,
                    "; ".join(block_msgs) or "audit blocked",
                    transport=_transport_for(server_config),
                    source=source,
                    command=str(server_config.get("command") or server_config.get("url") or ""),
                )
                continue

            try:
                transport = _transport_for(server_config)
                session = await self._connect_server(server_name, server_config, transport)

                # Fetch available tools
                tools_response = await session.list_tools()
                tool_names: list[str] = []

                for tool in tools_response.tools:
                    raw_schema = getattr(tool, "inputSchema", None)
                    if raw_schema is None:
                        raw_schema = getattr(tool, "input_schema", None)
                    problem = _schema_problem(raw_schema)
                    if problem is not None:
                        # 스키마 불일치는 조용히 넘기지 않는다(호스트 사전 검증이 무력해진다).
                        logger.error(
                            "Skipping MCP tool '%s' from '%s': %s",
                            tool.name,
                            server_name,
                            problem,
                        )
                        self.schema_errors.append({"server": server_name, "tool": str(tool.name), "reason": problem})
                        continue
                    annotations = _annotations_to_dict(getattr(tool, "annotations", None))
                    mcp_tool = MCPTool(
                        name=tool.name,
                        description=tool.description or "",
                        schema=cast(dict[str, object], raw_schema),
                        mcp_client=session,
                        server_name=server_name,
                        transport=transport,
                        annotations=annotations,
                        server_policy=_server_policy(server_config, server_name),
                        session_loop=self.session_manager.session_loops.get(server_name),
                    )
                    self.tools.append(mcp_tool)
                    tool_names.append(tool.name)
                    logger.info("Registered MCP tool: %s from %s", tool.name, server_name)

                mcp_health_cache.record_success(
                    server_name,
                    transport=transport,
                    tools=tool_names,
                    source=source,
                    command=str(server_config.get("command") or server_config.get("url") or ""),
                )

            except Exception as exc:
                logger.exception("Error loading tools from '%s'", server_name)
                mcp_health_cache.record_failure(
                    server_name,
                    str(exc),
                    transport=_transport_for(server_config),
                    source=source,
                    command=str(server_config.get("command") or server_config.get("url") or ""),
                )

    async def _connect_server(
        self,
        server_name: str,
        server_config: Mapping[str, object],
        transport: str,
    ) -> ClientSession:
        if transport == "stdio":
            command = str(server_config.get("command", "")).strip()
            args = _string_list(server_config.get("args", []))
            env = _optional_string_dict(server_config.get("env"))
            return await self.session_manager.connect_server(server_name, command, args, env)

        headers = _string_dict(server_config.get("headers", {}))
        # Inject interactive OAuth 2.1 Bearer token when present (vault-backed).
        try:
            from antigravity_k.engine.mcp_oauth import merge_oauth_headers

            headers = merge_oauth_headers(server_name, headers)
        except Exception:  # noqa: BLE001
            logger.debug("MCP OAuth header merge skipped for %s", server_name, exc_info=True)
        url = str(server_config.get("url") or server_config.get("endpoint") or "")
        timeout = _timeout_seconds(server_config, default=30)
        sse_read_timeout = _timeout_seconds(
            server_config,
            default=300,
            keys=("sse_read_timeout", "sse_read_timeout_ms"),
        )

        if transport in {"http", "streamable-http"}:
            return await self.session_manager.connect_streamable_http(
                server_name,
                url,
                headers=headers or None,
                timeout=timeout,
                sse_read_timeout=sse_read_timeout,
            )

        if transport == "sse":
            return await self.session_manager.connect_sse(
                server_name,
                url,
                headers=headers or None,
                timeout=timeout,
                sse_read_timeout=sse_read_timeout,
            )

        raise ValueError(f"Unsupported MCP transport: {transport}")


def _transport_for(server: Mapping[str, object]) -> str:
    transport = str(server.get("transport") or server.get("type") or "").lower()
    if transport in {"streamable_http", "streamable-http"}:
        return "streamable-http"
    if transport:
        return transport
    if server.get("command"):
        return "stdio"
    if server.get("url") or server.get("endpoint"):
        return "http"
    return "unknown"


def _annotations_to_dict(annotations: object) -> dict[str, object]:
    if annotations is None:
        return {}
    if hasattr(annotations, "model_dump"):
        return cast(dict[str, object], getattr(annotations, "model_dump")(exclude_none=True))
    if hasattr(annotations, "dict"):
        return cast(dict[str, object], getattr(annotations, "dict")(exclude_none=True))
    if isinstance(annotations, Mapping):
        mapping = cast(Mapping[object, object], annotations)
        return {str(key): value for key, value in mapping.items()}
    return {}


def _risk_from_annotations(annotations: Mapping[str, object]) -> RiskLevel:
    if annotations.get("destructiveHint"):
        return RiskLevel.HIGH
    if annotations.get("openWorldHint"):
        return RiskLevel.MEDIUM
    if annotations.get("readOnlyHint"):
        return RiskLevel.SAFE
    return RiskLevel.MEDIUM


def _timeout_seconds(
    config: Mapping[str, object],
    default: float,
    keys: tuple[str, str] = ("timeout", "timeout_ms"),
) -> float:
    primary, millis = keys
    if primary in config:
        return _as_float(config[primary], default)
    if millis in config:
        return _as_float(config[millis], default * 1000) / 1000
    return default


def _string_dict(raw: object) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    mapping = cast(Mapping[object, object], raw)
    return {str(key): str(value) for key, value in mapping.items()}


def _server_policy(config: Mapping[str, object], server_name: str = "") -> dict[str, object]:
    headers = config.get("headers", {})
    authenticated = bool(config.get("auth") or config.get("auth_profile"))
    if isinstance(headers, Mapping):
        header_map = cast(Mapping[object, object], headers)
        authenticated = authenticated or any(str(key).lower() == "authorization" for key in header_map)
    oauth_connected = False
    if server_name:
        try:
            from antigravity_k.engine.mcp_oauth import has_stored_tokens

            oauth_connected = has_stored_tokens(server_name)
            authenticated = authenticated or oauth_connected
        except Exception:  # noqa: BLE001
            pass
    return {
        "trust_level": config.get("trust_level", "experimental"),
        "authenticated": authenticated,
        "timeout_ms": config.get("timeout_ms") or config.get("timeout"),
        "oauth_connected": oauth_connected,
    }


# ─── MCP 서버 레지스트리 (커뮤니티 무료 서버 카탈로그) ─────────────


@final
class MCPServerRegistry:
    """MCP 에코시스템의 무료 커뮤니티 서버 카탈로그.

    추천 서버 목록을 관리하고, .mcp.json 설정 파일 자동 생성을 지원합니다.
    MCP가 Linux Foundation (Agentic AI Foundation)의 표준 프로토콜이 되면서
    1,000+ 서버가 에코시스템에 존재합니다.

    사용법:
        registry = MCPServerRegistry()
        recommended = registry.get_recommended()
        registry.generate_config(".mcp.json", ["filesystem", "github", "brave-search"])
    """

    # 검증된 무료 MCP 서버 카탈로그
    CATALOG: ClassVar[dict[str, dict[str, object]]] = {
        "filesystem": {
            "name": "Filesystem",
            "description": "로컬 파일시스템 읽기/쓰기/검색",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
            "category": "core",
            "free": True,
        },
        "github": {
            "name": "GitHub",
            "description": "GitHub API — 이슈, PR, 코드 검색",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
            "category": "dev",
            "free": True,
        },
        "brave-search": {
            "name": "Brave Search",
            "description": "Brave 웹 검색 API",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env": {"BRAVE_API_KEY": ""},
            "category": "search",
            "free": True,  # 무료 티어 2,000회/월
        },
        "sqlite": {
            "name": "SQLite",
            "description": "SQLite 데이터베이스 쿼리",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sqlite"],
            "category": "data",
            "free": True,
        },
        "puppeteer": {
            "name": "Puppeteer",
            "description": "브라우저 자동화 (스크린샷, 네비게이션)",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
            "category": "browser",
            "free": True,
        },
        "memory": {
            "name": "Memory",
            "description": "Knowledge Graph 기반 영속 메모리",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "category": "memory",
            "free": True,
        },
        "fetch": {
            "name": "Fetch",
            "description": "URL 콘텐츠 가져오기 (마크다운 변환)",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-fetch"],
            "category": "web",
            "free": True,
        },
        "sequential-thinking": {
            "name": "Sequential Thinking",
            "description": "구조화된 단계별 사고 (CoT 강화)",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
            "category": "reasoning",
            "free": True,
        },
        "gitnexus": {
            "name": "GitNexus",
            "description": "코드베이스 Knowledge Graph 및 파급 효과(Blast Radius) 분석",
            "command": "npx",
            "args": ["-y", "gitnexus@latest", "mcp"],
            "category": "dev",
            "free": True,
        },
    }

    # Phase 1 D11: 스킬이 등록한 MCP 서버 저장소 (클래스 레벨 — 모든 인스턴스 공유)
    _skill_servers: ClassVar[dict[str, dict[str, object]]] = {}

    def get_all(self) -> dict[str, dict[str, object]]:
        """전체 카탈로그를 반환합니다. (카탈로그 + 스킬 등록 서버 병합)"""
        merged = self.CATALOG.copy()
        for sid, config in self._skill_servers.items():
            merged[sid] = config
        return merged

    def get_by_category(self, category: str) -> dict[str, dict[str, object]]:
        """카테고리별 서버를 반환합니다. (스킬 등록 서버 포함)"""
        result = {k: v for k, v in self.CATALOG.items() if v.get("category") == category}
        result.update({k: v for k, v in self._skill_servers.items() if v.get("category") == category})
        return result

    def get_recommended(self) -> list[str]:
        """에이전트 기능 강화에 추천하는 서버 목록을 반환합니다."""
        return ["filesystem", "fetch", "memory", "sequential-thinking", "gitnexus"]

    # ─── Phase 1 D11: Skill-MCP 연동 API ────────────────────────────

    def register_skill_mcp(self, skill_name: str, mcp_config: Mapping[str, object]) -> bool:
        """스킬의 MCP 서버를 레지스트리에 등록합니다.

        SkillInstaller가 스킬 설치 시 호출하여, 해당 스킬이 제공하는 MCP 서버를
        MCPServerRegistry에 등록합니다. 이후 MCPToolLoader가 이 서버에서 도구를 로드할 수 있습니다.

        Args:
            skill_name: 스킬 이름 (예: "code-review")
            mcp_config: MCP 서버 설정 (command, args, env 등)

        Returns:
            등록 성공 여부
        """
        server_id = _as_text(mcp_config.get("serverId"), f"skill-{skill_name}")
        if server_id in self.CATALOG:
            logger.warning(
                "[MCPRegistry] Server '%s' already exists in catalog — skill '%s' registration skipped",
                server_id,
                skill_name,
            )
            return False

        # skill server config 저장
        self._skill_servers[server_id] = {
            "name": _as_text(mcp_config.get("name"), skill_name),
            "description": _as_text(
                mcp_config.get("description"),
                f"MCP server from skill '{skill_name}'",
            ),
            "command": _as_text(mcp_config.get("command")),
            "args": _string_list(mcp_config.get("args", [])),
            "env": _optional_string_dict(mcp_config.get("env")) or {},
            "category": "skill",
            "free": True,
            "skill_name": skill_name,
            "source": "skill",
        }

        logger.info(
            "[MCPRegistry] Skill MCP server registered: %s (skill=%s)",
            server_id,
            skill_name,
        )
        return True

    def unregister_skill_mcp(self, skill_name: str) -> bool:
        """스킬 제거 시 연결된 MCP 서버 등록을 해제합니다.

        Args:
            skill_name: 스킬 이름

        Returns:
            해제 성공 여부
        """
        removed = False
        for sid in list(self._skill_servers.keys()):
            if self._skill_servers[sid].get("skill_name") == skill_name:
                del self._skill_servers[sid]
                logger.info(
                    "[MCPRegistry] Skill MCP server unregistered: %s (skill=%s)",
                    sid,
                    skill_name,
                )
                removed = True
        if not removed:
            logger.debug("[MCPRegistry] No MCP servers found for skill '%s'", skill_name)
        return removed

    def get_skill_mcp_servers(self, skill_name: str | None = None) -> dict[str, dict[str, object]]:
        """스킬이 등록한 MCP 서버 목록을 반환합니다.

        Args:
            skill_name: 특정 스킬 이름 (None이면 모든 스킬 서버)

        Returns:
            server_id → config 매핑
        """
        if skill_name:
            return {sid: cfg for sid, cfg in self._skill_servers.items() if cfg.get("skill_name") == skill_name}
        return dict(self._skill_servers)

    def list_skills_with_mcp(self) -> list[dict[str, object]]:
        """MCP 서버를 등록한 스킬 목록을 반환합니다.

        Returns:
            스킬 이름 + MCP 서버 ID 목록
        """
        result: dict[str, list[str]] = {}
        for sid, cfg in self._skill_servers.items():
            skill_name = _as_text(cfg.get("skill_name"))
            if skill_name:
                result.setdefault(skill_name, []).append(sid)
        return [{"skill": skill, "servers": servers} for skill, servers in sorted(result.items())]

    def generate_config(self, output_path: str, server_ids: list[str] | None = None) -> str:
        """.mcp.json 설정 파일을 자동 생성합니다.

        Phase 1 D11: 스킬 등록 서버도 포함할 수 있습니다.

        Args:
            output_path: 출력 경로 (예: ".mcp.json")
            server_ids: 포함할 서버 ID 목록 (None이면 추천 목록)

        Returns:
            생성된 파일 경로

        """
        if server_ids is None:
            server_ids = self.get_recommended()

        config: dict[str, object] = {"mcpServers": {}}
        mcp_servers = cast(dict[str, object], config["mcpServers"])
        all_servers = self.get_all()

        for sid in server_ids:
            if sid not in all_servers:
                logger.warning("Unknown MCP server: %s", sid)
                continue

            entry = all_servers[sid]
            server_config = {
                "command": entry["command"],
                "args": entry["args"],
            }
            if "env" in entry:
                server_config["env"] = entry["env"]

            mcp_servers[sid] = server_config

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info(
            "[MCPRegistry] 설정 생성: %s (%s개 서버, %s개 스킬 서버)",
            output_path,
            len(mcp_servers),
            len(self._skill_servers),
        )
        return output_path

    def generate_config_with_skills(self, output_path: str, server_ids: list[str] | None = None) -> str:
        """.mcp.json 설정 파일을 생성합니다. (스킬 등록 서버 포함)

        Phase 1 D11: 추천 서버 + 스킬이 등록한 MCP 서버를 모두 포함한 설정 생성.

        Args:
            output_path: 출력 경로 (예: ".mcp.json")
            server_ids: 포함할 추가 서버 ID 목록 (None이면 추천 목록)

        Returns:
            생성된 파일 경로

        """
        if server_ids is None:
            server_ids = self.get_recommended()

        # 추천 서버 + 스킬 등록 서버 ID 모두 포함
        skill_server_ids = list(self._skill_servers.keys())
        all_ids = list(dict.fromkeys(server_ids + skill_server_ids))  # 중복 제거, 순서 유지

        return self.generate_config(output_path, all_ids)

    def get_catalog_summary(self) -> str:
        """카탈로그 요약을 사람이 읽기 쉬운 형식으로 반환합니다. (스킬 서버 포함)"""
        lines = ["📦 MCP 서버 카탈로그 (무료)", ""]
        by_category: dict[str, list[tuple[str, dict[str, object]]]] = {}

        all_servers = self.get_all()
        for sid, info in all_servers.items():
            cat = info.get("category", "other")
            by_category.setdefault(str(cat), []).append((sid, info))

        for cat, servers in sorted(by_category.items()):
            lines.append(f"  [{cat}]")
            for sid, info in servers:
                skill_tag = f" (skill: {info.get('skill_name', '')})" if info.get("source") == "skill" else ""
                lines.append(f"    - {sid}: {info['description']}{skill_tag}")

        return "\n".join(lines)
