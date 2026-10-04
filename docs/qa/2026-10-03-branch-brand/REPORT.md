# 하단 브랜치 표시 변경 검증 — GOOD

사용자가 지정한 채팅 하단 작업 환경의 표시를 `codex/m1-task-events`에서 `ssak-ai/m1-task-events`로 변경했다. 실제 Git 브랜치는 `codex/m1-task-events`로 유지하며, title 속성에 `실제 Git 브랜치: codex/m1-task-events`를 표시한다.

변경은 ChatPage.tsx1276의 기존 span 한 줄과 DESIGN.md79의 계약 한 줄이다. 시작 접두사 `/^codex\//`만 대체하므로 다른 접두사와 중간 문자열은 그대로 표시된다. 빈 브랜치를 숨기는 기존 조건도 유지한다. 저장소·API·PIN·실제 Git 상태와 외부 제공자 및 명령 팔레트는 변경하지 않았다.

| 확인 | 결과 | 증거 |
|---|---|---|
| 타입 검사 / 배포 빌드 | exit0, Vite20.66초 | BUILD.log, VERIFICATION.json |
| 실제 브라우저 | 375/768/1280px 및 기본757px에서 표시·title·폭 확인 | CAPTURE_MANIFEST.json |
| 보호 파일 | 작업 시작 기준4개 동일 | BASELINE.json, FINAL_INTEGRITY.json |
| 소스 / 배포 | 현재62개 /104개 해시 일치 | SOURCE_MANIFEST.json, BUNDLE_MANIFEST.json |
| 캡처 | 원본7개, 정확한 RGB 변환 비교PNG6개 | CAPTURE_CHECK.json, comparisons/ |
| 독립 검토 | A/B 모두 PASS, 차단 사항 없음 | REVIEW_A.md, REVIEW_B.md, REVIEW_LEDGER.json |

실제 DOM의 하단 텍스트와 title 값은 모든 수정 후 캡처에서 일치한다. 브랜치 영역이 뷰포트 안에 있고 문서 가로 넘침이 없다. 콘솔 warn/error는 관측하지 않았다. 기존 대화·모델·빈 입력이 유지되며 기본 창 크기를 복원했다.

## 최종 시각 판정

| 항목 | 판정 | 증거 |
|---|---|---|
| 실제 디자인 시스템 / DOM | good | 기존 context-item·AppIcon·텍스트 토큰 재사용 |
| 표시 동작 | good | 화면 별칭과 실제 원문 title 보존, 다른 접두사·빈 값 조건 유지 |
| 반응형 | good | 세 폭과 기본 창의 하단 텍스트가 잘림 없이 표시됨 |
| 이미지 / 투명도 | good | 정상 JPEG/PNG 크기와 RGB, 빈 합성 영역 없음 |
| 스타일 의도 | good | 기존 폰트·간격으로 ssak-ai 접두사 표시 |
| 한글 표시 | good | 하단 한글 라벨과 브랜치가 겹치거나 잘리지 않음 |

두 새 검토자가 전체13개 이미지를 원본 해상도로 열고,375/768/1280px의8/3/17개 diff hotspot을 모두 설명했다. 의도된 하단 문자열 변화 외에375px live clock,1280px reload 전후 사이드바 스크롤 위치와 작은 JPEG 차이가 포함된다. 전체 화면의 픽셀 동일성을 주장하지 않는다. 현재 소스 매니페스트 SHA-256은 `ad74348cdff8d1c1ee95c545f8424b0c762acd9a6f9df292c98fb398082a7327`이며 이전 응답 스타일의 승인은 이번 승인으로 재사용하지 않았다.

## 구현 및 도구 범위

기존 ChatPage는1202pureLOC이지만 이번 작업은 기존 표시 span 한 줄만 수정했다. 기존 string 타입과 표준 replace를 사용하며 새 helper·함수·의존성·타입 단언·오류 경계·variant 분기는 없다. 되돌릴 수 있는 작은 표시 변경을 그대로 복제하는 새 테스트는 작성하지 않고 타입 검사·빌드와 실제 화면으로 검증했다.

기존 pnpm workspace 확인 실패 때문에 설치된 실행 파일을 직접 사용했다. 사용자 선호에 따라 Biome LSP는 추가 설치하지 않았다. 실제 native hover 툴팁 팝업은 별도로 검증하지 않았으며 title 속성은 DOM에서 확인했다. Lighthouse·전체axe·OSIME·새 모델 요청은 이번 변경의 확인 범위가 아니다.
