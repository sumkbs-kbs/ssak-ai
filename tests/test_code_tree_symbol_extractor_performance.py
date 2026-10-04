from time import perf_counter

import pytest

from antigravity_k.engine.code_tree_symbol_extractor import RE_JS_FN, RE_OO_FN, extract_symbols


@pytest.mark.benchmark
def test_blank_lines_do_not_rescan_the_remaining_javascript_source() -> None:
    content = "function greet() {}\n" + "\n" * 10_000 + "const answer = 42;\n"
    start = perf_counter()
    names = [match.group(1) for match in RE_JS_FN.finditer(content)]
    elapsed_ms = (perf_counter() - start) * 1000
    assert names == ["greet"]
    assert elapsed_ms < 500, f"blank-line extraction took {elapsed_ms:.1f}ms"


def test_unindented_multiline_return_type_remains_discoverable() -> None:
    assert [match.group(1) for match in RE_OO_FN.finditer("\nSomeType\nrun(")] == ["run"]


def test_python_symbols_keep_source_order_and_deduplicate_each_category() -> None:
    content = (
        "import os as system, json\n"
        "class Example:\n    pass\n"
        "from pkg import helper as renamed, other\n"
        "def alpha(): pass\n"
        "async def beta(): pass\n"
        "import os\n"
        "class Example:\n    pass\n"
        "def alpha(): pass\n"
    )
    symbols = extract_symbols("example.py", content, ".py")
    assert symbols is not None
    assert symbols.functions == ["alpha", "beta"]
    assert symbols.classes == ["Example"]
    assert symbols.imports == ["os", "json", "pkg.helper", "pkg.other"]
    assert symbols.line_count == len(content.split("\n"))
