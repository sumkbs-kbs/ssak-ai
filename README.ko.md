<div align="center">

# Ssak-Ai 🚀

**Qwen3.8 27B 로컬 우선 자율형 엔지니어링 에이전트 — Apple Silicon 최적화**

[![CI](https://github.com/ssak-comp/Ssak-Ai/actions/workflows/ci.yml/badge.svg)](https://github.com/ssak-comp/Ssak-Ai/actions/workflows/ci.yml)
[![Benchmark Dashboard](https://img.shields.io/badge/📊_Benchmark_Dashboard-GitHub_Pages-9C27B0?style=for-the-badge)](https://ssak-comp.github.io/Ssak-Ai/benchmark/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Ruff](https://img.shields.io/badge/code_style-ruff-000000)](https://github.com/astral-sh/ruff)

</div>

---

> Apple Silicon에서 Ollama `qwen3.8`을 기본으로 사용하는 로컬 우선 자율형 엔지니어링 에이전트 **Ssak-Ai**입니다.
> Ollama, 직접 MLX, LM Studio OpenAI 호환 서버를 하나의 모델 레지스트리와 CLI, 모던 데스크톱 대시보드로 연결하고, 계획·도구 호출·RAG·메모리·평가 루프로 로컬 모델의 작업 품질을 극대화합니다.

> **지금 무엇이 참인가**(게이트 판정·8시간 soak 경과·열려 있는 기술 축·사람 축·포트 역할·지원 범위)는
> [현재 상태 단일 요약](docs/20_CURRENT_STATUS.md) 하나가 소유합니다. 이 README 는 설치·실행·기능을
> 소유하고, 상태 배너를 중복해서 들고 있지 않습니다.

## 기능

| 기능 | 설명 |
|:---|---:|
| 🧠 **로컬 추론 엔진** | Ollama Qwen3.8 기본, 직접 MLX와 LM Studio 선택 지원 |
| 🌐 **집단지성 (MoE Swarm)** | 다중 모델 교차 검증 및 토론 라우팅 |
| 🤖 **자율 에이전트** | ReAct 패턴 + 도구 호출 + 자가 진화 (Self-Evolution) |
| ⚡ **적응형 에이전트 (Adaptive)** | 4방향 태스크 분류, Graphify 코드 인텔리전스, Ssak-Search 웹 그라운딩, 다양성 프로브 TDD 복구 |
| 🔗 **RAG 파이프라인** | ChromaDB + 임베딩 + AST 기반 코드 인덱싱 |
| 👁 **멀티모달 비전** | mlx-vlm 기반 이미지/문서 분석 |
| 🛡️ **보안** | 접근 PIN 인증, 시크릿 스캐너, 선언적 보안 정책, Fail-Closed |
| 📊 **벤치마크 대시보드** | GitHub Pages 자동 배포 + 성능 회귀 테스트 |
| 🌍 **다국어 지원** | 한국어/English/日本語 인터페이스 |
| 📝 **구조화된 로깅** | JSON 기반 로깅 + 일별 로테이션 + 감사 로그 |
| 💰 **비용 제어** | 일일 예산, 시간당 Rate Limit, 모델별 과금 추정 |
| 🏆 **상용화 준비도 (GA-100)** | 33/33 전 과제 완료(**구현 이력**, GA 승인·출시 판정 아님), DR 4종 리허설, 8개 도메인 실전 코딩 벤치마크 검증 |
| 🔁 **최종 독립 검토(RP 시리즈, 과거)** | 2026-09-10 REQUEST CHANGES → 개선 작업 진행 중(RP-01~11, RP-13 독립 검증 완료 DONE, RP-12 8시간 soak-006 순항 중, 20/20 상용화 게이트 PASS). 이 표는 **RP 이력**이며 현재 상태가 아니다. 상세: [검토 보고서](docs/qa/2026-09-10/FINAL_REVIEW.md) · [개선 계획](docs/14_FINAL_REVIEW_REMEDIATION_PLAN.md) · [증거 인덱스](docs/ga/final-review-remediation.md) · [실행 체크리스트](docs/15_FINAL_REVIEW_REMEDIATION_CHECKLIST.md) |
| 🧪 **현재 상태(CR 시리즈)** | **CR-01 ~ CR-14 REVIEW · 최종 판정 NO-GO · required gate 전 항목 PASS를 커밋된 후보에서 달성**(되돌리기 0회 · 단일 코드 지문). **이 표는 휘발성 값을 담지 않는다** — 후보 SHA·게이트 인벤토리·코드 지문의 값은 [판정서 §5 판정 카드](docs/ga/CR14_FINAL_CANDIDATE_VERDICT.md)가 유일한 소유자이고, `C14-F22-1/2` 계약이 이 표에 값을 박는 것을 막는다(값을 박으면 다음 기록 커밋이 `README.md` 를 고쳐 **지문을 옮기고 그 순간 gate 증거가 낡는다** — attempt-013 에서 실제로 발생, F-22). **주의: attempt-013 이전의 20/20 은 게이트 도구가 실행자의 셸에서 와서 “lock 이 검증됐다”를 뜻하지 않았다** — 지금은 게이트가 자기 환경을 스스로 재고(계약 3종), wall-clock 성능 검사는 전용 required 게이트(`python-benchmark`)에서 돈다. **이 후보 범위에서는** 기술 축이 닫혔고(F-07 포함) 남은 차단 사유는 **사람의 영역**이다 — 독립 검토자 **미배정**(출시 책임자가 code/security/QA 를 **겸직**), 외부 승인(EX-01~06) **미확보**, C14-03/04/05 미실행, **GA 승인 없음**. **그 문장을 현재 작업 트리나 신뢰성 계획(NX) 범위로 넓혀 읽지 않는다** — NX-01~06 은 REVIEW, NX-06 런타임은 BLOCKED, NX-07~NX-15 는 TODO 이고 이 후보 이후의 변경은 **커밋되지 않았다**([현재 상태](docs/20_CURRENT_STATUS.md) §4). 참고: `git status` 에 ` M vault_data` 한 줄이 남지만 그것은 별도 저장소의 런타임 이벤트 로그이며 코드·산출물은 clean 이다(F-13). RP 상태와 CR 상태를 합산해 DONE으로 읽지 않는다. 재현→수정→회귀 증거는 `.omo/evidence/commercial-reliability/CR-0X/**`(gitignore 대상 — 작업 트리에만 있다)에 있다. 상세: [계획서 16](docs/16_COMMERCIAL_RELIABILITY_DEVELOPMENT_PLAN.md) · [체크리스트 17](docs/17_COMMERCIAL_RELIABILITY_CHECKLIST.md) · [최종 후보 판정서](docs/ga/CR14_FINAL_CANDIDATE_VERDICT.md) · [최종 준비도 보고서](docs/10_FINAL_READINESS_REPORT.md) |

## 기능↔구현 매트릭스

| 기능 | 핵심 구현 모듈·함수 | 진입점/CLI |
|:---|---|:---|
| 🧠 **로컬 추론 엔진** | `model_manager.py:generate()` / `model_registry.py:ModelRegistry` / `provider_adapters/` | `agk run`, `agk model list` |
| 🌐 **집단지성 (MoE Swarm)** | `model_manager.py:generate_collective()` / `engine/model_router.py` | `agk run --mode collective` |
| 🤖 **자율 에이전트** | `engine/orchestrator/agent.py` (ReAct graph) / `engine/tool_loop.py` / `engine/tool_executor.py` | `agk run`, `agk task resume` |
| ⚡ **적응형 에이전트 (Adaptive)** | `engine/unified_agent.py:UnifiedAgent` / `tools/ssak_search_client.py` / `api/routes/agent_ask.py` | `agk ask`, 대시보드 `⚡ Adaptive` 모드 |
| 🔗 **RAG 파이프라인** | `engine/rag_indexer.py:RAGIndexer` / `engine/code_intel/` / `engine/vault.py:VaultEngine` | `agk rag index`, `agk vault` |
| 👁 **멀티모달 비전** | `provider_adapters/mlx_vlm.py` / `tools/vision_tool.py` | `agk run --model mlx-...` |
| 🛡️ **보안** | `engine/security_policy.py` / `engine/secret_scanner.py` / `engine/approval_manager.py` / `engine/error_classifier.py` | `agk serve` (PIN), `agk security scan` |
| 📊 **벤치마크 대시보드** | `dashboard/` (React+TypeScript+Vite) / `scripts/benchmark_viz.py` / `.github/workflows/deploy-benchmark-pages.yml` | `make dev-dashboard`, GitHub Pages |
| 🌍 **다국어 지원** | `i18n.py` / `locales/{ko,en,ja}.json` | 환경변수 `AGK_LANG` |
| 📝 **구조화된 로깅** | `logging_setup.py` (JSON, rotation, audit) | `AGK_LOG_LEVEL`, `data/logs/` |
| 💰 **비용 제어** | `engine/cost_guard.py:CostGuard` / `engine/model_manager.py:UsageTracker` | `AGK_DAILY_BUDGET_USD`, `AGK_HOURLY_ACTION_LIMIT` |
| 🔄 **프로젝트 전환** | `engine/project_registry.py` (flock 원자적 저장) / `api/routes/` | `POST /api/projects/switch`, `GET /api/workspace/context` |
| 🗜 **대화 컴팩트** | `engine/conversation_store.py` (revision CAS + 프로세스간 flock) | `POST /v1/conversations/compact`, `POST /v1/conversations/append` |
| 🏆 **상용화 GA-100 & 실전 평가** | `docs/11_COMMERCIAL_GA_100_PLAN.md` / `tests/evals/real_coding/` / `scripts/dr_rehearsal.py` | `docs/12_COMMERCIAL_GA_100_CHECKLIST.md`, `make check` |

## 빠른 시작

### 필수 조건

- **macOS** (Apple Silicon M 시리즈)
- **Python 3.12+**
- **uv** ([설치 안내](https://docs.astral.sh/uv/))
- **Ollama** (기본 로컬 런타임)
- **(선택) Docker** — 샌드박스 코드 실행

### 설치

> **패키징 · 사용자 vs 개발자 (짧게)**  
> - **사용자용:** macOS DMG 설치·실행 → [`docs/packaging/MACOS_DMG_GUIDE.md`](docs/packaging/MACOS_DMG_GUIDE.md) §2.  
> - **개발자용:** `make dmg` / 클로저·Electron 셸·업데이트 채널 → 같은 가이드 §3 + [`docs/packaging/DESKTOP_SHELL_REFERENCE_PLAN.md`](docs/packaging/DESKTOP_SHELL_REFERENCE_PLAN.md) · [`desktop/README.md`](desktop/README.md).  
> - Windows 설치기는 설계 stub만 (`docs/packaging/notes/windows_closure_stub.md`) — 구현 deferred.

```bash
# 1. 저장소 클론
git clone https://github.com/ssak-comp/Ssak-Ai.git
cd Ssak-Ai

# 2. 의존성 설치 (개발·RAG·직접 MLX 런타임 포함)
uv sync --extra dev --extra rag --extra mlx

# 3. 기본 로컬 모델 설치
ollama pull qwen3.8:latest

# 4. CLI와 기본 모델 프로필 확인
uv run agk doctor
uv run agk model list

# 5. (선택) 대시보드 빌드
cd dashboard && pnpm install --frozen-lockfile && pnpm run build && cd ..
```

### 실행

```bash
# API 서버 실행 (기본 포트 8000 — AGK_SERVER_PORT로 변경 가능)
uv run agk serve --host 127.0.0.1 --port 8000

# 기본 Qwen3.8 로컬 에이전트 실행
uv run agk run "현재 프로젝트의 테스트 실패 원인을 요약해줘" --model qwen3.8

# 적응형(Adaptive) 에이전트 질의 및 코드 TDD 자가 복구 루프 실행
uv run agk ask "FastAPI BackgroundTasks 동작 원리"
uv run agk ask "Counter 클래스 작성" --test tests/test_counter.py

# 반환된 direct task ID의 상태/출력 조회 및 실패·일시정지 작업 재개
uv run agk task status direct_ab12cd34ef56
uv run agk task output direct_ab12cd34ef56
uv run agk task resume direct_ab12cd34ef56 --model qwen3.8

# 프로젝트 고유 용어를 메모리 canonical key에 연결
uv run agk memory alias-set database primary_store
uv run agk memory aliases

# 설치 및 CLI 명령 smoke 검사
make smoke-cli

# 대시보드 개발 서버 (별도 터미널)
make dev-dashboard
# 또는: cd dashboard && pnpm install --frozen-lockfile && pnpm run dev
```

프로젝트 메모리 별칭은 현재 workspace의 `.antigravity/memory/project_aliases.json`에 저장된다. 실행 중인 agent process에는 다음 시작부터 적용되며, `uv run agk memory alias-remove primary_store`로 제거할 수 있다.

## 프로젝트 구조

```
Ssak-Ai/
├── src/antigravity_k/          # 메인 패키지
│   ├── engine/                 # 코어 엔진
│   │   ├── orchestrator/agent.py # 오케스트레이터 (상태 그래프)
│   │   ├── model_manager.py    # 모델 관리
│   │   ├── model_registry.py   # 모델 레지스트리
│   │   ├── model_router.py     # 모델 라우터 (9Router)
│   │   ├── rag_indexer.py      # AST 기반 RAG 인덱서
│   │   ├── vault.py            # Git-First Vault 엔진
│   │   ├── security_policy.py  # 선언적 보안 정책
│   │   ├── quality_gate.py     # 품질 검증 게이트
│   │   ├── cost_guard.py       # 비용 제어 가드
│   │   ├── secret_scanner.py   # 시크릿 스캐너
│   │   ├── error_classifier.py # API 에러 분류
│   │   ├── tool_guardrails.py  # 도구 호출 가드레일
│   │   ├── tool_loop.py        # 도구 실행 루프
│   │   ├── tool_executor.py    # 도구 실행기
│   │   ├── memory/             # 메모리 프로바이더
│   │   ├── code_intel/         # 코드 인텔리전스
│   │   └── provider_adapters/  # LLM 프로바이더 어댑터
│   ├── agents/                 # 에이전트 구현
│   │   ├── base_agent.py       # 베이스 에이전트
│   │   ├── scout_agent.py      # 모델 스카우트
│   │   └── trainer_agent.py    # 트레이너
│   ├── api/                    # FastAPI 서버
│   │   ├── server.py           # 메인 서버 (CORS, 미들웨어, 헬스체크)
│   │   ├── models.py           # Pydantic 모델
│   │   ├── routes/             # API 라우트
│   │   └── dependencies.py     # 의존성 주입
│   ├── tools/                  # 도구 구현 (50+)
│   ├── security/               # 보안 모듈
│   ├── knowledge/              # 지식 관리 (Wiki, Memory)
│   ├── cli.py                  # Typer CLI
│   ├── config.py               # Pydantic 설정 관리
│   └── i18n.py                 # 다국어 지원
├── dashboard/                  # 웹 대시보드 (React + TypeScript + Vite)
├── tests/                      # 테스트 스위트 (70+ 파일)
├── scripts/                    # 유틸리티 스크립트
├── docs/                       # 문서
├── .github/workflows/          # GitHub Actions CI/CD
├── Makefile                    # 태스크 러너
├── Dockerfile                  # 컨테이너 배포
└── docker-entrypoint.sh        # Docker 엔트리포인트
```

## 기술 스택

| 계층 | 기술 | 역할 |
|:---|---:|:---|
| 추론 엔진 | Ollama / MLX / LM Studio | Qwen3.8 27B 기본 (config.yaml `qwen3.8`), 직접 MLX 및 OpenAI 호환 로컬 서버 |
| 비전 | mlx-vlm | 멀티모달 이미지/문서 분석 |
| 벡터 DB | ChromaDB | 로컬 임베딩 저장/검색 |
| 코드 인덱싱 | AST + RAGIndexer | 소스 코드 그래프 인덱싱 |
| API 서버 | FastAPI + uvicorn | OpenAI 호환 REST API |
| 설정 관리 | Pydantic Settings + YAML | 환경변수/파일 설정 |
| 대시보드 | React + TypeScript + Vite | 시스템 모니터링 UI |
| 로깅 | 구조화된 JSON + 로테이션 | 추적성 (Traceability) |
| i18n | 자체 번역 시스템 | 한국어/English/日本語 |
| CI/CD | GitHub Actions | Lint/Test/Deploy 자동화 |

## 개발 명령어

```bash
# 코드 품질
make lint          # Ruff 린트
make format        # Ruff 포맷
make typecheck     # Mypy 타입 체크
make check         # 전체 코드 품질 검사

# 테스트
make test          # 전체 테스트
make test-quick    # 빠른 테스트 (slow/benchmark 제외)
make test-e2e      # 임시 포트 API E2E smoke
make smoke-cli     # README의 CLI entrypoint와 Qwen 프로필 smoke
make coverage      # 커버리지 리포트

# 빌드
make build         # pip 패키지 빌드
make docker-build  # Docker 이미지 빌드
docker run -d --name antigravity-k -p 8000:8000 -v $(PWD)/vault_data:/app/vault_data antigravity-k:latest  # 컨테이너 실행 (compose 파일은 vllm 전용만 존재)

# 정리
make clean         # 빌드 아티팩트 정리
make pre-commit    # Pre-commit 훅 설치 및 실행
```

## API 문서

서버 실행 후:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

같은 포트가 대시보드(브라우저에서 그 주소를 열면 나오는 화면)와 `/health`·`/api/ready` 를 함께 낸다.
포트가 헷갈리기 쉬운 세 자리 — 제품 서버(기본 8000) / 대시보드 개발 서버(Vite 5173) / 패키징 셸이 쓰는
`SSAK_HOST_URL` — 는 [현재 상태 §1](docs/20_CURRENT_STATUS.md)이 구분해 둔다.

## 환경 변수

`.env.example` 파일을 참조하세요:

```bash
cp .env.example .env
# .env 파일을 편집하여 설정
```

주요 환경 변수:

| 변수 | 기본값 | 설명 |
|:---|---:|:---|
| `AGK_SERVER_HOST` | `127.0.0.1` | 바인딩 호스트 (외부 공개 시 강한 PIN 필수) |
| `AGK_SERVER_PORT` | `8000` | API 서버 포트 (코드 기본값과 같다). 같은 호스트에서 OpenAI 호환 로컬 런타임도 8000을 쓰므로 겹치면 한쪽을 옮긴다 |
| `AGK_SEC_ACCESS_PIN` | 비어 있음 | API 접근 PIN (production 또는 비-루프백 바인딩에서는 8자 이상 필수) |
| `AGK_ENV` | `development` | 실행 환경 (`development`/`production`) |
| `AGK_CORS_ORIGINS` | `localhost:5173,8000` | CORS 허용 오리진 |
| `AGK_LOG_LEVEL` | `INFO` | 로그 레벨 |
| `AGK_DAILY_BUDGET_USD` | `50.0` | 일일 비용 예산 |
| `AGK_HOURLY_ACTION_LIMIT` | `100` | 시간당 액션 제한 |
| `AGK_TASK_DB_PATH` | 패키지 data의 `tasks.db` | CLI/API가 공유할 durable task SQLite 경로 |
| `AGK_APPROVAL_REVIEW_MODEL` | 비활성 | 설정 시 Qwen/Ollama가 승인 후보를 구조화 검토하며, 정책 reviewer보다 권한을 높이지 않음 |
| `OPENROUTER_API_KEY` | — | OpenRouter API 키 |
| `NVIDIA_API_KEY` | — | NVIDIA NIM 무료 API 키 ([build.nvidia.com](https://build.nvidia.com/) 발급) |

### 로컬 프로바이더 설정 (Ollama + MLX + LM Studio)

기본 프로필은 `config.yaml`의 `qwen3.8`이며, reasoning·coding·vision 역할 모두에 Ollama를 사용합니다. `agk model list`로 등록된 이름과 프로바이더를 확인한 뒤 `agk run --model <name>`으로 역할별 모델을 명시적으로 선택할 수 있습니다.

`agk model list`, API의 `/v1/models`, 그리고 등록되지 않은 모델로 첫 생성 요청을 할 때 로컬 모델 자동 발견이 실행됩니다. Ollama `/api/tags`, LM Studio·llama.cpp·Unsloth·기타 루프백 OpenAI 호환 `/v1/models`, Hugging Face 캐시·`~/models`·LM Studio 모델 디렉터리의 GGUF/MLX 파일, `config.json`+Safetensors/PyTorch 가중치 디렉터리, `adapter_config.json` 기반 Unsloth LoRA 디렉터리를 정규화해 레지스트리에 병합합니다. 설정 프로필은 덮어쓰지 않으며 `qwen3.8:latest`처럼 프로필의 `repo`로 들어온 이름도 기존 프로필로 별칭 해석됩니다.

자동 발견 동작은 다음 환경변수로 조정할 수 있습니다.

```bash
export AGK_AUTO_DISCOVER_LOCAL_MODELS=true
export AGK_LOCAL_MODEL_DISCOVERY_TTL=30
export AGK_LOCAL_MODEL_DIRS="$HOME/models:$HOME/.cache/huggingface/hub"
export AGK_LOCAL_OPENAI_BASE_URLS="http://127.0.0.1:9000/v1"
export AGK_VLLM_API_BASE="http://127.0.0.1:8000/v1"
export AGK_TGI_API_BASE="http://127.0.0.1:3000/v1"
export AGK_KOBOLDCPP_API_BASE="http://127.0.0.1:5001/v1"
export AGK_TEXTGEN_WEBUI_API_BASE="http://127.0.0.1:5000/v1"
export AGK_LLAMA_SERVER_BIN="/opt/homebrew/bin/llama-server"
```

모델을 선택하면 런타임 연결도 자동으로 수행됩니다. GGUF는 기존 루프백 `llama.cpp` 서버를 재사용하고, 서버가 없으면 설치된 `llama-server`를 자동 기동합니다(`AGK_LLAMA_SERVER_BIN`으로 경로 지정). Transformers 가중치와 Unsloth LoRA adapter는 `transformers` optional extra가 설치되어 있으면 별도 서버 없이 프로세스 내부에서 직접 로드합니다. 필요한 런타임이 없을 때만 capability에 정확한 누락 사유와 설치 명령을 반환합니다. Unsloth 서버를 자동 탐색하려면 `UNSLOTH_API_BASE=http://127.0.0.1:18000/v1`을 설정합니다.

기본 라우팅 정책은 20B 미만 로컬 모델을 품질 경로에서 제외합니다. 감지된 7B/14B 모델을 직접 사용해야 할 때만 `config.yaml`의 `model_policy.allow_small_local_models`를 `true`로 설정하십시오. 이 옵션은 모델을 자동 승격하지 않고, 명시적인 로컬 모델 선택을 허용하는 정책 스위치입니다.

```bash
# Ollama: 기본 경로
ollama pull qwen3.8:latest
uv run agk run "간단한 작업 계획을 만들어줘" --model qwen3.8

# 직접 MLX: Apple Silicon에서 레지스트리의 32B 코딩 프로필 실행
uv sync --extra mlx
uv run agk run "이 모듈의 단위 테스트를 제안해줘" \
  --model mlx-community/Qwen2.5-Coder-32B-Instruct-4bit

# Transformers/Unsloth adapter 직접 실행
uv sync --extra transformers

# LM Studio: Qwen3.6을 불러오고 Local Server를 127.0.0.1:1234/v1로 시작한 뒤 실행
# Local Server에서 API 토큰을 활성화한 경우에만 설정
export LM_STUDIO_API_KEY=local-token
uv run agk run "현재 변경 사항을 요약해줘" --model lmstudio/qwen3.6

# 선택: 승인 후보만 Qwen 로컬 reviewer로 보조 검토
export AGK_APPROVAL_REVIEW_MODEL=qwen3.8
uv run agk serve
```

MLX 프로필은 `mlx-lm`이 모델 저장소를 직접 로드합니다. LM Studio 프로필은 OpenAI 호환 Local Server를 사용하며, 토큰을 활성화한 서버에서만 `LM_STUDIO_API_KEY`가 필요합니다. `agk doctor`는 `/v1/models`의 실제 로드 식별자와 프로필 `repo`를 비교해서, 다르면 `config.yaml`의 `lmstudio/qwen3.6` 프로필 `repo`를 무엇으로 바꿀지 힌트로 보여줍니다. 원격 OpenRouter·NVIDIA NIM 프로필도 레지스트리에 남아 있지만, 기본 실행에는 사용하지 않습니다.

승인 reviewer는 사용자 결정을 자동 실행하지 않습니다. 모델 호출 실패나 JSON 형식 오류는 사용자 에스컬레이션으로 닫히며, `.env`·credential·token 같은 민감 컨텍스트는 reviewer 프롬프트에서 생략됩니다.

### 로컬 모델 성능 증폭

로컬 27B급 모델(qwen3.8 등)의 성능 한계를 구조적 증폭(CoV 자기검증, 인지 루프, task decomposition, self-consistency, 품질 재생성)으로 보완합니다. `agk doctor`는 Ollama/LM Studio/MLX 대표 모델의 가용성, native tool calling 지원, 문제 발생 시 수정 명령, 그리고 현재 증폭 설정을 함께 확인합니다. 측정된 효과와 튜닝 가이드는 [AMPLIFICATION_GUIDE.md](docs/AMPLIFICATION_GUIDE.md)를 참고하세요.

프론티어 도달 여부는 단발 평균으로 선언하지 않습니다. 아래 명령은 동일한 frozen 케이스를 양쪽 모델에 반복 실행하고 실행 순서를 교차한 뒤, 데이터셋·하네스 SHA-256과 paired gap의 one-sided 95% 신뢰상한을 JSON 증거로 남깁니다. 기본 정책은 6개 이상의 paired 관측치에서 신뢰상한이 0.05 이하일 때만 통과합니다.

```bash
make frontier-evidence
make frontier-evidence ARGS="--local qwen3.8 --frontier openai/gpt-4o-mini --repeats 5"
```

결과는 `data/benchmarks/frontier-comparison.json`과 companion `.sha256` 파일에 기록됩니다. API 키나 frontier 제공자가 없으면 이 비교는 수행할 수 없으며, 내부 테스트 통과만으로 프론티어급 성능을 주장하지 않습니다.

### 보안: 승인 흐름 & 샌드박스

- **승인(Approval) UX**: 위험 도구 실행 시 diff 미리보기와 함께 승인 요청
  - `GET /api/approval/pending` — 대기 중인 승인 목록
  - `POST /api/approval/{id}/resolve` — 수락/거부/항상허용
- **샌드박스**: macOS `sandbox-exec`(seatbelt)로 명령 격리 (config `sandbox_enabled: true`)

## 기여

[CONTRIBUTING.md](CONTRIBUTING.md)를 참조하세요.

## 라이선스

MIT License — 자유롭게 사용, 수정, 배포하세요.
