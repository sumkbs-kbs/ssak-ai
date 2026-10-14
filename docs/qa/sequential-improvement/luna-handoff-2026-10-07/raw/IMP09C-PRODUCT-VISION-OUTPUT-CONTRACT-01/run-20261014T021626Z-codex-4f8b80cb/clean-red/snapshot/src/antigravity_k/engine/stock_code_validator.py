#!/usr/bin/env python3
"""
Ssak-Ai: 한국 주식 종목코드 검증 유틸리티
=============================================
사용자 쿼리에서 6자리 종목코드를 감지하고, 유효성을 검증하며,
잘못된 코드를 올바른 코드로 자동 교정/추천합니다.

주요 기능:
    - 6자리 숫자 종목코드 패턴 감지
    - KRX 상장 종목코드 대조표 기반 검증
    - 잘못된 코드 → 올바른 코드 자동 추천
    - 검색 쿼리 보강 (회사명 + 정확한 코드)

사용법:
    from antigravity_k.engine.stock_code_validator import (
        validate_query_stock_codes,
        enrich_search_query,
        format_code_correction,
    )

    result = validate_query_stock_codes("096732 주가 알려줘")
    if result.needs_correction:
        corrected_query = enrich_search_query("096732 주가 알려줘", result)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("stock_code_validator")

# ─── 주요 상장 종목코드 대조표 ─────────────────────────────────────
# 한국거래소(KRX) 유가증권시장 + 코스닥 시장 주요 종목
# 형식: {6자리코드: 회사명}
# 출처: KRX, 네이버증권 (2026년 기준 주요 종목)
_STOCK_CODE_MAP: dict[str, str] = {
    # === KOSPI (유가증권시장) ===
    "005930": "삼성전자",
    "005935": "삼성전자우",
    "000660": "SK하이닉스",
    "005380": "현대차",
    "207940": "셀트리온",
    "051910": "LG화학",
    "051905": "LG화학우",
    "006400": "삼성SDI",
    "005490": "POSCO홀딩스",
    "028260": "삼성물산",
    "012450": "한화에어로스페이스",
    "000270": "기아",
    "105560": "KB금융",
    "055550": "신한지주",
    "086790": "하나금융지주",
    "138040": "메리츠금융지주",
    "329180": "현대중공업",
    "009540": "HD한국조선해양",
    "010140": "삼성중공업",
    "042660": "한화오션",
    "018260": "삼성SDS",
    "032830": "삼성생명",
    "000810": "삼성화재",
    "030200": "KT",
    "017670": "SK텔레콤",
    "034020": "두산에너빌리티",
    "011170": "롯데케미칼",
    "096770": "SK이노베이션",
    "096760": "SK가스",
    "010130": "고려아연",
    "000100": "유한양행",
    "128940": "한미약품",
    "097950": "CJ제일제당",
    "004990": "롯데지주",
    "021240": "코웨이",
    "036570": "엔씨소프트",
    "251270": "넷마블",
    "259960": "크래프톤",
    "035420": "NAVER",
    "035720": "카카오",
    "247540": "에코프로비엠",
    "086520": "에코프로",
    "196170": "알테오젠",
    "003670": "포스코퓨처엠",
    "011200": "HMM",
    "000720": "현대건설",
    "047040": "대우건설",
    "034220": "LG디스플레이",
    "066570": "LG전자",
    "066575": "LG전자우",
    "015760": "한국전력",
    "033780": "KT&G",
    "316140": "우리금융지주",
    "086280": "현대글로비스",
    "161390": "한국타이어앤테크놀로지",
    "001040": "CJ",
    "060980": "HL만도",
    "011780": "금호석유",
    "010950": "S-Oil",
    # === KOSDAQ (코스닥) ===
    "091990": "셀트리온헬스케어",
    "263750": "셀트리온제약",
    "352820": "에코프로비엠",
    "095340": "ISC",
    "403870": "HPSP",
    "278280": "천보",
    "293490": "카카오게임즈",
    "263720": "알테오젠",
    "214150": "클래시스",
    "348370": "엔켐",
    "208370": "셀바스AI",
    "065350": "신성델타테크",
    "405100": "JW생명과학",
    "115180": "큐리언트",
    "226330": "신테카바이오",
    "096530": "씨젠",
    "144510": "지스마트글로벌",
    "058470": "리노공업",
    "084110": "휴온스글로벌",
    "228760": "에이티넘인베스트",
    "000880": "한화",
    "009830": "한화솔루션",
    "012330": "현대모비스",
    "003550": "LG",
    "034730": "SK",
    "078930": "GS",
    "004800": "효성",
    "006260": "LS",
    "003490": "대한항공",
    "020560": "아시아나항공",
    "004170": "신세계",
    "069960": "현대백화점",
    "028300": "HLB",
    "326030": "SK바이오팜",
    "302440": "SK바이오사이언스",
    "000250": "삼천당제약",
    "323410": "카카오뱅크",
    "377300": "카카오페이",
    "035900": "JYP Ent.",
    "041510": "SM Ent.",
    "122870": "YG Ent.",
    "253450": "스튜디오드래곤",
    "277810": "레인보우로보틱스",
    "454910": "두산로보틱스",
    "108320": "LX세미콘",
    "000990": "DB하이텍",
    "030530": "원익IPS",
    "319660": "피에스케이",
    "039030": "이오테크닉스",
    "042700": "한미반도체",
    "357780": "솔브레인",
    "271560": "오리온",
    "004370": "농심",
    "090430": "아모레퍼시픽",
    "051900": "LG생활건강",
    "139480": "이마트",
    "023530": "롯데쇼핑",
    "030000": "제일기획",
    "282330": "BGF리테일",
    "069080": "웹젠",
    "112040": "위메이드",
}

# 회사명 → 종목코드 역매핑 (부분 문자열 매칭용)
_STOCK_NAME_TO_CODE: dict[str, str] = {}
for code, name in _STOCK_CODE_MAP.items():
    _STOCK_NAME_TO_CODE[name.lower()] = code
    # 띄어쓰기 없는 버전도 매핑 (삼성전자 -> 삼성전자)
    _STOCK_NAME_TO_CODE[name.lower().replace(" ", "")] = code


@dataclass
class StockCodeValidationResult:
    """종목코드 검증 결과."""

    original_code: str
    is_valid: bool = False
    company_name: str = ""
    suggested_code: str = ""
    suggested_name: str = ""
    needs_correction: bool = False
    message: str = ""


@dataclass
class QueryValidationResult:
    """쿼리 전체 검증 결과 (여러 코드 포함 가능)."""

    original_query: str
    corrected_query: str = ""
    codes_found: list[StockCodeValidationResult] = field(default_factory=list)
    needs_correction: bool = False
    has_stock_context: bool = False


# ─── 종목코드 패턴 감지 ──────────────────────────────────────────


def extract_stock_codes(text: str) -> list[str]:
    """텍스트에서 6자리 숫자(종목코드 후보)를 모두 추출.

    6자리 연속 숫자를 찾되, 너무 긴 숫자 시퀀스(7자리 이상)는 제외.
    """
    # 6자리 숫자만 정확히 매칭 (앞뒤로 더 긴 숫자 제외)
    pattern = re.compile(r"(?<!\d)(\d{6})(?!\d)")
    return pattern.findall(text)


def has_stock_context(text: str) -> bool:
    """쿼리에 주식/주가 관련 키워드가 포함되어 있는지 확인."""
    # '코드'는 제외 (프로그래밍 코드와 혼동 방지) — '종목코드'는 '종목'으로 커버
    stock_keywords = [
        "주가",
        "주식",
        "시세",
        "종목",
        "티커",
        "상장",
        "증권",
        "kospi",
        "kosdaq",
        "코스피",
        "코스닥",
        "stock",
        "ticker",
        "price",
        "shares",
        "한국거래소",
        "krx",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in stock_keywords)


# ─── 단일 코드 검증 ──────────────────────────────────────────────


def validate_stock_code(code: str) -> StockCodeValidationResult:
    """6자리 종목코드의 유효성을 검증하고 추천을 제공.

    Args:
        code: 6자리 문자열 (예: "012450", "096732")

    Returns:
        StockCodeValidationResult 검증 결과
    """
    result = StockCodeValidationResult(original_code=code)

    # 형식 검증
    if not re.match(r"^\d{6}$", code):
        result.is_valid = False
        result.message = f"'{code}'은(는) 유효한 6자리 종목코드 형식이 아닙니다."
        return result

    # 대조표 검증
    if code in _STOCK_CODE_MAP:
        result.is_valid = True
        result.company_name = _STOCK_CODE_MAP[code]
        return result

    # 잘못된 코드 — 유사 코드 추천 시도
    result.is_valid = False
    result.needs_correction = True

    # 편집 거리 1 이하로 유사한 코드 찾기 (한 자리 차이 or 자리수 오류)
    candidates: list[tuple[str, str, int]] = []
    for valid_code, name in _STOCK_CODE_MAP.items():
        # 첫 3자리가 같거나 마지막 3자리가 같은 경우 (자주 발생하는 오타 패턴)
        if code[:3] == valid_code[:3] or code[3:] == valid_code[3:]:
            candidates.append((valid_code, name, 0))
        # 숫자 순서가 바뀐 경우 (인접 자리 swap)
        elif _levenshtein_distance(code, valid_code) <= 2:
            candidates.append((valid_code, name, _levenshtein_distance(code, valid_code)))

    candidates.sort(key=lambda x: x[2])

    if candidates:
        best_code, best_name, _ = candidates[0]
        result.suggested_code = best_code
        result.suggested_name = best_name
        result.message = (
            f"'{code}'은(는) 유효하지 않은 종목코드입니다. 혹시 **{best_name}({best_code})**을(를) 찾으셨나요?"
        )
    else:
        # 대조표에 없는 코드 — 일반적인 6자리 숫자이지만 모르는 코드
        result.message = f"'{code}'은(는) 종목코드 대조표에 없는 코드입니다. 올바른 6자리 코드인지 다시 확인해주세요."

    return result


# ─── 쿼리 수준 검증 ──────────────────────────────────────────────


def validate_query_stock_codes(query: str) -> QueryValidationResult:
    """사용자 쿼리에서 종목코드를 검증하고 교정 결과 반환.

    Args:
        query: 사용자 검색 쿼리 문자열

    Returns:
        QueryValidationResult 검증 결과 (교정된 쿼리 포함)
    """
    result = QueryValidationResult(original_query=query)
    result.has_stock_context = has_stock_context(query)

    codes = extract_stock_codes(query)
    if not codes:
        result.corrected_query = query
        return result

    for code in codes:
        validation = validate_stock_code(code)
        result.codes_found.append(validation)

        if validation.needs_correction:
            result.needs_correction = True

    # 교정 쿼리 생성
    if result.needs_correction:
        corrected = query
        for validation in result.codes_found:
            if validation.needs_correction and validation.suggested_code:
                corrected = corrected.replace(validation.original_code, validation.suggested_code)
                # 회사명도 추가하여 검색 정확도 향상
                corrected = f"{validation.suggested_name}({corrected})"
        result.corrected_query = corrected
    else:
        result.corrected_query = query

    return result


# ─── 검색 쿼리 보강 ──────────────────────────────────────────────


def enrich_search_query(query: str, validation: QueryValidationResult) -> str:
    """검색 결과 품질 향상을 위해 쿼리를 보강.

    - 잘못된 코드 → 올바른 코드로 교체
    - 회사명을 추가하여 검색 정확도 향상
    """
    if validation.needs_correction and validation.corrected_query:
        return validation.corrected_query
    return query


def format_code_correction(validation: QueryValidationResult) -> str:
    """사용자에게 보여줄 종목코드 교정 메시지 생성.

    LLM 프롬프트에 주입하여 사용자에게 안내할 수 있도록 함.
    """
    if not validation.needs_correction or not validation.codes_found:
        return ""

    corrections: list[str] = []
    for v in validation.codes_found:
        if v.needs_correction:
            if v.suggested_code:
                corrections.append(
                    f"⚠️ 종목코드 '{v.original_code}'이(가) 잘못되었습니다 → 올바른 코드: **{v.suggested_code} ({v.suggested_name})**"
                )
            else:
                corrections.append(
                    f"⚠️ 종목코드 '{v.original_code}'은(는) 대조표에 없는 코드입니다. 올바른 6자리 코드인지 다시 확인해주세요."
                )

    messages = [
        "[종목코드 검증 결과]",
        f"입력: '{validation.original_query}'",
        *corrections,
    ]
    return "\n".join(messages)


# ─── 유틸리티 함수 ──────────────────────────────────────────────


def _levenshtein_distance(s1: str, s2: str) -> int:
    """레벤슈타인 편집 거리 계산."""
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


# ─── CLI 테스트 ──────────────────────────────────────────────────

if __name__ == "__main__":
    test_queries = [
        "096732 주가 알려줘",
        "012450 주가 알려줘",
        "한화에어로스페이스 주가",
        "005930 주식 시세",
        "999999 주가",
        "삼성전자 주가 알려줘",
    ]

    for q in test_queries:
        print(f"\n{'=' * 60}")
        print(f"쿼리: '{q}'")
        result = validate_query_stock_codes(q)
        print(f"  주식 컨텍스트: {result.has_stock_context}")
        print(f"  코드 발견: {[c.original_code for c in result.codes_found]}")
        print(f"  교정 필요: {result.needs_correction}")
        if result.needs_correction:
            print(f"  교정 쿼리: '{result.corrected_query}'")
            for v in result.codes_found:
                if v.needs_correction:
                    print(f"  → {v.message}")
        else:
            for v in result.codes_found:
                status = "유효" if v.is_valid else v.message
                print(f"  → '{v.original_code}': {status} ({v.company_name or '알 수 없음'})")
