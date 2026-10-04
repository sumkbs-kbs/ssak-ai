"""Financial numeric extraction contracts."""

from decimal import Decimal

from antigravity_k.engine.data_extractor import DataExtractor
from antigravity_k.engine.financial_numbers import extract_financial_numbers


def test_extract_financial_numbers_preserves_korean_scale_currency_and_evidence() -> None:
    # Given: a Korean combined scale with an explicit currency.
    text = "연간 매출은 1조 2,345억 원이다."

    # When: the financial number parser reads the source text.
    numbers = extract_financial_numbers(text)

    # Then: the parsed amount keeps both exact provenance and unambiguous currency.
    assert len(numbers) == 1
    number = numbers[0]
    assert number.value == 1_234_500_000_000
    assert number.normalized_value == "1234500000000"
    assert number.unit == "KRW"
    assert number.currency == "KRW"
    assert number.raw_text == "1조 2,345억 원"


def test_extract_financial_numbers_combines_all_explicit_korean_scales() -> None:
    # Given: all three supported Korean scale units in one amount.
    text = "추정 규모는 1조 2억 3만원이다."

    # When: the parser reads the continuous scaled amount.
    numbers = extract_financial_numbers(text)

    # Then: it returns one normalized value instead of overlapping fragments.
    assert [(number.normalized_value, number.unit, number.raw_text) for number in numbers] == [
        ("1000200030000", "KRW", "1조 2억 3만원"),
    ]


def test_extract_financial_numbers_distinguishes_percent_percentage_points_and_basis_points() -> None:
    # Given: adjacent financial rates whose unit symbols overlap.
    text = "수익률은 -3.5%, 스프레드는 2.0%p, 가산금리는 25bps다."

    # When: the parser reads the units in priority order.
    numbers = extract_financial_numbers(text)

    # Then: each value is reported once with its original financial unit.
    assert [(number.value, number.unit, number.raw_text) for number in numbers] == [
        (-3.5, "percent", "-3.5%"),
        (2.0, "percentage_point", "2.0%p"),
        (25.0, "basis_point", "25bps"),
    ]


def test_data_extractor_keeps_numeric_value_source_index_and_exact_evidence() -> None:
    # Given: a source result at a non-default position.
    extractor = DataExtractor()
    text = "USD 1,234.50, 비용은 -₩500이다."

    # When: the public extractor adapts financial numbers for the existing result model.
    extracted = extractor.extract_numeric_data(text, source_index=4)

    # Then: legacy values are populated and provenance remains linked to that source.
    assert [(item.value, item.unit, item.currency, item.source_index, item.raw_text) for item in extracted] == [
        (1234.5, "USD", "USD", 4, "USD 1,234.50"),
        (-500.0, "KRW", "KRW", 4, "-₩500"),
    ]


def test_extract_financial_numbers_applies_a_leading_sign_to_the_whole_compound_amount() -> None:
    # Given: a negative compound Korean currency amount.
    text = "부채는 -1조 2,345억 원이다."

    # When: the parser extracts the compound amount.
    numbers = extract_financial_numbers(text)

    # Then: the leading sign applies to every explicit scale component.
    assert [(number.normalized_value, number.unit, number.currency) for number in numbers] == [
        ("-1234500000000", "KRW", "KRW"),
    ]


def test_extract_financial_numbers_keeps_prefix_currency_on_scaled_amount() -> None:
    # Given: an explicit prefix currency followed by a Korean scale.
    text = "투자액은 USD 1.5억이다."

    # When: the parser extracts the amount.
    numbers = extract_financial_numbers(text)

    # Then: currency and base-unit value remain linked in one result.
    assert [
        (number.normalized_value, number.unit, number.currency, number.display_unit, number.raw_text)
        for number in numbers
    ] == [
        ("150000000", "USD", "USD", "USD 억", "USD 1.5억"),
    ]


