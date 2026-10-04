# SSAK-AI

**A local-first AI engineering workspace for Apple Silicon.**

[![CI](https://github.com/sumkbs-kbs/ssak-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/sumkbs-kbs/ssak-ai/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[한국어](README.ko.md) · [Operations](docs/09_OPERATION_GUIDE.md) · [Contributing](CONTRIBUTING.md)

SSAK-AI connects local language models, a browser dashboard, and a CLI for conversation, code exploration, tool execution, retrieval, and task management. Ollama is the default inference path; direct MLX and LM Studio's OpenAI-compatible server are also available. Optional remote providers require their own configuration and credentials.

The core separates **Brain** planning and reasoning from **Body** execution. It keeps decisions, observations, and execution authority distinct: a model's confidence or a successful evaluation does not grant permission to run a tool.

For release and support status, see the [status document](docs/20_CURRENT_STATUS.md). Dated improvements and their verification limits are recorded in the [core execution plan](docs/ssak-ai-core/EXECUTION_PLAN_2026-10-03.md), [full feature live-validation plan](docs/ssak-ai-core/FULL_FUNCTION_LIVE_PLAN_2026-10-04.md), and [decision-diagnostics results](docs/qa/2026-10-04-oh-my-jev-followup/RESULT.md). Test results apply to the source and scope recorded in each report.

## What you can use

- **Local inference:** a shared model registry, local model discovery, provider adapters, and explicit model selection.
- **Engineering agents:** planning, tool calls, verification and repair loops, resumable tasks, and optional collective-model workflows.
- **Workspace dashboard:** conversation history, Markdown responses, files, task status, approvals, model controls, and a keyboard command palette.
- **Search and retrieval:** web search with source grounding, document extraction, optional vector retrieval, and code indexing.
- **Memory and knowledge:** project memory, recall budgeting and duplicate handling, plus a Markdown vault tracked through Git and YAML metadata.
- **Execution safeguards:** PIN authentication, policy checks, approval previews, secret scanning, sandbox controls, and audit records.
- **Optional domain tools:** financial-number extraction that preserves currency, scale, and source evidence; voice interfaces with bounded upload and audio validation. Actual voice inference depends on available engines.
- **Decision diagnostics:** accuracy, calibration error, Brier score, negative log-likelihood, reliability bins, selective coverage, 95% Wilson accuracy intervals, and bounded tag-level summaries.

Optional runtimes, credentials, models, and feature flags determine which integrations are available. Feature implementation does not by itself establish model quality or a production support commitment.

## Quick start

### Requirements

- Python **3.12+** and [uv](https://docs.astral.sh/uv/).
- A running local inference provider and a model that fits your hardware. Apple Silicon is the primary development target; the direct MLX path requires an appropriate Apple Silicon environment.
- For dashboard development: Node.js **22.13+** and pnpm **11.3+**, matching [dashboard/package.json](dashboard/package.json).
- Docker is optional for the sandbox execution path. Desktop build details are in the [macOS packaging guide](docs/packaging/MACOS_DMG_GUIDE.md).

```sh
git clone https://github.com/sumkbs-kbs/ssak-ai.git
cd ssak-ai

# Install the locked development environment.
uv sync --locked --extra dev

# Inspect commands, registered models, and runtime availability.
uv run agk --help
uv run agk model list
uv run agk doctor
```

Start Ollama or your chosen local server and load a model before requesting inference. The bundled configuration currently uses the `qwen3.8` Ollama profile; this is a configuration identifier, not a guarantee that a model is installed or available for download. Check `agk model list`, your runtime's installed models, and [the model configuration](src/antigravity_k/config.yaml). Select an installed, available registry identifier with `--model`.

### Run the dashboard and API

Set `AGK_SEC_ACCESS_PIN` privately before first startup if you want PIN-protected access; there is no universal default PIN. Then run:

```sh
uv run agk serve --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The same server exposes the dashboard, `/health`, `/api/ready`, [Swagger UI](http://127.0.0.1:8000/docs), and [OpenAPI JSON](http://127.0.0.1:8000/openapi.json). Enter your configured PIN when prompted.

For a question through the CLI:

```sh
uv run agk ask "Explain the architecture of the current project."
uv run agk ask --help
uv run agk task --help
```

### Optional dependencies and dashboard development

Install only the extras needed for your workflow:

```sh
uv sync --locked --extra dev --extra rag   # Vector retrieval and document tools
uv sync --locked --extra dev --extra mlx   # Direct MLX inference
uv sync --locked --extra dev --extra transformers  # Transformers / LoRA adapters
```

For dashboard development, keep the API running in another terminal:

```sh
cd dashboard
pnpm install --frozen-lockfile
pnpm run dev
```

Use the URL printed by Vite. The development server is separate from the product API. Build dashboard assets with `pnpm --dir dashboard run build`; see the [packaging guide](docs/packaging/MACOS_DMG_GUIDE.md) for producing a desktop bundle.

## Configuration and security

Provider profiles and feature settings live in [config.yaml](src/antigravity_k/config.yaml). Environment-variable names are listed in [.env.example](.env.example); review the example's provider and port values before copying it, since they are not all product defaults. Keep `.env`, credentials, authentication files, and private workspace data out of commits.

| Setting | Purpose |
| --- | --- |
| `AGK_SERVER_HOST`, `AGK_SERVER_PORT` | API binding; product defaults are `127.0.0.1` and `8000` |
| `AGK_SEC_ACCESS_PIN` | Private bootstrap PIN; authenticated deployments persist a PIN hash |
| `AGK_ENV` | Environment profile, including stricter production startup checks |
| `AGK_CORS_ORIGINS` | Allowed browser origins |
| `AGK_LOG_LEVEL` | Logging verbosity |
| `AGK_DAILY_BUDGET_USD`, `AGK_HOURLY_ACTION_LIMIT` | Cost and action-budget controls |
| `AGK_APPROVAL_REVIEW_MODEL` | Optional local model assistance for approval review |
| `LM_STUDIO_API_KEY` | Needed only when the LM Studio server requires a token |

Production or non-loopback startup requires strong authentication: an access PIN of at least eight characters or an accepted persisted authentication state. Keep the initial setup bound to loopback. Approval review assists the user and policy; it does not expand execution authority or replace approval. See the [operations guide](docs/09_OPERATION_GUIDE.md) for deployment and recovery procedures.

Local-first does not mean every feature is offline. Web search and configured remote providers can make network requests; optional integrations require their own access settings.

## Evaluate decision probabilities

The evaluator consumes supplied probabilities and answer labels. It does **not** call a model, train or calibrate it, or certify future accuracy.

```sh
uv run agk decision-eval --help
uv run agk decision-eval docs/qa/2026-10-04-oh-my-jev-followup/manual-cases.json
```

The authenticated API equivalent is `POST /api/benchmarks/decisions/evaluate`. Prediction and error cases may carry up to 16 unique tags; the report returns at most 25 tag groups with omitted-group counts. Accuracy intervals include the scored sample count and number of correct decisions. Overlapping tag groups are separate views of the same cases, so their counts must not be added together.

See [usage and interpretation](docs/qa/2026-10-04-oh-my-jev-followup/USAGE.md), the [implementation contract](docs/qa/2026-10-04-oh-my-jev-followup/IMPLEMENTATION_CONTRACT.md), and [verification results](docs/qa/2026-10-04-oh-my-jev-followup/RESULT.md). Calibration remains `unverified` unless separately demonstrated with appropriate labeled data.

## Development and tests

```sh
make lint
make typecheck
make test-quick

pnpm --dir dashboard run typecheck
pnpm --dir dashboard test
pnpm --dir dashboard run build
```

`make check` also checks formatting. `make test` runs the backend suite; `make test-e2e` starts an isolated API smoke server. Some integration tests require local runtimes or services. Use test workspaces rather than private data, and consult each QA report for its prerequisites and exact scope.

## Project layout

```text
src/antigravity_k/
  engine/        Models, orchestration, memory, vault, evaluation, safeguards
  api/           FastAPI routes and authentication
  tools/         Search, extraction, code and other tool interfaces
  security/      Authentication and security utilities
  cli.py         Typer command entry point (agk)
dashboard/       React, TypeScript and Vite workspace UI
desktop/         Desktop shell
tests/           Backend tests and integration scenarios
scripts/         Build, evaluation, audit and verification tools
docs/            Design plans, operations, QA and evidence
```

## Documentation and contribution

- [Korean README](README.ko.md), preserved from the previous project introduction.
- [Core execution and handoff plan](docs/ssak-ai-core/EXECUTION_PLAN_2026-10-03.md).
- [External feature improvements](docs/ssak-ai-core/EXTERNAL_FEATURE_UPGRADE_2026-10-03.md).
- [Local-model amplification guide](docs/AMPLIFICATION_GUIDE.md).
- [Live-validation scope and remaining checks](docs/ssak-ai-core/FULL_FUNCTION_LIVE_PLAN_2026-10-04.md).
- [Desktop shell](desktop/README.md) and [macOS packaging](docs/packaging/MACOS_DMG_GUIDE.md).
- [Contribution guidelines](CONTRIBUTING.md) and [agent protocol](AGENTS.md).

Knowledge-vault edits follow the project's Files-first and Git-first rules: use Markdown with YAML frontmatter, preserve provenance, and record changes through the vault engine or its documented Git workflow.

## License

SSAK-AI is distributed under the [MIT License](LICENSE). Dependencies, external models, datasets, and optional integrations have their own licenses and usage conditions; the project's license does not replace them.
