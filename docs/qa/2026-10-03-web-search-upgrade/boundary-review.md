---
title: Web search reader and parser boundary review
date: 2026-10-03
tags: [qa, web-search, boundary-review]
---

# Result

No open actionable regression was found in the final selected candidate. One P2 correctness regression at the plain-text/HTML boundary was reproduced, reported to the implementation owner, and fixed before this report was sealed. A late challenge-marker acceptance gap was also reproduced and hardened. This is a focused review of the selected reader/parser changes, not a whole-application security audit.

## Exact candidate

- Full HEAD from `head.txt`: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Final `candidate.sha256` SHA-256: `c96c377d16045c9104d0ead35a7ab61c72adcec51cba195d267e5be02a9612d9`.
- `shasum -a 256 -c docs/qa/2026-10-03-web-search-upgrade/candidate.sha256`: every listed entry returned `OK` after the final fixes.
- Before-task comparison: `baseline/original/src/antigravity_k/tools/web_search_engine.py` and `baseline/original/src/antigravity_k/tools/web_search_tool.py`. Unrelated existing dirty changes were excluded; this reviewer changed only this report, with no staging or commit.

The selected files were `web_reader.py`, `web_html.py`, `web_search_html.py`, their three test files, and the DuckDuckGo/JinaReader/PageScraper integration changes in `web_search_engine.py` plus the DuckDuckGo method in `web_search_tool.py`. The manifest also pins supporting search tests, manifest/lockfile, and manual driver. Primary upstream source pins are retained in `docs/web-search/WEB_SEARCH_UPGRADE_2026-10-03.md`; this review made no external network requests.

Graph discovery was attempted first against project `Users-mr.k-program-coding-ssak_comp-Ssak-Ai`. The new-file pattern returned zero nodes, so known-file reads were used. Existing PageScraper/JinaReader/public-URL symbols were read from the graph. A subsequent graph connection closed; remaining exact-file searches used the documented fallback.

## Fixed P2: already-text responses lost surrounding facts

Before remediation, `web_reader.py` accepted `text/plain` and `text/markdown`, but PageScraper passed every accepted body to `html_to_text`. The new semantic-root selection at `web_html.py:114–129` treated literal HTML examples inside plain text as actual document roots and discarded preceding/following prose.

Exact response body:

```text
Current safe version is 3.0. Example element: <main>Sample content</main>. Do not use 2.0.
```

Observed before remediation:

```text
baseline helper: 'Current safe version is 3.0. Example element: Sample content . Do not use 2.0.'
candidate helper: 'Sample content'
PageScraper, Content-Type: text/plain: 'Sample content'
```

The baseline had imperfect literal-tag preservation, but retained the version and warning. The candidate newly removed both. This was an observable data-loss regression, relevant when reading plain documentation or code examples as answer evidence.

Final fix: `web_search_engine.py:795–799` preserves non-HTML `text/*` bodies and applies the character cap directly. DOM extraction is used for `text/html`, `application/xhtml+xml`, or absent media type. `tests/test_web_reader.py:164–188` exercises the real PageScraper response path for both `text/plain` and `text/markdown`, with literal tags and a separate truncation assertion.

Final independent wire reproduction used HTTPX `MockTransport`, `/robots.txt` returning 404, the document returning 200 with each tested media type, public resolution returning `93.184.216.34`, and `RobotsRateLimitPolicy(min_interval=0)`. The exact body above was returned unchanged for both text types. Clients were closed after each scenario. The only product caller of `html_to_text` is PageScraper; remaining direct calls are benchmark/test consumers.

## Hardened challenge-marker coverage

The original detector inspected only the first 4,096 characters for both title and provider marker. A valid challenge title near the start followed by longer head/style content pushed the provider marker outside the inspected prefix. This was a coverage limitation of the new detector, not a regression from the before-task reader, which had no challenge filter.

Exact fixture construction:

```python
body = (
    '<html><head><title>Just a moment...</title><style>'
    + (' ' * 4100)
    + '</style></head><body><main>Please verify you are human before continuing.</main>'
    + '<script src="/cdn-cgi/challenge-platform/run"></script></body></html>'
)
```

Observed before hardening: 4,299 response bytes; marker offset 4,243; `is_reader_challenge(body)` returned `False`; PageScraper returned `Please verify you are human before continuing.`.

Final `web_reader.py:17–33` still requires a recognized challenge title in the first 4,096 characters, then scans the accepted body for the provider marker. The same independent wire reproduction now returned:

```json
{"challenge_detected": true, "returned": "[차단됨: 웹 본문 challenge_page]"}
```

`tests/test_web_reader.py:40–66` also covers the late Cloudflare marker through the JinaReader HTTP response path. Ordinary CAPTCHA research remains accepted by the separate article test.

## Boundary checks

