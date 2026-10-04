# Manual frontend QA review — 2026-10-03 Codex-inspired SSAK-AI UI

## Verdict and exact surface

Verdict: **FAIL (blocked before product surface)**. This is a manual QA execution record, not an inferred product pass. The exact surface was the Codex IAB browser at `http://127.0.0.1:8000/`. The exact first invocation was:

```js
await cua.getTab({url:'http://127.0.0.1:8000/'},{browser:'iab'})
```

It returned no tab. A fresh IAB tab was created at the same URL solely to establish the blocker. Its read-only AX tree contains the PIN gate and no application routes. The executor did not enter a PIN, alter auth, read tokens/cookies/storage, or modify the product.

Every scenario below was attempted against that real surface. A scenario marked `FAIL — blocked` is not a skipped or inferred pass; it identifies the missing prerequisite and the exact invocation that could not reach the requested state.

## Evidence and bundle binding

- Build: `BUILD_CURRENT.log` reports `vite build` completed, exit 0.
- Current source binding: HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, source digest `6b1aacf46676070701e3367fde89ecdecc4cd379ca57ef96d7f0c31513bb3006`.
- Current browser script binding required for final captures: `/assets/index-C1osb2i9.js`, SHA-256 `d99e4b85da7a49b170f76deb7d5472a0e9475353687d7891b1a8776324829184`; CSS `/assets/index-Gvc9kB2l.css`, SHA-256 `262203755555eb7fc244a646a41862d028f3d016e9ec0564835d58eb0bf58f0d`.
- Fresh lock-gate observation: [LOCKED_TAB_OBSERVATION.md](LOCKED_TAB_OBSERVATION.md) and [blocked-pin-lock-1280x720.jpg](captures/blocked-pin-lock-1280x720.jpg).
- Historical evidence was independently checked and rejected for final use because `BROWSER_OBSERVATIONS.json` binds to stale `/assets/index-CJUpMcF4.js`.

## Brainstorm scenarios (20)

All rows have the same blocker: after the stated navigation/action, the fresh IAB tab still shows `🔒 시스템 잠금` and the PIN field. No product route was reached.

