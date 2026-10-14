"""quant_quality — GGUF/MLX 양자화 품질 등급 산출 (Python).

대시보드 ``dashboard/src/utils/quantQuality.ts``와 1:1 대응하는 단일 진실원.
토큰 셋·등급 경계·우선순위를 양쪽이 동일하게 유지해야 하며, 수정 시 양쪽을
함께 고칠 것 (각 파일 상단에 상호 참조 주석 유지).

Conformance (Phase 46): ``tests/fixtures/quant_quality_conformance.json`` 하나를 TS 쌍생
구현과 공유 검증한다 — 토큰 케이스·등급 서열·grade/label 메타를 이 fixture 하나로 잠그며,
한쪽만 바뀌면 양쪽 테스트가 동시에 실패한다.

등급 체계 (unsloth Dynamic GGUF 품질 가이드 벤치마킹):
  - premium:  Q8_0 / F16 / BF16 / 8bit — 원본 손실 거의 없음
  - high:     Q6_K / Q5_K / 6bit / 5bit — 품질 저하 미미
  - balanced: Q4_K / IQ4 / 4bit — 크기·품질 스위트스팟 (unsloth 권장 기본값 UD-Q4_K_XL)
  - compact:  Q3 / Q2 / IQ2 / IQ1 / TQ / 3bit / 2bit — 용량 우선, 품질 희생
  - unknown:  파싱 실패 / 미표기 / Active·N/A 등 비양자화 표기
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 등급 우선순위: unknown < compact < balanced < high < premium.
# 숫자가 클수록 품질이 높다 — 필터/정렬에서 서열 비교에 사용 가능.
LEVEL_ORDER: dict[str, int] = {
    "unknown": 0,
    "compact": 1,
    "balanced": 2,
    "high": 3,
    "premium": 4,
}

# 대시보드 quantQuality.ts의 정규식과 동일한 토큰 셋/우선순위.
# JS 버전은 .test() (패턴 내 앵커 혼용) — 파이썬에서는 search()로 동일 동작 재현.
_PREMIUM_RE = re.compile(r"^(UD-)?(Q8|F16|BF16|FP16)|^\d?8bit$", re.IGNORECASE)
_HIGH_RE = re.compile(r"^(UD-)?(Q6|Q5)|^[65]bit$", re.IGNORECASE)
_BALANCED_RE = re.compile(r"^(UD-)?(Q4|IQ4)|^4bit$", re.IGNORECASE)
_COMPACT_RE = re.compile(r"^(UD-)?(Q3|Q2|IQ2|IQ1|TQ)|^[23]bit$", re.IGNORECASE)

_GRADE_INFO: dict[str, tuple[str, str]] = {
    "premium": ("P", "프리미엄 — 원본 손실 거의 없음"),
    "high": ("H", "높음 — 품질 저하 미미"),
    "balanced": ("B", "균형 — 크기·품질 스위트스팟"),
    "compact": ("C", "컴팩트 — 용량 우선"),
    "unknown": ("?", "양자화 정보 없음"),
}

_INFO: dict[str, "QuantQualityInfo"] = {}


@dataclass(frozen=True)
class QuantQualityInfo:
    """하나의 양자화 토큰에 대한 품질 등급 정보."""

    level: str
    grade: str
    label: str


for _level, (_grade, _label) in _GRADE_INFO.items():
    _INFO[_level] = QuantQualityInfo(level=_level, grade=_grade, label=_label)


def quant_quality(quantization: str | None) -> QuantQualityInfo:
    """양자화 토큰 → 품질 등급. dashboard/src/utils/quantQuality.ts와 1:1 대응."""
    raw = (quantization or "").strip()
    if not raw:
        return _INFO["unknown"]

    # "Active"/"N/A" 등 비양자화 표기 처리 (대시보드와 동일)
    if re.fullmatch(r"active|n/?a", raw, re.IGNORECASE):
        return _INFO["unknown"]

    if _PREMIUM_RE.search(raw):
        return _INFO["premium"]
    if _HIGH_RE.search(raw):
        return _INFO["high"]
    if _BALANCED_RE.search(raw):
        return _INFO["balanced"]
    if _COMPACT_RE.search(raw):
        return _INFO["compact"]
    return _INFO["unknown"]
