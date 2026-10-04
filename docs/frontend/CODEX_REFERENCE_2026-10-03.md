---
title: Codex UI 참고 근거와 SSAK-AI 적용 사항
tags: [frontend, codex, reference, design-system]
date: 2026-10-03
---

# 참고 근거

공개 [openai/codex](https://github.com/openai/codex)는 CLI/Rust TUI·app-server 소스이며 Codex Desktop의 React/CSS 원본 저장소가 아니다. 조사 시점 main 커밋 `604061ce51d194a3aa6aad3b3170240d096e1725`를 기준으로 아래 구조를 참고했다. Rust 코드를 복사하지 않고 기존 SSAK-AI 화면과 계약에 맞춰 독립 구현한다.

| 공개 소스에서 확인한 패턴 | SSAK-AI 적용 |
|---|---|
| [확정된 대화 기록과 현재 스트리밍 표시의 분리](https://github.com/openai/codex/blob/604061ce51d194a3aa6aad3b3170240d096e1725/codex-rs/tui/src/chatwidget.rs#L1-L17) | 기존 서버 리비전·스트리밍 계약을 유지하고, 본문 스크롤과 입력창을 분리 |
| [작업 상태와 중복 표시 억제](https://github.com/openai/codex/blob/604061ce51d194a3aa6aad3b3170240d096e1725/codex-rs/tui/src/chatwidget.rs#L19-L28) | 대화가 우선인 화면, 실제 상태만 보여 주는 간결한 헤더와 상세 펼침 |
| [경과 시간·중단·상태를 짧게 제공](https://github.com/openai/codex/blob/604061ce51d194a3aa6aad3b3170240d096e1725/codex-rs/tui/src/status_indicator_widget.rs#L1-L7) | 기존 생성 상태·중지 기능을 유지하며 작은 상태 줄 제공 |
| [키보드로 대화·활동·큐 접근](https://github.com/openai/codex/blob/604061ce51d194a3aa6aad3b3170240d096e1725/codex-rs/config/src/tui_keymap.rs#L140-L187) | Cmd/Ctrl+K, 이름 있는 탐색, Enter/Shift+Enter/IME 경계와 패널 Escape |

공식 [Codex 앱 소개](https://openai.com/index/introducing-the-codex-app/)에서 프로젝트별 대화와 작업 검토를 중심으로 하는 제품 구성을 확인했다. SSAK-AI의 프로젝트·대화·실행 상세를 이 우선순위에 맞춘다. Git 화면을 실제 없는 PR 기능으로 표시하거나 실행 이력을 예약 기능으로 표시하지 않는다.

# 서체와 화면 구성

설치된 OpenAI 앱의 자원을 읽기 전용으로 조사해 공유 OpenAI Sans Regular/Medium/Semibold 자산과 시스템 sans-serif 폴백이 존재함을 확인했다. Desktop 전용 전체 테마/사이드바 수치는 검증되지 않아 정확한 원본 값으로 표기하지 않는다. 독점 자산을 추출·복제하지 않는다.

SSAK-AI 구현 기준은 `dashboard/DESIGN.md`에 정의했다. 시스템 sans-serif와 한글 폴백, 14px UI·16px 대화·1.7 본문 행간, 248px 기본 탐색 폭, 760px 본문/입력창 폭, 중립 회색 표면을 사용한다. 이는 사용자 요청에 맞춘 적응형 설계 값이며 Codex 원본의 측정값이라고 주장하지 않는다. 작은 화면에서는 이름 있는 탐색과 보조 패널을 닫을 수 있는 모달로 제공한다.

# 유지할 계약

PIN 인증, 프로젝트 ID/epoch, 서버 대화 리비전/CAS, 모델 선택 영속화, Markdown 정제, 실제 텔레메트리의 UNKNOWN/0/stale/offline 의미는 그대로 유지한다. 참고 앱의 브랜드·로고·독점 코드·폰트 파일을 가져오지 않는다.
