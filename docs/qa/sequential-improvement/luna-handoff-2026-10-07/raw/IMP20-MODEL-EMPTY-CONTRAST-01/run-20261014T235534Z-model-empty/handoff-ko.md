# 모델 빈 상태 안내문 대비 수정

판정: IMPLEMENTED_STATIC_VERIFIED_BROWSER_PENDING.

수정은 `dashboard/src/styles/index.css`의 `.model-empty-notice` 색상 한 줄이다. 고정 `#6b7280`을 기존 `var(--text-muted)`로 바꾸었다. 모델 허브의 로딩/검색 결과 없음 문구가 테마의 의미 텍스트 색상을 사용한다. 기존 채팅 팝오버의 동일 토큰 규칙과도 일치한다. 다른 CSS 바이트와 테스트 소스는 변경하지 않았다.

## 검증

- 시나리오: 저장 전후 CSS 차이가 해당 색상 선언 하나인지 검사. 실행: `result.json`의 invocation. 관측: 전체 파일이 단일 문자열 치환 결과와 동일, `git diff --check` exit 0. 근거: `result.json`, `preimage/index.css`, `postimage.css`, `task-only.patch`.
- 시나리오: CSS 기본 다크 배경 `#202020`의 12px 일반 텍스트 대비. 같은 실행에서 WCAG 상대 휘도 수식으로 3.3702에서 6.2307로 개선됨을 계산했다. 라이트 토큰 `#5d6470`과 기준 흰색 조합은 5.9621이다. 이는 CSS 토큰의 정적 계산이며 실제 라이트 테마 배경이나 CSS cascade를 관측한 결과가 아니다.
- 실행 전후 실제 HTTP/모델 호출은 0회다. 번들, build-provenance는 상위 작업 소유이므로 변경하지 않았다. 실제 `/models` 데스크톱·모바일 브라우저 게이트는 상위 작업의 새 빌드 후 검증 대상이다. full GA 또는 브라우저 PASS를 주장하지 않는다.

최초 증거 스크립트 실행의 시스템 Python 버전 오류는 `initial-runtime-failure.md`에 보존했다. 후보 가상환경 Python에서 성공했다. Biome은 기존 미설치 및 사용자 설치 거절 상태로 설치하지 않았다. 기존 컴포넌트/토큰을 재사용하는 좁은 수정 범위여서 추가 도구 설치, 디자인 시스템 재작성, 확대 감사를 수행하지 않았다.
