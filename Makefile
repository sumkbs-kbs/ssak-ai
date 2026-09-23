# Ssak-Ai Makefile
# =======================
# Commercial-grade task runner for development, testing, and deployment

.PHONY: help install dev test test-e2e smoke-cli verify-clean-machine evidence-gate evidence-gate-full ga-gate ga-gate-list lint format clean build dmg dmg-smoke check-desktop docker-build \
        docker-run coverage check ci-setup pre-commit install-script \
        security audit audit-egress sbom doctor search-quality search-quality-extended search-live search-live-extended search-load claim-quality quality-contract local-rag-quality local-benchmark local-benchmark-frontier frontier-evidence \
        build-provenance dashboard-build-provenance dashboard-provenance-verify publish-provenance

SHELL := /bin/bash
# 프로젝트 venv(uv) 우선 — 시스템 python3는 구버전(union 타입 문법 미지원)일 수 있음
PYTHON := $(shell command -v uv >/dev/null 2>&1 && echo "uv run python" || echo "python3")
PACKAGE := antigravity-k
VENV := .venv
PROVENANCE_DIR ?= .artifacts
DASHBOARD_PROVENANCE ?= $(PROVENANCE_DIR)/dashboard-dist.json
PYTHON_PROVENANCE ?= $(PROVENANCE_DIR)/python-dist.json
PROVENANCE_MANIFEST ?= $(DASHBOARD_PROVENANCE)
PROVENANCE_SOURCE ?= ui_bundle

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Environment ─────────────────────────────────────────────────

install: ## Install the package in development mode
	$(PYTHON) -m pip install -e ".[dev,rag,mlx]"

venv: ## Create virtual environment
	$(PYTHON) -m venv $(VENV)
	@echo "Virtual environment created. Activate with: source $(VENV)/bin/activate"

install-script: ## Run the one-click installation script (dry-run first)
	@echo "Running Ssak-Ai installer in dry-run mode..."
	@bash scripts/install.sh --dry-run
	@echo ""
	@echo "To run the actual installation:"
	@echo "  bash scripts/install.sh"
	@echo ""
	@echo "For remote installation:"
	@echo "  curl -fsSL https://agk.sh | bash"

# ─── Development ──────────────────────────────────────────────────

dev: ## Start the development server with hot reload
	uv run agk serve --reload

doctor: ## Run environment diagnostic (checks deps, config, ports, vault)
	@$(PYTHON) -m antigravity_k.cli doctor

dev-dashboard: ## Start the dashboard dev server (pnpm pinned — packageManager)
	cd dashboard && pnpm install --frozen-lockfile && pnpm run dev

# ─── Linting & Formatting ─────────────────────────────────────────

lint: ## Run ruff linter
	$(PYTHON) -m ruff check src/ tests/ scripts/

lint-fix: ## Run ruff linter with auto-fix
	$(PYTHON) -m ruff check --fix src/ tests/ scripts/

format: ## Format code with ruff
	$(PYTHON) -m ruff format src/ tests/ scripts/

format-check: ## Check formatting without changing files
	$(PYTHON) -m ruff format --check src/ tests/ scripts/

typecheck: ## Run mypy type checking (config: pyproject [tool.mypy])
	uv run --extra dev python -m mypy src/

check: lint format-check typecheck ## Run all code quality checks

# ─── Testing ───────────────────────────────────────────────────────

test: ## Run all tests
	$(PYTHON) -m pytest tests/ -v --tb=short

test-e2e: ## Run API E2E smoke tests with automatic local server startup
	$(PYTHON) -m pytest tests/test_e2e_smoke.py -q

smoke-cli: ## Verify the documented CLI entrypoint and local Qwen profile
	uv run agk --help
	uv run agk model list
	uv run agk doctor

evidence-gate: ## 증거 게이트(fast): 리뷰·카나리아·digest·상태 주장·enum·purge·표면을 한 번에 돌린다
	$(PYTHON) scripts/evidence_gate.py --tier fast

evidence-gate-full: ## 증거 게이트(full): 로컬 회차가 필요한 전량 회귀 원장까지 포함한다
	$(PYTHON) scripts/evidence_gate.py --tier full

