#!/usr/bin/env python3
"""
Ssak-Ai: 데이터 추출 레이어 (Data Extractor)
==================================================
검색 결과의 원시 텍스트에서 숫자/날짜/가격 등 구조화된 데이터를
자동으로 추출하여 LLM이 정확히 인용할 수 있도록 합니다.

추출 가능 데이터:
    - 주식/금융: 종가, 시가, 고가, 저가, 거래량, 등락률
    - 날씨/기상: 기온, 습도, 미세먼지
    - 환율: 기준 환율, 변동
    - 날짜/시간: 절대적 날짜, 상대적 날짜
"""

import json
import logging
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, NotRequired, TypedDict, cast, final

logger = logging.getLogger("data_extractor")

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type MetricKey = Literal[
    "total_calls",
    "stock_attempts",
    "stock_success",
    "weather_attempts",
    "weather_success",
    "exchange_attempts",
    "exchange_success",
    "date_attempts",
    "date_found",
    "errors",
    "speculative_filtered",
]


class _RecentCall(TypedDict):
    timestamp: str
    type: str
    success: bool


class _SuccessRates(TypedDict):
    stock: float
    weather: float
    exchange: float
    overall: float


class _MetricsState(TypedDict):
    total_calls: int
    stock_attempts: int
    stock_success: int
    weather_attempts: int
    weather_success: int
    exchange_attempts: int
    exchange_success: int
    date_attempts: int
    date_found: int
    errors: int
    speculative_filtered: int
    recent_calls: list[_RecentCall]
    success_rates: NotRequired[_SuccessRates]
    total_attempts: NotRequired[int]
    total_successes: NotRequired[int]


def _as_json_object(value: object) -> dict[str, JsonValue] | None:
    if not isinstance(value, dict):
        return None
    items = cast(Mapping[object, object], value).items()
    return {key: cast(JsonValue, item) for key, item in items if isinstance(key, str)}


# ─── 데이터 모델 ──────────────────────────────────────────────────


@dataclass
class ExtractedStockPrice:
    """추출된 주식 가격 데이터."""

    name: str = ""
    ticker: str = ""
    close_price: int | None = None
    open_price: int | None = None
    high_price: int | None = None
    low_price: int | None = None
    change_percent: float | None = None
    change_amount: int | None = None
    volume: int | None = None
    source_index: int = 0  # 검색 결과 목록에서의 인덱스


@dataclass
class ExtractedWeather:
    """추출된 날씨 데이터."""

    location: str = ""
    temperature: float | None = None
    feels_like: float | None = None
    humidity: int | None = None
    condition: str = ""
    source_index: int = 0


@dataclass
class ExtractedExchangeRate:
    """추출된 환율 데이터."""

    currency_pair: str = ""
    rate: float | None = None
    change_percent: float | None = None
    source_index: int = 0


@dataclass
class ExtractedNumericData:
    """정규화 값은 ``unit``으로 측정하고 원문 단위는 ``display_unit``에 보존합니다."""

    label: str = ""
    value: float | str | None = None
    unit: str = ""
    source_index: int = 0
    raw_text: str = ""
    currency: str = ""
    normalized_value: str = ""
    display_unit: str = ""


@dataclass
class ExtractionResult:
    """전체 추출 결과 — LLM 컨텍스트에 주입될 데이터."""

    stock_prices: list[ExtractedStockPrice] = field(default_factory=list)
    weather: list[ExtractedWeather] = field(default_factory=list)
    exchange_rates: list[ExtractedExchangeRate] = field(default_factory=list)
    numeric_data: list[ExtractedNumericData] = field(default_factory=list)
    dates_found: list[str] = field(default_factory=list)

    def has_data(self) -> bool:
        """추출된 데이터가 하나라도 있는지 확인."""
        return bool(self.stock_prices or self.weather or self.exchange_rates or self.numeric_data or self.dates_found)

    def format_for_llm(self, max_lines: int = 30) -> str:
        """추출된 데이터를 LLM이 바로 사용할 수 있는 텍스트로 변환.

        Args:
            max_lines: 최대 출력 라인 수 (토큰 절약)

        Returns:
            구조화된 데이터 텍스트 (빈 줄로 구분된 섹션)
        """
        if not self.has_data():
            return ""

        lines: list[str] = []
        line_count = 0

        def _safe_add(new_lines: list[str]) -> bool:
            """라인 카운트를 추적하며 추가. max_lines 초과 시 False 반환."""
            nonlocal line_count
            remaining = max_lines - line_count
            if remaining <= 0:
                return False
            can_add = new_lines[:remaining]
            lines.extend(can_add)
            line_count += len(can_add)
            return line_count < max_lines

        # ── 주식 데이터 ──
        for sp in self.stock_prices:
            if line_count >= max_lines:
                break
            label = sp.name or f"종목 {sp.ticker}" if sp.ticker else "주식"

            # 가격 데이터를 한 줄에 요약
            prices: list[str] = []
            if sp.close_price is not None:
                prices.append(f"종가 {sp.close_price:,}원")
            if sp.open_price is not None:
                prices.append(f"시가 {sp.open_price:,}원")
            if sp.high_price is not None:
                prices.append(f"고가 {sp.high_price:,}원")
            if sp.low_price is not None:
                prices.append(f"저가 {sp.low_price:,}원")
            if sp.change_percent is not None:
                sign = "+" if sp.change_percent >= 0 else ""
                prices.append(f"등락률 {sign}{sp.change_percent:.2f}%")
            if sp.change_amount is not None:
                sign = "+" if sp.change_amount >= 0 else ""
                prices.append(f"등락액 {sign}{sp.change_amount:,}원")
            if sp.volume is not None:
                prices.append(f"거래량 {sp.volume:,}주")

            stock_line = f"📈 [{label}] {' | '.join(prices)}"
            if sp.ticker:
                stock_line += f" (종목코드: {sp.ticker})"
            if not _safe_add([stock_line]):
                break

        # 빈 줄 (주식과 날씨 사이)
        if self.stock_prices and line_count < max_lines:
            _ = _safe_add([""])

        # ── 날씨 데이터 ──
        for w in self.weather:
            if line_count >= max_lines:
                break
            parts = [f"📍 {w.location}"] if w.location else []
            if w.temperature is not None:
                parts.append(f"기온 {w.temperature:.1f}°C")
            if w.feels_like is not None:
                parts.append(f"체감 {w.feels_like:.1f}°C")
            if w.humidity is not None:
                parts.append(f"습도 {w.humidity}%")
            if w.condition:
                parts.append(w.condition)
            if not _safe_add([f"☀️ {' | '.join(parts)}"]):
                break

        if self.weather and line_count < max_lines:
            _ = _safe_add([""])

        # ── 환율 데이터 ──
        for er in self.exchange_rates:
            if line_count >= max_lines:
                break
            pair = er.currency_pair or "환율"
            rate = f"{er.rate:,.2f}" if er.rate is not None else "?"
            change = ""
            if er.change_percent is not None:
                sign = "+" if er.change_percent >= 0 else ""
                change = f" ({sign}{er.change_percent:.2f}%)"
            if not _safe_add([f"💱 [{pair}] {rate}{change}"]):
                break

        if self.exchange_rates and line_count < max_lines:
            _ = _safe_add([""])

        # ── 기타 숫자 데이터 ──
        if self.numeric_data and line_count < max_lines:
            nums: list[str] = []
            for nd in self.numeric_data[:5]:
                if nd.value is not None:
                    value = nd.normalized_value or str(nd.value)
                    nums.append(f"{nd.label}: {value}{nd.unit}")
            if nums:
                _ = _safe_add(["📊 기타 데이터:"])
                _ = _safe_add([f"   {n}" for n in nums])

        if line_count >= max_lines:
            lines.append("...(데이터 추출 결과 생략)")

        return "\n".join(lines)


