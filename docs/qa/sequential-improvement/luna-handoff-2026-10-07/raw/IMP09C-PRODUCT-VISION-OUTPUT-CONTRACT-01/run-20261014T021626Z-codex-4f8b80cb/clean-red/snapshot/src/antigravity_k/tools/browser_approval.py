"""브라우저 효과의 위험도 분류·승인 바인딩·사용자 인계 — task 18.

task 17 이 "무엇을 보고 무엇을 조작하는가"를 계약으로 묶었지만, 그 계약에는 **"이 행동이
무슨 의미인가"** 가 없었다. 그래서 클릭 한 번이 검색 버튼일 수도, 송금 버튼일 수도 있었고
둘 다 같은 경로로 실행됐다. 이 모듈이 그 빈 자리를 채운다.

세 가지 원칙:

1. **승인은 서버가 발급하고, 사람이 그 내용을 본다.** 모델은 토큰을 만들 수 없다 —
   이 모듈이 발급한 토큰만 통하고(형식만 흉내 낸 문자열은 `MODEL_TOKEN_REFUSED`),
   발급은 **사람의 해결(resolution)** 없이는 일어나지 않는다. 그래서 "무조건 자동 승인"
   설정은 존재하지 않는다.
2. **승인은 그 순간의 그 행동에만 묶인다.** 티켓은
   `owner · session · origin · action · ref · payload hash · generation · expiry(기본 60초)`
   전부에 묶이고 **한 번만** 소비된다. 페이지가 바뀌거나(DOM → generation), 주소가 바뀌거나
   (origin), 내용이 바뀌면(금액 등 → payload hash) **재승인**이다 — 모델이 승인 이후에
   몰래 다른 것을 보내려 해도 문이 없다.
3. **불확실하면 승인이다.** 분류기는 행동 이름이 아니라 **동작 의미**(요소의 역할·이름·주소·
   페이로드)로 판정하고, 어느 규칙에도 걸리지 않으면 `unknown` → 승인 필요다.
   페이지 문구가 "auto-approved"라고 주장해도 그것은 페이지의 주장일 뿐 판정에 쓰이지 않는다.

로그인 비밀은 **모델을 지나지 않는다**. 운영자가 넣은 비밀은 opaque handle(`sec_…`)로만
가리키고, 모델은 handle 조차도 값으로 바꿀 수 없다(평문 `value` 로 비밀 필드를 채우면
`SECRET_VALUE_NOT_ALLOWED`). handle 은 owner 에 묶이고 선택적으로 origin 에 못박힌다 —
피싱 페이지가 같은 handle 을 재사용하려 해도 주소가 다르면 거절된다.

MFA·CAPTCHA 는 실패가 아니라 **사람 차례**다(`handoff_signal` → 상태 `waiting_user`).
자동 재시도도, 자동 승인도 없다 — 코드를 사람이 넣어야 하는 일은 사람이 한다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final, Protocol, cast
from urllib.parse import urlsplit

from antigravity_k.tools.browser_observation import _maybe_await  # pyright: ignore[reportPrivateUsage]

logger = logging.getLogger(__name__)

APPROVAL_SCHEMA: Final = "ssak.browser.approval/1.0"
HANDOFF_SCHEMA: Final = "ssak.browser.handoff/1.0"

# 승인 티켓의 수명. 사람이 내용을 보고 누르기까지의 창이다 — 길게 두면 그 사이에 페이지가
# 바뀌어도 통과하는 창이 넓어지고, 짧게 두면 사람이 누르기 전에 만료된다.
DEFAULT_APPROVAL_TTL_SECONDS: Final = 60.0
MAX_TTL_SECONDS: Final = 600.0

# ── 오류 코드 ────────────────────────────────────────────────────────────────
APPROVAL_REQUIRED: Final = "APPROVAL_REQUIRED"
APPROVAL_REJECTED: Final = "APPROVAL_REJECTED"
APPROVAL_REPLAYED: Final = "APPROVAL_REPLAYED"
APPROVAL_EXPIRED: Final = "APPROVAL_EXPIRED"
APPROVAL_BINDING_CHANGED: Final = "APPROVAL_BINDING_CHANGED"
MODEL_TOKEN_REFUSED: Final = "MODEL_TOKEN_REFUSED"
MODEL_CLAIM_REFUSED: Final = "MODEL_CLAIM_REFUSED"
ALWAYS_ALLOW_FORBIDDEN: Final = "ALWAYS_ALLOW_FORBIDDEN"
SECRET_VALUE_NOT_ALLOWED: Final = "SECRET_VALUE_NOT_ALLOWED"
SECRET_HANDLE_UNKNOWN: Final = "SECRET_HANDLE_UNKNOWN"
SECRET_ORIGIN_MISMATCH: Final = "SECRET_ORIGIN_MISMATCH"
HANDOFF_REQUIRED: Final = "HANDOFF_REQUIRED"

# 모델이 스스로 "이건 안전하다/승인됐다"고 주장할 수 있는 필드들. 요청 본문에 있으면 거절한다 —
# 위험도는 서버가 요소의 의미로 판정하는 것이지 호출자가 선언하는 것이 아니다.
MODEL_CLAIM_FIELDS: Final = frozenset(
    {
        "approved",
        "approval_granted",
        "auto_approve",
        "auto_approved",
        "skip_approval",
        "always_allow",
        "allow_without_approval",
        "risk",
        "risk_level",
        "effect",
        "effect_class",
        "dangerous",
    }
)

_TOKEN_PREFIX: Final = "ssak1"

_HANDOFF_STATUS: Final = "waiting_user"


class BrowserApprovalError(RuntimeError):
    """승인 계약 위반. 코드는 공통 결과 계약의 어휘를 따른다."""

    def __init__(self, code: str, message: str, *, details: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details: dict[str, object] = dict(details or {})

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"error_code": self.code, "detail": str(self)}
        if self.details:
            payload["context"] = dict(self.details)
        return payload


# ── 효과 분류 ────────────────────────────────────────────────────────────────
class Effect(str, Enum):
    """행동의 **의미**. 도구 이름이 아니라 사용자에게 무엇을 하는지다."""

    READ = "read"  # 관찰·스크롤·검색 질의
    NAVIGATE = "navigate"  # 평범한 링크 이동
    INPUT = "input"  # 일반 입력칸에 값 넣기
    DOWNLOAD = "download"  # 샌드박스로 파일 받기
    SETTINGS = "settings"  # 설정·토글 변경
    TRANSMIT = "transmit"  # 전송·게시·제출·메시지
    UPLOAD = "upload"  # 로컬 파일을 바깥으로 내보내기
    AUTH = "auth"  # 로그인·비밀·인증 수단
    PERMISSION = "permission"  # 공유·초대·권한 부여
    DELETE = "delete"  # 삭제·해지·탈퇴
    FINANCIAL = "financial"  # 결제·송금·구매
    UNKNOWN = "unknown"  # 판정 불가 → 승인


# 승인이 필요한 효과. 여기 없는 것만 자동으로 지나간다.
REQUIRES_APPROVAL: Final[frozenset[Effect]] = frozenset(
    {
        Effect.SETTINGS,
        Effect.TRANSMIT,
        Effect.UPLOAD,
        Effect.AUTH,
        Effect.PERMISSION,
        Effect.DELETE,
        Effect.FINANCIAL,
        Effect.UNKNOWN,
    }
)

_RISK_BY_EFFECT: Final[dict[Effect, str]] = {
    Effect.READ: "safe",
    Effect.NAVIGATE: "low",
    Effect.INPUT: "low",
    Effect.DOWNLOAD: "low",
    Effect.SETTINGS: "medium",
    Effect.UNKNOWN: "medium",
    Effect.TRANSMIT: "high",
    Effect.UPLOAD: "high",
    Effect.AUTH: "high",
    Effect.PERMISSION: "high",
    Effect.DELETE: "critical",
    Effect.FINANCIAL: "critical",
}

# 위험한 것부터 검사한다 — 아래로 갈수록 덜 위험하다. "Delete and pay" 는 결제로 판정돼야 한다.
_HINTS: Final[tuple[tuple[Effect, tuple[str, ...]], ...]] = (
    (
        Effect.FINANCIAL,
        (
            "pay now",
            "payment",
            "checkout",
            "purchase",
            "buy now",
            "add to cart",
            "place order",
            "transfer",
            "remit",
            "wire",
            "donate",
            "subscribe",
            "billing",
            "credit card",
            "card number",
            "결제",
            "송금",
            "구매",
            "후원",
            "구독",
            "입금",
        ),
    ),
    (
        Effect.DELETE,
        (
            "delete",
            "remove",
            "destroy",
            "purge",
            "erase",
            "close account",
            "cancel account",
            "cancel order",
            "cancel subscription",
            "cancel booking",
            "unsubscribe",
            "deactivate",
            "탈퇴",
            "삭제",
            "해지",
            "취소",
        ),
    ),
    (
        Effect.AUTH,
        (
            "sign in",
            "log in",
            "login",
            "sign up",
            "password",
            "passcode",
            "one-time code",
            "verification code",
            "authenticate",
            "two-factor",
            "2fa",
            "mfa",
            "security key",
            "로그인",
            "비밀번호",
            "인증",
            "회원가입",
        ),
    ),
    (
        Effect.PERMISSION,
        (
            "invite",
            "grant access",
            "share with",
            "add member",
            "add user",
            "make admin",
            "change role",
            "manage access",
            "permissions",
            "초대",
            "공유",
            "권한",
            "멤버 추가",
        ),
    ),
    (
        Effect.TRANSMIT,
        (
            "send",
            "submit",
            "publish",
            "post",
            "reply",
            "comment",
            "tweet",
            "message",
            "email",
            "apply",
            "confirm order",
            "accept offer",
            "전송",
            "보내",
            "게시",
            "등록",
            "댓글",
            "제출",
            "신청",
        ),
    ),
    (
        Effect.SETTINGS,
        (
            "settings",
            "preferences",
            "configure",
            "enable",
            "disable",
            "turn on",
            "turn off",
            "install",
            "설정",
            "해제",
            "활성화",
        ),
    ),
    (
        # 페이지 이동 자체는 egress 규칙이 맡으므로 자동이다. 다만 **"계속하기" 류는 넣지 않는다** —
        # 그 버튼이 결제나 전송의 다음 단계일 수 있고, 모르면 묻는 것이 이 모듈의 규칙이다.
        Effect.NAVIGATE,
        (
            "next page",
            "previous page",
            "next",
            "previous",
            "pagination",
            "back to",
            "더 보기",
            "다음 페이지",
            "이전 페이지",
        ),
    ),
    (
        Effect.READ,
        (
            "search",
            "filter",
            "sort",
            "more",
            "refresh",
            "reload",
            "expand",
            "collapse",
            "copy",
            "link",
            "검색",
            "정렬",
            "필터",
        ),
    ),
)

# 전송 수단이 되는 URL 스킴 — 클릭 한 번이 곧 메시지 발송이다.
_TRANSMIT_SCHEMES: Final = frozenset({"mailto", "tel", "sms", "callto"})
# 조작할 수 없는 스킴(계약 밖). 분류 결과와 무관하게 실행 단계에서 거절된다.
_EXECUTABLE_SCHEMES: Final = frozenset({"javascript", "data", "blob", "file"})
# 주소 경로만 보고도 알 수 있는 의미.
_PATH_HINTS: Final[tuple[tuple[Effect, tuple[str, ...]], ...]] = (
    (Effect.DELETE, ("/delete", "/remove", "/destroy", "/purge", "/deactivate", "/unsubscribe")),
    (Effect.AUTH, ("/login", "/signin", "/sign-in", "/signup", "/sign-up", "/logout", "/auth", "/password")),
    (Effect.FINANCIAL, ("/pay", "/payment", "/checkout", "/billing", "/purchase", "/order", "/transfer")),
    (Effect.TRANSMIT, ("/send", "/submit", "/publish", "/post", "/comment", "/message", "/contact")),
)
_MESSAGE_FIELD_HINTS: Final = (
    "message",
    "comment",
    "reply",
    "post",
    "tweet",
    "body",
    "content",
    "email body",
    "메시지",
    "댓글",
    "내용",
)


@dataclass(frozen=True)
class EffectDecision:
    """`classify_effect` 의 판정. **왜** 그렇게 봤는지까지 남긴다(사람이 승인 화면에서 본다)."""

    effect: Effect
    requires_approval: bool
    risk: str
    reason: str
    matched: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "effect": self.effect.value,
            "risk": self.risk,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "matched": self.matched,
        }


def origin_of(url: str) -> str:
    """`scheme://host[:port]`. 승인 바인딩의 한 축이라 정규화를 한 곳에서만 한다."""
    if not url:
        return ""
    parts = urlsplit(url)
    if not parts.scheme or not parts.hostname:
        return parts.scheme or ""
    if parts.port is not None:
        return f"{parts.scheme}://{parts.hostname}:{parts.port}"
    return f"{parts.scheme}://{parts.hostname}"


def _match(haystack: str, needles: Sequence[str]) -> str:
    for needle in needles:
        if needle in haystack:
            return needle
    return ""


def classify_effect(
    action: str,
    *,
    role: str = "",
    name: str = "",
    tag: str = "",
    url: str = "",
    text: str | None = None,
    value: str | None = None,
    path: str | None = None,
    secret: bool = False,
    disabled: bool = False,
    eager: bool = False,
) -> EffectDecision:
    """행동 + 대상의 **의미**로 효과를 판정한다. 불확실하면 승인 쪽으로 기운다.

    판정 근거는 요소가 스스로 말하는 것(역할·접근성 이름·태그·주소·페이로드)뿐이다.
    페이지 문구나 모델의 주장은 근거가 아니다 — 그것들은 이 함수의 입력이 아니다.
    """
    if action in {"observe", "snapshot", "scroll"}:
        return EffectDecision(Effect.READ, False, _RISK_BY_EFFECT[Effect.READ], "관찰·스크롤은 페이지를 바꾸지 않는다")
    if action == "download":
        return EffectDecision(
            Effect.DOWNLOAD, False, _RISK_BY_EFFECT[Effect.DOWNLOAD], "다운로드는 작업 샌드박스 안에만 쓴다"
        )
    if action == "goto":
        parts = urlsplit(url or "")
        if parts.scheme in _TRANSMIT_SCHEMES:
            return EffectDecision(
                Effect.TRANSMIT, True, _RISK_BY_EFFECT[Effect.TRANSMIT], f"{parts.scheme} 이동은 메시지 발송이다"
            )
        if parts.scheme in _EXECUTABLE_SCHEMES:
            return EffectDecision(Effect.UNKNOWN, True, _RISK_BY_EFFECT[Effect.UNKNOWN], "스킴을 실행하는 이동이다")
        return EffectDecision(
            Effect.NAVIGATE, False, _RISK_BY_EFFECT[Effect.NAVIGATE], "주소 이동은 egress 규칙이 맡는다"
        )
    if action == "upload":
        return EffectDecision(Effect.UPLOAD, True, _RISK_BY_EFFECT[Effect.UPLOAD], "로컬 파일을 바깥으로 내보낸다")
    if action not in {"click", "fill", "select"}:
        return EffectDecision(Effect.UNKNOWN, True, _RISK_BY_EFFECT[Effect.UNKNOWN], f"계약에 없는 행동: {action}")

    haystack = " ".join(part for part in (name, tag, role, path or "") if part).lower()
    url_hints = f"{url} {path or ''}".lower()

    if action == "fill" and secret:
        return EffectDecision(
            Effect.AUTH, True, _RISK_BY_EFFECT[Effect.AUTH], "비밀 필드를 채우는 것은 인증 행위다", "secret"
        )
    if tag.lower() == "input" and (path or "").lower().endswith((".png", ".jpg", ".jpeg", ".pdf", ".csv", ".zip")):
        # file 입력칸에 경로가 온 것은 업로드다(계약 action 은 upload 지만 방어적으로 본다).
        return EffectDecision(Effect.UPLOAD, True, _RISK_BY_EFFECT[Effect.UPLOAD], "파일 입력칸이다", "input[file]")

    scheme = urlsplit(url or "").scheme
    if scheme in _TRANSMIT_SCHEMES:
        return EffectDecision(
            Effect.TRANSMIT, True, _RISK_BY_EFFECT[Effect.TRANSMIT], f"{scheme} 링크는 메시지 발송이다", scheme
        )
    if scheme in _EXECUTABLE_SCHEMES:
        return EffectDecision(Effect.UNKNOWN, True, _RISK_BY_EFFECT[Effect.UNKNOWN], "실행 스킴 링크", scheme)

    for effect, needles in _PATH_HINTS:
        hit = _match(url_hints, needles)
        if hit:
            return EffectDecision(effect, True, _RISK_BY_EFFECT[effect], f"주소가 {effect.value} 를 가리킨다", hit)

    for effect, needles in _HINTS:
        hit = _match(haystack, needles)
        if hit:
            requires = effect in REQUIRES_APPROVAL
            return EffectDecision(
                effect, requires, _RISK_BY_EFFECT[effect], f"이름/역할이 {effect.value} 를 가리킨다", hit
            )

    if action == "click":
        if role == "link" and url:
            return EffectDecision(
                Effect.NAVIGATE, False, _RISK_BY_EFFECT[Effect.NAVIGATE], "평범한 링크 이동", "a[href]"
            )
        if role in {"button", "menuitem", "tab", "checkbox", "radio", "switch", "slider"} or tag.lower() == "button":
            return EffectDecision(
                Effect.UNKNOWN, True, _RISK_BY_EFFECT[Effect.UNKNOWN], "무엇을 하는 버튼인지 이름만으로 알 수 없다"
            )
        return EffectDecision(Effect.UNKNOWN, True, _RISK_BY_EFFECT[Effect.UNKNOWN], "클릭의 의미를 판정할 수 없다")
    if action == "fill":
        payload = f"{text or ''} {value or ''}".lower()
        if path and not payload.strip():
            return EffectDecision(Effect.UPLOAD, True, _RISK_BY_EFFECT[Effect.UPLOAD], "파일 경로를 넣는 입력이다")
        if eager:
            # 값이 바뀌는 순간 무언가 나가는 칸(자동저장 처리기) — 이름이 무해해도 채우는 것은 전송이다.
            return EffectDecision(
                Effect.TRANSMIT,
                True,
                _RISK_BY_EFFECT[Effect.TRANSMIT],
                "값이 바뀌는 순간 서버로 나가는 칸이다(자동저장 처리기)",
                "autosave-handler",
            )
        hit = _match(f"{haystack} {payload}", _MESSAGE_FIELD_HINTS)
        if hit:
            return EffectDecision(
                Effect.TRANSMIT, True, _RISK_BY_EFFECT[Effect.TRANSMIT], "메시지로 나갈 수 있는 필드다", hit
            )
        return EffectDecision(Effect.INPUT, False, _RISK_BY_EFFECT[Effect.INPUT], "일반 입력칸", "")
    # select
    if disabled:
        return EffectDecision(Effect.UNKNOWN, True, _RISK_BY_EFFECT[Effect.UNKNOWN], "비활성 요소를 조작하려 했다")
    return EffectDecision(Effect.SETTINGS, True, _RISK_BY_EFFECT[Effect.SETTINGS], "선택은 폼 상태를 바꾼다")


# ── 승인 바인딩·티켓 ─────────────────────────────────────────────────────────
def _sha16(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def payload_fingerprint(
    *,
    action: str,
    url: str | None = None,
    text: str | None = None,
    value: str | None = None,
    path: str | None = None,
    delta: int | None = None,
    value_kind: str = "text",
) -> str:
    """행동 내용의 지문. **평문을 담지 않는다** — 승인 요청은 UI·DB·로그를 지나간다.

    비밀이면 값이 아니라 **handle** 을 받는다(`value_kind="secret_handle"`).
    """
    canonical = json.dumps(
        {
            "action": action,
            "url": url or "",
            "text_sha": _sha16(text) if text else "",
            "value_sha": _sha16(value) if value else "",
            "value_kind": value_kind if value else "",
            "path": path or "",
            "delta": delta,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _norm_origin(origin: str) -> str:
    return origin_of(origin) if "://" in origin else origin.lower()


@dataclass(frozen=True)
class ApprovalBinding:
    """승인이 묶이는 좌표. 하나라도 달라지면 그 승인은 다른 행동의 것이다."""

    owner_key: str
    session_tag: str
    origin: str
    action: str
    ref: str
    payload_hash: str
    generation: int
    effect: str
    fingerprint: str = ""

    def __post_init__(self) -> None:
        normalized_origin = _norm_origin(self.origin)
        if normalized_origin != self.origin:
            object.__setattr__(self, "origin", normalized_origin)
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", self._compute_fingerprint())

    def _compute_fingerprint(self) -> str:
        canonical = json.dumps(
            {
                "schema": APPROVAL_SCHEMA,
                "owner": self.owner_key,
                "session": self.session_tag,
                "origin": self.origin,
                "action": self.action,
                "ref": self.ref,
                "payload": self.payload_hash,
                "generation": self.generation,
                "effect": self.effect,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def field_differences(self, other: ApprovalBinding) -> list[str]:
        """어긋난 축의 **이름**만 돌려준다(값은 돌려주지 않는다 — 승인 화면에 값을 되풀이하지 않는다)."""
        names = ("owner_key", "session_tag", "origin", "action", "ref", "payload_hash", "generation", "effect")
        return [name for name in names if getattr(self, name) != getattr(other, name)]

    def to_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner_key[:12],
            "session_tag": self.session_tag,
            "origin": self.origin,
            "action": self.action,
            "ref": self.ref,
            "payload_hash": self.payload_hash[:16],
            "generation": self.generation,
            "effect": self.effect,
            "fingerprint": self.fingerprint[:16],
        }


@dataclass(frozen=True)
class HumanResolution:
    """사람이 실제로 내린 결정의 **서버 측 증거**. 이것 없이는 티켓이 발급되지 않는다."""

    request_id: str
    decision: str  # approve / deny / always_allow
    resolved_at: float

    @property
    def is_approval(self) -> bool:
        return self.decision == "approve"


@dataclass(frozen=True)
class ApprovalTicket:
    ticket_id: str
    token: str
    binding: ApprovalBinding
    issued_at: float
    expires_at: float
    request_id: str
    consumed_at: float | None = None

    def is_expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def to_dict(self, *, include_token: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": APPROVAL_SCHEMA,
            "ticket_id": self.ticket_id,
            "request_id": self.request_id,
            "binding": self.binding.to_dict(),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "ttl_seconds": round(self.expires_at - self.issued_at, 3),
            "consumed": self.is_consumed,
        }
        if include_token:
            payload["approval_token"] = self.token
        return payload


@dataclass(frozen=True)
class ApprovalRequirement:
    """사람에게 물어야 하는 한 건. `summary` 는 **무엇을** 승인하는지 사람이 읽는 문장이다."""

    request_id: str
    binding: ApprovalBinding
    effect: str
    risk: str
    reason: str
    summary: str
    created_at: float
    expires_at: float

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": APPROVAL_SCHEMA,
            "request_id": self.request_id,
            "effect": self.effect,
            "risk": self.risk,
            "reason": self.reason,
            "summary": self.summary,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "binding": self.binding.to_dict(),
        }


def _preview(value: str | None, limit: int = 120) -> str:
    if not value:
        return ""
    text = value.strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def summarize_effect(
    decision: EffectDecision,
    *,
    action: str,
    origin: str,
    name: str = "",
    role: str = "",
    text: str | None = None,
    value: str | None = None,
    value_kind: str = "text",
    secret_name: str = "",
) -> str:
    """사람이 읽는 한 줄. 비밀 값은 **이름만** 넣는다(값은 어디에도 남기지 않는다)."""
    target = name or role or "(이름 없는 요소)"
    where = origin or "(주소 없음)"
    if value_kind == "secret_handle" and secret_name:
        return f"{where} 에서 {target} 에 저장된 비밀 '{secret_name}' 을(를) 채웁니다 — {decision.reason}"
    detail = _preview(text if text is not None else value)
    suffix = f' 내용 "{detail}"' if detail else ""
    return f"{where} 에서 {target} 을(를) {action} 합니다{suffix} — {decision.reason}"


# ── 게이트 ───────────────────────────────────────────────────────────────────
class _Clock(Protocol):
    def __call__(self) -> float: ...


class BrowserApprovalGate:
    """승인 **원장**. 발급은 사람의 해결로만, 소비는 한 번만.

    이 클래스는 스레드 안전하다(API 는 스레드풀에서 돌고 도구 경로는 워커 스레드에서 돈다).
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_APPROVAL_TTL_SECONDS,
        clock: _Clock = time.time,
        max_entries: int = 128,
    ) -> None:
        self.ttl_seconds = max(1.0, min(float(ttl_seconds), MAX_TTL_SECONDS))
        self._clock = clock
        self._max_entries = max(8, int(max_entries))
        self._lock = threading.RLock()
        self._pending: dict[str, ApprovalRequirement] = {}
        self._tickets: dict[str, ApprovalTicket] = {}
        self._by_request: dict[str, str] = {}  # request_id → ticket_id (해결 1건 = 티켓 1장)

    # ── 서버 측: 물어볼 것 등록 ──
    def register(
        self,
        binding: ApprovalBinding,
        decision: EffectDecision,
        *,
        summary: str = "",
        request_id: str | None = None,
    ) -> ApprovalRequirement:
        """승인 요청을 **서버가** 만든다. request_id 를 모델이 주게 두지 않는다(기본은 발급)."""
        now = self._clock()
        requirement = ApprovalRequirement(
            request_id=request_id or f"breq_{secrets.token_hex(12)}",
            binding=binding,
            effect=decision.effect.value,
            risk=decision.risk,
            reason=decision.reason,
            summary=summary or f"{binding.origin} 에서 {binding.action} — {decision.reason}",
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )
        with self._lock:
            self._evict_locked(now)
            self._pending[requirement.request_id] = requirement
        logger.info(
            "[BrowserApproval] requested request=%s effect=%s origin=%s action=%s",
            requirement.request_id,
            requirement.effect,
            requirement.binding.origin,
            requirement.binding.action,
        )
        return requirement

    def pending(self, request_id: str) -> ApprovalRequirement | None:
        with self._lock:
            return self._pending.get(request_id)

    def list_pending(self) -> list[ApprovalRequirement]:
        now = self._clock()
        with self._lock:
            self._evict_locked(now)
            return list(self._pending.values())

    def withdraw(self, request_id: str) -> bool:
        """사람이 거절했거나 요청이 끝나 **더 이상 실행될 수 없는** 요청을 원장에서 뺀다.

        이게 없으면 거절된 요청이 TTL(60초)까지 목록에 남아, 화면이 이미 거절한 승인을 다시
        권한다. 발급(`issue`)은 그대로이고, 발급되지 않은 것만 치운다.
        """
        with self._lock:
            if request_id in self._by_request:
                return False
            return self._pending.pop(request_id, None) is not None

    # ── 서버 측: 사람의 해결 → 티켓 발급 ──
    def issue(self, binding: ApprovalBinding, resolution: HumanResolution) -> ApprovalTicket:
        """사람이 승인한 요청에 대해서만, **그때 물어본 좌표 그대로** 티켓을 발급한다."""
        with self._lock:
            now = self._clock()
            requirement = self._pending.get(resolution.request_id)
            if requirement is None:
                raise BrowserApprovalError(
                    APPROVAL_REJECTED,
                    "this approval request was not issued by the server (or was already used)",
                    details={"request_id": resolution.request_id},
                )
            if resolution.decision == "always_allow":
                # 무조건 자동 승인은 브라우저 효과에 존재하지 않는다.
                del self._pending[resolution.request_id]
                raise BrowserApprovalError(
                    ALWAYS_ALLOW_FORBIDDEN,
                    "browser effects cannot be approved 'always': every effect needs its own bound approval",
                    details={"request_id": resolution.request_id},
                )
            if not resolution.is_approval:
                del self._pending[resolution.request_id]
                raise BrowserApprovalError(
                    APPROVAL_REJECTED,
                    f"the user did not approve this action (decision={resolution.decision!r})",
                    details={"request_id": resolution.request_id, "decision": resolution.decision},
                )
            already = self._by_request.get(resolution.request_id)
            if already is not None:
                raise BrowserApprovalError(
                    APPROVAL_REPLAYED,
                    "this approval was already turned into a ticket",
                    details={"request_id": resolution.request_id},
                )
            if requirement.binding.fingerprint != binding.fingerprint:
                changed = requirement.binding.field_differences(binding)
                del self._pending[resolution.request_id]
                raise BrowserApprovalError(
                    APPROVAL_BINDING_CHANGED,
                    "the page, address, or payload changed since you were asked: ask again with the new state",
                    details={"request_id": resolution.request_id, "changed": changed},
                )
            ticket = ApprovalTicket(
                ticket_id=f"btk_{secrets.token_hex(8)}",
                token=self._mint_token(),
                binding=binding,
                issued_at=now,
                expires_at=now + self.ttl_seconds,
                request_id=resolution.request_id,
            )
            del self._pending[resolution.request_id]
            self._by_request[resolution.request_id] = ticket.ticket_id
            self._tickets[ticket.token] = ticket
            self._evict_locked(now)
        logger.info(
            "[BrowserApproval] issued ticket=%s request=%s ttl=%.0fs",
            ticket.ticket_id,
            resolution.request_id,
            self.ttl_seconds,
        )
        return ticket

    # ── 실행 직전: 원샷 소비 ──
    def authorize(self, token: str, binding: ApprovalBinding) -> ApprovalTicket:
        """토큰을 검증하고 **소비**한다. 검증과 소비가 같은 임계구역 안에서 일어난다."""
        if not token or not token.strip():
            raise BrowserApprovalError(
                APPROVAL_REQUIRED, "this effect needs a user approval: request one and retry with its token"
            )
        with self._lock:
            now = self._clock()
            ticket = self._tickets.get(token.strip())
            if ticket is None:
                raise BrowserApprovalError(
                    MODEL_TOKEN_REFUSED,
                    "this approval token was not issued by this server",
                    details={"token_prefix": token.strip()[:12]},
                )
            if ticket.is_consumed:
                raise BrowserApprovalError(
                    APPROVAL_REPLAYED,
                    "this approval was already used: approvals are one-shot",
                    details={"ticket_id": ticket.ticket_id},
                )
            if ticket.is_expired(now):
                raise BrowserApprovalError(
                    APPROVAL_EXPIRED,
                    "this approval expired: ask the user again",
                    details={"ticket_id": ticket.ticket_id, "expired_seconds": round(now - ticket.expires_at, 3)},
                )
            if ticket.binding.fingerprint != binding.fingerprint:
                changed = ticket.binding.field_differences(binding)
                raise BrowserApprovalError(
                    APPROVAL_BINDING_CHANGED,
                    "this approval was for a different effect: the page, address, or payload changed",
                    details={"ticket_id": ticket.ticket_id, "changed": changed},
                )
            consumed = ApprovalTicket(
                ticket_id=ticket.ticket_id,
                token=ticket.token,
                binding=ticket.binding,
                issued_at=ticket.issued_at,
                expires_at=ticket.expires_at,
                request_id=ticket.request_id,
                consumed_at=now,
            )
            self._tickets[ticket.token] = consumed
            self._evict_locked(now)
        logger.info("[BrowserApproval] consumed ticket=%s effect=%s", consumed.ticket_id, binding.effect)
        return consumed

    def revoke(self, token: str) -> bool:
        with self._lock:
            return self._tickets.pop(token.strip(), None) is not None

    def revoke_owner(self, owner_key: str) -> int:
        with self._lock:
            doomed = [token for token, ticket in self._tickets.items() if ticket.binding.owner_key == owner_key]
            for token in doomed:
                del self._tickets[token]
            self._pending = {rid: req for rid, req in self._pending.items() if req.binding.owner_key != owner_key}
        return len(doomed)

    def describe(self) -> dict[str, object]:
        now = self._clock()
        with self._lock:
            return {
                "ttl_seconds": self.ttl_seconds,
                "pending": len(self._pending),
                "tickets": len(self._tickets),
                "consumed": sum(1 for ticket in self._tickets.values() if ticket.is_consumed),
                "expired": sum(1 for ticket in self._tickets.values() if ticket.is_expired(now)),
            }

    def reset(self) -> None:
        with self._lock:
            self._pending.clear()
            self._tickets.clear()
            self._by_request.clear()

    # ── 내부 ──
    def _mint_token(self) -> str:
        return f"{_TOKEN_PREFIX}.{secrets.token_urlsafe(18)}"

    def _evict_locked(self, now: float) -> None:
        """만료된 것만 정리한다. 소비된 티켓도 만료 뒤에는 버린다(그때까지는 replay 판정에 쓴다)."""
        if len(self._tickets) > self._max_entries or len(self._pending) > self._max_entries:
            for token in [token for token, ticket in self._tickets.items() if ticket.is_expired(now)]:
                del self._tickets[token]
            for request_id in [rid for rid, req in self._pending.items() if req.expires_at <= now]:
                del self._pending[request_id]