ga-gate: ## Run the complete commercial GA gate manifest
	$(PYTHON) scripts/ga_gate.py --manifest scripts/commercial_ga_gates.json --output .artifacts/commercial-ga.json

ga-gate-list: ## Validate and list commercial GA gates without executing them
	$(PYTHON) scripts/ga_gate.py --manifest scripts/commercial_ga_gates.json --list

verify-clean-machine: ## 클린머신 재현 검증: HEAD 신규 익스포트 → uv sync(잠금강제) → CLI smoke → API E2E
	bash scripts/verify_clean_machine.sh $(ARGS)

vendor-ssak-bundle: ## W 릴리스에서 번들 artifact 를 패키지 데이터로 materialize (핀 검증)
	$(PYTHON) scripts/vendor_ssak_bundle.py --from $(SSAK_BUNDLE_SOURCE)

verify-ssak-bundle: ## 번들 검증: 설치본 handshake · 오프라인 시작 · 갱신/rollback (task 15 QA)
	uv run --frozen python scripts/verify_ssak_bundle.py --offline-start --rollback-test $(ARGS)

test-quick: ## Run fast tests (exclude slow/benchmark)
	$(PYTHON) -m pytest tests/ -v --tb=short -m 'not slow and not benchmark'

test-benchmark: ## Run benchmark tests
	$(PYTHON) -m pytest tests/ -v --tb=short -m benchmark

search-quality: ## Run deterministic search golden-set and citation checks
	$(VENV)/bin/python -m pytest tests/test_web_search_quality.py -q --tb=short

search-quality-extended: ## Validate the expanded human-labeled search fixture
	$(VENV)/bin/python -m pytest tests/test_web_search_quality.py -q --tb=short

search-live: ## Run live provider search benchmark against the golden set
	PYTHONPATH=src $(VENV)/bin/python -m antigravity_k.tools.search_benchmark

search-live-extended: ## Run live provider search benchmark against the expanded fixture
	PYTHONPATH=src $(VENV)/bin/python -m antigravity_k.tools.search_benchmark --fixture tests/fixtures/search_quality_cases_extended.json --output data/benchmarks/live-search-extended.json

search-load: ## Run repeated/concurrent live search latency and availability benchmark
	PYTHONPATH=src $(VENV)/bin/python scripts/run_search_load_benchmark.py

local-rag-quality: ## Run the local-RAG retrieval golden-set benchmark
	PYTHONPATH=src $(PYTHON) scripts/benchmark_local_rag.py

claim-quality: ## Run deterministic claim grounding and conflict benchmark
	PYTHONPATH=src $(VENV)/bin/python scripts/run_claim_grounding_benchmark.py

audit-egress: ## Inventory Python HTTP and URL egress call sites
	$(VENV)/bin/python scripts/audit_egress.py --root src/antigravity_k --output data/audits/egress-inventory.json

quality-contract: ## Run agent/search quality contract tests
	$(VENV)/bin/python -m pytest tests/test_web_search_quality.py tests/test_claim_grounding_benchmark.py tests/test_task_benchmark.py tests/test_long_horizon_benchmark.py -q --tb=short

local-benchmark: ## Run the local-first model benchmark (defaults to qwen3.8:latest)
	$(VENV)/bin/python scripts/run_local_model_benchmark.py

local-benchmark-frontier: ## Run the representative local frontier suite (defaults to qwen3.8:latest)
	$(VENV)/bin/python scripts/run_local_model_benchmark.py --suite frontier --output data/benchmarks/local-model-frontier.json

frontier-evidence: ## Run repeated paired local-vs-frontier evidence (pass options with ARGS="...")
	uv run python scripts/run_frontier_comparison.py $(ARGS)

coverage: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ -v --tb=short \
		--cov=src/antigravity_k \
		--cov-report=term-missing \
		--cov-report=html:coverage_html
	@echo "Coverage report generated: coverage_html/index.html"

# ─── Pre-commit ───────────────────────────────────────────────────

pre-commit: ## Install pre-commit hooks
	$(PYTHON) -m pip install pre-commit
	pre-commit install
	pre-commit run --all-files

pre-commit-run: ## Run pre-commit on all files
	pre-commit run --all-files

# ─── CI (local simulation) ────────────────────────────────────────

ci-setup: ## Simulate CI setup locally
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev,rag]"

