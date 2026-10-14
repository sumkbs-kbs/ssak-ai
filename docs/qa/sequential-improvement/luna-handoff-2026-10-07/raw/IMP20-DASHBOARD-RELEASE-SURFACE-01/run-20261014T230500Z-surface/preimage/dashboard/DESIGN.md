# Ssak-Ai Dashboard Design System

## 1. Atmosphere & Identity

A calm, conversation-first developer workspace inspired by the current Codex app. The sidebar gives projects and conversations a stable home; the main canvas gives reading and writing the most space. Neutral charcoal surfaces, readable system sans-serif, quiet borders and a restrained blue focus ring replace the former terminal decoration. SSAK-AI keeps its own name and actual capabilities.

Reference scope (2026-10-03): the public openai/codex repository at `604061ce51d194a3aa6aad3b3170240d096e1725` provides TUI/app-server patterns, not the Desktop React stylesheet. Adopt stable conversation history, a concise working status and keyboard access. A read-only inspection of the installed OpenAI bundle confirmed shared OpenAI Sans assets and system fallbacks; proprietary font files and application bundles are not copied. This is an adaptive SSAK-AI implementation of the requested hierarchy and typography, with no unsupported pixel-perfect claim.

Users and decisions: a Korean-speaking developer reads long responses, switches projects, chooses a local model, and inspects execution details. A returning user must identify the active conversation and model immediately. A keyboard user must reach navigation, composer, command palette and panels without losing focus. System detail is available on demand and never replaces conversation space.

## 2. Color

Canonical base tokens live in `src/styles/index.css`; workspace component styles live in `src/styles/codex-workspace.css`. New components use semantic variables. Existing theme preferences remain preserved.

| Role | Token | Value | Usage |
|---|---|---:|---|
| Main canvas | `--bg-primary` | `#202020` | Conversation and pages |
| Sidebar | `--bg-secondary` | `#181818` | Persistent navigation |
| Group / composer | `--bg-tertiary` | `#292929` | Input and grouped rows |
| Elevated / selected | `--bg-elevated` | `#333333` | Menus and selected rows |
| Panel | `--glass-bg` | `#252525` | Operational sections |
| Overlay | `--glass-bg-strong` | `#292929` | Popovers and drawers |
| Border | `--glass-border` | `rgba(255,255,255,.10)` | Quiet separators |
| Strong border | `--glass-border-strong` | `rgba(255,255,255,.20)` | Interactive boundaries |
| Hairline | `--terminal-border` | `#393939` | Code and utility separation |
| Primary text | `--text-primary` | `#ececec` | Headings and prose |
| Secondary text | `--text-secondary` | `#b8b8b8` | Supporting labels |
| Muted text | `--text-muted` | `#a0a0a0` | Metadata on dark surfaces |
| Dim text | `--text-dim` | `#929292` | Disabled labels |
| Interactive accent | `--accent-color` | `#a8bfff` | Links and selected tools; customizable |
| Focus | `--focus-ring` | `#a8bfff` | Keyboard outline, independent of preferences |
| Primary action background | `--action-bg` | `#ececec` | Send and primary buttons |
| Primary action text | `--action-text` | `#202020` | Text/icons on primary action |
| Success | `--success-color` | `#6ed6a0` | Real completed/healthy state |
| Warning | `--warning-color` | `#edc476` | Attention and paused state |
| Error | `--error-color` | `#ff8b8b` | Failure and disconnected state |
| Info | `--info-color` | `#a8bfff` | Informational state |

Use real state text beside status color. No neon telemetry glow, decorative grids, terminal comment prefixes or color-only states. Preserve user-selected accents; primary send contrast and focus do not depend on that preference.

## 3. Typography

| Level | Token | Size | Weight | Line height | Usage |
|---|---|---:|---:|---:|---|
| Empty conversation heading | `--text-4xl` | 28px | 600 | 1.25 | One clear starting prompt |
| Page heading | `--text-3xl` | 24px | 600 | 1.3 | Page titles |
| Panel heading | `--text-xl` | 16px | 600 | 1.45 | Section headings |
| Conversation prose | `--chat-font-size` | 16px | 400 | 1.7 | Assistant/user messages |
| UI body | `--text-base` | 14px | 400 | 1.5 | Navigation, controls, forms |
| Supporting body | `--text-sm` | 13px | 400 | 1.5 | Context, timestamps |
| Minimum metadata | `--text-xs` | 12px | 500 | 1.5 | Compact technical values |

