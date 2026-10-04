# Security Review — Codex UI Redesign

## Verdict

- **Recommendation:** PASS
- **Highest introduced severity:** None
- **Blocking security findings:** None
- **Reviewed HEAD:** `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- **Source manifest SHA-256:** `6b1aacf46676070701e3367fde89ecdecc4cd379ca57ef96d7f0c31513bb3006`

## Scope and integrity

This review covers the frontend redesign bound by `source-files.txt`, `SOURCE_MANIFEST.json`, and `WORKTREE.patch`. The manifest contains 39 scoped files. Every scoped file was read for hash verification and matched its recorded SHA-256. The four protected control files also matched their recorded before/after hashes and remained unchanged:

- `dashboard/src/stores/chatStore.ts`
- `dashboard/src/stores/projectStore.ts`
- `dashboard/src/api/client.ts`
- `dashboard/src/utils/accessPinCredential.ts`

The supplied manifest digest and HEAD both match the stated review inputs. No package or lockfile changed, and no font binary was added. The generated dashboard bundle was scanned for OpenAI-style tokens, AWS access identifiers, GitHub tokens, and JWT-shaped values; no matches were found.

## Threat review

| Area | Result | Evidence |
| --- | --- | --- |
| PIN/session authentication and API authorization | PASS | Protected credential and API client files are hash-identical before/after. Changed requests continue to use project identity headers. |
| Access-mode semantics | PASS | `ChatPage.tsx:359-378` updates the displayed mode only after an HTTP success. Non-2xx and transport errors preserve the prior mode and show an error. This prevents the UI from falsely representing a security-mode transition. |
| Markdown/HTML XSS | PASS | Assistant content still passes through DOMPurify plus `rehype-sanitize`; user content is rendered as React text. The changed message layout does not bypass these controls. Existing hostile-markup tests remain present. |
| Mermaid injection and network exfiltration | PASS | `ChatMessage.tsx` still obtains SVG exclusively through `loadMermaid()`. The unchanged loader uses strict mode, neutralizes dangerous input tags, removes active/resource-loading elements and event handlers, and strips non-local URI attributes before the SVG reaches `innerHTML`. |
| Links and tab control | PASS | Rendered Markdown links retain `target="_blank"` with `rel="noopener noreferrer"`; the sanitizer remains in the same rendering chain. |
| Clipboard behavior | PASS | The new `CopyButton` copies only on an explicit click, writes the supplied plain-text string through the Clipboard API, handles denial/failure, and does not execute or inject copied content. |
| Artifact/approval action integrity | PASS | Artifact and approval markup remains sanitized before event delegation. The redesign did not add a new action type or bypass the existing action dispatch. |
| Project IDs, paths, and navigation | PASS | Project switching/removal still passes typed server-provided project records into the unchanged project store. New navigation destinations are static application routes; no user-controlled route, filesystem path, or URL is evaluated as code. Displayed local paths are text/title content in the already-authenticated local dashboard surface. |
| Runtime bundle exposure | PASS | The final bundle manifest is bound to the same source-manifest digest. Targeted secret-pattern scanning across the built dashboard found zero matches. No new dependency, remote font, or proprietary font asset was introduced. |

## React Doctor diagnostic classification

React Doctor reports one `artifact-secret-leak` diagnostic at `dashboard/reports/mutation/mutation.html:334`. This is an **inherited, non-shipping test-artifact warning**, not an introduced vulnerability:

- The file is excluded by the repository's `dashboard/reports/` ignore rule and is absent from Git HEAD and the reviewed source manifest.
- Its modification timestamp predates this redesign.
- Redacted inspection found multiple token-shaped fixture strings adjacent to explicit fake/test markers; no credential value is reproduced here.
- None of those token-shaped values appears in the generated dashboard bundle.

**Severity:** NOTE / non-blocking. The artifact can be deleted locally to keep broad scanners quiet. The evidence supports test fixtures rather than a live credential, so this review does not claim that credential rotation is required. If this artifact is ever published independently, exclude or redact fixture values before publication.

## Direct slop and programming pass

The production diff and tests were checked for security-impacting overfit/slop: deletion-only security tests, tautological assertions, implementation-mirroring security tests, unnecessary parsing/normalization, broad new trust-boundary code, and needless security abstractions. None creates false confidence or violates the stated security criteria. The new copy helper is a real shared UI behavior with explicit failure handling; the access-mode change is the minimum state-integrity fix. Non-security style or module-size observations are outside this lane and are not blockers.

## Verification evidence

- `docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json` — digest and all file hashes verified.
- `docs/qa/2026-10-03-codex-ui/WORKTREE.patch` — reviewed for changed security-relevant behavior.
- Full current sources listed in `docs/qa/2026-10-03-codex-ui/source-files.txt` — read and hash-bound, with security-sensitive implementations inspected in full.
- `docs/qa/2026-10-03-codex-ui/TESTS_FINAL.log` — 100 test files passed; 971 tests passed.
- `docs/qa/2026-10-03-codex-ui/BUILD_FINAL.log` and `BUNDLE_MANIFEST.json` — production build completed and bundle provenance recorded.
- `docs/qa/2026-10-03-codex-ui/REACT_DOCTOR_CURRENT_RESULT.json` / `REACT_DOCTOR_RESULT.json` — one inherited ignored-artifact diagnostic, classified above.

## Evidence gaps

None that blocks the stated security criteria. Browser interaction was intentionally left to the QA owner; this lane relied on the bound source, build, tests, bundle, and scanner artifacts.