| Boundary | Selected source and observed evidence | Conclusion |
|---|---|---|
| Accepted decoded byte cap | `web_reader.py:53–71` checks accumulated decoded byte length before appending each chunk. Focused tests reject forged Content-Length, oversized bodies, and gzip output over 5 MiB. | The accepted decoded body is capped at 5 MiB. HTTPX decompression may allocate before yielding chunks; this is not a claim of a strict 5 MiB peak-memory bound. |
| Resource closure | `web_search_engine.py:454–461` uses nested client/response context managers for Jina; PageScraper uses `async with client.stream` at line 786, including redirects, status exits, and reader rejection. The large-stream test checks closure and stops after the third 2 MiB source chunk. | No introduced response-closure regression observed. |
| MIME boundary | `web_reader.py:37–40` rejects declared non-text/non-XHTML bodies. Final PageScraper lines 796–799 preserve accepted non-HTML text. | Binary MIME rejection and text preservation pass the focused wire tests. |
| DDG wrapper/target validation | `web_search_html.py:111–125` validates the wrapper before unwrapping only known DuckDuckGo `/l` hosts, then validates the extracted target. | Tests reject private targets, credentials on wrappers, malformed ports, and malformed IPv6. Unrelated external `uddg` query parameters remain unchanged. |
| Snippet ownership/challenge controls | `web_search_html.py:83–108` detects DDG structural challenge controls; lines 142–159 bind snippets to their owning result or bounded adjacent Lite title interval. | HTML, Lite, and sync adapter tests cover missing-first-snippet, reordered attributes, snippet-before-title, detached snippets, and ordinary CAPTCHA discussion. |
| URL/DNS/IP and fetch authorization | PageScraper lines 761–784 retain public URL checks, per-hop resolution, transport IP pinning, legal policy, and robots/rate-limit authorization. Lines 753–754 retain the egress hook and disabled automatic redirects. Jina retains pre-fetch resolution and request hook. | Selected diff did not bypass or weaken these existing checks. This conclusion is scoped to the changed integration. |
| Bundled authorization, citations, untrusted text | Baseline diffs of engine/tool show no selected changes to bundled routing/authentication, citation IDs, sanitation, or untrusted-content formatting. Existing manual production output has citation IDs and `[untrusted_web_content]`. | No weakening found in the selected diff. The unrelated baseline routing timing failure is outside this report. |

## Parser network/storage evidence

`web_html.py:6` imports only `scrapling.parser.Selector`; line 117 constructs it with `adaptive=False, huge_tree=False`. Installed versions observed during review were Scrapling 0.4.15 and lxml 6.1.1. Installed `scrapling/parser.py:155–166` constructs lxml's HTML parser without overriding its `no_network=True` default; lines 176–194 gate adaptive storage allocation on `adaptive`; lines 219–252 propagate the disabled adaptive setting to child selectors.

An independent read-only child review installed a Python audit hook after importing the parser, rejecting `socket.*`, `sqlite3.connect`, `sqlite3.connect/handle`, and writable-mode `open` events. It then passed these fixtures to `html_to_text`:

```text
remote HTML DOCTYPE at http://127.0.0.1:1/forbidden
local external entity declaring file:///etc/passwd
remote script and image URLs at http://127.0.0.1:1/forbidden
```

Observed outputs:

```text
output 'Visible fact'
output '&secret;\n\nVisible fact'
output 'Visible fact'
side_effects []
```

The local entity remained literal and remote resource references were not fetched by the parser. The audit hook observes Python audit events and does not independently establish the absence of native-library network activity; source/default inspection supplements the observation. No actionable parser network or adaptive-storage finding resulted.

## Verification and limits

Final focused command:

```bash
.venv/bin/python -m pytest -q tests/test_web_reader.py tests/test_web_html.py tests/test_web_search_html.py
```

Observed result: **70 passed, 19 warnings in 0.54s**. The warnings were the installed lxml `strip_cdata` deprecation. Final independent wire reproductions preserved the entire safety prose for plain text/Markdown and blocked the late-marker challenge. All manifest entries were verified after these executions.

This review relies on local source, before-task baseline comparison, HTTP-level controlled responses, parser side-effect probes, and the existing `manual-live.jsonl` observations. The existing live log contains successful private-URL rejection, missing-URL handling, a public Python documentation read, and a production web-search output with citations/untrusted markers; fresh post-restart live verification is the root task's responsibility.

Challenge detection intentionally requires a small known title set in the first 4,096 characters and a provider-specific marker, so it is not a universal bot-wall detector. Absent Content-Type retains HTML inference. Native closed dialog/details visibility and arbitrary stylesheet-based hiding are inherited/static-parser limitations and were excluded from new-regression findings. The review does not cover JavaScript execution, browser/profile behavior, all application tool paths, or unrelated dirty work.