- `--font-sans`: `-apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif`. Local system fonts support offline rendering and Korean text without copying proprietary OpenAI assets.
- `--font-serif` aliases the same sans-serif stack for existing headings. No editorial serif accents in product chrome.
- `--font-mono`: `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`, only code, terminal output and identifiers.
- Controls and metadata use the UI stack; no forced uppercase or letter spacing on Korean.

## 4. Spacing & Layout

Four-pixel spacing tokens (`--space-1` through `--space-20`) remain the shared scale. Controls use 8px internal gaps, 12–16px padding, and 24–32px between content groups.

| Token | Value | Usage |
|---|---:|---|
| `--sidebar-width` | 248px | Labelled desktop navigation; existing user preference may override |
| `--header-height` | 48px | One compact shell status/header row |
| `--chat-content-width` | 760px | Conversation and composer aligned on the same measure |
| `--chat-font-size` | 16px | Readable conversation body |
| `--border-radius` | 8px | Navigation rows and buttons |
| `--border-radius-lg` | 12px | Groups and panels |
| `--border-radius-xl` | 20px | Conversation composer |

- App shell uses 100dvh with min-height:0 children. The main page owns page scrolling; on chat, the named transcript scroll region owns it and the composer stays outside that region.
- Desktop >=1024px: labelled sidebar plus flexible main canvas. The inspection panel is a bounded third column only when enough space remains for the conversation.
- Below 1024px: explicit navigation toggle opens a labelled drawer with backdrop, Escape, focus trap and return. No anonymous icon-only rail. Selecting a destination closes the drawer.
- Below 1280px: inspection opens as an overlay with a labelled close button, focus trap and Escape; it never compresses or covers the composer without a dismissible modal boundary.
- 375/768/1280px are required QA widths. No horizontal primary-page scrolling at 375px. Grids use minmax(0,1fr), flex children min-width:0 and long IDs overflow-wrap:anywhere.
- Korean prose uses word-break:keep-all and natural spacing; code/path/IDs may break anywhere. Toolbars wrap rather than clipping controls.
- Project path, branch, permission, tools and model are secondary context, while the active conversation and message remain primary.
- The chat footer displays the `codex/` branch prefix as `ssak-ai/` for product naming. Its tooltip retains the exact Git branch; repository state and other technical branch views use the actual value.

## 5. Components

### Workspace Icon / Icon Button

Shared typed `AppIcon` renders 20px stroke SVGs at 1.7 stroke width. The icon is decorative (`aria-hidden`); the native button supplies a Korean accessible name, title, visible focus and pressed state when applicable. Controls are at least 32px desktop and 36px compact/mobile. No icon font or emoji substitutes. Disabled controls have both native disabled behavior and readable styling.

### Workspace Navigation

Native links for destinations and native buttons for project/session actions. Labels remain visible; selected rows use a tonal fill and `aria-current`. Projects have a separate expand control and selection action. Threads are a semantic list; rename/delete remain named controls. A mobile modal drawer reuses `useModalDialog`, returns focus on dismissal and closes after navigation. The sidebar has one named scroll region and a stable settings/footer row.

### System Status Disclosure

One summary line exposes actual connection status and a native details disclosure provides build, CPU, memory, vault and uptime. Loading/unknown, zero, stale and disconnected values retain their actual distinctions and existing test identifiers. No synthetic quota or nominal status is introduced. The popover is labelled, dismissible with Escape and uses the overlay surface.

### Conversation Canvas / Composer

A semantic conversation header, bounded transcript, centered empty state, and aligned composer. Assistant prose is open on the canvas; user text uses a subdued bounded bubble. Message copy, markdown sanitation, execution status, approvals and stream recovery remain functional. Composer contains a labelled textarea, optional attachments, wrapping tools, model selector and explicit send/stop action. Enter sends, Shift+Enter adds a line and IME composition does not send. Empty, disabled, streaming, error and attachment states use the same primitive rather than separate imitation forms.

