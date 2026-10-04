---
title: 외부 기능 강화 검토·실행 증거 원장
date: 2026-10-03
tags: [qa, evidence-ledger, external-feature-upgrade]
---

# 판정과 소스 바인딩

모든 아래 판정의 full Git HEAD는 `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`다.
공유 작업 폴더에는 커밋되지 않은 기존 수정이 있으므로 HEAD만으로 변경을 식별하지
않는다. 각 보고서에 기록된 실제 파일 SHA-256과 최종 [source.sha256](source.sha256)을
함께 비교한다. 같은 HEAD여도 파일 해시가 바뀌면 해당 범위의 판정은 재사용하지 않는다.

| 검토/실행 | 판정 | 적용 범위 | 근거와 보고서 SHA-256 |
| --- | --- | --- | --- |
| 독립 task/finance 코드 검토 | CLEAR / APPROVE | 보고서에 명시된 7개 파일. 현재 parser `5289fe93...`와 일치 | [task-finance-review.md](task-finance-review.md), `e538c6bb1f82880eb7b8b8db0bec98edbf9777f68098e1ff946b4db09757b9fa` |
| 독립 memory/voice 코드 검토 | CLEAR / APPROVE | 보고서에 명시된 7개 파일. 최종 회상 길이·IEEE float/개별 frame 경계 포함 | [memory-voice-review.md](memory-voice-review.md), `c94417bf719aa410a4b415d48a02a0d79452193f9ceabd4f049558815348636f` |
| Root 네 기능 직접 실행 | PASS | 실제 라이브러리 + loopback HTTP의 변경 경로. 검색/STT 외부 포트만 합성 입력으로 대체 | [root-library-qa.log](root-library-qa.log), `root-http-*.txt`; 최종 범위는 [RESULTS.md](RESULTS.md)에 기록 |
| Root 최초 통합 회귀 | PASS, 357 cases | chat-routing 수정 전 15개 파일 후보 `446223001a21bbb623530029510796a7cfe83a4691656315bb56715cd0d9cce0` | [root-regression.log](root-regression.log). 이후 최종 합본 회귀와 구분 |
| 자기보고 분류 최초 독립 검토 | BLOCK / REQUEST_CHANGES, 재수정 대상 | `84e9fadd...` / `b0c479ff...`: 일반 요청은 개선했으나 명시적 도구 사용 질문 분류가 누락됨 | [chat-routing-review-before-retake.md](chat-routing-review-before-retake.md), `fea1e416b023b29564c10cd86ab1f6be18e3ad3d68cfcfa83fa33ac7e7fa028a` |
| 자기보고 분류 최종 독립 검토 | CLEAR / APPROVE | `7e6428f6...` / `9dce35c9...`: 명시적 자기 질문 보존 및 일반 기능 작업 provider dispatch | [chat-routing-review.md](chat-routing-review.md), `637e0bd38f7c9bed27e02648a3360f8e694b5bc50279114f4a4a6b017404e850` |
| Root 최종 합본 회귀·정적 검사 | PASS, 361 cases | 최종 17개 파일 manifest `1fa855b80aaa27b7fbf7464f513cb02a6f8994a4146eea0e6563bc5bb76b8d13`; 오류 gate 통과 | [root-final-regression.log](root-final-regression.log), [root-final-ruff.log](root-final-ruff.log), [root-final-types.log](root-final-types.log), [root-final-lsp.md](root-final-lsp.md) |
| Root runtime debugging audit·실제 대화 | PASS for observed scenario | 같은 최종 후보와 full HEAD, PID 32914, 기존 qwen3.8 27.3B, 원문 동일 질문의 정확한 응답 | [chat-routing-runtime-audit.md](chat-routing-runtime-audit.md), `82c1b493b331af54d41e5a901f39c861737d545cdc8b915efa2729f89de81f33`; [chat-routing-after.txt](chat-routing-after.txt), [chat-routing-after.png](chat-routing-after.png). 실제 token 수는 노출되지 않아 미계측 |

자기 능력 분류 후속 수정은 위 네 기능 코드의 해시를 바꾸지 않는다. 이전 BLOCK/WATCH, 이전 Decimal
정밀도 후보 및 초기 음성 import 실패는 감사 이력이며 최종 통과 근거로 재사용하지 않는다.
