"""Parse financial numeric evidence without guessing missing currency or dates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Final

_NUMBER_BODY: Final = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_NUMBER_END: Final = r"(?![.\d]|,(?=\d))"
_UNSIGNED_NUMBER: Final = rf"(?<![\d,.]){_NUMBER_BODY}{_NUMBER_END}"
_NUMBER: Final = rf"(?<![\d,.])[+-]?{_NUMBER_BODY}{_NUMBER_END}"
_CURRENCY: Final = r"(?:USD\b|KRW\b|JPY\b|CNY\b|EUR\b|달러|원|엔|위안|유로|\$|₩|€|¥)"
_PERCENTAGE_POINT: Final = re.compile(rf"(?P<value>{_NUMBER})\s*%(?:p|P)")
_BASIS_POINT: Final = re.compile(rf"(?P<value>{_NUMBER})\s*(?:bps?|BPS?|BP)")
_PERCENT: Final = re.compile(rf"(?P<value>{_NUMBER})\s*%(?![pP])")
_SCALED: Final = re.compile(
    rf"(?:(?P<prefix_currency>{_CURRENCY})\s*)?"
    + rf"(?P<value>{_NUMBER})\s*(?P<scale>조|억|만)"
    + rf"(?:\s*(?P<minor>{_NUMBER})\s*(?P<minor_scale>억|만))?"
    + rf"(?:\s*(?P<tail>{_NUMBER})\s*(?P<tail_scale>만))?"
    + rf"(?:\s*(?P<suffix_currency>{_CURRENCY}))?",
)
_CURRENCY_PREFIX: Final = re.compile(rf"(?P<sign>[+-]?)\s*(?P<currency>{_CURRENCY})\s*(?P<value>{_UNSIGNED_NUMBER})")
_CURRENCY_SUFFIX: Final = re.compile(rf"(?P<value>{_NUMBER})\s*(?P<currency>{_CURRENCY})")
_LABELLED_VALUE: Final = re.compile(
    rf"(?:금리|이자율|수익률|배당률|GDP|성장률|물가상승률|실업률|인플레이션)\s*[:：]?\s*(?P<value>{_NUMBER})",
    re.IGNORECASE,
)
_SCALE_MULTIPLIERS: Final = {
    "만": Decimal("10000"),
    "억": Decimal("100000000"),
    "조": Decimal("1000000000000"),
}
_SCALE_DIGITS: Final = {
    "만": 4,
    "억": 8,
    "조": 12,
}
_CURRENCY_CODES: Final = {
    "USD": "USD",
    "KRW": "KRW",
    "JPY": "JPY",
    "CNY": "CNY",
    "EUR": "EUR",
    "달러": "USD",
    "원": "KRW",
    "엔": "JPY",
    "위안": "CNY",
    "유로": "EUR",
    "$": "USD",
    "₩": "KRW",
    "€": "EUR",
    "¥": "JPY",
}


@dataclass(frozen=True, slots=True)
class FinancialNumber:
    """Source-linked value where ``unit`` measures ``normalized_value`` exactly."""

    label: str
    value: Decimal
    normalized_value: str
    unit: str
    currency: str
    display_unit: str
    raw_text: str


@dataclass(frozen=True, slots=True)
class _FinancialMatch:
    """A parsed number and its original source range."""

    start: int
    end: int
    number: FinancialNumber


def _decimal(raw: str) -> Decimal:
    return Decimal(raw.replace(",", ""))


def _currency_code(raw: str) -> str:
    return _CURRENCY_CODES[raw.upper()] if raw.upper() in _CURRENCY_CODES else _CURRENCY_CODES[raw]


def _canonical_decimal(value: Decimal) -> str:
    whole, separator, fraction = format(value, "f").partition(".")
    trimmed_fraction = fraction.rstrip("0")
    if separator and trimmed_fraction:
        return f"{whole}.{trimmed_fraction}"
    return whole


def _number_from_match(
    match: re.Match[str],
    *,
    value: Decimal,
    unit: str,
    currency: str = "",
    display_unit: str = "",
) -> _FinancialMatch:
    raw_text = match.group(0)
    return _FinancialMatch(
        start=match.start(),
        end=match.end(),
        number=FinancialNumber(
            label=raw_text,
            value=value,
            normalized_value=_canonical_decimal(value),
            unit=unit,
            currency=currency,
            display_unit=display_unit,
            raw_text=raw_text,
        ),
    )


def _currency_value(match: re.Match[str]) -> Decimal:
    sign = match.groupdict().get("sign") or ""
    return _decimal(f"{sign}{match.group('value')}")


def json_compatible_value(value: Decimal) -> float | str:
    """Return a legacy float only when it preserves the Decimal value exactly."""
    float_value = float(value)
    if Decimal.from_float(float_value) == value:
        return float_value
    return _canonical_decimal(value)


def _scaled_match(match: re.Match[str]) -> _FinancialMatch | None:
    components = [
        (match.group("value"), match.group("scale")),
        (match.group("minor"), match.group("minor_scale")),
        (match.group("tail"), match.group("tail_scale")),
    ]
    named_components = [(raw, scale) for raw, scale in components if raw and scale]
    scales = [scale for _, scale in named_components]
    if any(
        _SCALE_MULTIPLIERS[current] >= _SCALE_MULTIPLIERS[previous]
        for previous, current in zip(scales, scales[1:], strict=False)
    ):
        return None

    first_raw, _ = named_components[0]
    if any(raw.startswith(("+", "-")) for raw, _ in named_components[1:]):
        return None
    sign = Decimal("-1") if first_raw.startswith("-") else Decimal("1")
    precision = (
        sum(sum(character.isdigit() for character in raw) + _SCALE_DIGITS[scale] for raw, scale in named_components) + 1
    )
    with localcontext() as context:
        context.prec = precision
        value = sign * sum(
            (_decimal(raw).copy_abs() * _SCALE_MULTIPLIERS[scale] for raw, scale in named_components),
            Decimal(),
        )

    prefix_currency = match.group("prefix_currency")
    suffix_currency = match.group("suffix_currency")
    raw_currency = prefix_currency or suffix_currency
    currency = _currency_code(raw_currency) if raw_currency else ""
    unit = currency or "base"
    if prefix_currency:
        display_unit = " ".join([prefix_currency, *scales])
    elif suffix_currency:
        display_unit = " ".join([*scales, suffix_currency])
    else:
        display_unit = " ".join(scales)
    return _number_from_match(match, value=value, unit=unit, currency=currency, display_unit=display_unit)


def _overlaps(existing: list[_FinancialMatch], candidate: _FinancialMatch) -> bool:
    return any(candidate.start < item.end and item.start < candidate.end for item in existing)


def extract_financial_numbers(text: str) -> list[FinancialNumber]:
    """Extract explicit financial quantities in source order without inference."""
    matches: list[_FinancialMatch] = []

    for pattern, unit in (
        (_PERCENTAGE_POINT, "percentage_point"),
        (_BASIS_POINT, "basis_point"),
        (_PERCENT, "percent"),
    ):
        for match in pattern.finditer(text):
            raw_unit = {"percentage_point": "%p", "basis_point": "bp", "percent": "%"}[unit]
            candidate = _number_from_match(
                match,
                value=_decimal(match.group("value")),
                unit=unit,
                display_unit=raw_unit,
            )
            if not _overlaps(matches, candidate):
                matches.append(candidate)

    for match in _SCALED.finditer(text):
        scaled_candidate = _scaled_match(match)
        if scaled_candidate is not None and not _overlaps(matches, scaled_candidate):
            matches.append(scaled_candidate)

    for pattern in (_CURRENCY_PREFIX, _CURRENCY_SUFFIX):
        for match in pattern.finditer(text):
            candidate = _number_from_match(
                match,
                value=_currency_value(match),
                unit=_currency_code(match.group("currency")),
                currency=_currency_code(match.group("currency")),
                display_unit=match.group("currency"),
            )
            if not _overlaps(matches, candidate):
                matches.append(candidate)

    for match in _LABELLED_VALUE.finditer(text):
        candidate = _number_from_match(match, value=_decimal(match.group("value")), unit="base")
        if not _overlaps(matches, candidate):
            matches.append(candidate)

    return [item.number for item in sorted(matches, key=lambda item: item.start)]