# ── 비밀 handle — 모델은 값을 보지 않는다 ────────────────────────────────────
@dataclass(frozen=True)
class SecretGrant:
    """운영자가 넣은 비밀 한 건. 값은 어디에도 직렬화되지 않는다."""

    handle: str
    name: str
    owner_key: str
    origins: tuple[str, ...]
    created_at: float
    expires_at: float


class BrowserSecretVault:
    """로그인 비밀의 **프로세스 안** 보관소. 값은 handle 로만 나가고 원문은 반환되지 않는다.

    OS/browser 자격증명 통합은 릴리스 단계의 일이고, 여기서 지키는 계약은 **모델이 값을
    보지 못한다**는 것이다: 모델은 `sec_…` handle 만 다루고, 실제 값은 서버가 채운다.
    저장은 메모리뿐이다(디스크·로그·승인 요청에 남기지 않는다).
    """

    def __init__(self, *, clock: _Clock = time.time, max_entries: int = 64, ttl_seconds: float = 3600.0) -> None:
        self._clock = clock
        self._max_entries = max(4, int(max_entries))
        self._ttl_seconds = max(30.0, float(ttl_seconds))
        self._lock = threading.RLock()
        self._grants: dict[str, SecretGrant] = {}
        self._values: dict[str, str] = {}

    def put(self, name: str, value: str, *, owner_key: str, origins: Sequence[str] = ()) -> str:
        if not value:
            raise BrowserApprovalError(SECRET_VALUE_NOT_ALLOWED, "an empty secret is not useful here")
        handle = f"sec_{secrets.token_urlsafe(16)}"
        now = self._clock()
        with self._lock:
            self._evict_locked(now)
            self._grants[handle] = SecretGrant(
                handle=handle,
                name=name.strip()[:64] or "unnamed",
                owner_key=owner_key,
                origins=tuple(_norm_origin(item) for item in origins if item),
                created_at=now,
                expires_at=now + self._ttl_seconds,
            )
            self._values[handle] = value
        logger.info("[BrowserSecret] stored handle=%s name=%s origins=%d", handle[:12], name[:32], len(origins))
        return handle

    def resolve(self, handle: str, *, owner_key: str, origin: str = "") -> tuple[str, SecretGrant]:
        """값을 돌려준다 — **서버 측에서만** 부른다. owner·origin 이 다르면 거절한다."""
        with self._lock:
            now = self._clock()
            grant = self._grants.get(handle)
            value = self._values.get(handle)
            if grant is None or value is None or grant.expires_at <= now:
                raise BrowserApprovalError(
                    SECRET_HANDLE_UNKNOWN, "this secret handle is unknown, expired, or was revoked"
                )
            if grant.owner_key != owner_key:
                raise BrowserApprovalError(
                    SECRET_HANDLE_UNKNOWN, "this secret handle belongs to a different user session"
                )
            current = _norm_origin(origin)
            if grant.origins and current and current not in grant.origins:
                raise BrowserApprovalError(
                    SECRET_ORIGIN_MISMATCH,
                    "this secret is pinned to another site: refusing to fill it here",
                    details={"handle": handle[:12], "origin": current, "pinned": list(grant.origins)},
                )
        return value, grant

    def name_of(self, handle: str) -> str:
        with self._lock:
            grant = self._grants.get(handle)
            return grant.name if grant else ""

    def describe_for_owner(self, owner_key: str) -> list[dict[str, object]]:
        """그 owner 의 비밀 목록. handle 은 **주인에게만** 낸다(UI 가 폐기할 수 있어야 한다).

        `describe()` 는 운영 상태용이라 handle 을 앞 12자로 줄이지만, 자기 비밀을 관리하려면
        전체 handle 이 필요하다 — 값은 어느 쪽에도 없다.
        """
        now = self._clock()
        with self._lock:
            self._evict_locked(now)
            return [
                {
                    "handle": grant.handle,
                    "name": grant.name,
                    "origins": list(grant.origins),
                    "created_at": grant.created_at,
                    "expires_at": grant.expires_at,
                }
                for grant in self._grants.values()
                if grant.owner_key == owner_key
            ]

    def owned_by(self, handle: str, owner_key: str) -> bool:
        """이 handle 이 그 owner 의 것인가(값을 꺼내지 않고 판정한다)."""
        with self._lock:
            grant = self._grants.get(handle)
            return grant is not None and grant.expires_at > self._clock() and grant.owner_key == owner_key

    def discard(self, handle: str) -> bool:
        with self._lock:
            self._values.pop(handle, None)
            return self._grants.pop(handle, None) is not None

    def describe(self) -> dict[str, object]:
        now = self._clock()
        with self._lock:
            self._evict_locked(now)
            return {
                "count": len(self._grants),
                "secrets": [
                    {
                        "handle": grant.handle[:12],
                        "name": grant.name,
                        "owner": grant.owner_key[:12],
                        "origins": list(grant.origins),
                        "expires_at": grant.expires_at,
                    }
                    for grant in self._grants.values()
                ],
            }

    def reset(self) -> None:
        with self._lock:
            self._grants.clear()
            self._values.clear()

    def _evict_locked(self, now: float) -> None:
        for handle in [item for item, grant in self._grants.items() if grant.expires_at <= now]:
            self._values.pop(handle, None)
            del self._grants[handle]
        if len(self._grants) > self._max_entries:
            overflow = len(self._grants) - self._max_entries
            oldest = sorted(self._grants.items(), key=lambda pair: pair[1].created_at)[:overflow]
            for handle, _ in oldest:
                self._values.pop(handle, None)
                del self._grants[handle]