# ─── 추출 메트릭 ───────────────────────────────────────────────────


@final
class ExtractionMetrics:
    """데이터 추출 성능 메트릭 수집기 (클래스 레벨 싱글턴).

    DataExtractor의 인스턴스가 생성될 때마다 공유되는 전역 카운터로,
    전체 시스템의 데이터 추출 정확도를 추적합니다.
    """

    _lock = threading.Lock()
    _metrics: _MetricsState = {
        # 호출 카운트
        "total_calls": 0,
        "stock_attempts": 0,
        "stock_success": 0,
        "weather_attempts": 0,
        "weather_success": 0,
        "exchange_attempts": 0,
        "exchange_success": 0,
        "date_attempts": 0,
        "date_found": 0,
        # 오류/필터
        "errors": 0,
        "speculative_filtered": 0,
        # 최근 호출 로그 (최대 50개)
        "recent_calls": [],
    }

    @classmethod
    def increment(cls, key: MetricKey, delta: int = 1) -> None:
        with cls._lock:
            value = cls._metrics[key]
            cls._metrics[key] = value + delta

    @classmethod
    def record_call(cls, call_type: str, success: bool) -> None:
        """추출 호출을 기록하고 최근 목록에 추가합니다."""
        with cls._lock:
            cls._metrics["total_calls"] += 1
            cls._metrics["recent_calls"].append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "type": call_type,
                    "success": success,
                }
            )
            # 최근 50개만 유지
            if len(cls._metrics["recent_calls"]) > 50:
                cls._metrics["recent_calls"] = cls._metrics["recent_calls"][-50:]

    @classmethod
    def get_stats(cls) -> _MetricsState:
        """현재까지 수집된 모든 메트릭 통계를 반환합니다."""
        with cls._lock:
            stats = cls._metrics.copy()

            # 각 타입별 성공률 계산
            stock_rate = 0.0
            if stats["stock_attempts"] > 0:
                stock_rate = round(stats["stock_success"] / stats["stock_attempts"] * 100, 1)
            weather_rate = 0.0
            if stats["weather_attempts"] > 0:
                weather_rate = round(stats["weather_success"] / stats["weather_attempts"] * 100, 1)
            exchange_rate = 0.0
            if stats["exchange_attempts"] > 0:
                exchange_rate = round(stats["exchange_success"] / stats["exchange_attempts"] * 100, 1)

            # 전체 성공률
            total_attempts = sum(
                [
                    stats["stock_attempts"],
                    stats["weather_attempts"],
                    stats["exchange_attempts"],
                ]
            )
            total_successes = sum(
                [
                    stats["stock_success"],
                    stats["weather_success"],
                    stats["exchange_success"],
                ]
            )

            stats["success_rates"] = {
                "stock": stock_rate,
                "weather": weather_rate,
                "exchange": exchange_rate,
                "overall": round(total_successes / max(1, total_attempts) * 100, 1),
            }
            stats["total_attempts"] = total_attempts
            stats["total_successes"] = total_successes

            return stats

    @classmethod
    def reset(cls) -> None:
        """모든 메트릭을 초기화합니다 (테스트용)."""
        with cls._lock:
            for key in (
                "total_calls",
                "stock_attempts",
                "stock_success",
                "weather_attempts",
                "weather_success",
                "exchange_attempts",
                "exchange_success",
                "date_attempts",
                "date_found",
                "errors",
                "speculative_filtered",
            ):
                cls._metrics[key] = 0
            cls._metrics["recent_calls"] = []


# ─── 추출기 ────────────────────────────────────────────────────────