### Assistant Response Typography / Disclosure

- **Structure**: the named assistant article contains readable Markdown followed by message copy and a native, initially collapsed `응답 정보` disclosure. The article supplies the SSAK-AI identity without a repeated visual label above every answer.
- **Typography**: prose uses `--font-sans`, `--chat-font-size` (16px), weight 400 and `--leading-relaxed` (1.7). Strong text and headings use weight 600. H1/H2 use `--text-2xl` (18px); H3–H6 use the 16px conversation size. Metadata and fenced code use `--text-sm` (13px); table cells use `--text-base` (14px). Only code and original preformatted text use `--font-mono`.
- **Spacing**: paragraphs and code/table groups use `--space-4` (16px); heading groups use `--space-6` (24px) above and `--space-3` (12px) below. Lists use `--space-6` indentation and `--space-2` between items. The first/last content groups have no extra outer margin.
- **Wrapping**: prose paragraphs without inline code use `text-wrap: pretty` with Korean word boundaries, keeping a short trailing word or emoji from occupying its own line. Paragraphs containing code retain ordinary inline flow so adjacent Korean particles stay attached. Emergency wrapping remains available for unbreakable strings; fenced code retains literal whitespace and internal scrolling.
- **Variants**: ordinary prose, streaming, headings/lists, inline code, labelled or unlabelled fenced code, table, blockquote, thought/tool/approval content, visible failure, and expanded response information. Code has a flat neutral surface, hairline border, UI-font header and named copy action. Tables and long code own horizontal scrolling inside the answer; the transcript remains the vertical scroll owner.
- **Envelope**: only recognized producer mode/CEO decoration and terminal successful quality/token records move to response information. Quoted, indented, fenced, inline-code, user and ordinary emoji content remain answer content. Retry/fail quality and action/error records stay visible. The stored response remains unchanged; an optional nested `원문 보기` disclosure exposes selectable original text, with a 240px bounded preformatted viewport.
- **Markdown boundary**: the renderer's existing CommonMark/GFM parser stack supplies literal code ranges from AST source positions. List-relative indentation, HTML blocks and incomplete inline text must pass the existing DOMPurify HTML profile with `style` forbidden; presentation code must not infer a sanitizer bypass from whitespace or delimiter heuristics. Exact thought tag markers retain their original streaming behavior while thought content remains sanitized.
- **States**: copy pending/success/error remains announced, metadata can arrive during streaming without replacing the answer, and failure/approval semantics remain visible and operable. Copying an assistant answer excludes recognized system decoration and existing private thought content; code copy preserves the actual code including unlabelled blocks.
- **Accessibility**: native disclosure keyboard behavior, persistent accessible article names, named copy controls, visible focus, semantic headings/lists/table and sanitized Markdown links/actions. Response information wraps at 375px and uses text labels rather than decorative emoji. Real failures retain their error color and text.
- **Motion**: no added animation. Neutral surfaces use existing color, border and radius tokens. Prose, code and table styling lives in scoped `workspace-response.css` and does not change operational pages.

### Conversation Run / Fork / Retry States (2026-10-03)

- **Progressive response**: existing assistant article displays received SSE content while generation continues. Working/Stop remain visible; the reading position follows output only while the user is already near the transcript end. An explicit latest-response action restores following when the user scrolls away. No layout animation or forced focus.
- **Run ownership**: one visible conversation owns the current run and its queued inputs. Stop or conversation/project navigation synchronously invalidates that run; late events cannot alter another conversation or a subsequent run. Queued inputs are cleared with visible feedback on cancellation; failed parent runs retain queued text and attachments for explicit edit or resend. Previously received prose remains readable. Returning to a saved conversation refreshes server history.
- **Conversation fork**: a named native action creates a server-backed new conversation from the active authoritative revision. It preserves the source row and history, uses the normal new-session display, and is discoverable from the command palette. Idle, pending, disabled-during-run/compaction, success, stale-revision and request-error states use existing buttons/status/toast primitives. No new color, type or motion token.
- **Task retry**: an error notice identifies an unresolved submit/fork operation and offers a named native retry action. The immutable operation/key is reused only in its original project and owner scope; a fresh user operation gets a new key. Input stays available after failure and clears after confirmed success only when the same draft is still present. Pending disables repeated clicks. Status is visible text and politely announced; no optimistic duplicate task row.

