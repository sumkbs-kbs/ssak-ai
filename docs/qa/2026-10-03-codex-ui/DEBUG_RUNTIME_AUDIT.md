---
title: Codex UI 최종 런타임 감사
tags: [frontend, runtime, qa, debugging]
date: 2026-10-03
---

# 판정: PASS — 직접 관찰한 범위

HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` + dirty46 SOURCE_MANIFEST `f8d138c7f6f47059dfb98ff672057fc7a0b5df993be18d6de1dd524f257236cd`, CAPTURE_MANIFEST `ace91095874923c893bd4948274fa324e0407828959c6cbc94400014d4e7b1d3`. root가 기존 Electron 소유 localhost:8000 production 화면을 사용자 잠금 해제 IAB2/1에서 CUA로 직접 조작한 감사다. mainCEvvbZ3V/CSSC19bV3rn,46소스/보호4/배포104 바이트 해시를 확인했다. 이전 감사는 archive-round7과 DEBUG_RUNTIME_AUDIT_ROUND2에 보존했다.

## 원인과 수리

- 초기 서버 프로젝트ID 지연으로 빈 이력이 보이는 ChatPage 복원 경계를 제한된 복원으로 수리했다. 작성 중 초안·첨부·새 대화·스트림을 덮어쓰지 않는 자동 회귀 근거를 보존했다.
- 직접 비대화 페이지를 열면 Sidebar 이력이 비어 보이는 경계는 서버 프로젝트ID 준비·빈 대화 상태에서 기존 저장 이력을 로드하도록 수리했다.
- 가장 마지막 실제 실패: cold Settings에서 이전 대화를 한 번 클릭해도 ChatPage 마운트가 최신 캐시를 다시 로드해 선택을 취소했다. Sidebar가 선택한 세션을 기존 saveToStorage로 저장한 뒤 navigate하도록 두 파일의 최소 수정으로 수리했다. 실제 Sidebar→ChatPage 마운트 테스트 RED1실패13통과 → GREEN26통과; 전체1001통과. 스토어/API/인증 코드는 작업 시작 해시 그대로다.
- 팝업 헤더를 가린 스태킹 컨텍스트, 첫 진입 불투명도, 도움말 초기/순환 포커스를 CSS와 기존 모달 생명주기로 수리했다. 최종 Settings 실제 helper 클래스에도 keep-all을 적용했고 compact 제목·복사·도구·모델·닫기·footer 크기를36px로 보완했다.

## 최종 직접 관찰

- 17경로×375/768/1280의51원본,27상태,3Settings helper 원본 총81JPEG. 모든46소스 편집 후 생성됐고 서명/요청폭/실제이미지크기 일치, documentWidth=viewport, 가로 넘침0. Git은 실제 Staged Changes를 기다렸다. 768 Code/Changes는 전환이 끝난 뒤 재촬영했고 Changes opacity1/선택탭을 기록했다.
- qwen3.8:latest27.3B에서 도구 없는 알려진 인사 요청이 정상 완료됐다. 생성중 상태→실제 인사 응답, 실제 ShiftEnter 줄바꿈, 응답 복사 버튼 상태와 복사된 Markdown의 인사문 포함을 확인했다. 렌더링 텍스트와 rawMarkdown 전체 바이트 일치를 주장하지 않는다. 503·승인요청이 표시되지 않았고 승인 버튼을 누르지 않았다.
- cold Studio/Wiki/Settings 각각 이전 제목을 정확히 한 번 클릭한 뒤 이전 제목·질문·응답으로 이동함을 확인했다. 그 시점6저장기록, 마지막 정상 대화 후7. 이후 세 페이지를 새로고침해7기록을 확인했다. 기존 원본과 검증기록을 삭제하지 않았으며 UI 작업 동안 만든 synthetic기록은6개다.
- 375/768 이력·검사 actual X/Escape, 닫기 중심 히트 테스트, 한글 미전송 초안·opener포커스·inert해제를 확인했다. 팔레트/도움말 handoff는 하나의 전면 모달, opacity1/entryanimationnone, 도움말 initial close 및 실제 양방향 Tab 포함을 관찰했다.
- 별도768 팔레트 초기 순간 초점이 이전 입력에 남은 관찰과 nullaria 관찰은 삭제하지 않았다. 안정된 다음 상태에서 검색어 입력 INPUT/combobox → 실제 ShiftTab 마지막 Plugin option BUTTON → 실제 Tab 검색어 입력, 모두 withinPalette=true를 확인했다. 한글 임시초안 보존/Escape복귀 후 내가 작성한 초안만 비웠다.
- compact375/768에서 실제 보이는 main16개(탐색 opener포함)+inspection닫기+navfooter 총18개씩 모두 폭·높이>=36px. Settings의 보여줍니다 다섯 글자가375/768/1280 모두 같은 줄이며 실제 helper 픽셀 원본이 있다.
- 1280 검사 도킹3탭, 출력 탭과 상태 상세를 실제 열고 닫았다. 시스템/한글 서체, UI14px, 대화16px/27.2px, composer16px/25.6px, sidebar248px/content760px을 computed style로 기록했다.
- 전체103파일1001테스트, typecheck/build exit0. 원본 로그와 RED/GREEN, SOURCE/BUNDLE/CAPTURE/VERIFICATION/직접관찰 JSON에 연결된다.

## 한계와 정리

네이티브 OS IME, composing/key229, 권한503의 read-only·오류표시, API typedCAS409/integrity/migration503, 늦은 복원 경쟁은 자동 테스트 범위다. 실패 전송 뒤 초안 보존이나 실제 장애주입 전부 통과를 주장하지 않는다. 기존 Skills/Metrics401은 bounded오류 화면으로 확인했고 서버 성공은 제외했다. ReactDoctor는 기존 무시된 비배포 fixture로exit1; 독립 배포 보안 검토는PASS다. Monaco/Mermaid의 기존 큰 청크 경고가 남고 전체axe/Lighthouse/nativeElectron/Codex픽셀 일치는 미검증이다.

PIN/토큰/숨긴 저장소를 읽거나 전달하지 않았다. debug포트·임시로깅·권한변경·대화삭제를 만들지 않았다. 루트 임시debugjournal은 앞선 감사에 정리해 제거했고 다시 생성하지 않았다. 최종 viewport.reset으로 원래757×954를 복원했다. 실제 가시 모달0/출력패널닫힘/빈초안 상태를 DELIVERABLE에 기록하고 사용자 탭을 유지했다. 비교는757원본을RGBPNG로 변환만 한 것으로, 과거 blackpadded768은 제외됐다. 독립 시각/QA 판정은 별도 보고서이며 이 감사가 이를 대신하지 않는다.