def test_extract_financial_numbers_marks_unqualified_scaled_amount_as_base_unit() -> None:
    # Given: a Korean scale amount without an explicit currency.
    numbers = extract_financial_numbers("GDP는 2억이다.")

    # When: the parser normalizes the value.
    number = numbers[0]

    # Then: the normalized unit is base and the original scale stays display-only.
    assert (number.normalized_value, number.unit, number.currency, number.display_unit) == (
        "200000000",
        "base",
        "",
        "억",
    )


def test_extract_financial_numbers_rejects_double_sign_and_malformed_numeric_suffixes() -> None:
    # Given: malformed financial numeric tokens.
    malformed = "-$-5, 1,23원, 1.2.3%"

    # When: the parser scans the source text.
    numbers = extract_financial_numbers(malformed)

    # Then: it neither raises nor accepts a valid-looking suffix from malformed input.
    assert numbers == []


def test_data_extractor_serializes_unsafe_integer_as_exact_text_with_base_unit() -> None:
    # Given: a valid KRW amount above JavaScript's safe integer boundary.
    extractor = DataExtractor()
    text = "자산은 9,007,199,254,740,993원이다."

    # When: the public model is built for API serialization.
    extracted = extractor.extract_numeric_data(text)

    # Then: exact decimal text is authoritative and the unit matches its base value.
    assert len(extracted) == 1
    item = extracted[0]
    assert item.value == "9007199254740993"
    assert item.normalized_value == "9007199254740993"
    assert item.unit == "KRW"
    assert item.display_unit == "원"


def test_extract_financial_numbers_keeps_long_decimal_currency_exact() -> None:
    # Given: a currency amount whose decimal coefficient exceeds Decimal's default precision.
    raw_value = "0.12345678901234567890123456789"

    # When: the parser makes its source-linked normalized record.
    number = extract_financial_numbers(f"USD {raw_value}")[0]

    # Then: the exact source decimal is not rounded during canonical formatting.
    assert number.value == Decimal(raw_value)
    assert number.normalized_value == raw_value
    assert (number.unit, number.currency, number.display_unit) == ("USD", "USD", "USD")


def test_extract_financial_numbers_keeps_long_scaled_amount_exact() -> None:
    # Given: an explicit Korean scale whose normalized coefficient exceeds default precision.
    raw_value = "123456789012345678901234567890"
    expected = "123456789012345678901234567890000000000000"

    # When: the parser converts the displayed scale into its base-unit quantity.
    number = extract_financial_numbers(f"{raw_value}조원")[0]

    # Then: both Decimal value and exact normalized text retain every supplied digit.
    assert number.value == Decimal(expected)
    assert number.normalized_value == expected
    assert (number.unit, number.currency, number.display_unit) == ("KRW", "KRW", "조 원")


def test_extract_financial_numbers_keeps_long_compound_scaled_amount_exact() -> None:
    raw_value = "123456789012345678901234567890"
    expected = "123456789012345678901234666655432100000000"

    number = extract_financial_numbers(f"{raw_value}조 987654321억 원")[0]

    assert number.value == Decimal(expected)
    assert number.normalized_value == expected
    assert (number.unit, number.currency, number.display_unit) == ("KRW", "KRW", "조 억 원")


def test_extract_financial_numbers_keeps_long_fractional_minor_scale_exact() -> None:
    expected = "1000000001234.5678901234567890123456789"

    number = extract_financial_numbers("1조 0.12345678901234567890123456789만")[0]

    assert number.value == Decimal(expected)
    assert number.normalized_value == expected


def test_extract_financial_numbers_keeps_tiny_fractional_minor_scale_exact() -> None:
    expected = "1000000000000.000000000000000000000001"

    number = extract_financial_numbers("1조 0.0000000000000000000000000001만")[0]

    assert number.value == Decimal(expected)
    assert number.normalized_value == expected


def test_data_extractor_repeats_canonical_tiny_fractional_scaled_value() -> None:
    expected = "1000000000000.000000000000000000000001"

    item = DataExtractor().extract_numeric_data("1조 0.0000000000000000000000000001만")[0]

    assert item.value == expected
    assert item.normalized_value == expected
