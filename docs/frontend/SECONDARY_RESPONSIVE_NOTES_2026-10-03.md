---
title: Secondary-page responsive contract
tags: [dashboard, responsive, codex-workspace]
date: 2026-10-03
---

# Secondary-page responsive contract — 2026-10-03

`dashboard/src/styles/workspace-pages.css` is an additive compatibility layer for the legacy Unsloth Studio, Start, Model Hub, and Settings surfaces. It is imported after the existing workspace styles so it can correct inherited fixed-width layout rules without changing component behavior.

## Responsive rules

- **Page roots:** `.unsloth-studio-container`, `.unsloth-start-container`, `.unsloth-hub-container`, and `.settings-page` have an intrinsic inline size (`min-inline-size: 0; inline-size: 100%`). Their content remains in the normal page scroll owner.
- **Studio:** `.unsloth-studio-header` stacks below 1024px; `.unsloth-telemetry-card` and `.unsloth-stepper-bar` use intrinsic grids. The five pipeline steps remain visible and operable, instead of forming a horizontally overflowing strip. `.unsloth-model-grid` may become one column.
- **Start:** `.unsloth-start-header` stacks below 1024px and `.endpoint-hud-card` becomes an intrinsic grid. `.integrations-grid` uses `minmax(min(280px, 100%), 1fr)`, so a 375px canvas retains a readable card. `.cmd-text` is the intentional bounded code-overflow region; commands otherwise wrap.
- **Model Hub:** `.hub-category-pills`, `.hub-resource-filter`, and `.hub-quant-tier-pills` wrap controls. Category and quality buttons use intrinsic, compact controls with Korean phrase boundaries (`word-break: keep-all`), rather than narrow equal-width pills. `.hub-models-grid` and `.model-specs-row` use zero-minimum grids, and long provider, model, and spec values wrap inside their card.
- **Settings:** section headings and known fixed-width API status rows can wrap at compact widths. The local inline width on `.settings-row-status` yields to the compact stack, keeping visible controls inside the panel.

## Typography and visual behavior

The layer uses only the Design System's existing semantic variables and `--font-sans`. Secondary body text is 13px with 1.5 line height; page titles stay at the documented 24px. Korean prose uses `word-break: keep-all`; technical values may use `overflow-wrap: anywhere`. No content is hidden to mask overflow, no data/state styles are changed, and the primary action styles remain independent of the user accent preference.
