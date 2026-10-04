---
title: Independent manual QA operator instructions, round 5
tags: [qa, frontend, manual-qa, codex]
date: 2026-10-03
---

# Operator instructions

Mode: **QA-agent-directed/root-executed**. Root alone operates the existing user-unlocked IAB browser2/tab1 at `http://127.0.0.1:8000/`. This QA judge does not open another browser profile, request or enter a PIN, inspect authentication storage, or transfer credentials.

Expected binding: HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, dirty `SOURCE_MANIFEST.json` SHA-256 `7adf26f802aa3a1092a96f606951bbdc9606785eb9c20f83b22df0c35b93c236`, main JavaScript `/assets/index-D6IQTpgA.js`, main CSS `/assets/index-BLgp1deP.css`. The final capture inventory must accurately include every fresh frame, including added entrance frames, with matching observations and hashes.

Repeat the following at **375×812 and 768×900**. Use real UI clicks/keys and read-only DOM observations; no synthetic event dispatch, terminal browser automation, authentication manipulation, or backend fault injection.

1. **A02 conversation history header and close:** start on `/` with an unsent distinctive Korean draft. Click history and capture a settled frame with the complete title and close X. Record the title/close bounding boxes and `elementFromPoint` at the close button center; the hit target must be that button or its descendant. Actually click X, then record zero visible dialogs and zero inert regions, focus returned to the history opener, and the same draft. Reopen/Escape and record the same result. Reopen and select a preexisting QA conversation through the real UI; confirm closure and selected conversation content without deleting sessions.
2. **A01 compact inspection header and tabs:** click inspection. For environment, code, and changes, capture a settled frame with a full title and close X and record the close-center hit target above the shell status strip. Actually click X on each tab and record zero dialogs/inert regions plus focus return. Reopen for the next tab. On one tab also exercise Escape and check focus/draft return. Retain the existing 1280×900 docked tab checks.
3. **B19 command palette entry and handoff:** from inspection with an unsent draft, press Meta+K. Capture the first available painted palette frame and its settled frame. Observe computed `opacity`, `backgroundColor`, and `animationName`; entry and settled text must be legible on an opaque foreground. Record focus in the search combobox and the preceding inspection dismissal. Escape must leave zero dialogs/inert regions, restore focus appropriately, and preserve the draft. No artificial millisecond sleep is required; an `animationName: none` observation and normal first/settled captures document immediate opaque entry.
4. **B19 shortcut guide entry and dismissal:** press Meta+/. Capture the first available and settled guide frames, observe opaque foreground styles and focus within the guide, then use Tab and Shift+Tab to verify containment. Actually click X, reopen, and Escape. Record zero dialogs/inert regions and focus restoration after both dismissal paths.

Record the action results and observation timestamps in `QA_DIRECTED_RESULTS.json`, with its exact current source/script/CSS binding and artifact references. Do not replace a pointer click with hit-testing alone: the real click must close the modal. Do not infer visible layering from viewport bounds alone.

# Scope and final review

Keep the original **B01–B20 and A01–A05** matrix. `QA_SCENARIOS.md` and `QA_SCENARIO_MATRIX.md` were absent when this judge started; the preserved matrix is in `QA_REVIEW_ROUND4.md`, originating in `QA_REVIEW_ROUND1.md`. B12 refers to the real file-history route; A02 refers to conversation history.

Native OS IME, controlled 503/CAS errors, and late-project-hydration races remain **AUTOMATED-only** preservation evidence. They are not claimed as manual browser scenarios and do not expand this UI task into artificial backend fault injection. A03 retains real Shift+Enter/send/copy coverage separately from its automated IME portion.

The judge will wait for `QA_CAPTURE_READY.md` to bind the expected source digest and a complete fresh inventory, verify hashes/format/dimensions/freshness and all required route/state evidence, then write one `QA_REVIEW.md` verdict: PASS with no blockers, or evidence-backed REVISE.