### Inspection Drawer

Environment/code/changes remain real tabs backed by current stores. Desktop column and compact modal share the same content. The modal has a labelled close action, Escape dismissal, focus trap and focus return. Active tab uses text plus selected state. Internal code/output owns bounded scrolling; header remains reachable.

### Conversation History Drawer

A labelled modal contains the existing project-scoped conversation list. Native selection, rename and delete controls retain the current store behavior. The header remains reachable, the list owns scrolling, and an empty state explains the scope. Escape returns focus to the opener. Opening the command palette, folder browser or shortcut guide closes the preceding modal and releases its focus trap. On initial project hydration, an empty untouched chat may restore its project cache once; a draft, attachment, new conversation or active stream prevents replacement.

### Operational Page Layout

Studio, Start and Model Hub share intrinsic header, metric and model-card grids. Compact headers stack below 1024px; filters and pipeline steps wrap with visible labels. Their page owns vertical scrolling; technical code may own bounded horizontal scrolling. Settings status rows and Korean body copy wrap within the panel. Legacy controls keep their current model, training, API and permission behavior. Layout corrections live in `workspace-pages.css` and use canonical font, spacing and color tokens.

### Capability and Catalog Truthfulness (2026-10-04)

- **Structure**: existing operational page, native controls, status text and error alert; no new visual token or animation.
- **Variants**: loading, confirmed empty, installed, running, unavailable, unverified, cached data with refresh failure, and retry pending. An authentication or transport failure must not become an empty catalog or completed operation.
- **Models**: installed catalog and provider runtime snapshot are separate facts; an unreadable runtime snapshot is unknown. Active model selection remains a separate label.
- **Studio and bridge**: only real job/artifact/capability receipts can establish completed training/export or a ready tunnel. Unsupported actions use native disabled controls and visible explanations. Copyable configuration uses named placeholders, never live credentials.
- **Extraction and skills**: shared authenticated HTTP boundary; loading and errors are visible, retry is named, cached content remains on failed refresh. Skills counts distinguish unknown from zero; publishing form discovery may fail independently of the catalog.
- **Palette and wiki**: a note is opened only after a successful authenticated read in the same project/session scope. Search navigates to the real wiki, new-note navigation opens the form, and unconnected self-test actions remain disabled. Merely visiting the wiki does not persist configuration.
- **Accessibility/layout**: status uses text plus color and polite announcements, errors use alerts, disabled actions retain readable reasons. Existing font, spacing, focus, wrapping and scrolling contracts apply at 375/768/1280px.

### Glass Panel

- **Structure**: semantic section or article with `.glass-panel`.
- **Variants**: default, elevated.
- **Spacing**: caller chooses `--space-3`, `--space-4`, or `--space-6` by density.
- **States**: default, hover, `focus-within`.
- **Accessibility**: does not replace semantic heading or landmark structure.
- **Motion**: border, shadow, transform using declared transition tokens.
- **Layout**: content wrapper; never owns scroll by default.

### Execution Run Selector

- **Structure**: labelled native `select`, live connection label, last-sequence metadata.
- **Variants**: loading, connected, reconnecting, complete, error, empty.
- **Spacing**: cluster with `--space-2` and `--space-3`.
- **States**: hover, focus-visible, disabled, loading, empty, error.
- **Accessibility**: persistent label, native keyboard support, live status announced politely.
- **Motion**: none beyond existing micro-transition tokens.
- **Layout**: wrapping cluster; page shell remains scroll owner.

### Agent Tree

- **Structure**: nested semantic list with agent label, relationship, status, and latest sequence.
- **Variants**: root-only, parallel children, metadata unavailable, empty.
- **Spacing**: dense stack using `--space-1` and `--space-2`.
- **States**: active, completed, failed, paused, unknown.
- **Accessibility**: nested lists preserve hierarchy; status is text, not color alone.
- **Motion**: none. Streaming updates preserve stable row identity.
- **Layout**: stack; no internal scrolling.