# ── 모델 주장 차단 ───────────────────────────────────────────────────────────
def guard_request_claims(body: Mapping[str, object]) -> None:
    """본문에 "안전하다/승인됐다"는 **주장**이 있으면 거절한다.

    위험도는 서버가 요소의 의미로 판정한다. 호출자가 `risk`/`approved` 같은 필드로 낮출 수
    있으면 그 판정은 의미가 없어진다 — 그래서 그런 필드는 "무시" 가 아니라 **거절**이다.
    """
    claimed = sorted(key for key in body if key in MODEL_CLAIM_FIELDS)
    if claimed:
        raise BrowserApprovalError(
            MODEL_CLAIM_REFUSED,
            f"this request may not assert {'/'.join(claimed)}: the server classifies the effect and the user approves it",
            details={"fields": claimed},
        )


# ── 사용자 인계(MFA·CAPTCHA) ─────────────────────────────────────────────────
@dataclass(frozen=True)
class HandoffSignal:
    """사람이 해야만 하는 단계의 신호. 실패가 아니라 **차례가 바뀐 것**이다."""

    kind: str  # mfa / captcha
    reason: str
    hints: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        return _HANDOFF_STATUS

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": HANDOFF_SCHEMA,
            "status": _HANDOFF_STATUS,
            "kind": self.kind,
            "reason": self.reason,
            "hints": list(self.hints),
            "requires_human": True,
            "auto_retry": False,
        }


