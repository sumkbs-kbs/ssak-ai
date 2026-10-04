# 응답 스타일 반영 검증

답변 표시를 Codex 기반 워크스페이스에 맞춰 정돈했다. 글꼴은 macOS 시스템 및 한국어 fallback, 본문16px/행간1.7, 제목18/16px, 코드13px, 표14px로 일관되게 적용한다. 문단·목록·표·인용문과 코드 도구 막대는 기존 의미 토큰을 사용한다. 긴 코드는 코드 영역 안에서 가로 스크롤한다.

시스템이 덧붙인 모드·CEO·성공 품질·토큰 정보는 기본 닫힌 ‘응답 정보’로 이동했다. 중첩 ‘원문 보기’에서 저장된 원문을 평문으로 확인할 수 있다. 실패·재시도·승인·작업 로그를 임의로 지우지 않는다. 답변 복사는 정돈된 본문을, 각 코드 복사는 코드 자체를 복사한다. 일반 이모지와 코드·인용·들여쓰기 안의 문구는 원문대로 보존한다.

| 검증 | 결과 | 증거 |
|---|---|---|
| 전체 테스트 | 105파일/1,043개 통과 | TESTS.log |
| 타입 검사 및 배포 빌드 | exit0; vite26.11초 | BUILD.log, VERIFICATION.json |
| 원문/HTML 경계 | 실제 CommonMark/GFM AST 기반; 이전HIGH 정화 우회 수정 후 독립 코드 검토 승인 | CODE_REVIEW_FINAL.md |
| 실제 브라우저 | 기존/새 응답375/768/1280px, 본문·정보·원문·코드·표·인용·링크, 키보드토글, 복사 붙여넣기 | MANUAL_QA.md, COPY_RESULTS.json |
| 실제 모델 응답 | qwen3.8:latest27.3B, 입력143/출력184, 생성 완료, 콘솔warn/error0 | REAL_RESPONSE.txt, BROWSER_LOGS.json |
| 기존 대화 | 기존7개 보존, 검증1개 추가 | HISTORY_PRESERVATION.json |
| 보호 파일 | 저장소·프로젝트·API·PIN4개 작업 시작 기준 동일 | PROTECTED_CHECK.json |
| 배포 일치 | 소스62개와 배포104개 해시 | SOURCE_MANIFEST.json, BUNDLE_MANIFEST.json |
| 시각 증거 | 원본26개 및 동일RGB 비교PNG6개, 전체55hotspot | CAPTURE_MANIFEST.json, CAPTURE_CHECK.json, comparisons/ |
| 독립 시각 검토 | 진행 중 | VISUAL_REVIEW_A.md, VISUAL_REVIEW_B.md |

이번 작업은 Codex와 어울리는 응답 표시를 반영하며 비공개 Desktop 글꼴이나 정확한 픽셀 복제를 주장하지 않는다. 이전 전체UI 검토 PASS를 이번 승인으로 사용하지 않았다.

## 검증 도구와 확인 범위

로컬 pnpm 기본 실행은 이전 Stryker 임시 샌드박스8개를 별도 프로젝트로 발견하여 스크립트 전에 실패한다. 설치된 Vitest/tsc/Vite 실행 파일로 전체 검증과 배포를 마쳤고, 지원되는 일회성 `--config.verify-deps-before-run=warn` 타입 검사도 통과했다. 설치·모듈 삭제·전역 설정 변경은 하지 않았다(TOOLING_FINAL.json). Biome LSP는 설치되지 않았고 사용자 요청에 따라 추가 설치하지 않았으며 타입 검사/테스트/빌드로 검증했다. 기존 큰 번들 경고는 남아 있다.

실제 새 응답에서 모델이 도구 금지 지시에도 로컬 Markdown 아티팩트를 만들었으며 첫 항목 앞 줄바꿈을 생성하지 않았다. 응답 원문과 작업 로그를 보존했고 해당 모델 동작을 UI 스타일 수정으로 바꾸지 않았다. 실제503/CAS/추가 승인/OS IME는 유도하지 않았다. 운영 전체 페이지·Lighthouse/axe·Electron 네이티브 접근성을 검증한 주장은 아니다.

검증은 커밋을 만들지 않은 현재 작업 폴더 기준이다. HEAD와 별도로 소스 파일별 해시를 기록해 이전 변경 및 이번 응답 변경이 함께 포함된 실제 배포 빌드에 결속했다.

## 작업 인계

표시 계약: dashboard/DESIGN.md의 Assistant Response Typography / Disclosure. 표시 컴포넌트: ChatMessage, ChatMarkdown, ChatCodeBlock, MessageMetadata. 응답 해석/정화: utils/responsePresentation.ts. 응답 CSS: styles/workspace-response.css. 원문/정화 경계를 건드릴 때 실제 렌더 DOM 회귀 테스트와 원문/코드 보존 테스트를 함께 통과시키고 실제 브라우저 캡처를 다시 만든다.