### Execution Checklist

- **Structure**: ordered list of step or task milestones with text status and optional tool metadata.
- **Variants**: planned, running, completed, failed, cancelled, blocked, unknown.
- **Spacing**: dense stack using `--space-2`.
- **States**: default, live update, empty.
- **Accessibility**: status has a visible label; sequence order matches DOM order.
- **Motion**: none.
- **Layout**: stack; no internal scrolling.

### Terminal Event Card

- **Structure**: article header, command/tool metadata, bounded preformatted output, sequence footer.
- **Variants**: running, completed, failed, approval-required, output-truncated.
- **Spacing**: `--space-3` header and footer, `--space-4` output.
- **States**: default, focus-within, empty output, truncated output.
- **Accessibility**: output is selectable text, status is not color-only, long content wraps without moving primary layout.
- **Motion**: none.
- **Layout**: stack. Output preview owns vertical scrolling and is height-bounded.

### Execution Block Stack

- **Structure**: an ordered list of typed projection blocks; each block delegates to one documented execution primitive.
- **Variants**: agent tree, checklist, terminal evidence.
- **Spacing**: intrinsic two-column grid for agent/checklist blocks followed by a full-width terminal block.
- **States**: each delegated primitive owns loading, empty, running, waiting, completed, failed, and cancelled states.
- **Accessibility**: block order matches event comprehension order; every block retains its semantic heading and landmark.
- **Motion**: none. Event projection updates preserve stable block and row identity.
- **Layout**: the stack never owns page scrolling; terminal output remains the only bounded nested scroll region.

### Command Palette Item

- **Structure**: native button with a semantic SVG icon, title, optional category, and selected state.
- **Variants**: built-in action, note search result, plugin action, unavailable/error row.
- **Spacing**: `--space-3` vertical padding, `--space-4` horizontal padding, `--space-2` internal gap.
- **States**: default, hover, keyboard-selected, focus-visible, disabled.
- **Accessibility**: listbox owns `aria-activedescendant`; each option has a stable ID and is operable with Enter or click.
- **Motion**: background and icon-color feedback use `--transition-fast`; no layout property animates.
- **Layout**: title truncates without hiding the category; the result list is the bounded scroll owner.

### Task Queue Panel

- **Structure**: labelled submit form followed by server-owned task rows and lifecycle controls.
- **Variants**: empty, pending, running, resuming, completed, failed, paused, cancelled.
- **Spacing**: compact operational stack using `--space-2` and `--space-3`.
- **States**: selected task, submitting, cancelling, resuming, disabled invalid action.
- **Accessibility**: prompt has a persistent label; each cancel/resume control includes the task title in its accessible name.
- **Motion**: color feedback only; streamed state changes do not move focus.
- **Layout**: task rows are the named bounded scroll region; task status remains a server projection.

### Session History / Fork

- **Structure**: the canonical task-history rows inside Task Queue, with source status, selection, lifecycle controls, and an explicit fork action.
- **Variants**: active source, terminal source, paused/failed source, fork request pending, fork failure.
- **Spacing**: history heading uses `--space-3`; row actions retain the compact `--space-2` cluster.
- **States**: selected source, fork pending, fork created and selected, source preserved.
- **Accessibility**: the fork control includes the source task title in its accessible name; creating a fork does not move or remove the source row.
- **Motion**: none. The new session appears through the normal server-list refresh without an optimistic clone.
- **Layout**: history reuses the Task Queue bounded list; no second scroll owner or session store is introduced.

### Approval Queue

- **Structure**: pending request list, selected request metadata, existing DiffViewer preview, and explicit deny/always-allow/approve controls.
- **Variants**: empty, pending request, no-diff request, resolving, request error.
- **Spacing**: compact list beside a flexible detail region using `--space-3`.
- **States**: selected, resolving, rejected, approved, always allowed.
- **Accessibility**: risk and tool name are visible text; each decision control includes the request description in its accessible name.
- **Motion**: none. Resolution removes only the server-confirmed request.
- **Layout**: queue and detail collapse to one column below tablet width; DiffViewer owns its bounded editor viewport.

