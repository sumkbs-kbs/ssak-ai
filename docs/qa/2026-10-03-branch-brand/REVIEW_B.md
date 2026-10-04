# Visual QA Review B — footer branch alias / CJK precision

**VERDICT: PASS**  
**CONFIDENCE: HIGH**

## Intent and scope

The requested user-visible outcome is limited to the bottom chat footer: display an actual branch beginning with `codex/` as `ssak-ai/`, preserve the exact Git branch in the title tooltip, and leave repository state and other branch views unchanged. This review does not treat the preserved conversation/model content as a product issue, and makes no proprietary pixel-clone, Lighthouse, new-chat, or full-accessibility claim.

## Evidence binding

- Frozen source: `SOURCE_MANIFEST.json` SHA-256 `ad74348cdff8d1c1ee95c545f8424b0c762acd9a6f9df292c98fb398082a7327`; repository HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Current hashes reproduce the manifest: `ChatPage.tsx` `8dd7cd8d3e5ea920973b73c2dab2aa65b482f96fbb44b445820e1fcd9fc247fe`; `DESIGN.md` `acf4eaf7dc081b467854f5c50c5a0f829d058f93602f896f24666da26a2a24ef`.
- Source was frozen at 15:40:38 KST; build finished after that and the four final captures were produced after the build (15:42:09–15:42:11 KST). The three `before-*` images are explicitly declared baseline exceptions.
- `TASK_DELTA.patch` contains exactly the relevant one-line JSX presentation change and one-line design contract. The anchored expression `workspaceContext.branch.replace(/^codex\//, 'ssak-ai/')` changes only the leading display prefix. The title is `실제 Git 브랜치: ${workspaceContext.branch}` and therefore preserves the original value. Empty-branch conditional rendering remains intact.
- `VERIFICATION.json` records typecheck and production build exit 0; `BUILD.log` ends with `built in 20.66s`. `BROWSER_LOGS.json` is empty. No implementation-mirroring test was added for this reversible label-only change.

## Direct image inventory (13/13 opened at original resolution)

Original JPEGs: `before-375.jpg` (375×954), `before-768.jpg` (768×954), `before-1280.jpg` (1280×954), `after-375.jpg` (375×954), `after-768.jpg` (768×954), `after-1280.jpg` (1280×954), and `deliverable.jpg` (757×954). Comparison PNGs: `before-375.png`, `before-768.png`, `before-1280.png`, `after-375.png`, `after-768.png`, and `after-1280.png`, each matching its named viewport. All were directly opened with original-detail rendering; no sampling or prior PASS was reused.

The footer reads `ssak-ai/m1-task-events` in all four post-change originals. It remains on one line, visually legible, and clear of the viewport edge and adjacent `로컬` label at 375, 768, 1280, and 757 widths. Measured branch width increases slightly from 128.21875px to 134.84375px, as expected for the longer prefix. Bounds remain inside every viewport: x=162.984375 at 375, x=174.984375 at 768/757, and x=534.984375 at 1280; height is 18px. The captured DOM title is exactly `실제 Git 브랜치: codex/m1-task-events` in every after capture.

The Korean footer/tooling labels and visible Korean conversation text show no dropped glyphs, tofu, clipped baselines, one-character orphan caused by the alias, or new semantic wrapping. Existing body and code overflow belongs to preserved conversation content and is outside this footer-label change.

## Diff evidence and complete hotspot trace

All three JSONs report `command=image-diff`, matching dimensions, intact alpha, and reference/actual sizes equal to the named viewport. The values below account for every hotspot.

### 375×954

`totalPixels=357750`, `diffPixels=4204`, `diffRatio=0.0118`, `similarityScore=99`, `alphaChannelIntact=true`; 8/8 hotspots:

- `(5,0) x234 y0 47×119, 0.1454`; `(4,0) x187 y0 47×119, 0.1275`; `(6,0) x281 y0 47×119, 0.0704`: live server age changes from 2s to 1s and nearby JPEG antialiasing in the top status strip.
- `(5,7) x234 y834 47×120, 0.1294`; `(4,7) x187 y834 47×120, 0.1289`; `(3,7) x140 y834 47×120, 0.0767`; `(6,7) x281 y834 47×120, 0.0590`: intended footer text replacement plus the 6.625px wider prefix and local text antialiasing. Direct inspection shows no collision or clipping.
- `(5,2) x234 y238 47×119, 0.0114`: minor JPEG/raster variation within the unchanged code block; no source change or visible layout displacement.

### 768×954

`totalPixels=732672`, `diffPixels=2209`, `diffRatio=0.0030`, `similarityScore=100`, `alphaChannelIntact=true`; 3/3 hotspots:

- `(2,7) x192 y834 96×120, 0.1298`; `(3,7) x288 y834 96×120, 0.0323`; `(1,7) x96 y834 96×120, 0.0313`: all intersect the footer branch region and its immediate antialiasing footprint. They map to the requested `codex/` → `ssak-ai/` display substitution; the label remains fully visible and separated from adjacent items.

### 1280×954

`totalPixels=1221120`, `diffPixels=83744`, `diffRatio=0.0686`, `similarityScore=93`, `alphaChannelIntact=true`; 17/17 hotspots:

- Sidebar/reload state: `(0,5) x0 y596 160×119, 0.6222`; `(0,3) x0 y357 160×120, 0.5898`; `(0,6) x0 y715 160×119, 0.5852`; `(0,4) x0 y477 160×119, 0.5840`; `(0,1) x0 y119 160×119, 0.5607`; `(0,2) x0 y238 160×119, 0.3137`; `(0,7) x0 y834 160×120, 0.2637`; `(1,3) x160 y357 160×120, 0.2334`; `(1,1) x160 y119 160×119, 0.2167`; `(1,4) x160 y477 160×119, 0.2006`; `(1,5) x160 y596 160×119, 0.0371`; `(0,0) x0 y0 160×119, 0.0256`; `(1,2) x160 y238 160×119, 0.0204`; `(1,7) x160 y834 160×120, 0.0183`; `(1,0) x160 y0 160×119, 0.0061`. Direct comparison confirms the before image holds the desktop sidebar at a previous scroll offset while the after image is at reload initial position: `새 채팅` and list rows shift into view. This is outside the changed source region and matches the declared capture-state difference; the main conversation/composer geometry remains stable.
- Intended footer alias: `(3,7) x480 y834 160×120, 0.0887` covers the branch item and maps to `codex/` → `ssak-ai/` plus the slight width increase. It is legible and unclipped.
- Live clock/status: `(4,7) x640 y834 160×120, 0.0254` is low-level raster variation at the footer/composer boundary; direct inspection shows no product displacement. The top live clock remains 3s in the paired images, while minor antialiasing and the neighboring changed branch footprint account for residual pixels.

## Findings

- **[product] Good:** The bottom footer alone presents `ssak-ai/m1-task-events`; the actual `codex/m1-task-events` survives unchanged in the title measurement and source expression.
- **[product] Good:** The longer label fits at all required widths and the default 757px deliverable. No CJK clipping, overlap, or new wrap is visible.
- **[evidence] Good:** The four after captures are fresh relative to frozen source and successful build; signatures, dimensions, manifest hashes, source binding, and browser-log evidence agree.
- **[evidence] Note:** Before captures are historical baselines by declared exception, so they are valid only as references. The 1280 pair is not a same-scroll pixel target; its non-footer hotspots are fully explained by prior-scroll versus reload-initial sidebar state. This limits whole-frame fidelity inference but does not weaken verification of the scoped footer outcome.

## Blocking

None.
