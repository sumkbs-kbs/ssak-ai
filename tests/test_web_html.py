from __future__ import annotations

import pytest

from antigravity_k.tools.web_search_engine import html_to_text


def test_semantic_body_keeps_article_header_when_page_has_boilerplate() -> None:
    # Given: page furniture and an article with its own headline.
    content = (
        "<html><head><title>Site title</title></head><body>"
        "<header>Site branding</header><div>Subscribe banner</div>"
        "<article><header><h1>Article headline</h1></header>"
        "<p>Verified body fact.</p></article><div>Recommended stories</div></body></html>"
    )

    # When: extracting the useful semantic body.
    result = html_to_text(content)

    # Then: the article headline and fact survive without page furniture.
    assert "Article headline" in result
    assert "Verified body fact." in result
    assert all(noise not in result for noise in ("Site title", "Site branding", "Subscribe", "Recommended"))


@pytest.mark.parametrize(
    "hidden_element",
    [
        "<div hidden><span>Invisible fact</span></div>",
        '<div aria-hidden="true"><span>Invisible fact</span></div>',
        '<div style="DISPLAY: none !important"><span>Invisible fact</span></div>',
        '<div style="visibility : hidden;"><span>Invisible fact</span></div>',
        '<div style="visibility: collapse"><span>Invisible fact</span></div>',
        "<template><article>Invisible fact</article></template>",
        "<noscript><span>Invisible fact</span></noscript>",
        "<form><p>Invisible fact</p><button>Submit</button></form>",
        "<aside><aside>Invisible fact</aside>Outer aside</aside>",
    ],
)
def test_hidden_and_non_body_subtrees_are_excluded_when_nested(hidden_element: str) -> None:
    # Given: unwanted nested text between visible paragraphs.
    content = f"<main><p>First fact.</p>{hidden_element}<p>Last fact.</p></main>"

    # When: extracting the visible main content.
    result = html_to_text(content)

    # Then: exclusion applies to the entire subtree and preserves its visible siblings.
    assert "Invisible fact" not in result
    assert "Outer aside" not in result
    assert "Submit" not in result
    assert "First fact." in result and "Last fact." in result


def test_entities_and_inline_korean_are_preserved_when_text_spans_elements() -> None:
    # Given: inline markup splits Korean syllables and an entity encodes punctuation.
    content = "<article><p>한국어<strong>문장</strong>입니다. A &amp; B&nbsp;가격은 &#8361;1,000.</p></article>"

    # When: rendering text without inserting separators between every DOM string.
    result = html_to_text(content)

    # Then: words keep their original adjacency and entities become readable characters.
    assert result == "한국어문장입니다. A & B 가격은 ₩1,000."


def test_inline_words_and_block_boundaries_survive_when_document_has_no_semantic_root() -> None:
    # Given: a body fragment with inline English emphasis and adjacent block elements.
    content = "<body><div><p>One <em>small</em> step.</p><p>Second fact.</p></div></body>"

    # When: rendering the fallback body.
    result = html_to_text(content)

    # Then: inline spacing and the boundary between paragraphs are preserved.
    assert "One small step." in result
    assert "step.Second" not in result
    assert "Second fact." in result


def test_code_literals_and_indentation_survive_when_html_encodes_angle_brackets() -> None:
    # Given: a code sample with encoded markup, comparison signs, and indentation.
    content = (
        "<main><h1>Example</h1><pre><code>def render():\n"
        '    return "&lt;tag&gt;" if 2 &lt; 3 else "A&amp;B"\n'
        "</code></pre></main>"
    )

    # When: extracting article text.
    result = html_to_text(content)

    # Then: decoding entities never turns code literals back into removable HTML.
    assert 'def render():\n    return "<tag>" if 2 < 3 else "A&B"' in result


def test_table_facts_keep_cell_boundaries_when_cells_have_no_whitespace() -> None:
    # Given: the source has no formatting whitespace between table cells.
    content = "<main><table><tr><th>Model</th><th>Memory</th></tr><tr><td>Qwen</td><td>24 GB</td></tr></table></main>"

    # When: extracting table text.
    result = html_to_text(content)

    # Then: related cell facts remain distinct and row ordering is readable.
    assert "Model\tMemory" in result
    assert "Qwen\t24 GB" in result


def test_all_nonoverlapping_semantic_areas_survive_when_article_is_nested_in_main() -> None:
    # Given: empty roots, nested roots, and additional separate main/article areas.
    content = (
        "<body><main></main><main><h1>Primary headline</h1>"
        "<article><p>Nested fact.</p></article><p>Main fact.</p></main>"
        "<article><p>Separate article fact.</p></article>"
        '<section role="main"><p>Role main fact.</p></section><div>Outside noise</div></body>'
    )

    # When: extracting semantic content.
    result = html_to_text(content)

    # Then: every useful area appears once and outside page noise is omitted.
    for fact in ("Primary headline", "Nested fact.", "Main fact.", "Separate article fact.", "Role main fact."):
        assert result.count(fact) == 1
    assert "Outside noise" not in result


def test_body_fallback_keeps_facts_when_semantic_areas_are_empty_or_hidden() -> None:
    # Given: unusable semantic areas beside a normal body paragraph.
    content = (
        "<body><main><script>ignored()</script></main>"
        "<div hidden><article>Hidden article fact.</article></div>"
        "<p>Fallback evidence.</p><footer>Footer noise</footer></body>"
    )

    # When: selecting the useful body.
    result = html_to_text(content)

    # Then: an empty or hidden semantic marker cannot discard actual body evidence.
    assert result == "Fallback evidence."


def test_malformed_html_recovers_facts_when_attributes_contain_angle_brackets() -> None:
    # Given: incomplete paragraph closures and a quoted attribute with a greater-than sign.
    content = '<main><h1 title="x > y">제목</h1><p>첫 사실 &amp; 근거<p>두 번째 사실<script>noise()</script></main>'

    # When: parsing recoverable HTML.
    result = html_to_text(content)

    # Then: structural parsing keeps content without leaking attribute or script fragments.
    assert "제목" in result and "첫 사실 & 근거" in result and "두 번째 사실" in result
    assert 'y">' not in result and "noise()" not in result


@pytest.mark.parametrize("max_chars", [0, -1, -500])
def test_nonpositive_cap_returns_empty_when_input_has_content(max_chars: int) -> None:
    # Given: meaningful content with no allowed output characters.
    content = "<main><p>Useful evidence.</p></main>"

    # When: applying the output cap.
    result = html_to_text(content, max_chars=max_chars)

    # Then: negative caps cannot return Python's negative-slice prefix.
    assert result == ""


@pytest.mark.parametrize("content", ["", "   \n\t", "<main></main>", "<script>noise()</script>"])
def test_empty_content_returns_empty_when_no_visible_text_exists(content: str) -> None:
    # Given: no visible body facts.
    # When: extracting text.
    result = html_to_text(content)

    # Then: empty documents stay empty.
    assert result == ""


def test_plain_text_and_cap_are_compatible_when_input_is_already_text() -> None:
    # Given: already extracted text containing a comparison sign.
    content = "  한국어 본문: 2 < 3 and 5 > 4.\nNext fact.  "

    # When: extracting a capped plain text prefix.
    result = html_to_text(content, max_chars=20)

    # Then: text is not mistaken for markup and the cap counts output characters.
    assert result == "한국어 본문: 2 < 3 and 5 "
