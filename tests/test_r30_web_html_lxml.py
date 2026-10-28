"""r30 (1B): web_html uses lxml directly; outputs match the former scrapling-based parser (goldens captured from it)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from antigravity_k.tools import web_html
from antigravity_k.tools.web_html import html_to_text

GOLDEN = [
    (
        "<html><body><p>a<!-- c -->b</p><div hidden>x</div>tail<b>bold</b> after</body></html>",
        5000,
        "ab\ntailbold after",
    ),
    ("<html><body><p>a<!-- c -->b</p><div hidden>x</div>tail<b>bold</b> after</body></html>", 7, "ab\ntail"),
    ("<pre>  code\n    indent</pre><table><tr><td>a</td><td>b</td></tr></table>", 5000, "code\n    indent\n\na\tb"),
    ("<pre>  code\n    indent</pre><table><tr><td>a</td><td>b</td></tr></table>", 7, "code\n  "),
    ("<header>H</header><main><header>in</header><p>M<br>2</p></main><script>x</script>", 5000, "in\n\nM\n2"),
    ("<header>H</header><main><header>in</header><p>M<br>2</p></main><script>x</script>", 7, "in\n\nM\n2"),
    ("<div style='display:none'>h</div><span aria-hidden=true>z</span><nav>n</nav>ok", 5000, "ok"),
    ("<div style='display:none'>h</div><span aria-hidden=true>z</span><nav>n</nav>ok", 7, "ok"),
    ("<body><article><h1>T</h1><p>x <i>y</i>z</p></article><aside>ad</aside></body>", 5000, "T\n\nx yz"),
    ("<body><article><h1>T</h1><p>x <i>y</i>z</p></article><aside>ad</aside></body>", 7, "T\n\nx yz"),
]


@pytest.mark.parametrize(("html", "cap", "expected"), GOLDEN)
def test_matches_former_scrapling_output(html: str, cap: int, expected: str) -> None:
    assert html_to_text(html, max_chars=cap) == expected


def test_module_no_longer_imports_scrapling_or_tld() -> None:
    tree = ast.parse(Path(web_html.__file__).read_text(encoding="utf-8"))
    names = {
        (n.module or "") if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [n])  # type: ignore[attr-defined]
    }
    assert not any(m.split(".")[0] in {"scrapling", "tld"} for m in names)


def test_lock_and_sbom_have_no_tld() -> None:
    root = Path(__file__).resolve().parents[1]
    assert 'name = "tld"' not in (root / "uv.lock").read_text(encoding="utf-8")
    assert '"tld"' not in (root / "src/antigravity_k/release/python.cdx.json").read_text(encoding="utf-8")