@final
class DataExtractor:
    """검색 결과 텍스트에서 구조화된 데이터를 추출합니다.

    사용법:
        extractor = DataExtractor()
        result = extractor.extract_all(snippets=["...", "..."])
        llm_text = result.format_for_llm()
    """

    # ── 주식 데이터 패턴 ──

    # 종목명 + 종목코드 패턴들 (1차: 기본 패턴, 2차: 복잡 패턴 폴백)
    # 기본: "한화에어로스페이스 (012450)" / "한화에어로스페이스 012450"
    _TICKER_PATTERN = re.compile(
        "".join(
            (
                r"([가-힣a-zA-Z\s·|,./&\-]{1,40}?)\s*",
                r"(?:\([^)]*?)?",
                r"(\d{6})\s*\)?",
            )
        )
    )
    # 폴백: 텍스트 어디에서든 6자리 코드 발견 + 앞뒤 문맥으로 종목명 추출
    _CODE_ONLY_PATTERN = re.compile(r"(\d{6})")

    # 가격 패턴: "943,000원" or "943000원"
    _PRICE_KRW_PATTERN = re.compile(r"(\d{1,3}(?:,\d{3})*)\s*원")

    # 만원 표기법: "95만원" → 950,000원, "99.6만원" → 996,000원
    _PRICE_MANWON_PATTERN = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*만\s*원?")

    # 억원 표기법: "1.5억원" → 150,000,000원, "2억원" → 200,000,000원
    _PRICE_EOKWON_PATTERN = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*억\s*원?")

    # 변동률 패턴: "+1.51%" or "-2.3%" or "▲1.51%"
    _CHANGE_PCT_PATTERN = re.compile(r"([▲▼]?)([+-]?\d+\.?\d*)\s*%")
    # 괄호 포함 변동률: "(-0.82%)" or " ( +1.51%)"
    _CHANGE_PCT_PAREN_PATTERN = re.compile(r"\(\s*([▲▼]?)([+-]?\d+\.?\d*)\s*%\s*\)")
    # 라벨 기반 변동률: "등락률: +1.51%" or "전일대비 -0.82%"
    _CHANGE_PCT_LABEL_PATTERN = re.compile(r"(등락률|전일대비)\s*[:：]?\s*([▲▼]?)([+-]?\d+\.?\d*)\s*%")

    # 변동액 패턴: "▲14,000원" or "▼14,000원" or "+14,000원"
    _CHANGE_AMT_PATTERN = re.compile(r"([▲▼]|[+-])(\d{1,3}(?:,\d{3})*)\s*원")

    # 거래량 패턴: "142,859주" or "142859주"
    _VOLUME_PATTERN = re.compile(r"(\d{1,3}(?:,\d{3})*)\s*주")

    # ── 오탐 방지 컨텍스트 패턴 ──

    # 실제 가격이 아닌 것으로 의심되는 컨텍스트 (앞에 오는 단어)
    # "목표 95만원", "전망 100만원" → 필터
    _SPECULATIVE_PREFIX = re.compile(
        (
            r"(목표|전망|예상|희망|기대|제시|상향|하향|조정|추정|예측|"
            r"target|forecast|expect|estimate|projected)"
            r"[\s:：]*"
        ),
        re.IGNORECASE,
    )
    # 실제 가격이 아닌 것으로 의심되는 컨텍스트 (뒤에 오는 단어)
    # "95만원을 향해", "186만인데" → 필터
    _SPECULATIVE_SUFFIX = re.compile(
        r"(?:을|를|으로)?\s*"
        + r"(향해|돌파|도달|기대|인데|인가|일까|이라는|이지만|지만|"
        + r"까지|정도|이상|미만|내외|선|대|수준)"
    )
    # 실제 가격임을 확인하는 컨텍스트
    # "현재 95만원", "종가 95만원" → 유지
    _VALID_PRICE_PREFIX = re.compile(
        "".join(
            (
                r"(현재|종가|시가|장중|거래|기록|마감|",
                r"current|close|trading|opening)",
                r"[\s:：]*",
            )
        ),
        re.IGNORECASE,
    )
    _VALID_PRICE_SUFFIX = re.compile(r"(?:에|으로|에서)?\s*(거래|기록|마감|형성|settle|close|trade)")

    # 주식 라벨 패턴
    _STOCK_CLOSE_LABEL = re.compile(r"(종가|종가\s*[:：])\s*(\d[\d,]*원?)")
    _STOCK_OPEN_LABEL = re.compile(r"(시가|시가\s*[:：])\s*(\d[\d,]*원?)")
    _STOCK_HIGH_LABEL = re.compile(r"(고가|고가\s*[:：])\s*(\d[\d,]*원?)")
    _STOCK_LOW_LABEL = re.compile(r"(저가|저가\s*[:：])\s*(\d[\d,]*원?)")
    _STOCK_VOLUME_LABEL = re.compile(r"(거래량|거래량\s*[:：])\s*(\d[\d,]*)")

    # 금융 데이터 스니펫 (Self-Hosted 엔진 출력)
    _STOCK_SNIPPET_PATTERN = re.compile(
        "".join(
            (
                r"📊\s*(.+?)\s*\((\d{6})\)\s*",
                r"([\d,]+)원\s*",
                r"([+-]\d+\.?\d*)%\s*",
                r"\((.+?)\)",
            )
        )
    )
    # "📊 한화에어로스페이스 (012450) 943,000원 +1.51% (상승)"

    # ── TOP 1 심층 분석 JSON 블록 추출 ──

    # Markdown Content: 라인 이후의 모든 텍스트 (JSON 블록의 시작 위치 검출용)
    _TOP1_JSON_PATTERN = re.compile(
        r"Markdown\s*Content:\s*\n",
        re.IGNORECASE,
    )

    # ── 날씨 데이터 패턴 ──

    _TEMPERATURE_LABEL = re.compile(r"(기온|온도|현재기온)\s*[:：]?\s*([+-]?\d+\.?\d*)\s*[°]?\s*[CFcf]?")
    _HUMIDITY_LABEL = re.compile(r"(습도)\s*[:：]?\s*(\d+)\s*%")
    _FEELS_LIKE_LABEL = re.compile(r"(체감|체감온도)\s*[:：]?\s*([+-]?\d+\.?\d*)\s*[°]?\s*[CFcf]?")
    _WEATHER_CONDITION = re.compile(
        (
            r"(맑음|흐림|구름|비|눈|안개|황사|태풍|번개|천둥|소나기|"
            r"폭우|폭설|강풍|한파|더위|clear|cloudy|rain|snow|fog|storm)"
        )
    )

    # ── 환율 데이터 패턴 ──

    _EXCHANGE_PATTERN = re.compile(
        (
            r"(환율|[가-힣]{2,4}/\w+|[가-힣]+달러|달러당|원/)\s*"
            r"[:：]?\s*(\d{1,3}(?:,\d{3})*\.?\d*)\s*"
            r"(\s*[+-]?\d+\.?\d*%\s*)?"
        )
    )

    # ── 날짜 패턴 ──

    _DATE_KOREAN = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
    _DATE_ISO = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")

    def __init__(self) -> None:
        self._stock_names: dict[str, str] = {}
        self._load_stock_names()

    def _load_stock_names(self) -> None:
        """stock_code_validator에서 종목명-코드 매핑을 가져옵니다."""
        try:
            from antigravity_k.engine import stock_code_validator

            name_to_code = cast(dict[str, str], getattr(stock_code_validator, "_STOCK_NAME_TO_CODE"))
            code_map = cast(dict[str, str], getattr(stock_code_validator, "_STOCK_CODE_MAP"))
            self._stock_names = dict(name_to_code)
            # 코드→이름 역방향도 추가
            for code, name in code_map.items():
                self._stock_names[code] = name
                self._stock_names[name] = code
        except ImportError:
            logger.debug("Stock code validator not available — ticker validation disabled")

    # ─── 오탐 방지: 가격 컨텍스트 검증 ────────────────────────────

    def _is_likely_current_price(self, text: str, match_start: int, match_end: int) -> bool:
        """매칭된 가격이 실제 현재 가격일 가능성이 높은지 검증합니다.

        추측성/목표/전망 컨텍스트의 가격(오탐)을 걸러냅니다.
        예) "목표 95만원" → False, "현재 95만원" → True
        예) "186만인데" → False (뉴스 제목, 추측성)

        Args:
            text: 전체 검색 결과 텍스트
            match_start: 매칭된 가격의 시작 위치
            match_end: 매칭된 가격의 끝 위치

        Returns:
            True면 현재 가격으로 신뢰 가능, False면 오탐으로 필터링
        """
        # 매칭 전후 30자 컨텍스트 추출
        context_before = text[max(0, match_start - 40) : match_start].strip()
        context_after = text[match_end : min(len(text), match_end + 40)].strip()

        # 1. 먼저 VALID prefix/suffix 체크 (keep 우선)
        if self._VALID_PRICE_PREFIX.search(context_before):
            return True
        if self._VALID_PRICE_SUFFIX.search(context_after):
            return True

        # 2. SPECULATIVE prefix/suffix 체크 (filter out)
        if self._SPECULATIVE_PREFIX.search(context_before):
            ExtractionMetrics.increment("speculative_filtered")
            return False
        if self._SPECULATIVE_SUFFIX.search(context_after):
            ExtractionMetrics.increment("speculative_filtered")
            return False

        # 3. 라벨 기반 추출(종가/시가 등)에서 이미 검증된 경우는 통과
        #    (extract_stock_prices step 2에서 이미 추출됨)

        # 4. 기본값: 컨텍스트가 모호하면 통과 (false negative 방지)
        return True

    # ─── TOP 1 JSON 블록 추출 ──────────────────────────────────

    def _extract_top1_json(self, text: str) -> dict[str, JsonValue] | None:
        """검색 결과 텍스트에서 TOP 1 심층 분석의 JSON 블록을 추출합니다.

        웹 검색 결과의 'Markdown Content:' 섹션에 포함된
        {"query":..., "answer":{...}, "results":[...]} JSON 객체를
        파싱하여 반환합니다.

        JSON이 중간에 잘려도(truncated) answer.text만이라도 추출할 수 있도록
        폴백 로직을 제공합니다.

        Args:
            text: WebSearchTool.execute()의 전체 출력 텍스트

        Returns:
            파싱된 JSON dict, 또는 최소 {answer: {text: ...}} dict
        """
        # 1. Markdown Content: 라인의 위치 찾기
        md_match = self._TOP1_JSON_PATTERN.search(text)
        if not md_match:
            return None

        # 2. Markdown Content: 이후의 텍스트에서 첫 번째 { 찾기
        content_start = md_match.end()
        after_content = text[content_start:]

        brace_start = after_content.find("{")
        if brace_start < 0:
            return None

        # 3. 브레이스 매칭으로 완전한 JSON 객체 추출
        depth = 0
        json_end = -1
        for i in range(brace_start, len(after_content)):
            ch = after_content[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    json_end = i + 1
                    break

        # 4. JSON 파싱 시도 (완전한 JSON)
        if json_end > 0:
            json_str = after_content[brace_start:json_end]
            try:
                data = _as_json_object(cast(object, json.loads(json_str)))
                if data is not None and "answer" in data:
                    return data
            except (json.JSONDecodeError, ValueError):
                logger.debug("TOP 1 JSON 파싱 실패 (truncated?)", exc_info=True)

        # 5. 폴백: 잘린 JSON에서 answer.text만 regex로 추출
        #    "text":"..." 패턴을 찾아서 텍스트 값 추출
        try:
            # 최대한 많은 텍스트를 확보 (brace_end가 없으면 끝까지)
            raw_json = after_content[brace_start:] if json_end < 0 else after_content[brace_start:json_end]

            # "text":"(내용)" 패턴 (내용은 " 다음에 오는 첫 번째 ", 또는 \\ 다음 문자 까지)
            text_match = re.search(
                r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"',
                raw_json,
            )
            if text_match:
                answer_text = text_match.group(1)
                if len(answer_text) > 10:
                    return {
                        "answer": {"text": answer_text},
                        "results": [],
                        "query": "(truncated JSON에서 추출)",
                    }

            # 폴백2: "text":"로 시작해서 다음 ","까지 (JSON 파싱 없이)
            text_pos = raw_json.find('"text":"')
            if text_pos >= 0:
                val_start = text_pos + 8  # len('"text":"')
                val_end = raw_json.find('"', val_start)
                if val_end > val_start:
                    answer_text = raw_json[val_start:val_end]
                    if len(answer_text) > 10:
                        return {
                            "answer": {"text": answer_text},
                            "results": [],
                            "query": "(truncated JSON에서 추출)",
                        }
        except Exception:
            logger.debug("TOP 1 JSON 폴백 추출 실패", exc_info=True)

        return None

    def _extract_answer_texts(self, data: dict[str, JsonValue]) -> list[str]:
        """TOP 1 JSON에서 answer.text와 results content를 텍스트 리스트로 추출합니다.

        Args:
            data: _extract_top1_json()이 반환한 파싱된 JSON

        Returns:
            추출된 텍스트 조각 리스트 (먼저 answer.text, 그 다음 results content)
        """
        texts: list[str] = []

        # 1. answer.text (최우선 — LLM 요약에 주가 데이터 포함)
        answer = data.get("answer", {})
        if isinstance(answer, dict):
            answer_text = answer.get("text", "")
            if isinstance(answer_text, str) and len(answer_text) > 10:
                texts.append(answer_text)

        # 2. results 배열의 각 content
        results = data.get("results", [])
        if isinstance(results, list):
            for r in results:
                if isinstance(r, dict):
                    content = r.get("content", "")
                    title = r.get("title", "")
                    if isinstance(content, str) and len(content) > 10:
                        texts.append(content)
                    if isinstance(title, str) and len(title) > 5:
                        texts.append(title)

        return texts

    def _extract_change_percent(self, text: str) -> float | None:
        """텍스트에서 변동률(change_percent) 값을 추출합니다.

        여러 패턴을 순차적으로 시도합니다:
        1. _CHANGE_PCT_PATTERN: "+1.51%", "-0.82%", "▲1.51%"
        2. _CHANGE_PCT_PAREN_PATTERN: "(-0.82%)", " ( +1.51%)"
        3. _CHANGE_PCT_LABEL_PATTERN: "등락률: +1.51%", "전일대비 -0.82%"

        Args:
            text: 검색 결과 텍스트 (raw 또는 combined)

        Returns:
            추출된 변동률 값(float), 또는 None
        """
        for pattern in [
            self._CHANGE_PCT_PATTERN,
            self._CHANGE_PCT_PAREN_PATTERN,
            self._CHANGE_PCT_LABEL_PATTERN,
        ]:
            pct_match = pattern.search(text)
            if not pct_match:
                continue

            # 패턴별 그룹 인덱스 처리
            # _CHANGE_PCT_PATTERN: groups=(sign, value)
            # _CHANGE_PCT_PAREN_PATTERN: groups=(sign, value)
            # _CHANGE_PCT_LABEL_PATTERN: groups=(label, sign, value)
            if pattern == self._CHANGE_PCT_LABEL_PATTERN:
                sign_prefix = pct_match.group(2) if pct_match.lastindex is not None and pct_match.lastindex >= 2 else ""
                value_str = pct_match.group(3) if pct_match.lastindex is not None and pct_match.lastindex >= 3 else ""
            else:
                sign_prefix = pct_match.group(1) if pct_match.lastindex is not None and pct_match.lastindex >= 1 else ""
                value_str = pct_match.group(2) if pct_match.lastindex is not None and pct_match.lastindex >= 2 else ""

            if not value_str:
                continue

            try:
                val = float(value_str)
                if sign_prefix in ("▼", "-"):
                    val = -abs(val)
                elif sign_prefix == "▲":
                    val = abs(val)
                return val
            except (ValueError, TypeError):
                continue

        return None

    def _enrich_stock_price(self, sp: ExtractedStockPrice, raw_text: str) -> None:
        """원시 검색 결과 텍스트를 스캔하여 추출된 주식 데이터를 보강합니다.

        TOP 1 JSON answer.text에서 추출하지 못한 필드(특히 change_percent)를
        raw_text에서 찾아 추가합니다.

        Args:
            sp: 기존 추출된 주식 데이터 (변경 가능)
            raw_text: 원시 검색 결과 텍스트
        """
        # change_percent가 없으면 raw_text에서 추출
        if sp.change_percent is None:
            pct = self._extract_change_percent(raw_text)
            if pct is not None:
                sp.change_percent = pct

        # ticker가 없으면 raw_text에서 추출
        if not sp.ticker:
            ticker_match = self._TICKER_PATTERN.search(raw_text)
            if ticker_match:
                code = ticker_match.group(2)
                if code in self._stock_names:
                    sp.ticker = code
                    if not sp.name:
                        known = self._stock_names.get(code)
                        if known and len(known) > 1:
                            sp.name = known

        # close_price가 없으면 raw_text에서 만원/억원 패턴 시도 (컨텍스트 필터 적용)
        if sp.close_price is None:
            for match in self._PRICE_MANWON_PATTERN.finditer(raw_text):
                raw = match.group(1).replace(",", "")
                try:
                    val = int(float(raw) * 10000)
                    if self._is_likely_current_price(raw_text, match.start(), match.end()):
                        sp.close_price = val
                        break
                except (ValueError, OverflowError):
                    logger.debug("Failed to parse 만원 price in enrichment: %s", raw[:20])
                    continue

    def _extract_from_top1_json(
        self, data: dict[str, JsonValue], source_index: int = 0, raw_text: str = ""
    ) -> ExtractedStockPrice | None:
        """TOP 1 JSON의 answer.text에서 주식 가격 데이터를 추출합니다.

        answer.text 필드에는 LLM이 생성한 자연어 요약이 포함되며,
        이 요약에 주식 가격 데이터가 포함되어 있습니다.

        추출 후 change_percent 등 부족한 필드는 raw_text에서 보강합니다.

        Args:
            data: TOP 1 JSON dict
            source_index: 소스 인덱스
            raw_text: 원시 검색 결과 텍스트 (보강용, 선택적)

        Returns:
            추출된 주식 가격 데이터, 또는 None
        """
        texts = self._extract_answer_texts(data)
        if not texts:
            return None

        # 모든 텍스트를 합쳐서 패턴 매칭
        combined = "\n".join(texts)

        # 기존 extract_stock_prices()로 파싱
        sp = self.extract_stock_prices(combined, source_index=source_index)
        if sp is not None:
            # 보강: raw text에서 change_percent 등 추가 필드 추출
            if raw_text:
                self._enrich_stock_price(sp, raw_text)
            return sp

        # 실패 시 results content에서 개별적으로 시도
        results = data.get("results", [])
        if isinstance(results, list):
            for r in results:
                if isinstance(r, dict):
                    content = r.get("content", "")
                    if isinstance(content, str) and len(content) > 10:
                        sp = self.extract_stock_prices(content, source_index=source_index)
                        if sp is not None:
                            if raw_text:
                                self._enrich_stock_price(sp, raw_text)
                            return sp

        return None

    # ─── 기존 추출 메서드 ─────────────────────────────────────

    def extract_stock_prices(self, text: str, source_index: int = 0) -> ExtractedStockPrice | None:
        """텍스트 한 조각에서 주식 가격 데이터를 추출합니다."""
        sp = ExtractedStockPrice(source_index=source_index)

        # 1. 구조화된 금융 데이터 스니펫 먼저 확인 (Self-Hosted 엔진)
        stock_match = self._STOCK_SNIPPET_PATTERN.search(text)
        if stock_match:
            sp.name = stock_match.group(1).strip()
            sp.ticker = stock_match.group(2)
            # 가격 추출 (쉼표 제거)
            price_str = stock_match.group(3).replace(",", "")
            try:
                sp.close_price = int(price_str)
            except ValueError:
                pass
            try:
                sp.change_percent = float(stock_match.group(4))
            except ValueError:
                pass
            return sp

        # 2. 라벨 기반 추출 (종가/시가 등)
        close_match = self._STOCK_CLOSE_LABEL.search(text)
        if close_match:
            price_clean = re.sub(r"[^\d]", "", close_match.group(2))
            try:
                sp.close_price = int(price_clean)
            except ValueError:
                pass

        open_match = self._STOCK_OPEN_LABEL.search(text)
        if open_match:
            price_clean = re.sub(r"[^\d]", "", open_match.group(2))
            try:
                sp.open_price = int(price_clean)
            except ValueError:
                pass

        high_match = self._STOCK_HIGH_LABEL.search(text)
        if high_match:
            price_clean = re.sub(r"[^\d]", "", high_match.group(2))
            try:
                sp.high_price = int(price_clean)
            except ValueError:
                pass

        low_match = self._STOCK_LOW_LABEL.search(text)
        if low_match:
            price_clean = re.sub(r"[^\d]", "", low_match.group(2))
            try:
                sp.low_price = int(price_clean)
            except ValueError:
                pass

        vol_match = self._STOCK_VOLUME_LABEL.search(text)
        if vol_match:
            vol_clean = re.sub(r"[^\d]", "", vol_match.group(2))
            try:
                sp.volume = int(vol_clean)
            except ValueError:
                pass

        # 3. 변동률 추출
        sp.change_percent = self._extract_change_percent(text)

        # 4. 변동액 추출
        amt_match = self._CHANGE_AMT_PATTERN.search(text)
        if amt_match:
            sign_str = amt_match.group(1)
            raw_num = amt_match.group(2).replace(",", "")
            try:
                val = int(raw_num)
                if sign_str in ("▼", "-"):
                    val = -val
                sp.change_amount = val
            except ValueError:
                pass

        # 5. 종목명/코드 추출 (오탐 방지: 추출명이 알려진 종목명인지 검증)
        ticker_match = self._TICKER_PATTERN.search(text)
        if ticker_match:
            name_candidate = ticker_match.group(1).strip()
            code = ticker_match.group(2)
        else:
            # 1차 패턴 실패 → 코드만 찾고 문맥에서 이름 추출
            code_match = self._CODE_ONLY_PATTERN.search(text)
            if code_match:
                code = code_match.group(1)
                # 코드 앞뒤 80자에서 한국어/영문 이름 추출 시도
                code_pos = code_match.start()
                context = text[max(0, code_pos - 60) : code_pos]
                ctx_name = re.search(
                    r"([가-힣a-zA-Z][가-힣a-zA-Z\s·|,./&\-]{0,30})$",
                    context.rstrip(),
                )
                name_candidate = ctx_name.group(1).strip() if ctx_name else ""
            else:
                name_candidate = ""
                code = ""

        if code and code in self._stock_names:
            sp.ticker = code
            # 추출된 이름이 알려진 종목명이면 그대로 사용
            if name_candidate and name_candidate in self._stock_names:
                sp.name = name_candidate
            else:
                # 추출명이 KOSPI 같은 오탐이면 코드 매핑의 공식명 사용
                known_name = self._stock_names.get(code)
                if known_name and len(known_name) > 1:
                    sp.name = known_name
                elif name_candidate:
                    sp.name = name_candidate

        # close_price가 아직 없으면 기본 가격 패턴 시도 (원 → 만원 → 억원 순)
        # 각 패턴은 _is_likely_current_price()로 오탐 필터링 수행
        if sp.close_price is None:
            for match in self._PRICE_KRW_PATTERN.finditer(text):
                price_str = match.group(1).replace(",", "")
                try:
                    val = int(price_str)
                    if self._is_likely_current_price(text, match.start(), match.end()):
                        sp.close_price = val
                        break
                except ValueError:
                    logger.debug("Failed to parse KRW price: %s", price_str[:20])
                    continue

        if sp.close_price is None:
            for match in self._PRICE_MANWON_PATTERN.finditer(text):
                raw = match.group(1).replace(",", "")
                try:
                    val = int(float(raw) * 10000)
                    if self._is_likely_current_price(text, match.start(), match.end()):
                        sp.close_price = val
                        break
                except (ValueError, OverflowError):
                    logger.debug("Failed to parse 만원 price: %s", raw[:20])
                    continue

        if sp.close_price is None:
            for match in self._PRICE_EOKWON_PATTERN.finditer(text):
                raw = match.group(1).replace(",", "")
                try:
                    val = int(float(raw) * 100000000)
                    if self._is_likely_current_price(text, match.start(), match.end()):
                        sp.close_price = val
                        break
                except (ValueError, OverflowError):
                    logger.debug("Failed to parse 억원 price: %s", raw[:20])
                    continue

        # 하나라도 데이터가 있으면 반환 (ticker만 있어도 유효)
        if any(
            [
                sp.close_price,
                sp.open_price,
                sp.high_price,
                sp.low_price,
                sp.change_percent is not None,
                sp.change_amount is not None,
                sp.volume,
                sp.ticker,
            ]
        ):
            return sp

        return None

    def extract_weather(self, text: str, source_index: int = 0) -> ExtractedWeather | None:
        """텍스트에서 날씨 데이터를 추출합니다."""
        w = ExtractedWeather(source_index=source_index)

        # 위치 추출 (wttr.in 출력에서)
        loc_match = re.search(r"Weather report:\s*(.+?)(?:\n|$)", text)
        if loc_match:
            w.location = loc_match.group(1).strip()

        temp_match = self._TEMPERATURE_LABEL.search(text)
        if temp_match:
            try:
                w.temperature = float(temp_match.group(2))
            except ValueError:
                pass

        feels_match = self._FEELS_LIKE_LABEL.search(text)
        if feels_match:
            try:
                w.feels_like = float(feels_match.group(2))
            except ValueError:
                pass

        humid_match = self._HUMIDITY_LABEL.search(text)
        if humid_match:
            try:
                w.humidity = int(humid_match.group(2))
            except ValueError:
                pass

        cond_match = self._WEATHER_CONDITION.search(text)
        if cond_match:
            w.condition = cond_match.group(1)

        if w.temperature is not None or w.humidity is not None:
            return w
        return None

    def extract_exchange_rate(self, text: str, source_index: int = 0) -> ExtractedExchangeRate | None:
        """텍스트에서 환율 데이터를 추출합니다."""
        match = self._EXCHANGE_PATTERN.search(text)
        if not match:
            return None

        er = ExtractedExchangeRate(
            currency_pair=match.group(1).strip(),
            source_index=source_index,
        )
        try:
            er.rate = float(match.group(2).replace(",", ""))
        except ValueError:
            pass

        change_str = match.group(3)
        if change_str:
            try:
                er.change_percent = float(change_str.strip().rstrip("%"))
            except ValueError:
                pass

        return er

    def extract_dates(self, text: str) -> list[str]:
        """텍스트에서 날짜 문자열을 추출합니다.

        유효성 검증:
          - 1월~12월만 허용 (0월, 13월+ 제거)
          - 1일~31일만 허용 (0일, 32일+ 제거)
          - 연도는 1900~2099년만 허용
        """
        dates: list[str] = []

        def _is_valid_date(y: int, m: int, d: int) -> bool:
            """날짜 유효성 검증: 1900<=y<=2099, 1<=m<=12, 1<=d<=31"""
            if y < 1900 or y > 2099:
                return False
            if m < 1 or m > 12:
                return False
            if d < 1 or d > 31:
                return False
            return True

        for match in self._DATE_KOREAN.finditer(text):
            y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if _is_valid_date(y, m, d):
                dates.append(f"{y}년 {m}월 {d}일")
        for match in self._DATE_ISO.finditer(text):
            y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if _is_valid_date(y, m, d):
                dates.append(f"{y}년 {m}월 {d}일")
        return dates

    def extract_numeric_data(self, text: str, source_index: int = 0) -> list[ExtractedNumericData]:
        """명시된 금융 수치를 값·단위·원문 근거와 함께 추출합니다."""
        from antigravity_k.engine.financial_numbers import extract_financial_numbers, json_compatible_value

        return [
            ExtractedNumericData(
                label=number.label,
                value=json_compatible_value(number.value),
                unit=number.unit,
                source_index=source_index,
                raw_text=number.raw_text,
                currency=number.currency,
                normalized_value=number.normalized_value,
                display_unit=number.display_unit,
            )
            for number in extract_financial_numbers(text)
        ]

    # ─── 통합 추출 ───────────────────────────────────────────────

    def extract_all(self, texts: list[str], query: str = "") -> ExtractionResult:
        """여러 텍스트 조각에서 모든 데이터를 통합 추출합니다.

        Args:
            texts: 검색 결과 스니펫/본문 텍스트 목록
            query: 원본 검색 쿼리 (카테고리 분류용)

        Returns:
            모든 추출 데이터를 담은 ExtractionResult
        """
        result = ExtractionResult()
        has_top1_stock = False
        _stock_attempted = False  # 중복 카운트 방지 플래그

        ExtractionMetrics.increment("total_calls")

        for idx, text in enumerate(texts):
            if not text or len(text) < 5:
                continue

            # ── 1차: TOP 1 심층 분석 JSON 블록 추출 시도 ──
            top1_data = self._extract_top1_json(text)
            if top1_data:
                query_value = top1_data.get("query", "?")
                query_text = query_value if isinstance(query_value, str) else "?"
                logger.info("TOP 1 JSON 블록 발견: query=%s", query_text[:50])

                # answer.text에서 주식 데이터 추출 (raw text로 보강)
                ExtractionMetrics.increment("stock_attempts")
                _stock_attempted = True
                top1_stock = self._extract_from_top1_json(top1_data, source_index=idx, raw_text=text)
                if top1_stock:
                    result.stock_prices.append(top1_stock)
                    has_top1_stock = True
                    ExtractionMetrics.increment("stock_success")
                    ExtractionMetrics.record_call("stock", True)
                    logger.info("TOP 1에서 주식 데이터 추출 성공: %s", top1_stock.name)

                # answer 및 results 텍스트에서 추가 데이터 추출
                top1_texts = self._extract_answer_texts(top1_data)
                for t in top1_texts:
                    # 날씨 (주식 외 데이터)
                    if not has_top1_stock and not result.weather:
                        ExtractionMetrics.increment("weather_attempts")
                        weather = self.extract_weather(t, source_index=idx)
                        if weather:
                            result.weather.append(weather)
                            ExtractionMetrics.increment("weather_success")
                            ExtractionMetrics.record_call("weather", True)

                    # 환율
                    if not result.exchange_rates:
                        ExtractionMetrics.increment("exchange_attempts")
                        exchange = self.extract_exchange_rate(t, source_index=idx)
                        if exchange:
                            result.exchange_rates.append(exchange)
                            ExtractionMetrics.increment("exchange_success")
                            ExtractionMetrics.record_call("exchange", True)

                    # 날짜
                    ExtractionMetrics.increment("date_attempts")
                    dates = self.extract_dates(t)
                    if dates:
                        result.dates_found.extend(dates)
                        ExtractionMetrics.increment("date_found", len(dates))

                    # 기타 숫자
                    numeric = self.extract_numeric_data(t, source_index=idx)
                    result.numeric_data.extend(numeric)

            # ── 2차: 기존 패턴 기반 추출 (TOP 1에서 주식을 못 찾았거나 보강) ──
            # 주식 데이터 (TOP 1에서 못 찾았거나, 추가 결과 보강)
            # 주의: TOP 1 경로에서 이미 stock_attempted이면 이중 카운트 방지
            if not has_top1_stock:
                if not _stock_attempted:
                    ExtractionMetrics.increment("stock_attempts")
                    _stock_attempted = True
                stock = self.extract_stock_prices(text, source_index=idx)
                if stock:
                    result.stock_prices.append(stock)
                    ExtractionMetrics.increment("stock_success")
                    ExtractionMetrics.record_call("stock", True)

            # 날씨 데이터 (TOP 1 추출에서 중복 방지)
            if not result.weather:
                ExtractionMetrics.increment("weather_attempts")
                weather = self.extract_weather(text, source_index=idx)
                if weather:
                    result.weather.append(weather)
                    ExtractionMetrics.increment("weather_success")
                    ExtractionMetrics.record_call("weather", True)

            # 환율 데이터 (TOP 1 추출에서 중복 방지)
            if not result.exchange_rates:
                ExtractionMetrics.increment("exchange_attempts")
                exchange = self.extract_exchange_rate(text, source_index=idx)
                if exchange:
                    result.exchange_rates.append(exchange)
                    ExtractionMetrics.increment("exchange_success")
                    ExtractionMetrics.record_call("exchange", True)

            # 날짜 (중복은 최종 제거)
            ExtractionMetrics.increment("date_attempts")
            dates = self.extract_dates(text)
            if dates:
                result.dates_found.extend(dates)
                ExtractionMetrics.increment("date_found", len(dates))

            # 기타 숫자
            numeric = self.extract_numeric_data(text, source_index=idx)
            result.numeric_data.extend(numeric)

        # 중복 제거
        result.dates_found = list(dict.fromkeys(result.dates_found))

        # 쿼리 기반 필터링
        q = query.lower()
        if not any(kw in q for kw in ("주가", "주식", "시세", "코스피", "코스닥", "stock", "price")):
            result.stock_prices.clear()
        if not any(kw in q for kw in ("날씨", "weather", "기온", "온도")):
            result.weather.clear()
        if not any(kw in q for kw in ("환율", "달러", "exchange", "currency")):
            result.exchange_rates.clear()

        return result


# ─── 진입점: 텍스트에서 바로 구조화 데이터 추출 ─────────────────


def extract_structured_data(texts: list[str], query: str = "") -> str:
    """여러 텍스트에서 구조화된 데이터를 추출하여 LLM용 문자열로 반환합니다.

    Args:
        texts: 검색 결과 텍스트 조각 목록
        query: 원본 검색 쿼리

    Returns:
        구조화된 데이터 문자열 (비어있으면 빈 문자열)
    """
    extractor = DataExtractor()
    result = extractor.extract_all(texts, query=query)
    return result.format_for_llm()


# ─── CLI 테스트 ──────────────────────────────────────────────────

if __name__ == "__main__":
    # 테스트용 데이터
    test_snippets = [
        "📊 한화에어로스페이스 (012450) 943,000원 +1.51% (상승)",
        ("종가: 943,000원 | 시가: 930,000원 | 고가: 970,000원 | 저가: 905,000원 | 거래량: 142,859주 | 등락률: +1.51%"),
        "삼성전자(005930) 84,500원 (-0.82%)",
        "서울 날씨: 기온 28.5°C, 습도 65%, 맑음",
        "원/달러 환율 1,382.50원 (-0.12%)",
    ]

    extractor = DataExtractor()
    result = extractor.extract_all(test_snippets, query="한화에어로스페이스 주가")

    print("=" * 50)
    print("  Data Extractor Test")
    print("=" * 50)

    print(f"\n주식 데이터: {len(result.stock_prices)}개")
    for sp in result.stock_prices:
        print(f"  - {sp.name} ({sp.ticker}): 종가={sp.close_price:,}원")

    print(f"\n날씨 데이터: {len(result.weather)}개")
    for w in result.weather:
        print(f"  - {w.location}: 기온={w.temperature}°C, 습도={w.humidity}%")

    print(f"\n환율 데이터: {len(result.exchange_rates)}개")
    for er in result.exchange_rates:
        print(f"  - {er.currency_pair}: {er.rate}")

    print(f"\n날짜 발견: {result.dates_found}")

    print("\n" + "=" * 50)
    print("  LLM 포맷 출력:")
    print("=" * 50)
    print(result.format_for_llm())
