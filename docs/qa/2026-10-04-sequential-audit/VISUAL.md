---
title: 전체 화면 반응형 및 수정된 UI 상태 검증
date: 2026-10-04
tags: [qa, browser, responsive, accessibility]
status: historical-independent-two-pass-approved; current-run-review-required
---

## 과거 승인 범위 — 원 캡처에 한정

아래 두-pass approval은 당시의 특정 증거 artifact set에 한정된다. 2026-10-06 isolated current-source synthetic `run6`은 새 스크린샷을 생성했으나 아직 독립 검토되지 않았으며 이 과거 판정을 상속하지 않는다. run6은 원래 0.7페이지 이동과 다른 고정 개수 등분 스크롤이며 Agent는 빈 대기열을 사용했다. 개수 일치를 원 승인 기준 충족으로 해석하지 않는다. 현재 실행별 처리 상태는 [run6 검토 보고서](../sequential-improvement/2026-10-04-111745-6a1c/IMP-08/browser-final10-2026-10-06/residual-populated-supplement-2026-10-06-run6/README.md)에 기록한다.

실제 IAB의 production dashboard를 임시 인증/저장소와 연결했다. 모형 화면이나 screenshot overlay를 사용하지 않았다. 수정된 최종 bundle에서14개 canonical route × 375/768/1280px, 높이900px의42개 기본 상태 및63개 내부 스크롤 구간을 다시 캡처했다. routes: chat, studio, models, start, agent, wiki, skills, data-extraction, git, history, plugins, plugins/job-operations, mutation, settings. `/`는 chat alias이며 별도 화면으로 중복 계산하지 않는다.

추가 상태18장: 위키 생성창 열림/닫힘 각3너비, Embedding 모델 필터3너비, 채팅 모델 선택창3너비, 실제 추출 A/B 완료3너비 및 마지막 환율 행까지의 후속 스크롤3장. 원 승인된 전체 123장 증거는 [route manifest](browser/capture-manifest.json), [interaction manifest](browser/state-manifest.json), [JPEG/dimension validation](browser/hygiene.json)에 있다. 별도로 추가된 2026-10-06 synthetic run6 증거와 한계는 [run6 보고서](../sequential-improvement/2026-10-04-111745-6a1c/IMP-08/browser-final10-2026-10-06/residual-populated-supplement-2026-10-06-run6/README.md)에 기록했다. 스크롤이 필요한 화면은 실제 scrollTop이 scrollHeight-clientHeight에 도달한 것을 확인했다. 모든 후속 프레임은0.7page씩 이동하여 visibleOverlap≥0을 확인했다.

위키 Tab 실제 순서: path → title → tags → cancel → close → path. Escape 후 새 문서 생성 트리거로 포커스가 돌아왔다. 같은 동작이3너비에서 모두 관찰됐다. Embedding 필터는 nomic-embed-text만 남고 전체 필터 복귀 후6개로 돌아온다.

캡처 도구 오류: viewport override가 현재 활성화된 surfaceTab에만 적용되어 별도 chat 탭의 모델 선택창3장은 최초 너비/높이가 맞지 않았다. 올바른 surfaceTab에서3장을 재촬영하고 실제 innerWidth/innerHeight 및 JPEG dimensions 일치를 검증했다. Python 검사 명령의 escaping/filename mismatch 실패도 제품 결함으로 세지 않았다.

독립2개 첫 검토는103장을 모두 직접 열고 REVISE를 반환했다.20개의 실제 미합성/blank frame과48px 스크롤 누락은 캡처 도구 문제였다. 원본은browser-v1에 보존했다. native getScreenshot의 합성된 후속 프레임으로 최종123장을 다시 촬영했다. JPEG/너비/높이 오류0, body blank 후보0, 스크롤 gap0이다.

제품 결함도 수정했다: MCP 긴 경로로 밀려 사라진 버튼, 좁은 적용 버튼, 세로로 갈라진 설치됨 badge, Studio/Start 한국어 문장, 모바일 table identifier 줄바꿈/흰 scrollbar. Root는 최종 settings375 MCP/적용, model1280 badge/0.494B, chat-selector375 tuple/수평스크롤을 직접 열어 확인했다. 새 독립2개 검토가 최종123장을 각각 모두 열고 PASS/APPROVE를 반환했다: [구현·데이터 검토](visual-integrity-final.md), [레이아웃·가독성 검토](visual-layout-final.md). 구체적인 디자인 참조 이미지가 없는 기존 제품 기능 점검이므로 pixel-diff는 적용하지 않는다. 기존 애니메이션 전체와 모든 조합 상태의 완전 검증을 주장하지 않는다. 이 원장은 열거한 route/state만 다룬다.

추출 A/B는 개선 후 실제 버튼 실행에서4/4케이스,20/20필드,100%로 표시됐다. 모델 검색 답변의 사실/형식 정확성은 시각 검토와 별도로 QUESTIONS.md에 기록한다. 초기 표 누락 재발을 비롯한 실제 실패를 보존했고 backend 개선 후 최종 동일질문 연속2회에서 표1개/데이터2행/유효officialhref1개를 확인했다(`search-final-live-{1,2}.*`, `search-final-live-verified.json`). QA09B 단일할당문/링크1개/도구금지 정정도 실제 재실행에서 통과했다. 최종 검색 보정은 dashboard 소스를 바꾸지 않았다.