_HANDOFF_JS: Final = """
(() => {
  const attr = (el, name) => (el && el.getAttribute ? (el.getAttribute(name) || '') : '');
  const hay = (el) => [
    attr(el, 'aria-label'), attr(el, 'name'), attr(el, 'placeholder'), attr(el, 'autocomplete'),
    attr(el, 'title'), el && el.id ? el.id : '', attr(el, 'data-testid'),
  ].join(' ').toLowerCase();
  const mfa = /(one-?time|otp|verification code|verify code|two-?factor|2fa|mfa|authenticator|인증\\s*번호|인증코드|일회용)/;
  const captcha = /(captcha|recaptcha|hcaptcha|turnstile|sitekey|i'?m not a robot|로봇이 아닙니다|자동입력 방지)/;
  const mfaHits = [];
  for (const el of Array.from(document.querySelectorAll('input, textarea'))) {
    const text = hay(el);
    const numeric = attr(el, 'inputmode') === 'numeric' || attr(el, 'type') === 'tel';
    const len = el.getAttribute('maxlength');
    if (attr(el, 'autocomplete') === 'one-time-code' || mfa.test(text) || (numeric && (len === '6' || len === '4'))) {
      mfaHits.push((text || attr(el, 'type') || 'input').trim().slice(0, 80));
    }
  }
  const captchaHits = [];
  for (const el of Array.from(document.querySelectorAll('[class*=captcha], [id*=captcha], [data-sitekey], iframe'))) {
    const text = [attr(el, 'src'), attr(el, 'data-sitekey'), el && el.className && el.className.toString ? el.className.toString() : '', el && el.id ? el.id : ''].join(' ').toLowerCase();
    if (captcha.test(text)) captchaHits.push(text.trim().slice(0, 80));
  }
  const body = (document.body && document.body.innerText ? document.body.innerText : '').toLowerCase().slice(0, 6000);
  return {
    mfa: mfaHits,
    captcha: captchaHits,
    mfa_text: /(enter the code|verification code|two-?factor|confirm your identity|verify it'?s you|인증번호를 입력|2단계 인증|본인 확인)/.test(body),
    captcha_text: /(i'?m not a robot|로봇이 아닙니다|자동입력 방지|로봇인지 확인)/.test(body),
  };
})()
"""


