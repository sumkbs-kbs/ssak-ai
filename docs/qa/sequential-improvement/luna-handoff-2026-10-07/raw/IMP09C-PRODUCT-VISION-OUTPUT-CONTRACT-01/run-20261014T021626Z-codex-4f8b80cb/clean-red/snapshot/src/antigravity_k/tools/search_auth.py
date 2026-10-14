"""원격 검색 백엔드 자격 증명 — 단일 정책 지점.

Ssak-Ai의 HTTP 검색 adapter 세 곳(`web_search_engine._search_self_hosted`,
`web_search_tool._sync_search_self_hosted`, `ssak_search_client.search`)은 모두 같은
백엔드(`AGK_SEARCH_ENGINE_URL` 의 `/api/search`)를 호출한다. 그 백엔드는 기본 모드에서
`Authorization: Bearer <key>` 를 요구하는데(W의 `src/middleware/api-auth.ts`,
`validateApiKeyAsync` — `AUTH_OPEN_MODE` 미설정 시 closed) 어느 adapter도 헤더를 보내지
않아, 기본 배포에서 self-hosted provider가 **조용히 401을 받고 빈 결과로 강등**됐다.

규칙을 한 곳에 두는 이유는 세 adapter가 서로 다르게 굴지 않게 하기 위해서다:
`JINA_API_KEY`/`TAVILY_API_KEY` 처럼 각자 env를 읽던 관행을 그대로 두면 다음 adapter가
또 하나의 예외가 된다.

비밀 위생:
- 값은 로그·오류 메시지·모델 컨텍스트 어디에도 남기지 않는다(`redact_secret`).
- `_FILE` 변형을 지원해 프로세스 인자/환경 덤프에 노출되는 면적을 줄일 수 있다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import suppress

#: 검색 백엔드 bearer. `AGK_SEARCH_ENGINE_URL` 과 같은 접두사를 쓴다.
SEARCH_TOKEN_ENV = "AGK_SEARCH_ENGINE_TOKEN"
#: 토큰이 담긴 파일 경로. 값 자체보다 이쪽이 안전하다(ps/환경 덤프 회피).
SEARCH_TOKEN_FILE_ENV = "AGK_SEARCH_ENGINE_TOKEN_FILE"
#: 토큰이 없을 때 진단 메시지가 가리킬 이름(테스트/문서가 같은 문자열을 쓰게 한다).
REDACTED = "***redacted***"


def resolve_search_token(env: Mapping[str, str] | None = None) -> str | None:
    """환경(또는 파일)에서 bearer를 읽는다. 없으면 None."""
    source: Mapping[str, str] = os.environ if env is None else env
    direct = (source.get(SEARCH_TOKEN_ENV) or "").strip()
    if direct:
        return direct
    path = (source.get(SEARCH_TOKEN_FILE_ENV) or "").strip()
    if not path:
        return None
    with suppress(OSError):
        with open(path, encoding="utf-8") as handle:
            token = handle.read().strip()
        return token or None
    return None


def search_auth_headers(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """검색 백엔드 요청에 실을 인증 헤더. 토큰이 없으면 빈 dict.

    열린 모드(`AUTH_OPEN_MODE=1`)의 로컬 백엔드는 토큰이 없어도 동작하므로
    빈 dict 를 돌려주는 것이 정상 경로다.
    """
    token = resolve_search_token(env)
    return {"Authorization": f"Bearer {token}"} if token else {}


def auth_is_configured(env: Mapping[str, str] | None = None) -> bool:
    return resolve_search_token(env) is not None


def redact_secret(text: str, env: Mapping[str, str] | None = None) -> str:
    """문자열에 섞여 들어온 토큰을 지운다.

    업스트림 응답 본문이나 예외 문자열을 그대로 로그/모델에 넘기는 경로가 생기면
    공유 비밀이 transcript 에 박히므로, 노출면을 만들 때는 항상 이 함수를 통과시킨다.
    """
    token = resolve_search_token(env)
    return text.replace(token, REDACTED) if token else text
