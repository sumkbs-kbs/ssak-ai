# Debug Journal — frontend browser verification

Started: 2026-10-03
Goal: Codex UI 기반 폰트·화면 구성 변경의 실제 동작 확인.

## Environment

React 19 / Vite production bundle, running Electron-owned API localhost:8000. No debugger attached and no credential read. Existing PIN-unlocked in-app browser is used through CUA only. HEAD: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382, shared dirty checkout. LSP server is unavailable; tsc validates changed TypeScript.

References: debugging SKILL.md, node.md, 00-setup.md, 02-investigate.md. Browser driving stays on CUA per higher-level tool instructions.

## Hypotheses

1. Source/build mismatch: presentation loaded from old bundle. Distinguishing evidence: browser rendered workspace classes and live index script hash. Fix if true: rebuild/reload.
2. New rendering suppresses stored sessions: changed component removes list/history binding. Distinguishing evidence: current source still binds store.sessions and protected hydration is unchanged. Fix if true: restore binding.
3. Reload restores a different project-scoped local history: storage hydration clears/rekeys sessions while durable server records remain. Distinguishing evidence: existing store key policy and project epoch hooks vs unchanged baseline hashes; no browser hidden storage inspection. Fix if true: separate persistence investigation with a failing fixture, not speculative data migration.

## Observations

- First live new bundle: `document.documentElement.clientWidth=1280`, `clientHeight=900`, body sans-serif system stack; new sidebar and composer render; browser warn/error logs empty.
- After reload sidebar shows `대화 0개` and native history shows `No chat history found.` Existing history uses local store.sessions only, no server list request. ChatPage worker confirms load/hydrate/CAS/epoch paths unchanged. No record deletion was performed.
- Old baseline resize captures had dimensions714x900/375x473 despite requested1280x900/375x812. Capturing immediately after viewport set returned the previously composited aspect ratio. New pipeline checks actual DOM dimensions and loaded surface before screenshots; faulty baseline names must not be treated as requested-size references.

## Artifacts

- This journal: preserve sanitized final record in QA folder then remove root journal.
- Browser viewport override: reset before final.
- Preview captures: evidence only, mark as preview and never final approval evidence.
- No temporary code logging, debugger ports, environment override or data migration created.

## Current conclusion

The old initial ID/path hydration race was reproduced with a failing fixture and corrected at the ChatPage boundary. Root personally observed the existing prior conversation restore after ID hydration, then a new real 27.3B response (연결 정상입니다.) through the current production API. No storage migration/deletion occurred. Stored preference and server CAS remain unchanged.

Root manual QA found and corrected three presentation regressions: block shell left unused bottom space (explicit column flex); model popover extended 6px left off-screen (mobile positioning relative to action row); title text and copy controls needed bounded ellipsis/visible actions. Final build is index-BjO0ehSf.js (SHA256 6f34e2ac4eee4680114937ebeda49a33775b31d7a3843e7103af58a555058121), source manifest855b9221a7bfca549813e226f530fd5b406dbefc800cc53c35e31ad45b84cc20. All69 complete current captures use this bundle;17 route frames at each375/768/1280 width report horizontal overflow0.

Independent QA directs root-operated browser scenarios because executor profiles are isolated from the existing user-unlocked tab. Root verifies actual UI with CUA, no credential transfer. Two independent visual reviewers inspect the complete final69 capture set. No console logging/debugger instrument was added.


## Final runtime observations

- Current final build returned a real27.3B reply `연결 정상입니다.`. Copy feedback and actual clipboard known-reply match were true; Shift+Enter textarea endsWithNewline was true and the test draft was cleared.
- Root discovered narrow Studio, Start, ModelHub and bottom Settings logger overflow while visiting all routes. Intrinsic responsive page CSS and three logger class hooks corrected this. The41-file manifest and settled51 route frames have zero horizontal main/page overflow.
- At1280px the body is14px system/Korean sans; assistant text16px/27.2px, sidebar248px and assistant content760px. Inspection is docked at1280 and modal below1280; output content was captured after the actual `로딩 중...` indicator disappeared.
- Final route traversal observes inherited Skills/Metrics401 errors. Their page/API sources are unchanged; no auth widening or speculative bypass was performed. Their current error-state UI is bounded, but backend success is not claimed.
- React Doctor exit1 remains a pre-existing ignored nonshipping mutation fixture advisory, independently classified by the security reviewer. It is not called a zero-diagnostic pass.

## Runtime audit verdict

PASS for the requested font/layout update and core chat preservation on HEAD8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382 plus the exact41-file manifest above. Known inherited auxiliary endpoint401 and large lazy bundle warnings are retained in the final report. Current evidence: CAPTURE_MANIFEST.json, BROWSER_OBSERVATIONS.json, TYPOGRAPHY_LIVE.json, TESTS_CURRENT.log, BUILD_CURRENT.log, SECURITY_REVIEW.md. Independent lane verdicts remain their own gates.
