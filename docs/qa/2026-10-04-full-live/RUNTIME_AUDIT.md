---
title: Root 전 기능 검증 실행 감사와 정리
date: 2026-10-04
tags: [qa, runtime, cleanup, evidence]
full_head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
manifest_sha256: c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5
verdict: PARTIAL_BLOCKED
---

실제로 실행한 범위의 검증은 통과했다. 마지막 제품 화면·동일 검색 질문의
재검증과 전체 27 기능군의 운영 인수는 **미완료**다. 저장된 사이트 권한의
차단을 우회하거나 미관찰 답변을 사용자 저장소에서 대신 읽지 않았다.

## 실행 증거

| 실행 | 관찰 결과 | 경계 |
| --- | --- | --- |
| Root production HTTP/curl | 118/118 PASS | 실제 loopback socket·인증·임시 저장소; 외부 검색·음성 포트는 합성 fixture |
| Root CLI | 9/9 PASS | 실제 CLI의 print-only 경로·임시 저장소; 외부 클라이언트/터널 실행 제외 |
| Root backend 회귀 | 283 passed | 명시한 수정 경계의 격리 시험; 기존 Starlette 경고 1개 |
| Root UI 회귀 | 16 files / 133 passed | UI 회귀 시험; 실제 화면 검증을 대체하지 않음 |
| dashboard build | PASS | 최신 bundle 생성; 기존 large-chunk 경고 유지 |
| 실제 Ollama catalog 조회 | running 1 / installed 5 | 읽기 전용 상태 확인; 모델 load/unload 없음 |
| 동일 R2-05/R2-06 질문 | PASS | 파일 읽기 1회 후 정확한 5필드·숫자 9; 실제 모델 답변 |
| R2-12 중간 live 재시도 | 검색 실행 PASS, 표·링크 FAIL | web_search call/result 1개; 마지막 링크 수정 후 재시도는 차단 |
| R2-16 실제 모델 질문 | PASS | 목적 JSON 단일 객체; 검색·도구 없는 응답 |
| R2-17 | UNOBSERVED | 질문 제출 뒤 브라우저 차단; 답변을 확인하지 못함 |

현재 소스와 harness/design 69개 항목을 다시 해시 확인하여 mismatch 0을
[runtime-audit-receipt.json](runtime-audit-receipt.json)에 기록했다.
개수와 내용은 [QUESTIONS.md](QUESTIONS.md)·[CHECKLIST.md](CHECKLIST.md),
[root-api-118.json](root-api-118.json)·[root-cli-final.jsonl](root-cli-final.jsonl),
[root-final-regression.log](root-final-regression.log)·[root-final-ui-tests.log](root-final-ui-tests.log),
[dashboard-final-build.log](dashboard-final-build.log)·[root-model-status.json](root-model-status.json)에 결속한다.
서로 겹치는 회귀/독립 검토 수치는 합산하지 않는다.

## 실행 격리와 정리

합성 fixture는 project import 전에 Path.home·expanduser·cwd·AGK 경로를
전용 임시 저장소로 고정했다. HOME/CODEX_HOME 환경값을 다른 경로로 덮어쓰지
않았다. Header 파일은 curl의 파일 입력으로만 사용했고 내용을 출력하지 않았다.
사용자 vault·메모리·설정·모델 파일을 검증 자료로 읽거나 삭제하지 않았다.

본 서버는 최신 코드로 재시작한 PID **25430**을 유지한다. 안전한 startup
표시와 마지막 process 조회로 실행 상태를 확인했다. 브라우저 접근 차단 후
본 서버의 readiness·마지막 답변을 별도 HTTP/CDP 경로로 재확인하지 않았다.
재시작 후 access mode는 화면에서 READ_ONLY로 다시 확인해야 한다.

Owned 합성 UI 서버의 실제 명령과 PID **30256**을 확인한 뒤 그 PID만 TERM으로
종료했다. 이어 process 조회에서 PID25430만 남았고, fixture 임시 root와
request-header가 모두 없어졌음을 확인했다. Owned QA tab4는 닫았고 원래 사용자
탭은 닫지 않았다. 다른 프로세스·공유 변경·사용자 자료를 정리 대상으로 삼지 않았다.
이 회차 root 소유의 임시 .debug-journal.md는
[DEBUG_JOURNAL_ARCHIVE.md](DEBUG_JOURNAL_ARCHIVE.md)에 원문을 보존하고 archive 본문
byte 일치를 확인한 뒤 제거했다. 이 디렉터리의 manifest-owned QA helper bytecode도
소유 범위만 정리했다.

## 미완료 인수

최종 citation/table 패치는 코드·회귀 검증을 통과하고 PID25430에 활성화됐지만,
같은 R2-12 질문의 공식 링크가 최신 제품 화면에 실제로 표시되는지 미검증이다.
Model UI, terminal, attachment·실제 snapshot·clipboard payload의 남은 시나리오,
누락된 responsive 6 frame과 palette/modal은 새 화면 증거가 필요하다.
하드웨어·실제 training·STT/TTS·외부 자격증명·다른 플랫폼의 운영 증거도 별도다.

독립 검토 4 PASS·context FAIL을 보존하여 aggregate는 **FAILED**다.
두 visual lane도 **REVISE / NEEDS EVIDENCE**를 유지한다. 이 실행 감사의
PARTIAL_BLOCKED를 전체 gate PASS나 모든 기능 완료로 해석하지 않는다.
