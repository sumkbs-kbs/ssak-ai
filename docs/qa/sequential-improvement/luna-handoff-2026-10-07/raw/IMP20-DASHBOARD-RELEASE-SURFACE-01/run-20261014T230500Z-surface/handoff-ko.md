# 대시보드 릴리스 표면 수정 인계

판정: 구현 및 범위 내 검증 완료. 독립 검수·최종 커밋 후보의 전체 GA gate는 상위 작업 소유자에게 인계한다. 이 작업에서 stage/commit/push는 하지 않았다.

작업 후보: `/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai`. 시작 이후 상위 작업자의 커밋 창이 있었으며, 수정 전 사본을 보존하고 재개 시 해당 파일 해시를 대조했다. 현재 source를 과거 Git SHA의 clean source라고 주장하지 않는다.

## 수정 내용과 근거

1. AgentMonitorPanel의 상태 색을 기존 의미 토큰으로 연결하고, 상태 카드의 metric label을 `--text-muted`로 지정했다. 이전 실제 브라우저 /agent desktop·mobile 대비 실패가 근거다.
2. 팔레트 선택/hover 부제목의 텍스트 토큰을 `--text-primary`로 변경했다. 수동 브라우저 측정에서 `#b8b8b8` / `#434a5d`가 4.45:1로 4.5:1에 미달했다(`manual-attempt-4/palette-desktop-1440-dark.axe.json`). 최종 변경 후 심각·치명 위반 0이다.
3. 현재 대화 navigation의 accessible role/name을 사용하고 모바일 drawer가 닫혔으면 열도록 DashboardPage를 고쳤다. CR07 셸은 현재 `SSAK-AI 탐색`으로 찾고, CR08 inert는 실제 DOM의 조상 상속을 검사한다. focus 순환·복귀, retry/reload·404·대화 보존, IME, 악성 Mermaid 차단 단언을 유지했다.
4. CR10은 사용자처럼 상세 지표 disclosure를 열고 실제 text와 API 값을 비교한다. 마지막 실패에서 900초가 `14M 59S`로 표시되는 제품 결함도 발견했다. 화면 시계가 새 관측 시각보다 앞선 경우 음수 경과 시간을 더하던 문제로, `Math.max(0, now - observedAt)` 한 경계를 수정했다. 고정 API 기대값은 바꾸지 않았다.
5. Python 읽기 스타일 테스트의 이전 240px literal을 CSS 토큰 정의·양수 값·실제 sidebar width/min-width 참조 계약으로 바꿨다. 디자인 명세와 현재 UI는 248px이며 실제 desktop DOM도 248px이다. 나머지 렌더링·보안 단언은 그대로다.

기존 published bundle이 source보다 오래됐다는 증거는 없었다. 원래 bundle commit은 source 변경보다 뒤였으며 문제 일부는 이전 UI locator였다. ROOT의 전체 frontend diff를 읽기 전용으로 비교했다. 단순 전면 복사는 하지 않았고 마지막 `preservation-check.json`에서 ROOT frontend diff가 동일함을 확인했다.

## 실행과 실제 관측

| 시나리오 | 명령/근거 | 관측 |
|---|---|---|
| 관련 실제 Chromium 6 spec | `browser-attempt-1/checks.json`, `browser.stdout.txt` | 57개 중 56 PASS, 1 FAIL. accessibility 35, CR07 4, CR08 5, CR09 4, CR10 4, file-explorer 5. 실패는 C10 uptime 14M59S이며 PNG·error-context 보존 |
| uptime 경계 단위 재현 | `pnpm --dir dashboard exec vitest run src/components/Layout/__tests__/SystemTelemetricsBar.cr10.test.tsx -t '새 관측'` → `telemetry-unit-red.txt` | 수정 전 1 FAIL, 선택에서 제외된 기존 11개 skipped. 예상15M00S/실제14M59S |
| uptime 수정 후 전체 해당 단위 파일 | 동일 경로, `-t` 없이 → `telemetry-unit-green.txt` | 12 PASS, exit0 |
| 동일 C10 실패 브라우저 selector | `browser-c10-attempt-2/checks.json` | `cr10-telemetry.spec.ts:163` 1 PASS, 실제 `15M 00S`, exit0. build/PID/CPU/MEM/VAULT/API 기대값 유지 |
| 읽기 스타일 Python selector | `reading-style-before.txt`, `reading-style-after.txt` | 수정 전1 FAIL → 후1 PASS |
| 수동 실제 Chrome, owned no-auth backend | `manual-attempt-5/checks.json`, `manual-observations.json`, 8개 PNG·axe JSON·snapshot | Agent와 palette × desktop1440/mobile390 × dark/light OS preference. 8관측 심각·치명0, documentWidth=viewport, desktop sidebar248/mobile숨김0. OS light preference에서도 앱 data-theme는 null이고 화면은 어두운 기본 테마였음. 실제 별도 light 앱 테마 검증이라고 주장하지 않음 |
| 표준 production build | `build-attempt-1/2/3/checks.json` | 각 exit0, tsc 및 Vite build 통과. 대형 chunk 경고 보존 |
| F34 정확한 build 명령 재현 | `build-reproduce-1/checks.json`: `pnpm run build`, cwd=`dashboard` | exit0, `bundle-reproduction.json`의 106파일 경로·크기·SHA 동일 |
| 정적/패치 | `eslint-owned.txt`, `eslint-telemetry.txt`, `ruff-reading-style.txt`, `patch-reconstruction.json` | lint 진단 없음, Ruff 통과, git diff --check 통과. task-only.patch의 소유10파일을 시작 사본에 적용해 최종 bytes 동일 |