ci-check: lint format-check typecheck test-quick ## Simulate CI checks locally

# ─── Build & Package ──────────────────────────────────────────────

build: ## Build wheel and sdist
	$(PYTHON) -m pip install build
	$(PYTHON) -m build

dmg: ## Build macOS .app bundle and distributable .dmg installer
	@bash scripts/build_mac_dmg.sh

dmg-smoke: ## Smoke Host from built .app on :18080 (does not use :8000)
	@bash scripts/dmg_smoke.sh

check-desktop: ## Fast desktop/packaging sanity gate (no DMG build, no Host, no soak kill, offline)
	@echo "── check-desktop: key packaging files ──"
	@test -f desktop/main.js
	@test -f scripts/dmg_smoke.sh
	@test -f scripts/build_mac_dmg.sh
	@echo "── check-desktop: update-channel fixture test (offline) ──"
	@node desktop/test_updateChannels.js
	@echo "── check-desktop: narrow pytest (diagnostics + network access + phase6 settings) ──"
	@$(PYTHON) -m pytest \
		tests/test_diagnostics_export.py \
		tests/test_network_access_api.py \
		tests/test_phase6_settings_env_smoke.py \
		-q --tb=short
	@echo "── check-desktop: PASS (skipped: full-repo ruff/mypy, DMG rebuild, Host start, update feed network) ──"

build-provenance: build ## Build Python distributions and verify their provenance manifest
	@mkdir -p "$(dir $(PYTHON_PROVENANCE))"
	$(PYTHON) src/antigravity_k/engine/artifact_provenance.py create dist --root . --output "$(PYTHON_PROVENANCE)"
	$(PYTHON) src/antigravity_k/engine/artifact_provenance.py verify "$(PYTHON_PROVENANCE)" --root .

dashboard-build-provenance: ## Build the dashboard and fail if its provenance manifest is invalid
	pnpm --dir dashboard build
	@mkdir -p "$(dir $(DASHBOARD_PROVENANCE))"
	$(PYTHON) src/antigravity_k/engine/artifact_provenance.py create dashboard/dist --root . --output "$(DASHBOARD_PROVENANCE)"
	$(PYTHON) src/antigravity_k/engine/artifact_provenance.py verify "$(DASHBOARD_PROVENANCE)" --root .

dashboard-provenance-verify: ## Verify the existing dashboard provenance manifest
	$(PYTHON) src/antigravity_k/engine/artifact_provenance.py verify "$(DASHBOARD_PROVENANCE)" --root .

publish-provenance: ## Publish a manifest to a configured task event store
	scripts/publish_artifact_provenance.sh "$(PROVENANCE_MANIFEST)" "$(PROVENANCE_SOURCE)"

clean: ## Clean build artifacts
	rm -rf dist/ build/ *.egg-info
	rm -rf .coverage coverage_html/
	rm -rf .mypy_cache .ruff_cache
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

# ─── Docker ────────────────────────────────────────────────────────

docker-build: ## Build Docker image
	docker build -t antigravity-k:latest .

docker-run: ## Run Docker container
	docker run -d --name antigravity-k \
		-p 8000:8000 \
		-v $(PWD)/vault_data:/app/vault_data \
		antigravity-k:latest

docker-up: ## Start all services with Docker Compose
	docker compose up -d

docker-down: ## Stop all services
	docker compose down

docker-logs: ## Follow logs
	docker compose logs -f

# ─── Security ───────────────────────────────────────────────────
security: audit sbom ## Run all security checks (dependency audit + SAST + SBOM)

audit: ## Audit dependencies for known CVEs (pip-audit) and run SAST (bandit)
	@echo "── pip-audit (dependency vulnerabilities) ──"
	pip-audit --strict --desc
	@echo ""
	@echo "── bandit (SAST, MEDIUM+ severity) ──"
	bandit -r src/antigravity_k -ll -x src/antigravity_k/engine/secret_scanner.py

sbom: ## Generate a CycloneDX SBOM from the dependency manifest
	@command -v cyclonedx-py >/dev/null 2>&1 || pip install cyclonedx-bom
	cyclonedx-py environment -o sbom.cdx.json --schema-version 1.5
	@echo "SBOM written to sbom.cdx.json"
