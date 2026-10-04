---
title: Round 6 independent QA operator instructions
tags: [qa, frontend, manual-qa, keyboard]
date: 2026-10-03
---

# Operator instructions

Execution mode: **QA-agent-directed/root-executed**. Root alone operates the existing user-unlocked IAB browser2/tab1. This QA judge reviews the saved results and does not open a separate profile or interact with the PIN flow.

Required source binding: `a1552cf1f91459253bfb96910eeb7fcd0d29e5e8cb0e836cbcfc93267014d3b8`, Git HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus the 45-file dirty-source manifest. Expected current main assets: `index-DNX9exh1.js` and `index-BLgp1deP.css`.

These steps were sent to root before final execution. Root clarified that the supported foreground handoffs use the existing shortcuts, not palette menu commands; the judge accepted this correction before review.

1. At **375×812 and 768×900**, leave a distinct unsent draft. Open conversation history and each environment/code/changes inspection tab. Inspect the complete title and close header, test whether the actual close-button center hits that button, then click the real close control. Reopen and use Escape. Record visible dialogs, inert regions, focused element and retained draft after each dismissal.
2. From the open compact inspection dialog, press **Meta+K** to open the actual command palette. Record destination-only dialog ownership, combobox initial focus, foreground background/opacity/animation, and the early/settled visible surface. Use actual Tab and Shift+Tab, then Escape. Confirm the inspection opener regains focus, all released modal/inert state clears and the draft persists.
3. From open conversation history, press **Meta+Slash** to open the actual shortcut guide. Confirm only the guide remains and initial focus moves to its named Close button. Use actual Tab and Shift+Tab including boundary wrapping; focus must remain inside. Click the actual X and confirm the history opener regains focus. Repeat the handoff and dismiss with Escape, recording zero dialogs/inert regions and the same draft. Retain readable early/settled guide captures.
4. Retain the original **B01–B20 and A01–A05** case IDs. Native OS IME, controlled 503/CAS and late-hydration race checks remain explicitly **AUTOMATED-only**; do not label them as real browser passes.
5. Publish `QA_CAPTURE_READY.md` only after the complete fresh **78-frame packet** is ready: all 17 routes at the three required widths (51 route frames), plus 27 listed states including all six 768px panel/foreground additions and early 375px palette/guide entry. Bind source, output assets, captures, DOM and directed action results to the same source/build. Do not reuse earlier-round captures as final approval evidence.

The final judge will inspect the completed packet and write a one-shot **PASS** or actionable **REVISE** in `QA_REVIEW.md`; no final verdict is issued from this instruction file.
