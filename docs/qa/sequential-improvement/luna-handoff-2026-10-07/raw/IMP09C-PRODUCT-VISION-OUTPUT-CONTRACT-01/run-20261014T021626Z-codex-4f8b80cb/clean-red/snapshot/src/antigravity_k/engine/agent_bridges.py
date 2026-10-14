"""에이전트 브리지 — 외부 CLI 에이전트를 Ssak-Ai 로컬 모델에 원커맨드 연결.

============================================================
벤치마킹 출처: unsloth `unsloth start claude/codex/...` (OpenAI/Anthropic 호환 API 브리지).
Claude Code, Codex 등의 에이전트가 Ssak-Ai를 LLM 백엔드로 사용할 수 있도록
환경변수 매핑과 엔드포인트를 결정한다.

권장 브리지 환경변수 블록 (Phase 34/35/36 라이브 검증 기준)
------------------------------------------------------------

**Claude Code** (anthropic 프로토콜 — BASE_URL에 `/v1` 접미사 금지, CC가 직접 붙임):

    ANTHROPIC_BASE_URL=http://127.0.0.1:8000
    unset ANTHROPIC_API_KEY
    ANTHROPIC_AUTH_TOKEN="${SSAK_ACCESS_TOKEN:?set a token issued by /api/auth/login}"
    ANTHROPIC_MODEL=qwen3.8:latest
    CLAUDE_CODE_MAX_CONTEXT_TOKENS=262144      # 미등록 모델의 실제 컨텍스트 윈도.
        # 미설정 시 CC는 보수 기본 윈도로 자동 압축(claude.exe 내장 안내:
        # "set CLAUDE_CODE_MAX_CONTEXT_TOKENS to its real window").
    ANTHROPIC_SMALL_FAST_MODEL=qwen3.8:latest  # 백그라운드 소형 작업도 로컬 모델로.
    ANTHROPIC_DEFAULT_HAIKU_MODEL=qwen3.8:latest
    ANTHROPIC_DEFAULT_SONNET_MODEL=qwen3.8:latest  # haiku/sonnet 별칭도 로컬 모델 매핑.

    /model 피커에 등록해 "모델 카탈로그에 없음" 경고([claude-code:unrecognized_model])를
    없애려면 사용자 설정(~/.claude/settings.json — 프로젝트 체크아웃 설정은 무시됨):

        {"modelPicker": {"options": [
            {"model": "qwen3.8:latest", "behavesAs": "claude-sonnet-4-6"}
        ]}}

    behavesAs 값은 CC 내장 모델 키(claude-sonnet-4-6 등) — claude.exe 스키마
    ("an object with an \"options\" array of { model, label?, description?, behavesAs? } rows").

**Codex** (openai 프로토콜 — env만으로 연결 불가, config 오버라이드 필수. Phase 35):

    export OPENAI_API_KEY="${SSAK_ACCESS_TOKEN:?set a token issued by /api/auth/login}"
    codex exec --sandbox read-only --skip-git-repo-check \
      -c model_provider=ssak \
      -c 'model_providers.ssak.base_url="http://127.0.0.1:8000/v1"' \
      -c 'model_providers.ssak.env_key="OPENAI_API_KEY"' \
      -c 'model_providers.ssak.wire_api="responses"' -m qwen3.8:latest "<prompt>" < /dev/null

    - Codex 0.150+ 는 wire_api="chat"를 제거하고 Responses API(/responses)만 지원
      (openai/codex#7782) — Ssak-Ai 측 엔드포인트는 responses_api.py.
    - exec 모드에서 stdin을 끊어야 함 (< /dev/null) — 아니면 stdin 대기로 멈춤.

확장: AGENT_BRIDGES에 항목 한 줄을 추가하면 새 에이전트가 지원된다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from shlex import quote
from typing import Final, Literal

BridgeProtocol = Literal["anthropic", "openai"]

ANTHROPIC_ENDPOINT = "/v1/messages"
OPENAI_ENDPOINT = "/v1/chat/completions"
SIGNED_TOKEN_REFERENCE: Final[str] = "${SSAK_ACCESS_TOKEN:?set a token issued by /api/auth/login}"
CREDENTIAL_ENV_KEYS: Final[frozenset[str]] = frozenset({"ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY"})


class UnknownAgentError(ValueError):
    """지원하지 않는 에이전트 이름."""


@dataclass(frozen=True, slots=True)
class AgentBridgeSpec:
    """한 에이전트의 연결 스펙."""

    name: str
    display_name: str
    protocol: BridgeProtocol
    # 에이전트가 LLM 백엔드를 가리킬 때 쓰는 환경변수들 (값은 resolve 시 채움)
    env_vars: tuple[tuple[str, str], ...] = field(default_factory=tuple)


AGENT_BRIDGES: dict[str, AgentBridgeSpec] = {
    "claude": AgentBridgeSpec(
        name="claude",
        display_name="Claude Code",
        protocol="anthropic",
        env_vars=(
            ("ANTHROPIC_BASE_URL", "{api_base}"),
            ("ANTHROPIC_AUTH_TOKEN", "{access_token}"),
            ("ANTHROPIC_MODEL", "{model}"),
            # 미등록 모델 컨텍스트 윈도 등록 (보수 자동압축 방지) — {context_window}는
            # resolve_bridge가 ModelRegistry context_length로 채움 (모르면 200000).
            ("CLAUDE_CODE_MAX_CONTEXT_TOKENS", "{context_window}"),
            ("ANTHROPIC_SMALL_FAST_MODEL", "{model}"),
            ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "{model}"),
            ("ANTHROPIC_DEFAULT_SONNET_MODEL", "{model}"),
        ),
    ),
    "codex": AgentBridgeSpec(
        name="codex",
        display_name="OpenAI Codex",
        protocol="openai",
        env_vars=(
            ("OPENAI_BASE_URL", "{api_base}"),
            ("OPENAI_API_KEY", "{access_token}"),
            ("AGK_BRIDGE_MODEL", "{model}"),
        ),
    ),
    "opencode": AgentBridgeSpec(
        name="opencode",
        display_name="OpenCode",
        protocol="openai",
        env_vars=(
            ("OPENAI_BASE_URL", "{api_base}"),
            ("OPENAI_API_KEY", "{access_token}"),
            ("AGK_BRIDGE_MODEL", "{model}"),
        ),
    ),
    "openclaw": AgentBridgeSpec(
        name="openclaw",
        display_name="OpenClaw",
        protocol="anthropic",
        env_vars=(
            ("ANTHROPIC_BASE_URL", "{api_base}"),
            ("ANTHROPIC_AUTH_TOKEN", "{access_token}"),
            ("ANTHROPIC_MODEL", "{model}"),
        ),
    ),
    "hermes": AgentBridgeSpec(
        name="hermes",
        display_name="Hermes Agent",
        protocol="openai",
        env_vars=(
            ("OPENAI_BASE_URL", "{api_base}"),
            ("OPENAI_API_KEY", "{access_token}"),
            ("AGK_BRIDGE_MODEL", "{model}"),
        ),
    ),
}


def resolve_bridge(
    agent: str,
    *,
    model: str = "",
    api_base: str = "",
    default_model: str = "",
    context_window: int = 0,
) -> tuple[AgentBridgeSpec, dict[str, str]]:
    """에이전트 이름으로 브리지 스펙과 환경변수 값을 확정한다.

    Args:
        agent: 에이전트 이름 (claude, codex, opencode, openclaw, hermes).
        model: 사용할 모델 이름. 비우면 default_model로 폴백.
        api_base: Ssak-Ai API base URL. 비우면 http://127.0.0.1:<port> 형식.
        default_model: model이 비었을 때 사용할 기본 모델.
        context_window: 모델의 실제 컨텍스트 윈도 (토큰). 0이면 보수 기본값 200000.
            Claude Code의 CLAUDE_CODE_MAX_CONTEXT_TOKENS용 (Phase 36).

    Returns:
        (스펙, 환경변수 dict)

    Raises:
        UnknownAgentError: 지원하지 않는 에이전트.

    """
    spec = AGENT_BRIDGES.get(agent.strip().casefold())
    if spec is None:
        supported = ", ".join(sorted(AGENT_BRIDGES))
        raise UnknownAgentError(
            f"지원하지 않는 에이전트: '{agent}'. 지원 목록: {supported}",
        )

    resolved_model = (model or default_model).strip()
    if not resolved_model:
        raise UnknownAgentError("모델이 필요합니다. --model 또는 기본 모델을 지정하세요.")

    base = (api_base or "http://127.0.0.1:8000").rstrip("/")
    # /v1 접미사 규약이 프로토콜마다 다르다 (Phase 36 수정):
    # - openai 계열(codex 등): 클라이언트가 base + "/chat/completions"|"/responses"를
    #   호출하므로 /v1 포함이 정답 (Phase 35 라이브 검증).
    # - anthropic 계열(claude 등): 클라이언트가 스스로 /v1/messages를 붙이므로
    #   /v1 접미사가 있으면 /v1/v1/messages로 404. 접미사 없이 전달.
    needs_v1 = spec.protocol == "openai"
    full_base = (base if base.endswith("/v1") else f"{base}/v1") if needs_v1 else base.removesuffix("/v1")

    env: dict[str, str] = {}
    for key, template in spec.env_vars:
        env[key] = template.format(
            api_base=full_base,
            model=resolved_model,
            context_window=str(context_window) if context_window > 0 else "200000",
            access_token=SIGNED_TOKEN_REFERENCE,
        )

    return spec, env


def format_bridge_plan(spec: AgentBridgeSpec, env: dict[str, str]) -> str:
    """브리지 연결 안내를 마크다운으로 렌더링."""
    endpoint = ANTHROPIC_ENDPOINT if spec.protocol == "anthropic" else OPENAI_ENDPOINT
    if spec.name == "codex":
        endpoint = "/v1/responses"
    lines = [
        f"# {spec.display_name} ↔ Ssak-Ai 브리지",
        "",
        f"- 프로토콜: {spec.protocol} 호환 (`{endpoint}`)",
        "- Ssak-Ai API 서버가 실행 중이어야 합니다: `uv run agk serve`",
        "- 이 명령은 연결 계획만 출력합니다. 에이전트를 실행하거나 연결을 검증하지 않습니다.",
        "- `/api/auth/login`에서 발급한 서명 토큰을 터미널의 `SSAK_ACCESS_TOKEN` 변수로 지정하세요.",
        "",
        "## 환경변수 설정",
        "",
        "```bash",
    ]
    if spec.protocol == "anthropic":
        lines.append("unset ANTHROPIC_API_KEY")
    for key, value in env.items():
        if key == "ANTHROPIC_API_KEY":
            continue
        rendered = f'"{SIGNED_TOKEN_REFERENCE}"' if key in CREDENTIAL_ENV_KEYS else quote(value)
        lines.append(f"export {key}={rendered}")
    lines.extend(["```", "", "설정 후 해당 에이전트를 실행하면 Ssak-Ai의 로컬 모델이 사용됩니다."])
    if spec.name == "claude":
        model_id = env.get("ANTHROPIC_MODEL", "")
        lines.extend(
            [
                "",
                "## (선택) /model 피커 등록 — unrecognized_model 경고 제거",
                "",
                f"`{model_id}`가 CC 모델 카탈로그에 없으면 ~/.claude/settings.json에 매핑을 추가합니다:",
                "",
                "```json",
                json.dumps(
                    {"modelPicker": {"options": [{"model": model_id, "behavesAs": "claude-sonnet-4-6"}]}},
                    indent=2,
                ),
                "```",
                "",
                "- `behavesAs`는 CC 내장 모델 키를 사용합니다 (claude-sonnet-4-6 등).",
                "- `CLAUDE_CODE_MAX_CONTEXT_TOKENS`가 모델의 실제 컨텍스트 윈도라서",
                "  미설정 시 보수 기본 윈도로 자동 압축이 걸립니다.",
            ],
        )
    if spec.name == "codex":
        model_id = env.get("AGK_BRIDGE_MODEL", "")
        base_option = "model_providers.ssak.base_url=" + json.dumps(
            env.get("OPENAI_BASE_URL", ""),
            ensure_ascii=False,
        )
        lines.extend(
            [
                "",
                "## Codex CLI 실연결 (config 오버라이드 — env만으로는 부족)",
                "",
                "```bash",
                "codex exec --sandbox read-only --skip-git-repo-check \\",
                "  -c model_provider=ssak \\",
                f"  -c {quote(base_option)} \\",
                "  -c 'model_providers.ssak.env_key=\"OPENAI_API_KEY\"' \\",
                "  -c 'model_providers.ssak.wire_api=\"responses\"' \\",
                f'  -m {quote(model_id)} "<prompt>" < /dev/null',
                "```",
                "",
                '- Codex 0.150+는 Responses API만 지원합니다 (wire_api="chat" 제거됨).',
                "- exec 모드는 stdin을 `< /dev/null`로 끊어야 stdin 대기로 멈추지 않습니다.",
            ],
        )
    return "\n".join(lines)
