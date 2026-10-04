---
title: Bridge CLI authentication plan contract
tags: [qa, bridge, cli, authentication]
date: 2026-10-04
---

Planned ownership: `src/antigravity_k/engine/agent_bridges.py`, `tests/test_agent_bridge_auth_plan.py`, and the explicitly approved Anthropic variable, model-copy quoting and API-base corrections in `dashboard/src/pages/AgentStartPage.tsx` and its focused test. CLI entry-point, API authentication, config/store, tunnel execution, and other dashboard source remain outside this change.

Planned evidence: `bridge-cli-auth-red.txt`, `bridge-cli-auth-focused.txt`, and this contract. The manual CLI driver owner adds and runs the ninth safe `agk start codex` print-only case separately.

## Debug journal

Hypothesis: the print-only bridge resolver supplies a fake credential, and the renderer repeats it in Codex configuration. Protected routes require the signed `/api/auth/login` bearer token. Model/base values and optional JSON configuration also need data encoding before a user later copies them.

Static evidence: `resolve_bridge` is called by the CLI `start_agent_bridge`, which prints `format_bridge_plan` and does not launch a process. Five bridge specs used the same fake key; Codex separately replaced it inline and displayed an unresolved base placeholder.

Reproduction boundary: patch `Path.home()` and expansion before product imports, preserve `HOME` and `CODEX_HOME`, use synthetic isolated configuration/stores and reject outbound network. Evaluate only shell export blocks with synthetic tokens; parse agent command text without running agents, tunnels, models, or real authentication.

Primary client contract verified 2026-10-04: [Claude Code environment variables](https://code.claude.com/docs/en/env-vars). `ANTHROPIC_AUTH_TOKEN` supplies bearer authentication, while `ANTHROPIC_API_KEY` supplies `X-Api-Key`. The latter does not match this repository's protected-route bearer-only authentication policy. No client connection was attempted.

## Results

- Failing first: all 20 new isolated contract cases failed before the backend fix (`bridge-cli-auth-red.txt`). The approved GUI bearer-variable assertion also failed before its correction.
- Green: 34 cases across existing bridge tests and the new auth-plan tests (`bridge-cli-auth-focused.txt`); Python Ruff passes; Python basedpyright reports zero errors, warnings, and notes. The stale basedpyright launcher shebang was bypassed with the already installed `.venv/bin/python -m basedpyright`; nothing was installed.
- Direct local AgentStartPage Vitest: twelve cases pass, including the approved model-copy shell argument regression and the actual-origin/configured-base corrections. Targeted ESLint passes. Direct dashboard TypeScript `tsc --noEmit` passes.
- All five plans use a guarded named signed-token reference. The renderer never reads the token environment and ignores supplied credential-map values. Anthropic plans unset the inherited API-key variable and export the bearer-token variable. Codex receives credentials through the exported environment, with no token in process arguments.
- Noncredential shell values use `shlex.quote`; Codex's resolved base is encoded as a TOML-compatible quoted string; astral Unicode is retained rather than encoded as invalid TOML surrogate escapes. The optional Claude model-picker JSON is encoded as data.
- Independent read-only review approved the credential/no-launch boundary and identified the Unicode TOML edge, which is now covered by the parsed-TOML command regression.
- Repository graph lookup was attempted before the tunnel capability check but this exact checkout was unindexed. Bounded fallback inspection finds no Python/YAML tunnel/cloudflared implementation under src/antigravity_k. The copied cloudflared command assumes an already configured, user-named external tunnel; repository configuration does not supply or verify that match. Tunnel readiness and external reachability remain unverified.

CLI entry-point and authentication policy are unchanged. Planning succeeds without a token because it prints configuration only; evaluating the exports later requires the user's signed token and otherwise produces actionable missing-variable output. No signed token was obtained, logged, supplied in argv, or persisted. No external CLI, model, tunnel or remote exposure was launched. Parent owns the actual safe CLI/browser surface QA.

## Live retest reopened source

The parent directly opened the latest UI at `http://127.0.0.1:50816/start` and observed that the HUD and manual settings still displayed port 8000, while copied `agk start` commands omitted `--api-base`. This is the explicit reason the prior source freeze was lifted; it is parent live evidence, not a browser observation by this worker.

Current client requests use same-origin relative `/v1`; Vite's dev proxy uses `VITE_BACKEND_URL` or `AGK_BACKEND_URL`. No current source API resolver consumes `VITE_API_BASE`. The bridge page now preserves that explicit compatibility override when present, resolves absolute or relative values against the current origin, retains proxy path prefixes, removes one terminal `/v1` for the CLI/Anthropic root, and appends exactly `/v1` for OpenAI. The HUD, all environment snippets, copied `--api-base`, and copied tunnel `--url` derive from that root. A public-origin URL still does not verify local tunnel ingress or existing external configuration.

The failing-first follow-up produced ten failed and two passing focused cases (`bridge-base-red.txt`). After the minimal page fix, all twelve focused cases pass (`bridge-base-focused.txt`), and the six-file seam suite passes all forty-four cases (`bridge-palette-focused.txt`). Cases cover actual port 50816, absolute and relative API overrides, path prefixes, blank overrides, and shell metacharacters in copied bases. Backend source and its thirty-four-case verification are unchanged.

Final source SHA-256:

```text
2707235869471bfb990a47f5d8e6e10a03710b779efaacf136484b2df85da258  src/antigravity_k/engine/agent_bridges.py
ff6707a16af0e74556f037931029afc60b9cd01322bb10ee6477f2f2c1cd98e3  tests/test_agent_bridge_auth_plan.py
b25399815bac5f949f64c40a3c90a0c936ee2e79021c281bc418b627ac9221cb  dashboard/src/pages/AgentStartPage.tsx
76671be4f5962c74d544ffe6fee29a388b04449c3dc4fa65b22a7b97550431d0  dashboard/src/pages/AgentStartPage.test.tsx
```
