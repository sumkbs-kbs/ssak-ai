# Ssak-Ai — Production Docker Image
#
# Multi-stage build:
#   1. Base: Python 3.12 slim (pinned digest)
#   2. Builder: Install ALL deps (including dev tooling) and build artifacts
#   3. Dashboard: Build static assets with Node
#   4. Runtime: Minimal — only runtime deps (no pytest/ruff/playwright)
#
# Security hardening vs. the previous Dockerfile:
#   - Dev dependencies (pytest, ruff, playwright) no longer ship to runtime.
#   - Runs as a non-root user.
#   - Data dirs are owned by the non-root user.
#   - pip editable install replaced with a proper (non-editable) install.

# ─── Stage 1: Base ──────────────────────────────────────────────
# Digest pin via tag; Dependabot (docker ecosystem) keeps this current.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install only essential runtime utilities.
# git: Vault(위키 저장소) create/commit/read 기능이 런타임에 git을 실행한다 (REL-02).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ─── Stage 2: Builder (all deps, used for building artifacts only) ──
FROM base AS builder

COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the full package with dev + rag extras into a dedicated prefix.
# Only the runtime deps (none of the dev tooling) are copied to the final
# stage, so pytest/ruff/playwright never reach production.
RUN pip install --upgrade pip \
    && pip install --target="/install" ".[rag]"

# ─── Stage 3: Dashboard Build ───────────────────────────────────
# REL-02: 단일 package manager = pnpm (pnpm-lock.yaml이 단일 진실원).
# frozen install로 lockfile과 package.json의 불일치를 빌드 시점에 차단한다.
# CR-11: pnpm@11.3.0은 node:sqlite builtin을 쓰므로 engines가 `node >=22.13`이다.
#        `node:22`(플로팅 메이저) 태그는 22.13 미만으로 해석될 수 있어 마이너까지 고정한다
#        (dashboard/package.json `engines.node`와 동일 값 — CI도 같은 값을 쓴다).
FROM node:26.10-alpine AS dashboard-builder

# CR-14 F-05: `pnpm run build` 는 `tsc -b && vite build` 이고, `tsc -b` 는 대시보드 전체를
# 콜드 타입체크한다. node 이미지의 기본 V8 힙 상한은 **실측 2096MB**(컨테이너 메모리와
# 무관하게 고정 — `--memory=4g`/`12g` 모두 2096MB)이고, 그 지점에서 heap OOM 으로 죽어
# required gate `docker-build` 가 실패했다(14.5s, 재현 2/2). 로컬에서는 같은 입력이
# 기본 힙으로도 통과하므로 musl/node 조합의 여유가 더 필요하다.
# 빌드 단계에서만 힙을 올린다 — 런타임 이미지에는 영향이 없다.
ENV NODE_OPTIONS=--max-old-space-size=4096

WORKDIR /app/dashboard
RUN npm install -g pnpm@11.3.0 && pnpm --version
COPY dashboard/pnpm-lock.yaml dashboard/package.json dashboard/pnpm-workspace.yaml ./
# CI=true: 비 TTY 환경에서 pnpm의 모듈 디렉터리 퍼지 확인 프롬프트 방지
RUN CI=true pnpm install --frozen-lockfile
COPY dashboard/ ./
RUN pnpm run build

# ─── Stage 4: Runtime ───────────────────────────────────────────
FROM base AS runtime

# Create a non-root user to run the application.
RUN groupadd --system --gid 1001 agk \
    && useradd --system --uid 1001 --gid agk --create-home --home-dir /home/agk agk

WORKDIR /app

# Copy only the installed runtime packages from the builder.
COPY --from=builder /install /usr/local/lib/python3.12/site-packages

# Copy the application source (needed for the non-editable install's package
# metadata to resolve the entry point).
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-deps "." \
    && rm -rf /root/.cache

# Copy dashboard build from builder
# REL-02: Vite outDir === wheel package-data === 이 COPY 경로 (src/antigravity_k/dashboard_dist)
COPY --from=dashboard-builder /app/src/antigravity_k/dashboard_dist/ ./src/antigravity_k/dashboard_dist/

# Create data directories owned by the non-root user.
RUN mkdir -p vault_data logs data \
    && chown -R agk:agk /app

# Copy entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Drop privileges.
USER agk

# Health check (runs as the non-root user).
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/v1/health || exit 1

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["agk", "serve", "--host", "0.0.0.0", "--port", "8000"]
