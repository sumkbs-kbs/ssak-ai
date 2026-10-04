---
title: oh-my-jev follow-up implementation and verification result
date: 2026-10-04
tags: [qa, decision, benchmark, uncertainty, checklist]
status: complete
head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
source_manifest_sha256: 47e26236e414be601803feba31d052835aa9d1f332c1711846ce951585698132
---

## 구현 결과

기존 SSAK-AI 확률 평가기에 두 기능을 추가했다. upstream의 현재 커밋은 이전
분석과 동일한 `c03c182013b64223a9b3a15095e85ef17c002b56`이다. 따라서
이미 반영된 정확도/ECE/Brier/NLL 기능을 재구현하지 않고 해석과 진단을 보완했다.
SHA로 고정한 원본 근거와 도입/보류 판단은 RESEARCH.md에 정리했다.

- 정확도에 Wilson 95% 구간과 채점 표본 수/정답 수를 함께 반환한다. 오류,
  잘못된 확률 합, 무라벨, 선택지에 없는 정답은 채점 분모에서 제외한다.
  채점 가능한 사례가 없으면 구간은 null이다.
- 예측/오류 사례의 선택적인 태그로 동일한 집계 규칙을 적용한 세부 결과를
  반환한다. 사례당 최대16개의 중복 없는 태그와 최대25개의 출력 그룹을
  허용한다. 그룹은 전체 사례 수 내림차순, 태그 이름순으로 정렬하고 생략
  수를 표시한다. 작은 표본과 전체 공통 태그도 표시한다.
- 전체/그룹이 같은 계산 함수를 사용하므로 기존 제외 기준과 동률 정책이
  유지된다. 빈/생략 태그는 기존 입력 fingerprint를 유지한다. 이전 보고서는
  새 reader에서 기본값으로 파싱된다.

변경한 코드는 engine 모델/계산기2파일, 신규 시험2파일, 기존 fingerprint
시험의 기대 직렬화1부분이다. API·CLI production 코드의 변경 전후 해시는
같으며 기존 명령과 경로에 새 typed 결과가 연결된다. 외부 코드/시험/데이터/
모델을 복사하거나 dependency를 설치하지 않았다. 사용자 vault·PIN·인증·
모델 선택·Constitution·Brain/Body·도구 승인·승격 정책은 변경하지 않았다.
Git mutation 없이 기존 공유 변경을 보존했다.

## 직접 사용과 최종 검증

Root는 기존 격리 launcher로 실제 등록된 Typer 명령을 새 프로세스에서 실행했다.
launcher는 프로젝트 import 전에 임시 home/설정/인증/저장 경로를 적용한다.
모델/provider를 호출하지 않고 synthetic JSON만 사용했다.

| 직접 CLI 사용 | 관측 |
| --- | --- |
| 정상6사례 | exit0, stdout의 JSON을 독립 기대값과 비교 |
| 중복 태그 | exit2, stdout 없음, 입력/태그를 노출하지 않는 안전한 stderr |
| `decision-eval --help` | exit0, 기존 명령/입력 도움말 표시 |
| 채점 표본/정답/정확도 | 2 / 1 / 0.5 |
| Wilson 95% 구간 | 0.09452865480086614 ~ 0.9054713451991339 |
| ECE/Brier/NLL | 0.45 / 0.6500000000000001 / 0.8573992140459633 |
| 선택된 표본/coverage | 1 / 0.5 |
| 태그 순서 | en, ko, routing, ambiguous |
| 그룹 멤버십 합계/전체 | 9 / 6; 겹치는 보기이므로 독립 표본9건으로 해석하지 않음 |

초기 Root 수동 oracle는 routing 그룹과 전체의 모든 metrics가 같아야 한다고
잘못 가정했다. 유효률/오류율의 그룹 분모가 다르므로 이 assertion은 실패했다.
동일한 채점 집합의 accuracy/ECE/Brier/NLL/구간만 같고, 그룹별 유효률/오류율은
각자의 분모를 쓰도록 독립 기대값을 정정해 직접 사용3경로를 다시 확인했다.
production 계산 결함이 아니며 이 과정은 manual-receipt.json에도 기록했다.

최종 source-manifest의8파일 기준으로 다음이 통과했다:

