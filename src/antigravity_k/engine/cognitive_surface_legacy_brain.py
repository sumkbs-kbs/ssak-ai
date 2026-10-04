"""Legacy observation-only Brain adapter shared by surface ports."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from antigravity_k.engine.cognitive.runtime import ThinkOutcome


class SurfaceBrainPort:
    """실제 모델을 Primary Brain port(think)로 결선하는 최소 어댑터.

    shadow episode의 판단 주체다 — 모델 호출이 실패하면 failed think로 episode가
    BRAIN_FAILED로 종료된다(legacy 경로와 무관하다). 모델 응답의 의미 해석은 여기서
    하지 않고 detail로 실어 보낼 뿐이다(최종 통합은 Primary, Body는 전달).
    """

    def __init__(self, generate: Callable[[str], str]) -> None:
        self._generate = generate

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        prompt = (
            "SSAK-AI shadow observation. context_ref={context_ref} request={request_signature} attempt={attempt}. "
            "이 상호작용의 관찰 요약을 한 문장으로 제시하라."
        ).format(context_ref=context_ref, request_signature=request_signature, attempt=attempt)
        try:
            detail = str(self._generate(prompt))
        except Exception as exc:  # noqa: BLE001 — 모델 실패는 failed think로 끝난다
            return ThinkOutcome(judgment_ref="", failed=True, detail=f"surface brain port: {exc}")
        # 관찰 요약이 물질 판단을 주장하지 않는다 — delta를 비워 simple 경로로 끝나고,
        # material 여부는 Primary가 다른 경로에서 주장할 일이다(Body가 대신 정하지 않는다).
        return ThinkOutcome(
            judgment_ref=f"judgment:{uuid.uuid4()}",
            delta=None,
            detail=detail[:500],
        )
