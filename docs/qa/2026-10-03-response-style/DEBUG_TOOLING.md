# 빌드 도구 메타데이터 검증 기록

Node/Vitest/Vite 기반 대시보드. 파서 라이브러리는 이미 설치된 버전을 직접 의존성으로 올렸으며 해석된 패키지 버전은 변경되지 않았다.

## 가설과 관측

1. 애플리케이션/TypeScript 오류: 집중 92개 테스트 및 tsc가 통과했고, 실패 로그는 테스트 실행 전 pnpm install에서 종료했다. 반증.
2. 실제 파서 패키지 누락: unified/remark-parse의 기존 `.pnpm` 경로를 가리키는 직접 심볼릭 링크와 버전이 존재한다. 반증.
3. 설치 메타데이터 불일치: 프로젝트 lock의 새 직접 의존성 두 항목이 가상 저장소 lock에 없어서 pnpm run이 자동 설치를 시작했다. 두 명령 모두 `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`로 끝났다. 대규모 의존성 디렉터리 삭제는 중단되었다.

## 수정 전 기록

pnpm test/build 실패 로그의 사본은 `TOOLING_FAILED_TESTS.log`, `TOOLING_FAILED_BUILD.log`로 보존한다. 가상 저장소 lock의 이전 파일은 `baseline/virtual-store-lock.yaml`로 보존한다.

프로젝트 lock과 가상 저장소 lock의 차이가 직접 의존성 두 항목의 6줄뿐임을 확인한 뒤 로컬 가상 저장소 메타데이터를 동기화한다. 설치된 실제 패키지/심볼릭 링크를 유지하고 다운로드·모듈 디렉터리 삭제·설정 변경을 하지 않는다. 이후 원래 pnpm test/build 명령을 다시 실행하여 원인을 확인한다.

임시 디버거, 포트, 실행 코드 계측, 영구 환경 변수 변경은 없다. 이 문서는 검증 증거로 보존하는 기록이다.

## 후속 진단 기록 (pnpm 11.3.0)

앞선 가상 저장소 lock 동기화만으로는 경고가 사라지지 않았다. 후속 조사는 세 가설을 구분한다: (1) 런타임 프로젝트 목록과 저장된 프로젝트 목록이 다름, (2) 동일 경로에서 프로젝트 이름/버전이 다름, (3) 저장 상태 파일의 경로와 실제 workspace 경로가 다름. pnpm 내부의 실제 비교 지점에서 값을 읽어 확인하며 추측에 따라 메타데이터를 수정하지 않는다.

진단 산출물 사전 기록: 로컬 Node inspector 프로세스(기본 127.0.0.1:9229, 종료 후 포트 폐쇄), 해당 터미널 세션, 최종 관측 `TOOLING_FINAL.json`. `--config.verify-deps-before-run=warn`을 이 진단 명령에만 지정하여 자동 설치/모듈 삭제 분기에 진입하지 않는다. 실행 소스, 프로젝트 설정, 영구 환경 변수에는 변경하지 않는다. 설치된 외부 pnpm 코드는 프로젝트 그래프에 노드가 없어 직접 읽었다.

## 확정 관측과 범위

실제 Node inspector 비교 지점(`pnpm.mjs:165310`)에서 `workspaceDir`와 `rootProjectManifestDir`는 모두 대시보드의 절대 경로였고, `configuredPatterns`는 `["."]`였다. 저장된 프로젝트는 1개였지만 현재 목록은 **9개**였다: 대시보드 1개와 기존 ignored `dashboard/stryker-tmp/sandbox-*` 8개. 두 번째 실행에서도 같은 목록을 관측했다. 정확한 비교식을 읽기 전용으로 평가한 결과는 `original={count:9,structureChanged:true}`, `configuredRootOnly={count:1,structureChanged:false}`였다. 배열이나 저장 상태는 변경하지 않았다.

pnpm 11.3.0의 실행 전 검증은 `pnpm-workspace.yaml`의 `packages`를 직접 읽어 검색한다(`pnpm.mjs:165459`). 현재 YAML에 그 키가 없으므로 내부 검색 기본값 `[".","**"]`가 적용된다(`39967`). 반면 설치/list 설정은 `["."]`로 해석한다(`114478`). 이 차이가 이전 Stryker sandbox의 package.json까지 프로젝트로 포함시킨다. 루트 경로/이름/버전은 저장 값과 같았고, 가상 저장소 lock도 프로젝트 lock과 완전히 같았다(`cmp` exit 0). 따라서 앞서 동기화한 직접 의존성 6줄은 남아 있는 workspace 경고의 원인이 아니다.

안전한 재현 명령 `pnpm --dir dashboard --config.verify-deps-before-run=error typecheck`는 설치를 시작하지 않고 `ERR_PNPM_VERIFY_DEPS_BEFORE_RUN`과 동일한 workspace 메시지로 exit 1이었다. 지원되는 명령별 설정 `pnpm --dir dashboard --config.verify-deps-before-run=warn typecheck`는 그 경고를 표시한 뒤 `$ tsc -b --pretty false`를 실행하여 **exit 0**이었다. `--config.` 접두사를 포함해야 한다. 전체 출력과 런타임 프로젝트 경로는 `TOOLING_FINAL.json`에 보존한다.

프로젝트의 UI 작업 범위를 유지한다. 오래된 sandbox를 설치 메타데이터에 추가하면 실제 workspace를 잘못 기록하므로 하지 않았고, 관련 없는 Stryker 산출물 삭제나 package/workspace 설정 변경도 하지 않았다. 기본 pnpm wrapper에는 기존 workspace 검색 경고가 남아 있으며, 명령별 warn 설정으로 설치나 모듈 삭제 없이 검증할 수 있다.

정리: 최초 sandbox에서는 inspector 포트 열기가 허용되지 않았다. 로컬 loopback 관측을 승인받아 9239에서 실행했고, 조사 종료 후 세션을 닫고 `lsof -iTCP:9239 -sTCP:LISTEN -nP`가 빈 출력(exit 1)임을 확인했다. 임시 실행 소스 계측, 다운로드, 설치, 모듈 삭제, 영구 설정 변경은 없었다. 이 후속 조사에서 ignored 설치 메타데이터는 수정하지 않았다.
