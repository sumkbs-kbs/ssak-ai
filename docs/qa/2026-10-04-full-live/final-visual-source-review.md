# Final visual-source review — REVISE (needs evidence)

**Recommendation:** `REVISE` for the full visual gate.  This is an evidence-only
revision, not a confirmed visual/product regression.  The available source and
the 15 valid frames support the current fixes, but cannot establish the required
complete route/state coverage.  `PASS` must not be inferred from a representative
subset.

**Binding inspected:** HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` and
`final-source-manifest.json` SHA-256
`c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5`.
I independently recomputed both values and the relevant UI source hashes matched
the manifest.  The manifest lists 56 source/test files and 12 harness files.

## Scope and method

This review covers the current functional-fix UI surface, whose intent is to
retain the existing Codex-inspired SSAK-AI hierarchy and tokens, make state
truthful, and **not** claim an exact clone.  `dashboard/DESIGN.md` explicitly
defines the adaptive, non-pixel-perfect scope.  There is no supplied exact
reference image, so an image-diff similarity score would be misleading and is
not claimed.

I inspected the complete valid JPEG set listed in
`visual-capture-metadata.json`, its file signatures/dimensions, the current UI
components and styles in the manifest, the current working-tree delta, the
source manifest, and the cited focused UI/API/build receipts.  I did not use a
browser, CDP, private user data, HTTP workaround, or any alternative route
around the saved-localhost permission denial.

## Coverage actually available

| Route family | 375 | 768 | 1280 | Result from inspected frames |
| --- | --- | --- | --- | --- |
| Data extraction | valid | valid | valid | Responsive, readable fixture state; the desktop output includes `1조 2,345억 원 : 1234500000000KRW`. |
| Studio | valid | valid | valid | The step grid wraps, and the Monitor & Export state presents no fabricated completion. |
| Agent Start | valid | valid | valid | Command blocks wrap and show `--api-base`; the endpoint is `127.0.0.1:50816/v1`. |
| Job operations | valid | valid | valid | Zero completed runs is rendered as `—` / `No completed runs`, not 100%. |
| Skills | valid | valid | **missing** | Empty MCP state is shown, but the capture alone does not prove an authenticated catalog request. |
| Wiki | **missing** | **missing** | valid | The wide frame shows sidebar/tree/content anatomy only. |
| Models | **missing** | **missing** | **missing** | No valid current frame. |

The expected static responsive matrix is 21 frames (seven routes at three
widths); 15 valid frames are present.  The one retained file named
`root-ui-skills-capture-mismatch-1280.jpg` is actually 375×900, is correctly
marked `valid_review_capture: false`, and was excluded.  The requested Wiki
create/edit/search, command-palette, and modal states have no corresponding
valid capture.  They remain unverified rather than passed.

## Design-system and DOM integrity

### What the source proves

- **Live component tree:** each reviewed route renders DOM components and native
  controls.  Examples include the extraction sections and retry controls in
  `dashboard/src/pages/DataExtractionPage.tsx:105`, Studio's live SVG/chart and
  disabled export buttons in `dashboard/src/pages/StudioPage.tsx:648` and
  `:700`, Wiki's `WikiSidebar`, `ContentPanel`, and modal components in
  `dashboard/src/pages/WikiPage.tsx:81`, and the job list/run-history controls
  in `dashboard/src/features/job-operations/JobOperationsPage.tsx:176`.
  The reviewed route sources contain no `<img>`, `background-image`, data-image,
  or canvas substitute for a page screenshot.  The Studio chart is a live SVG,
  driven by `lossHistory`, rather than a raster stand-in.
- **Reusable primitives and layers:** the app shell loads
  `codex-workspace.css` from `dashboard/src/main.tsx`; that layer imports the
  shell/chat/response/inspection/history/page primitives.  Its shared shell
  rules use `--font-sans`, `--text-base`, `--focus-ring`, surfaces, and button
  states (`dashboard/src/styles/codex-workspace.css:1-37`).  Operational layout
  wrappers and responsive grids live in
  `dashboard/src/styles/workspace-pages.css:1-304`; they use semantic spacing,
  typography, and surface tokens.
- **Token-driven owned delta:** the visual additions in the current fix delta
  use semantic variables such as `--space-2`, `--space-4`, `--text-muted`, and
  `--error-color` in the Skills and extraction failure states
  (`dashboard/src/pages/SkillsPage.tsx:38-78`,
  `dashboard/src/pages/DataExtractionPage.tsx:179-183`).  The design scale is
  centrally declared in `dashboard/src/styles/index.css:65-124`.  The current
  job projection reuses its existing tokenized metric tile instead of adding a
  bespoke visual treatment (`JobOperationsPage.tsx:169-173`; associated style
  `index.css:9317-9350`).
- **Truthful functional states:** Studio exposes unavailable export controls as
  native disabled buttons with a visible explanation
  (`StudioPage.tsx:693-724`).  Agent Start derives and displays the actual API
  base/command, reports the tunnel as unverified, and shows copy success/failure
  rather than claiming a connection (`AgentStartPage.tsx:94-216`).  The Skills
  surface sends the catalog through the shared authenticated client and has
  separate error/retry state (`SkillsPage.tsx:21-93`,
  `pages/skills/skillsApi.ts:37-73`).  Palette Wiki selection reads a document
  before it navigates (`features/command-palette/commandRegistry.ts:56-77`).

The independent source/build receipts corroborate these paths but are not used
as a substitute for visual interaction evidence: `root-final-ui-tests.log`
reports 133 passing focused UI tests, `dashboard-final-build.log` records a
successful Vite build, and `final-qa-review.md` limits its 118 API / 9 CLI
passes to their executed isolated surfaces.  The root checklist's fixture UI
receipt records Wiki create/edit/search as passing in an isolated vault; it is
not promoted here to proof for an unrecorded production modal frame.

### Visual observations from the valid frames

The valid frames use the same dark shell, quiet borders, compact top status,
and Korean/system-sans hierarchy specified by the design contract.  At 375px,
the route body becomes the scroll owner, toolbars/cards wrap, and no primary
horizontal overflow is visible in extraction, Studio, Start, or Jobs.  At 768px
the grids use a two/four-card intermediate layout; at 1280px the labelled
sidebar returns and the main content retains a readable density.  I found no
black compositor regions or malformed image signatures.  JPEG has no alpha
channel, so alpha preservation cannot be positively verified from these files.

## Findings

### CRITICAL

None.  No reviewed source indicates a pasted screenshot, raster page surrogate,
or a fake completed/connected state in the owned fixes.

### HIGH

1. **[evidence] Full visual coverage is incomplete.** The valid set lacks
   Models at 375/768/1280, Skills at 1280, Wiki at 375/768, and every requested
   Wiki create/edit/search, palette, and modal state.  A full visual acceptance
   cannot pass while these are absent.  This is not a source-change request;
   capture each missing state from the frozen current build at the declared
   viewport, validate signature/dimensions, and bind it to the manifest.

2. **[evidence] No current live recheck is available for the saved-browser
   boundary.** `final-source-manifest.json` explicitly records the saved browser
   permission block.  The existing actual frames demonstrate appearance only;
   they do not verify interactions such as the authenticated Skills load or the
   palette-to-Wiki selection on the user-local surface.  Preserve the block and
   obtain the permitted live receipt instead of working around it.

### MEDIUM

1. **[evidence] Alpha and interaction transitions are not assessable from the
   supplied JPEG rest frames.** The files are valid JPEGs at the requested
   dimensions, but JPEG cannot establish alpha integrity, and there are no
   before/mid/settled frames for modal, palette, retry, copy, or disabled-control
   interactions.  Capture those states with their declared outcome; this is a
   coverage gap, not evidence of a rendering defect.

### LOW

1. **[product, baseline debt] Some legacy operational-page styling remains
   hard-coded outside this functional-fix delta.** For example, Studio's legacy
   chart colors use literal values in `dashboard/src/pages/StudioPage.tsx:651-683`
   and its older page CSS uses literal spacing/color values in
   `dashboard/src/styles/index.css:9686-9755`.  These predate the reviewed
   state/auth changes; the owned delta did not add corresponding literals, and
   the captured pages are visually coherent.  Consolidating this legacy styling
   into semantic tokens would improve system rigor, but it is not evidence that
   the current fixes faked the UI or introduced a current visual regression.

## Concrete acceptance conditions

1. Supply valid current-build frames for the six missing static route/viewport
   cells and for the requested Wiki/palette/modal interaction states.
2. Once saved-localhost permission permits, record the same live interactions
   that matter to the fixes: authenticated Skills state (or visible failure),
   palette search → successful Wiki document read, Wiki create/edit/save, the
   Studio disabled export explanation, Agent Start copy result, and Job zero-run
   summary.  Do not use an alternate browser/API/CDP route as a substitute.
3. Re-run this visual gate against that complete capture set.  No exact
   pixel-comparison target is required by `dashboard/DESIGN.md`; the check is
   fidelity to its documented adaptive hierarchy and token system.

## Verdict

**REVISE — NEEDS EVIDENCE.** Product/source integrity for the inspected current
fixes is acceptable; the full visual gate is **inconclusive** because route and
interaction coverage is incomplete.  Missing frames and the saved-browser block
must remain explicitly unavailable, never promoted to `PASS`.