def _page_frames(page: object) -> list[object]:
    """페이지 + 그 안의 프레임들. CAPTCHA 는 대개 iframe 안에 산다."""
    frames: list[object] = []
    page_frames = getattr(page, "frames", None)
    if isinstance(page_frames, (list, tuple)):
        frames.extend(cast("Sequence[object]", page_frames))
    else:
        main = getattr(page, "main_frame", None)
        if main is not None:
            frames.append(main)
            frames.extend(list(getattr(main, "child_frames", []) or []))
    if not frames:
        frames.append(page)
    return frames


async def detect_user_handoff(page: object) -> HandoffSignal | None:
    """MFA·CAPTCHA 를 **실측**한다. 있으면 행동은 수행되지 않고 사람 차례가 된다."""
    mfa_hints: list[str] = []
    captcha_hints: list[str] = []
    for frame in _page_frames(page):
        evaluator = getattr(frame, "evaluate", None)
        if not callable(evaluator):
            continue
        try:
            raw = await _maybe_await(evaluator(_HANDOFF_JS))
        except Exception as exc:  # noqa: BLE001 - 프로브 실패가 브라우징을 막지 않는다
            logger.debug("[BrowserApproval] handoff probe failed: %s", exc)
            continue
        if not isinstance(raw, Mapping):
            continue
        data = cast("Mapping[str, object]", raw)
        mfa_hints.extend(str(item) for item in cast("Sequence[object]", data.get("mfa") or []))
        captcha_hints.extend(str(item) for item in cast("Sequence[object]", data.get("captcha") or []))
        if data.get("captcha_text") is True:
            captcha_hints.append("page text asks for a robot check")
        if data.get("mfa_text") is True:
            mfa_hints.append("page text asks for a verification code")
    if captcha_hints:
        return HandoffSignal(
            "captcha",
            "the page presents a CAPTCHA/robot check: a human must solve it before the task continues",
            tuple(dict.fromkeys(captcha_hints))[:5],
        )
    if mfa_hints:
        return HandoffSignal(
            "mfa",
            "the page asks for a one-time code or second factor: a human must complete it",
            tuple(dict.fromkeys(mfa_hints))[:5],
        )
    return None


