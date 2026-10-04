---
title: Codex UI 기반 SSAK-AI 프론트엔드 개선 결과
tags: [frontend, codex, handoff, qa]
date: 2026-10-03
---

# 결과

폰트·색·간격과 대화 중심 화면 구성을 Codex의 차분한 사용감에 맞춰 개선했다. 실행 중인 localhost:8000 production 화면에 반영했고, 최종 독립 검토는 모두 통과했다.

- 시스템 UI 서체와 한글 폴백을 통일했다. UI14px, 대화16px/27.2px행간, 코드 고정폭을 적용했다.
- 왼쪽248px 프로젝트·최근대화 탐색, 최대760px 읽기영역, 본문 스크롤과 분리된 하단 입력창을 구성했다. 중복 상태·강조색을 줄이고 공통 토큰과 SVG아이콘으로 정리했다.
- 모델·도구·첨부·전송·복사·이력·검사 패널을 정리했다. 좁은 화면은 모달로 전환하고 헤더·X·키보드 포커스·초안을 보존한다. 작은 화면의 주요 조작 영역은36px이상이다.
- 스튜디오·모델·설정 등 보조 화면의 간격·한글 줄바꿈·긴 식별자를 정리했다. 비대화 화면의 직접 새로고침 이력을 복원하고, 이전 대화를 한 번 클릭해도 최신 캐시가 다시 열리던 선택 버그를 수리했다.

# 검증

| 검증 | 결과 | 근거 |
|---|---|---|
| 전체 프론트엔드 |103파일/1001테스트 통과 |TESTS_CURRENT.log |
| TypeScript/production build |exit0 |TYPECHECK_CURRENT.log/BUILD_CURRENT.log |
| 이전 대화 선택 회귀 |실제 Sidebar→ChatPage 마운트 RED→GREEN, cold3경로 한 번 클릭 통과 |FINAL_SESSION_DELTA.patch/ssak-sidebar-selection-red.log/green.log/RECENT_SINGLE_CLICK_LIVE.json |
| 브라우저 화면 |17경로×3크기+27상태+3설명=81현재 원본, 가로 넘침0 |CAPTURE_MANIFEST/CAPTURE_HYGIENE/BROWSER_OBSERVATIONS |
| 실제 대화 |27.3B 정상 인사 완료, ShiftEnter줄바꿈, Markdown복사에 인사문 포함 |LIVE_CHAT_RESULT |
| 저장 대화 |최종 직전6개 보존+검증1개=7개, coldStudio/Wiki/Settings 모두 표시 |NONCHAT_RESTORE_LIVE |
| 모바일 패널/키보드 |X/Escape, 초안·포커스·inert복귀, 도움말·팔레트Tab순환 |QA_DIRECTED_RESULTS |
| 글꼴/한글/조작 영역 |UI14·대화16/27.2, helper3폭 낱말 유지, compact18개씩>=36 |TYPOGRAPHY_LIVE/SETTINGS_WORD_GEOMETRY/COMPACT_CONTROL_BOUNDS |
| 독립 검토 |Code/Security/QA/Context/Goal·VisualA/VisualB 모두PASS |[INDEPENDENT_REVIEW.md](INDEPENDENT_REVIEW.md) |
| 직접 런타임 감사 |명시한 실제브라우저 범위PASS |DEBUG_RUNTIME_AUDIT.md |

![최종 사용자 화면](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/deliverable.jpg)

# 유지한 계약과 인수 기준

코어 설계·서버CAS·PIN인증은 그대로다. 보호 대상 chatStore/projectStore/APIclient/accessPinCredential의 이번 UI 작업 시작 해시와 현재 해시가 같다. qwen3.8:latest27.3B가 유지되고125B선택지는 삭제하지 않았다. 기존 작업을 되돌리거나 Git커밋을 생성하지 않았으며 독점 폰트·앱 번들을 복사하거나 의존성을 설치하지 않았다.

기준은 HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` + dirty46 SOURCE_MANIFEST `f8d138c7f6f47059dfb98ff672057fc7a0b5df993be18d6de1dd524f257236cd`, CAPTURE_MANIFEST `ace91095874923c893bd4948274fa324e0407828959c6cbc94400014d4e7b1d3`다. main `/assets/index-CEvvbZ3V.js`, CSS `/assets/index-C19bV3rn.css`. SOURCE_MANIFEST에는 새 파일도 포함된다. WORKTREE.patch는 현재 dashboard작업트리의 tracked diff이므로 이 UI의 단독 패치나 전체 인수본으로 취급하지 않는다. 마지막 수리 범위는 FINAL_CSS_DELTA와 FINAL_SESSION_DELTA에 따로 기록했다. REVIEW_LEDGER는 각 판정의 fullHEAD·sourceSHA·reportSHA를 보존한다.

다음 에이전트는 dashboard/DESIGN.md의 토큰·폭·한글 줄바꿈·모달 계약과 docs/frontend의 참고 분석·완료된 실행계획을 기준으로 작업하면 된다. 셸·대화·이력·검사·보조페이지 스타일의 소유권을 유지하고 프로젝트ID·리비전·모델영속화·정제·승인 데이터 경계를 기존 테스트와 함께 보존한다. 현재 소스46개·배포104개·원본81개는 최종 검토에 묶였다.

# 범위와 기존 한계

공개 openai/codex는 CLI/RustTUI·app-server이며 Desktop ReactUI 원본이라고 주장하지 않는다. 시스템 글꼴과 재사용 토큰으로 원하는 사용감을 반영했고, 정확한 Desktop픽셀 복제·독점 폰트 일치는 검증하지 않았다. [참고 분석](../../frontend/CODEX_REFERENCE_2026-10-03.md), [시각 QA](VISUAL_QA.md)에 근거와64hotspot 대응이 연결된다.

기존 Skills/Metrics401은 정돈된 오류 화면까지만 확인했다. 해당 백엔드 기능의 성공은 이번 UI 작업 범위가 아니다. ReactDoctor는 기존 무시된 비배포 mutationfixture 경고로exit1이며 배포 보안 검토는PASS다. 기존 Monaco/Mermaid 큰 청크 경고가 남는다.

네이티브OSIME, composing/key229, 권한503의 read-only·오류표시, API typedCAS409/integrity/migration503와 늦은 복원 경쟁은 자동 회귀 범위다. 실패 전송 후 초안 유지나 실제 장애주입 전체 통과를 주장하지 않는다. 전체axe/Lighthouse/nativeElectron은 미실행이다. UI 작업에서 만든 합성 검증 대화는 총6개이며 원래 기록과 함께 삭제하지 않았다.

시각 비교는 실제757×954전후 원본을 변환만 한 PNG로 계산했다. 과거 blackpadded768합성 오류는 제외·보존했고, similarity0은 품질 점수가 아니다. 이전 실패는 immutable archive로 보존하며 변경된 소스에 이전PASS를 재사용하지 않았다. Round6의987테스트 원시 로그 보존 한계는 ROUND6_LOG_RECEIPT에 명시했다. 임시 viewport를 reset했고 빈초안/가시모달0/출력패널닫힘 상태의 사용자 탭을 유지했다.