| ID | Criterion | Priority | Surface and exact invocation | Steps and expected result | Actual result / verdict | Artifact refs |
|---|---|---:|---|---|---|---|
| B01 | Route `/` initial hydration | P0 | IAB tab 1; `tab.goto('http://127.0.0.1:8000/')`; `tab.getAXState()` | Fresh home should render sidebar, heading, composer and active model. | PIN gate only; **FAIL — blocked**. | A5,A6 |
| B02 | `/chat` alias | P1 | `tab.goto('http://127.0.0.1:8000/chat')`; AX snapshot | Alias should resolve to chat without fallback. | PIN gate only; **FAIL — blocked**. | A5 |
| B03 | `/studio` | P1 | `tab.goto('http://127.0.0.1:8000/studio')`; screenshot + AX | Studio heading and controls should load. | PIN gate only; **FAIL — blocked**. | A5 |
| B04 | `/models` | P1 | `tab.goto('http://127.0.0.1:8000/models')`; screenshot + AX | Model hub heading/list should load without clipping. | PIN gate only; **FAIL — blocked**. | A5 |
| B05 | `/start` | P1 | `tab.goto('http://127.0.0.1:8000/start')`; AX | Agent start page should expose its labelled form. | PIN gate only; **FAIL — blocked**. | A5 |
| B06 | `/wiki` | P1 | `tab.goto('http://127.0.0.1:8000/wiki')`; screenshot + AX | Wiki page should expose heading and content area. | PIN gate only; **FAIL — blocked**. | A5 |
| B07 | `/agent` | P1 | `tab.goto('http://127.0.0.1:8000/agent')`; screenshot + AX | Agent page should render its semantic sections. | PIN gate only; **FAIL — blocked**. | A5 |
| B08 | `/settings` secrets masking | P0 | `tab.goto('http://127.0.0.1:8000/settings')`; DOM text snapshot | Settings should load and mask sensitive values. | PIN gate only; **FAIL — blocked**. | A5 |
| B09 | `/skills` | P1 | `tab.goto('http://127.0.0.1:8000/skills')`; AX | Skills page should render discoverable skill rows. | PIN gate only; **FAIL — blocked**. | A5 |
| B10 | `/data-extraction` | P1 | `tab.goto('http://127.0.0.1:8000/data-extraction')`; screenshot + AX | Data extraction heading and controls should load. | PIN gate only; **FAIL — blocked**. | A5 |
| B11 | `/git` | P1 | `tab.goto('http://127.0.0.1:8000/git')`; screenshot + AX | Git inspection page should load its tabs/panels. | PIN gate only; **FAIL — blocked**. | A5 |
| B12 | `/history` | P0 | `tab.goto('http://127.0.0.1:8000/history')`; screenshot + AX | History page should expose project-scoped sessions. | PIN gate only; **FAIL — blocked**. | A5 |
| B13 | `/plugins` | P1 | `tab.goto('http://127.0.0.1:8000/plugins')`; AX | Plugin index should render. | PIN gate only; **FAIL — blocked**. | A5 |
| B14 | `/mutation` | P1 | `tab.goto('http://127.0.0.1:8000/mutation')`; AX | Mutation page should render status/content. | PIN gate only; **FAIL — blocked**. | A5 |
| B15 | `/plugins/hello-world` | P1 | `tab.goto('http://127.0.0.1:8000/plugins/hello-world')`; AX | Plugin route should render its page. | PIN gate only; **FAIL — blocked**. | A5 |
| B16 | `/plugins/job-operations` | P1 | `tab.goto('http://127.0.0.1:8000/plugins/job-operations')`; AX | Job operations console should render. | PIN gate only; **FAIL — blocked**. | A5 |
| B17 | Intentional unknown route fallback | P0 | `tab.goto('http://127.0.0.1:8000/intentional404route')`; screenshot + AX | NotFound fallback should be visible and remain inside shell. | PIN gate only; **FAIL — blocked**. | A5 |
| B18 | Mobile navigation drawer | P0 | viewport 375×812; `tab.goto('/')`; click labelled nav toggle; AX/screenshot | Drawer/backdrop opens, Escape closes, focus returns. | PIN gate prevents toggle; **FAIL — blocked**. | A5 |
| B19 | Command palette and shortcut guide | P0 | viewport 768×900; `tab.goto('/')`; `tab.pressKey(null,'ControlOrMeta+K')`, then `Meta+/`; AX | Palette/guide opens, labelled, and closes without focus loss. | PIN gate prevents shortcut host; **FAIL — blocked**. | A5 |
| B20 | Model selector layout and persistence | P0 | viewport 375×812; `tab.goto('/')`; click model selector; reload; AX + rects | Current qwen27.3B selection and popover should fit and persist. | PIN gate prevents model UI; **FAIL — blocked**. | A5 |

## Augmentation scenarios (5)

| ID | Criterion / adversarial class | Priority | Surface and exact invocation | Steps and expected result | Actual result / verdict | Artifact refs |
|---|---|---:|---|---|---|---|
| A01 | Inspection tabs and bounded scrolling | P0 | viewport 1280×900; `tab.goto('/')`; click Inspection → Environment/Code/Changes; AX + screenshot | Each tab should show current content, bounded output, and reachable close/focus return. | PIN gate prevents inspection panel; **FAIL — blocked**. | A5 |
| A02 | History drawer selection and route link | P0 | viewport 768×900; `tab.goto('/')`; open History; select a session; click route link; AX | Drawer should close after navigation and preserve selected session. | PIN gate prevents history; **FAIL — blocked**. | A5 |
| A03 | Composer keyboard / IME / clipboard | P0 | viewport 375×812; focus composer; `Shift+Enter`, IME composition source-backed check, send, copy last response | Shift+Enter inserts newline, Enter sends only after composition, Copy writes last response. | Composer/response unavailable; **FAIL — blocked**. | A5,A8 |
| A04 | Terminal/output viewing safety | P0 | `tab.goto('/')`; open terminal/output viewer; read visible output without entering a command; AX/screenshot | Existing output is viewable; no command is sent by inspection. | Terminal unavailable behind gate; **FAIL — blocked**. | A5 |
| A05 | Recovery adversaries: 503, CAS, hydration | P0 | `tab.goto('/')`; source-backed expected checks for 503 retry, CAS conflict, and project hydration; browser state observation | 503 shows retry, CAS preserves conflict state, hydration restores only untouched chat. | No app state can be observed; **FAIL — blocked**. | A5,A8 |