# ── 전역(프로세스) 인스턴스 ──────────────────────────────────────────────────
_gate: BrowserApprovalGate | None = None
_vault: BrowserSecretVault | None = None


def get_browser_approval_gate() -> BrowserApprovalGate:
    global _gate
    if _gate is None:
        _gate = BrowserApprovalGate()
    return _gate


def get_browser_secret_vault() -> BrowserSecretVault:
    global _vault
    if _vault is None:
        _vault = BrowserSecretVault()
    return _vault


def reset_browser_approval() -> None:
    """시험용: 승인 원장과 비밀 보관소를 모두 비운다."""
    global _gate, _vault
    if _gate is not None:
        _gate.reset()
    if _vault is not None:
        _vault.reset()
    _gate = None
    _vault = None


__all__ = [
    "APPROVAL_BINDING_CHANGED",
    "APPROVAL_EXPIRED",
    "APPROVAL_REJECTED",
    "APPROVAL_REPLAYED",
    "APPROVAL_REQUIRED",
    "APPROVAL_SCHEMA",
    "ALWAYS_ALLOW_FORBIDDEN",
    "DEFAULT_APPROVAL_TTL_SECONDS",
    "HANDOFF_REQUIRED",
    "HANDOFF_SCHEMA",
    "MODEL_CLAIM_FIELDS",
    "MODEL_CLAIM_REFUSED",
    "MODEL_TOKEN_REFUSED",
    "REQUIRES_APPROVAL",
    "SECRET_HANDLE_UNKNOWN",
    "SECRET_ORIGIN_MISMATCH",
    "SECRET_VALUE_NOT_ALLOWED",
    "ApprovalBinding",
    "ApprovalRequirement",
    "ApprovalTicket",
    "BrowserApprovalError",
    "BrowserApprovalGate",
    "BrowserSecretVault",
    "Effect",
    "EffectDecision",
    "HandoffSignal",
    "HumanResolution",
    "SecretGrant",
    "classify_effect",
    "detect_user_handoff",
    "get_browser_approval_gate",
    "get_browser_secret_vault",
    "guard_request_claims",
    "origin_of",
    "payload_fingerprint",
    "reset_browser_approval",
    "summarize_effect",
]
