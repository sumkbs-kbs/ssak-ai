---
title: Final independent manual QA operator instructions
tags: [qa, frontend, manual-qa, codex]
date: 2026-10-03
---

# Operator instructions

Mode: **QA-agent-directed/root-executed**. Root alone operates the existing user-unlocked IAB browser2/tab1. This judge does not open a browser, access authentication storage, enter a PIN, modify source, run Git actions, or create child agents.

Required binding: declared HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus 46 manifested source/test/design files; `SOURCE_MANIFEST.json` SHA-256 `0b48c75d2c6b08a3d474331f10eca54152d8a1d76023a2f64fc0bcb8298b35f7`; current assets `index-Gjb0ANVb.js` and `index-DDs7Uh9z.css`. Final approval waits for a completed READY packet on this binding.

These steps were sent before final execution and clarified with root. The original 25 IDs refer to **B01–B20 and A01–A05 QA scenarios**, not 25 saved conversations. There are four pre-final saved conversations to preserve. Retention uses visible titles/content; no hidden storage/session-ID inspection is needed. The model selector is checked on applicable chat views.

1. Cold reload `/studio`, `/wiki`, and `/settings` independently. Verify all four pre-final conversations remain in recent navigation, with no false empty state. Select a pre-final conversation through the visible sidebar after a nonchat reload; record its visible title/content, navigation to `/chat`, and retained 27.3B model selection. Record any new QA conversation separately and do not delete originals.
2. Inspect the complete Korean helper text on Wiki at 375×812, Settings at 1280×900, and file History at 1280×900. Verify `생성하세요`, `보여줍니다`, and `저장됩니다` stay intact; inspect their other required widths and neighboring text for overflow or clipping. On Mutation at all three widths, verify all 40 characters of `6d0a24d4e6a0686693ce29a4d13a69443ae5149b`, including the final `b`, remain readable with historical/stale provenance wording retained.
3. Await the actual populated Git branch/status/list, then capture matching settled JPEG and DOM at 375×812, 768×900, and 1280×900. Measure page bounds. Do not stage, unstage, commit, or execute another Git action.
4. At 375×812 and 768×900, retain a distinct Korean unsent draft. Open the real conversation history and each inspection tab. Capture complete title/X headers, test the close-button center, actually click X, then reopen/use Escape. Record dialog/inert cleanup, draft retention and opener focus restoration.
5. From inspection use the actual Meta+K palette handoff; from history use Meta+Slash guide handoff. Record destination-only dialog ownership and initial focus. Capture the first observed and settled 375px foreground frames plus required 768px frames; record opaque computed backgrounds, opacity and animation. Use actual Tab/Shift+Tab containment and X/Escape restoration where specified by the retained matrix. Verify guide labels wrap legibly.
6. Finish the same complete fresh **78-frame inventory**: 17 routes at 375/768/1280 (51 route frames), plus the 27 listed states. Bind current source/output, every capture, fresh route DOM, current directed action results and actual generation/copy/model evidence. Native OS IME, controlled 503/CAS faults and late hydration/early-draft races remain **AUTOMATED-only**. Earlier-round evidence is historical and cannot approve the final build.

This judge will directly inspect all 78 final JPEGs, all 51 route DOM snapshots and the complete current directed/live-chat evidence, independently verify file bindings/hygiene, and write one final **PASS** with no blockers or an actionable **REVISE** to `QA_REVIEW.md`.
