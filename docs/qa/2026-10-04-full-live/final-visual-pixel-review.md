---
title: Full live final visual and CJK pixel review
tags: [qa, visual-qa, cjk, evidence]
date: 2026-10-04
---

# Final visual pixel review

**VERDICT: REVISE**  
**CONFIDENCE: HIGH**  
**Binding:** full HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`; capture-manifest SHA-256 `c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5`.

The 15 valid supplied JPEG frames are fully composited, have valid JPEG signatures, and match their declared widths at 900 px height. I opened every valid frame at original detail. The reviewed subset has no visible tofu, clipped CJK baseline/descender, one-character Korean orphan, detached particle/ending, or primary-page horizontal overflow. The full visual gate still needs evidence: the enumerated route/viewport matrix and interactive-state matrix are incomplete, so these frames cannot support a final PASS.

## Coverage

| Surface | 375 | 768 | 1280 | Result |
|---|---:|---:|---:|---|
| Data extraction / DEX | opened | opened | opened | 3/3 |
| Studio | opened | opened | opened | 3/3 |
| Start | opened | opened | opened | 3/3 |
| Jobs | opened | opened | opened | 3/3 |
| Skills | opened | opened | missing | 2/3 |
| Wiki | missing | missing | opened | 1/3 |
| Models | missing | missing | missing | 0/3 |
| Palette/modal states | missing | missing | missing | 0 required state frames |

Total opened and adjudicated: **15/21 route-width frames**. Required route-width evidence missing: **6 frames**. Required palette/modal state evidence is also absent. The preserved `root-ui-skills-capture-mismatch-1280.jpg` is correctly excluded: its decoded bounds are 375 x 900, not the claimed 1280 x 900, so it is pipeline-failure evidence and supplies no Skills 1280 proof.

## Blocking findings

1. **[evidence] [blocking] Incomplete responsive route coverage.** Models is absent at all three required widths; Wiki is absent at 375 and 768; Skills is absent at 1280. This violates the required complete enumeration and the `dashboard/DESIGN.md` 375/768/1280 QA-width contract. Evidence: directory inventory plus `visual-capture-metadata.json`; exact missing cells are listed above. Concrete fix: capture the six missing 900 px-high frames from the current build and validate signature, dimensions, full compositing, and source binding before review.
2. **[evidence] [blocking] Interactive state coverage is absent.** No current command-palette or modal-state capture is present, despite those states being explicitly required. This prevents inspection of focus containment, overlay bounds, dismissal controls, CJK wrapping, and underlying-content occlusion. Evidence: `docs/qa/2026-10-04-full-live/` contains only the listed route frames and metadata. Concrete fix: capture the enumerated palette and modal states at their required widths, including settled states, then inspect each original.
3. **[evidence] [blocking] The manifest does not bind captures to rendered-source bytes or enumerate routes/states.** `visual-capture-metadata.json` validates image hashes and dimensions, but has no source digest, build digest, capture timestamp field, route inventory, or state inventory. The filesystem times alone do not prove capture-after-last-rendered-source-edit. Evidence: the manifest's top-level data contains capture entries only. Concrete fix: issue a current manifest that binds the build/source digest, capture time, full expected matrix, and exclusion reason while retaining the original JPEG hashes.

## Pixel and CJK observations

- **[product] [note] Mobile Start toast crowds the shell header.** In `root-ui-start-375.jpg`, bounds approximately x=114..359, y=16..61, the copy-success toast covers the right side of the compact header and leaves the workspace label visually truncated near x=58..113. It does not prove content clipping after the toast settles, but the transient state should be rechecked as part of modal/overlay evidence.
- **[product] [note] Start endpoint breaks inside its numeric port at desktop width.** In `root-ui-start-1280.jpg`, the Local Endpoint card around x=709..878, y=72..151 renders `http://127.0.0.1:508` then `16/v1`. This is readable and the design contract permits emergency breaking for technical identifiers, so it is not a gate blocker; keeping the short endpoint on one line would improve scanning.
- **[product] [good] CJK rendering in the reviewed subset is stable.** Korean headings, descriptions, labels, and status copy remain legible across DEX, Studio, Start, Jobs, Skills, and Wiki. No visible glyph substitution, baseline clipping, isolated particle, or semantic Korean phrase fragment was found.
- **[product] [good] Responsive composition is coherent where supplied.** The 375/768 frames remove the labelled desktop sidebar and retain a named compact header; DEX grids, Studio steps/metrics, Start cards, and Jobs cards reflow without horizontal page overflow. The 1280 frames use the expected labelled sidebar and bounded content canvas.
- **[product] [good] Tokens and typography are consistent.** The reviewed pages use the same charcoal surfaces, quiet borders, restrained lavender focus/accent treatment, system sans body type, monospace only for technical values, and shared card radii/spacing. Nothing in the captures suggests a pasted screenshot or flat-image substitute.

## Evidence boundaries

This is a visual/CJK adjudication of the supplied current-build artifacts, not an exact-reference pixel comparison: the task defines a Codex-inspired adaptive layout and explicitly makes no pixel-clone claim. There is no reference image packet or same-size baseline to diff. Backend-only changes after these captures do not themselves imply a visible regression, but they also do not repair the missing frontend route/state evidence. Browser recapture remains pending because the authorized localhost user-browser surface is unavailable under the recorded browser-preference constraint; no CDP, alternate UI, HTTP, crop, resize, image edit, or fabricated frame was used.

## Terminal verdict

**REVISE — NEEDS EVIDENCE.** The 15/15 valid supplied frames pass direct pixel/CJK inspection for the visible regions, while the full visual gate cannot pass until the six missing route-width frames and required palette/modal states are captured from the current build and reviewed. No missing state is treated as a PASS.
