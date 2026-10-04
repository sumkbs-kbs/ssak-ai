---
title: oh-my-jev 적용 최종 인수 체크리스트
date: 2026-10-03
completed: 2026-10-04
tags: [qa, acceptance, checklist]
---

## 이번 반영 인수

- [x] 외부 소스 full SHA를 고정하고 실제 clone·그래프·코드·시험을 읽음
- [x] gateway/backend·평가/보정·현재 SSAK 경로를 분리 조사함
- [x] Apache-2.0 코드와 데이터·모델 조건을 구분하고 외부 assets를 복제하지 않음
- [x] 현재 HEAD·공유 수정 기준을 보존하고 적용/제외 이유를 분석 문서에 기록함
- [x] 외부의 분모 불일치와 confidence 동률 순서 의존을 보완함
- [x] typed 불변 prediction/error 입력과 report를 구현함
- [x] 유한 숫자·범위·일대일 길이·고유/비어 있지 않은 key와 case_id 검사
- [x] 요청1,000사례·선택지64개·key128문자·CLI2MiB 경계 검사
- [x] strict/lenient 합계 허용 오차를 분리하고 invalid를 normalize하지 않음
- [x] 정확도·ECE·Brier·NLL의 공통 scored 분모와 null 빈 결과 확인
- [x] ECE15구간의 confidence1 포함, multiclass Brier, NLL floor 수계산 확인
- [x] argmax 동률과 동일 confidence coverage의 입력 순서 불변성 확인
- [x] 정보 부족·정답 없음·선택지 밖 정답·실행 오류를 별도 집계함
- [x] 출처 provided_probabilities·상태 unverified·입력 SHA256과 ID 근거 기록
- [x] 기존 root CLI와 생산 API router에 연결하고 OpenAPI에서 발견 가능함
- [x] 기존 인증과 정책을 보존하고 실제 인증 없음401을 확인함
- [x] CLI 오류2·API generic422의 내용 비노출과 OpenAPI 오류 형식 일치 확인
- [x] 새 기능71개와 관련 기존89개, 총160개 회귀 통과
- [x] Ruff 통과·새 파일 무필터 타입0오류0경고·변경8파일 LSP error 없음
- [x] Root가 실제 CLI의 help/성공/실패와 실제 HTTP5시나리오를 실행함
- [x] 최종 full HEAD·파일 manifest에 바인딩된 독립 검토2개 CLEAR
- [x] 실제8000서버 재시작·health200·typed route등록·인증401 확인
- [x] 임시 홈·subprocess 홈·캐시 격리와 합성 인증 파일 제거 확인
- [x] 분석·구현 계약·사용법·결과·증거 원장을 연결하고 단계 계획 완료

최종 근거는 [RESULTS.md](RESULTS.md), 소스 바인딩은 [source.sha256](source.sha256),
검토 판정은 [EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md)에서 확인한다.

## 이번 범위 밖의 후속 조건

실제 모델의 선택지별 확률/로짓 제공, 독립 holdout·fit/eval provenance, 온도 보정,
한/영 및 선택지 순서 benchmark, 모델 학습·승격 적용은 이번 완료 항목에 포함되지
않는다. 후속 구현 시 기존 기본 방침을 유지하고 결과가 실제로 보정되었다는 별도
증거를 확보해야 한다. 현재 결과를 모델 정확도 개선이나 승인 보장으로 주장하지 않는다.
