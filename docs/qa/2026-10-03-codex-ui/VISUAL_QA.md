---
title: Codex UI 시각 QA 인수 기록
tags: [frontend, visual, qa]
date: 2026-10-03
---

# 판정: PASS — Codex를 참고한 적응형 UI

소스 `f8d138c7f6f47059dfb98ff672057fc7a0b5df993be18d6de1dd524f257236cd`, 캡처 `ace91095874923c893bd4948274fa324e0407828959c6cbc94400014d4e7b1d3`, HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`. 공개 Codex의 CLI/TUI·app-server 원칙과 사용자가 선호하는 Desktop의 차분한 폰트·배치를 참고했다. 실제 Desktop ReactCSS 원본이나 픽셀 타깃을 받은 것으로 표기하지 않는다.

- 원본81개:17경로×3폭51개, 상태27개, 실제 Settings 설명3개. 모든 JPEG의 해시·서명·요청/실제 크기·소스 편집 후 시점과 대응 DOM이 검증됐다. 가로 넘침0.
- Goal/Visual-A와 Visual-B가 각각81개를 original detail로 직접 열었다. 두 검토 모두 PASS이며 전체 원본 목록과64hotspot의 좌표별 대응은 GOAL_REVIEW와 VISUAL_REVIEW_B에 있다.
- 실제 글꼴은 system UI와 한글 폴백. UI14px, 대화16px/행간27.2px, composer16px/25.6px, desktop탐색248px/본문최대760px. TYPOGRAPHY_LIVE에 실측했다.
-375/768의18개 실제 compact조작 영역은 각각>=36px. Settings의 보여줍니다는 세 폭 모두 다섯 글자가 같은 줄이며, Mutation의40자 SHA가 잘리지 않는다. COMPACT_CONTROL_BOUNDS/SETTINGS_WORD_GEOMETRY 및 실제 원본 근거다.
- 이력·검사 헤더와X가 가려지지 않고 팔레트·도움말은 불투명하다. 실제 닫기/포커스/한글초안/Tab/ShiftTab 근거는 QA_DIRECTED_RESULTS. 768Code/Changes는 실제 전환 완료 뒤 다시 촬영했다.

# 비교 방법

원래757×954 before-default.jpg와 최종 deliverable.jpg를 RGB PNG로 변환만 했다. 크기변경·여백·crop·redraw를 하지 않았고 decoded pixels의 일치도 검증됐다. IMAGE_DIFF_RECEIPT는 원본/변환/계산 해시를 연결한다. 64hotspot은 의도적인 배경·레이아웃·글꼴 변화와 서로 다른 합성 테스트 대화를 포함한다. similarity0은 품질 점수가 아니다.

과거768×900 파일은375×812콘텐츠에 검은 여백이 붙은 compositor오류였다. IMAGE_DIFF_INVALID_BASELINE768에 보존하고 평가에서 제외했다. 현재81프레임의 실제documentWidth와 요청폭은 모두 일치한다.

# 최종 사용자 화면

viewport override를 reset해 원래757×954로 돌아갔다. 대화7개를 보존하고27.3B모델을 유지한 채, 빈초안/실제 열린 모달0/출력패널닫힘 상태의 deliverable.jpg를 저장했다. 사용자 브라우저 탭은 열린 상태다. 접근성 전체 자동 감사와 nativeElectron은 수행하지 않았다.
