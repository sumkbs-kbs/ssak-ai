---
title: Bridge and palette action contracts
date: 2026-10-04
tags: [qa, dashboard, authentication, command-palette, agent-bridge]
---

This worker verified source and synthetic request/DOM contracts. The parent task owns the production build and live browser verification. No external agent, model generation, self-test harness, TDD task, tunnel, or vault write was launched by this worker.

Parent-supplied live failures: port 8000 /start showed Cloudflare Tunnel Ready and a demo API key; an actual command-palette note query showed Search unavailable after debounce. These are parent observations, not independent browser evidence from this worker.

The parent later reopened the source freeze after directly observing the latest isolated UI at http://127.0.0.1:50816/start still hardcoded port 8000 and omitted --api-base in copied bridge commands. The minimal follow-up now derives the HUD, protocol-specific manual settings, all bridge --api-base arguments, and guarded tunnel --url from the current origin or explicit VITE_API_BASE override while preserving its path prefix. This current-address contract passed failing-first focused verification; parent owns the latest production rebuild and browser confirmation.

Implemented contracts:
- Note search and explicit vault sync use existing apiRequestPath, which attaches signed bearer, project/revision and tab session headers. Existing 401 authentication recovery remains enabled.
- A selected search result performs a parsed authenticated GET /api/vault/read, updates the existing wiki state only after success, then navigates to /wiki. A denied read preserves the selected note and does not navigate. The consumer captures the project epoch, credential and newest selection before reading; stale successes and failures cannot apply note state, navigation or login recovery. Current-scope 401 still emits normal authentication recovery and throws its typed error.
- Search Notes opens /wiki. Create New Note opens the actual existing form at /wiki?new=1 without submitting it. Wiki mount uses existing read-only loadTree and no longer restores configuration through initVault's automatic POST.
- Self-Test is disabled with an unavailable explanation because no dashboard execution/result surface exists. TDD disables the conflicting Adaptive mode, enables existing chat TDD mode and navigates to /chat without issuing a request or replacing input.
- Bridge status is explicitly unverified with neutral semantic color and a status landmark. Credential assignments reference guarded SSAK_ACCESS_TOKEN, with Anthropic using ANTHROPIC_AUTH_TOKEN for bearer transport, Anthropic base URLs excluding /v1 and OpenAI bases including it. Inherited ANTHROPIC_API_KEY is explicitly unset. No real credential is read or embedded.
- Copy reports success only after the clipboard resolves, handles denied clipboard access, and releases its timeout on unmount. Selected model shell metacharacters remain a single quoted argument in both the displayed and copied bridge command. Tunnel copy uses an explicitly named existing tunnel, a local loopback URL, and changes no readiness state.

Backend/runtime constraints:
- cli.py start_agent_bridge prints a connection plan. It does not launch an agent or authenticate one.
- The parent's follow-up expanded this worker's scope to engine/agent_bridges.py. Its CLI plan now uses the same guarded signed-token variable, resolved Codex provider base, quoted model/base values and valid JSON/TOML data. See bridge-cli-auth-contract.md for the isolated failing-first regression and current focused verification.
- Codex needs the CLI plan's provider configuration in addition to environment variables. The UI does not claim that environment variables alone complete setup.
- There is no verified read-only Cloudflare status API, command or registry in the inspected code. The copied command requires an installed cloudflared and an already configured tunnel named in SSAK_TUNNEL_NAME. No tunnel existence or external reachability was verified.
- Vault keyword search's backend 500 without optional RAG is being addressed by the parent's vault_keyword_search_fix worker. These frontend tests prove auth and action contracts, not that backend availability.
- Existing wikiStore loadTree is reused unchanged. Existing wiki mutation controls remain explicit user actions; opening wiki now does not invoke config restoration. Project headers on these requests are client identity contracts, not proof that every backend vault dependency isolates its storage by project.
- Existing real Self-Test endpoints execute harness work. This worker left them uncalled. TDD execution remains the user's explicit chat submission.

Verification:
- Direct local Vitest: 6 files / 44 tests passed, including command-palette modal/IME/stale-search, selected-note ownership, safely quoted model-copy and current-origin/configured API-base coverage.
- Direct local TypeScript project check: exit 0 after the concurrent ModelHubPage test fix. A prior check reported Element/HTMLElement errors in that worker's test; those were reported to the parent and are now resolved.
- Direct local targeted ESLint on all 8 changed TypeScript files: exit 0.
- Several automatic LSP hooks timed out without diagnostics; the direct TypeScript check reported no diagnostics in this worker's files.
- Independent read-only spotreview approved the final seam after TDD/Adaptive conflict, stale selection/scope and stale 401 fixes.
- pnpm exec initially attempted its automatic dependency-status install and aborted before removal due to non-TTY. Subsequent checks used installed Node binaries directly. No dependency installation was completed.
- Live UI/clipboard/tunnel connections were not independently verified here; parent owns the build and safe browser retest.

Source SHA-256:
```text
b25399815bac5f949f64c40a3c90a0c936ee2e79021c281bc418b627ac9221cb  dashboard/src/pages/AgentStartPage.tsx
76671be4f5962c74d544ffe6fee29a388b04449c3dc4fa65b22a7b97550431d0  dashboard/src/pages/AgentStartPage.test.tsx
cc962f102c7732cd117d34a820721fb1e4d40accc9a9963e6de24e57dde940cb  dashboard/src/pages/WikiPage.tsx
b37bffcec16443c19c964f826f16034aa83cac845a16b7cf7d73c8357e977601  dashboard/src/pages/WikiPage.commandActions.test.tsx
b2d2c947c615c568d9e4abc3d9e53ccb040e87d302cae19ea8454f277ba20bfd  dashboard/src/features/command-palette/commandRegistry.ts
cda38becbc81566102f2e1d92ba2cc71445ea6923dc3381d7ee47934b3cc751d  dashboard/src/features/command-palette/commandRegistry.test.ts
bf90d75aa0318ed00d69dfb5c66867e8d4a49ad5cffbdf5234d4790c8c114679  dashboard/src/features/command-palette/commandRegistry.auth.test.ts
e75d3cbe9f99dab893b02406f257dd6309ee4011d7ffe38d6a275cf1808eb496  dashboard/src/features/command-palette/commandRegistry.selectionRace.test.ts
```