## Manual QA matrix

### `surfaceEvidence`

The 25 scenario rows above are the required surface-evidence matrix. Each contains scenario ID, criterion, exact surface/invocation, verdict, and artifact references. There are **0 PASS** rows; all are concrete failures caused by the locked-tab prerequisite.

### `adversarialCases`

| Scenario ID | Criterion reference | Adversarial class | Expected behavior | Verdict | Artifact refs |
|---|---|---|---|---|---|
| B17 | NotFound route | Route fallback | Unknown route renders intentional NotFound fallback. | FAIL — blocked | A5 |
| B18 | Responsive navigation | 375px drawer/focus | Drawer opens, Escape closes, focus returns, no horizontal overflow. | FAIL — blocked | A5 |
| B20 | Model selector | Mobile popover overflow | Popover stays within 375px viewport and selected model survives reload. | FAIL — blocked | A5 |
| B08 | Settings | Secrets masking | Settings never exposes raw credentials or keys. | FAIL — blocked | A5 |
| A03 | Composer | IME / Shift+Enter | Composition does not send; Shift+Enter creates a draft newline. | FAIL — blocked | A5,A8 |
| A05 | API recovery | 503 retry / CAS conflict | Retry and conflict states are explicit and preserve user input. | FAIL — blocked | A5,A8 |
| A05 | Project hydration | Hydration replacement | Only untouched empty chat may be replaced by project cache. | FAIL — blocked | A5,A8 |
| A04 | Terminal viewer | Command transmission | Viewing output does not execute a command. | FAIL — blocked | A5 |
| B19 | Keyboard access | Focus trap / shortcut collision | Palette and guide are keyboard reachable and restore focus. | FAIL — blocked | A5 |
| B03–B16 | All secondary routes | CJK/layout clipping | Korean labels and long IDs wrap without horizontal page overflow. | FAIL — blocked | A5 |

## Artifact references

| ID | Kind | Description | Path |
|---|---|---|---|
| A1 | build-log | Final build completion and exit 0 | `docs/qa/2026-10-03-codex-ui/BUILD_CURRENT.log` |
| A2 | manifest | Current source and bundle hashes | `docs/qa/2026-10-03-codex-ui/BUNDLE_MANIFEST.json` |
| A3 | manifest | Source file inventory and final binding | `docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json` |
| A4 | design-contract | Responsive routes, focus, keyboard, CJK and layout expectations | `dashboard/DESIGN.md` |
| A5 | screenshot | Fresh CUA JPEG showing the blocking PIN gate, 1280×720 | `docs/qa/2026-10-03-codex-ui/captures/blocked-pin-lock-1280x720.jpg` |
| A6 | observation | Exact CUA invocation, AX tree, DOM metrics, screenshot hash | `docs/qa/2026-10-03-codex-ui/LOCKED_TAB_OBSERVATION.md` |
| A7 | historical-observation | Prior browser evidence checked and rejected as stale C1osb2i9 coverage | `docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json` |
| A8 | test-log | Source-backed automated test baseline (980 tests) used only for expected behavior | `docs/qa/2026-10-03-codex-ui/TESTS_CURRENT.log` |
| A9 | capture-manifest | Current capture inventory and blocked route coverage | `docs/qa/2026-10-03-codex-ui/CAPTURE_MANIFEST.json` |

## Blocker and next action

The missing prerequisite is an already PIN-unlocked IAB tab at localhost:8000 bound to this QA session. The executor is explicitly prohibited from entering or changing PIN/auth state, so a fresh tab cannot be unlocked here. No browser route, responsive breakpoint, state interaction, or adversarial case can be marked PASS until that tab is supplied; rerun all rows with fresh C1osb2i9 captures after the blocker is removed.