| 검사 | 결과 | 증거 |
| --- | --- | --- |
| 기존+신규 평가/API/CLI 회귀 | 137 passed, 12 existing warnings | root-pytest.txt |
| 무필터 basedpyright, 변경5파일 | 0 errors / 0 warnings / 0 notes | root-typing.txt |
| 프로젝트 설정 Ruff | All checks passed | root-ruff.txt |
| programming 규칙, 변경5파일 | no violations | root-programming.txt |
| 실제 CLI 정상/오류/help | PASS; exit0/2/0 | manual-receipt.json와 manual-*-stdout/stderr.txt |
| 독립 통계 검토 | PASS | statistical-review.md, REVIEW_LEDGER.md |
| 독립 호환성/API/CLI 검토 | PASS | compatibility-review.md, REVIEW_LEDGER.md |

137시험은 기존71개와 신규66개(계산기37/표면29)를 포함한다. 기존 warnings는
Starlette/httpx deprecation과 다른 등록 route들의 OpenAPI operation ID 중복이다.
이번 benchmark route의 실패가 아니며 관련 없는 모듈을 수정하지 않았다.
표면 시험 helper의 타입 경고1건은 exhaustive wildcard+assert_never로 해결했고,
최종 무필터 타입 검사와 규칙 검사 모두 경고/위반 없이 통과했다.

독립 통계 검토는 Decimal로 score equation을 풀어29개 구간을 비교했으며 최대
차이는2.22e-16이었다. 가능한 표본쌍501500개에서도 구간 범위와 관측 비율
포함이 확인되었다. 독립 호환성 driver는 prediction/error/mixed의 빈 태그
fingerprint를 포함한11개 사실을 확인했다. 검토 전후8파일 해시는 일치했다.

작업 코드의 pure LOC는 모델113, 계산기232, 신규 계산 시험190, 신규 표면
시험217, 기존 평가 시험248이다. 계산기/표면/기존 시험은200~250 경고 구간에
있으므로 향후 기능을 더 추가할 때는 책임별 분리를 먼저 검토한다. 모델은
typed boundary, 계산기는 decision 요약, 각 시험은 해당 behavioral contract를
담당한다. 공통 summary를 재사용하며 variant는 exhaustive match로 처리한다.

## 실행 프로그램과 검증 한계

변경 반영을 위해 이전 task-owned server PID58771의 명령 identity를 확인한
후 정상 종료 신호를 보내고 현재 checkout의 `.venv/bin/agk serve --host
127.0.0.1 --port 8000`을 재실행했다. 새 session60054, PID79178의
`127.0.0.1:8000 LISTEN`을 OS 수준에서 확인했다. 이것은 재실행/포트 관측이며
live HTTP/API 또는 화면을 확인했다는 증거가 아니다.

API 시험은 실제 등록 route/auth middleware를 쓰는 격리 in-memory TestClient이며,
startup lifespan은 꺼져 있다. 저장된 브라우저 접근 차단은 우회하지 않았다.
화면/대화/전체 subsystem startup/실제 Qwen 정확도나 모델 보정은 이번에
검증하지 않았다. 전체 프로그램 gate나 이전 전체 QA의 해결로 보고하지 않는다.

제공된 확률의 보정 상태는 계속 unverified이다. Wilson 구간은 표본 독립성이나
미래 성능을 인증하지 않으며 ECE/Brier/NLL 또는 선택된 empirical risk에 적용하지
않는다. 겹치는 태그의 다중 비교 보정도 없다. 구간을 승인/승격 근거로 쓰지 않는다.
새 reader의 과거 report parsing은 확인했지만, 추가 필드를 거부하는 외부의
옛 strict reader까지 새 report와 호환된다는 보장은 하지 않는다. runtime 시험은
Python3.13.12/Pydantic2.13.4이며 최소 지원 버전 runtime은 별도 설치하지 않았다.

## 인수 체크리스트

- [x] upstream 최신 SHA·기존 적용 범위·license/source 경계 확인
- [x] 기존 기본 방침을 유지하는 명시적 typed 구현 계약 작성
- [x] 올바른 이유의 red 후 Wilson/태그 공통 집계 구현
- [x] 입력 한도·안전한 오류·인증·OpenAPI·기존 fingerprint 회귀 확인
- [x] Root 직접 CLI 정상·오류·help 실행과 독립 기대값 확인
- [x] 최종137시험·무필터 타입·프로젝트 lint·규칙 검사 통과
- [x] frozen HEAD+내용 해시로 독립 검토2건과 증거 ledger 결속
- [x] 현재 코드로 서버 재실행, OS listener 확인
- [x] 사용법·해석 한계·scope·실행 계획 상태 확정

사용법은 USAGE.md, 재현 명령/출력은 root-quality-receipt.json와 수동 실행
artifacts에 있다. 이후 agent는 source-manifest와 ledger를 읽고 실제 파일
해시가 일치하는지 확인한 후 해당 범위의 증거만 재사용해야 한다.