### Job Operations Console

- **Structure**: health summary, policy alert, schedule list, and selected execution history.
- **Variants**: loading, empty, healthy, needs-attention, API error, retry pending.
- **Spacing**: metric grid uses `--space-3`; panels use `--space-4`; run rows use `--space-2`.
- **States**: selected schedule, failed run, retrying run, refresh pending.
- **Accessibility**: policy failures use an alert landmark and visible text; schedule selection uses native buttons; retry controls name the run ID.
- **Motion**: none; refresh and retry state changes do not animate layout or steal focus.
- **Layout**: `job-operations-layout` is a responsive two-column `list-detail` primitive that collapses to one column below `768px`; the page shell remains the only vertical scroll owner.

### Persistent Agency Console

- **Structure**: labelled objective form, scheduler state summary, durable context preview, and objective lifecycle list.
- **Variants**: loading, unavailable, idle, objective-ready, paused, and API error.
- **Spacing**: panel uses `--space-4`; form controls and objective rows use `--space-2` and `--space-3`.
- **States**: submitting, refreshing, paused, resumed, validation error, and completed objective.
- **Accessibility**: objective title has a persistent label; pause/resume is a named button; scheduler state is exposed through `role="status"` text and not color alone.
- **Motion**: no layout animation; state feedback uses existing control transitions and reduced-motion behavior.
- **Layout**: intrinsic single-column stack inside the agent page; context preview and long objective text wrap without horizontal overflow.

### Mutation Snapshot Console

- **Structure**: provenance summary, aggregate metrics, filter controls, and per-target historical result cards.
- **Variants**: historical snapshot, stale snapshot, invalid snapshot, and empty filter result.
- **Spacing**: summary and cards use `--space-5`; compact metric clusters use `--space-2` and `--space-4`.
- **States**: snapshot metadata, threshold comparison, stale warning, parse error, and no-match empty state.
- **Accessibility**: provenance and freshness are visible text with `role="status"`; threshold state is text plus color and cards remain keyboard operable.
- **Motion**: only the existing card border/hover transition; no motion implies live data.
- **Layout**: single-column stack with wrapping metric clusters; the page shell remains the scroll owner.

## 6. Motion & Interaction

| Type | Token | Usage |
|---|---|---|
| Micro | `--transition-fast` | Hover, active, focus feedback |
| Standard | `--transition-normal` | Surface and control state change |
| Slow | `--transition-slow` | Reserved for deliberate panel transitions |

- Streaming data updates do not animate layout or steal focus.
- Interactive controls include hover, active, focus-visible, disabled, loading, empty, and error states where applicable.
- Only transform and opacity may animate. Reduced-motion preference disables nonessential effects.

## 7. Depth & Surface

Strategy: neutral tonal separation with quiet borders.

- Primary depth comes from `--bg-primary` through `--bg-elevated`.
- `.glass-panel` supplies a subtle border for operational grouping without decorative blur.
- Shadows are reserved for overlays, selected elevated content, and hover feedback. Dense nested rows use tonal shifts instead of a card inside every card.
- Border radii follow the existing three-level system: `--border-radius`, `--border-radius-lg`, and `--border-radius-xl`. Pill radius is limited to badges and compact controls.

## 8. Accessibility Constraints & Accepted Debt

Constraints:

- Target WCAG 2.2 AA.
- Body text contrast is at least 4.5:1; large text and graphical controls are at least 3:1.
- Every interactive element is keyboard reachable and has a visible focus indicator.
- Status is communicated with text plus color.
- Live connection changes use polite announcements and do not interrupt current reading.
- Primary content has no horizontal page scroll at 375px.
- Korean and English labels remain legible without clipping or forced letter spacing.

Accepted debt:

| Item | Location | Why accepted | Owner / Exit |
|---|---|---|---|
| None | - | New debt requires explicit user approval | - |

Known pre-existing inconsistencies, not accepted as debt: the legacy stylesheet contains raw colors, emoji icons, undersized operational text, and repeated one-off spacing. New task-execution components do not extend those patterns; consolidation remains a separate refactor.