실행별 source binding을 별도 보존했다. 최초 56개 브라우저 성공과 수동 8관측은 **surface-de1fbf4e9a85** 번들 근거다. 이후 uptime 한 줄 및 단위 테스트가 추가된 최종 번들 **surface-4c68417e510b**는 CR10 unit12와 실패했던 브라우저1건을 검증했다. 전체57개가 최종 새 번들에서 다시 실행됐다고 합산하지 않는다. 상위 지시에 따라 이미 성공한56개/수동8관측은 반복하지 않았다.

## 빌드 provenance와 보존

`dashboard/buildStamp.ts`의 기존 순서는 환경변수 override → build-provenance.json → Git fallback이다. 기존 JSON pin을 사용하므로 이후 커밋이 생겨도 Git fallback 때문에 바이트가 달라지지 않는다. 새 custom skip이나 gate 변경은 없다. 실행 driver는 inherited AGK_BUILD_ID/AGK_BUILT_AT을 제거했다. 최종 pin과 source digest 산식·개별 파일은 `build-source-v3.json`에 있다. digest는 sorted dashboard/src 경로·SHA tuple의 Python repr UTF-8 SHA-256이며 dirty working source의 식별자다. Git commit SHA가 아니다.

`preimage-manifest.json`의 기존 bundle·로그·가용 첨부 145파일을 최종 재대조했다. 원래 parent accessibility/witness 첨부는 후속 ambient 실행이 test-results를 바꾼 뒤라 확보할 수 없었고, 원문 로그만 보존했다. 이 작업의 새 실패 첨부는 browser-attempt-1/test-results에 있다.

최종 소유 파일은 `patch-reconstruction.json`의10경로와 표준 생성 bundle뿐이다. `task-only.patch`는10경로만 담으며 generated bundle은106파일 manifest와 표준 build 재현으로 연결한다. 다른 worker 소유 Python 테스트/문서/백엔드와 ROOT 사용자 frontend는 수정하지 않았다.

## 실패·한계 및 정리

- codebase graph는 project unindexed였으며 상위 작업의 index 시도도 timeout이었다. 알려진 파일과 문자열에 한정해 fallback 탐색했다.
- Node REPL의 guarded browser loader가 process unavailable로 실패해, 같은 documented guarded loader를 Bun에서 실행했다. browser engine 우회 import는 하지 않았다.
- manual-attempt-1은 axe transitive dependency 경로 때문에 browser 생성 전에 실패했다. 미리 시작된 이 작업의 backend PID22845/22847을 해당 runtime env로 식별해 SIGTERM 후 둘 다 소멸을 확인했다(`setup-cleanup.json`). 후속 helper는 자산 확인 후 서버를 시작하고 finally에서 정리한다.
- manual-attempt-2는 자산 symlink 경로 해석 실패로 서버 시작 전 종료됐다. attempt-3은 CSP 때문에 script node 주입이 막혀 axe가 없었고 finally 정리했다. 최종 도구는 CDP 평가로 검사 라이브러리를 주입한다.
- attempt-4의 mobile 이름 캡처는 실제 viewport가1440이어서 mobile 증거로 쓰지 않는다. navigation 후 emulation을 적용한 attempt-5에서390/1440을 DOM 측정하고 정상 캡처했다. attempt-4의 팔레트 대비 실패는 보존했다.
- manual-attempt-5는125개 요청 URL을 보존했고 전부 해당 backend 원점이다. agent/status/assets 조회이며 chat inference 요청은 없다. 모든 실행에서 모델 API 주소는 bound-but-not-listening loopback으로 설정했다. 실제 Ollama/live 모델 추론을 수행하지 않았다.
- 최종 manual browser/profile/backend 정리 완료. actual browser gate wrapper도 exit와 reap receipt를 남겼다. 인증·모델 품질·전체 GA 승인을 이 결과로 주장하지 않는다.
- 증거 helper의 LSP는 ROOT TypeScript 설치 부재를 보고했고 CSS LSP Biome도 사용 불가였다. production 표준 tsc build와 명시 ESLint 검사를 수행했다. CR07 기존 readonly tuple에 관한 LSP 진단은 원래 사본에도 있던 내용이다.

다음: 상위 작업자가 scoped patch·bundle manifest를 독립 검수하고, 후보 커밋 후 전체 GA gate와 push를 진행한다. 최종 후보 전체 gate 결과는 본 문서의 좁은 통과와 별도로 기록해야 한다.
