---
title: SSAK-AI 전체 기능 실사용 검증 최종 증거 요약
date: 2026-10-04
tags: [qa, live-manual, final-results, evidence, limitations]
status: incomplete-live-acceptance
aggregate_review: FAILED
full_head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
final_source_manifest_sha256: c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5
---

**전체 실사용 검증은 미완료이며, 종합 리뷰 판정은 FAILED다.** 실행한 격리 HTTP·CLI와 집중 회귀 검사는 통과했고 현재 수정 범위에서 코드 CRITICAL/MAJOR 또는 보안 CRITICAL/HIGH blocker는 보고되지 않았다. 그러나 마지막 R2-12 실제 화면 재검증, R2-17 응답 관찰, Model UI 및 나머지 기능·화면 증거가 남아 있다. 27개 기능군 전체의 운영 PASS를 선언하지 않는다. 근거는 [체크리스트](CHECKLIST.md), [질문 기록](QUESTIONS.md), [리뷰 요약](REVIEW_SUMMARY.md)이다.

기준 HEAD는 `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, [최종 소스 manifest](final-source-manifest.json)의 SHA256은 `c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5`이다. manifest가 이번 수정의 소스·테스트 56개, harness 12개 및 디자인 계약을 고정한다. 독립 리뷰가 해당 69개 항목의 해시 일치를 확인했다. 공유 작업 폴더의 다른 미커밋 변경은 이 판정에 포함하지 않는다. 이 문서는 기존 실행·리뷰 기록을 취합했으며 새 실행이나 재검사를 수행하지 않았다.

| 현재 실행 증거 | 결과 | 입증하는 범위 |
| --- | --- | --- |
| Root [HTTP JSON](root-api-118.json)·[종료 기록](root-api-118.jsonl) | **118/118 PASS** | 실제 loopback production route·인증·임시 저장소. 검색 producer·transcriber·unavailable model port는 명시된 합성 경계이며 startup lifespan은 OFF |
| Root [CLI 기록](root-cli-final.jsonl) | **9/9 PASS** | 임시 설정·저장소의 실제 child CLI 출력. bridge는 합성 URL의 실행하지 않는 연결 계획 |
| Root [backend 회귀](root-final-regression.log) | **283 passed** | 고정 소스의 집중 12-suite 회귀. third-party deprecation warning 1개 |
| Root [UI 회귀](root-final-ui-tests.log) | **133 passed / 16 files** | 집중 dashboard 시험. 실제 브라우저의 전체 상호작용 통과와 구분 |
| [최종 dashboard 빌드](dashboard-final-build.log) | **PASS** | Vite build 성공. large-chunk warning 존재 |
| [독립 QA 리뷰](final-qa-review.md) | **PASS, 실행 범위 한정** | 별도로 재현한 HTTP118·CLI9·backend283 및 소스/harness 해시·cleanup 확인 |
| Root [실제 model 상태](root-model-status.json) | **running 1 / installed 5** | readonly Ollama catalog/process 조회. 새 load·모든 모델 generation 증거가 아님 |

HTTP와 CLI의 임시 서버·인증 header·저장소 cleanup은 영수증에 기록되어 있다. 실제 사용자 vault·memory·auth·raw log를 대상으로 한 검증이 아니다. 과거 HTTP114/CLI8, citation 회귀243, 현재 backend283/UI133, 질문·UI·독립 재현은 서로 범위가 겹친다. 이를 합산한 기능 통과 수를 만들지 않는다. [증거 원장](EVIDENCE_LEDGER.md)과 [API 실행 경계](API_SCENARIOS.md)에 세부 범위가 있다.

| 수정 및 관찰 | 현재 증거와 한계 |
| --- | --- |
| 코어 읽기 예산·간결한 출력 | [R2-05/R2-06](QUESTIONS.md)은 동일 실제 질문 재검증에서 파일 읽기 1회 후 필수 5개 필드, 숫자 `9` 단독 응답으로 PASS. 성공 R2-05의 정확한 전체 live token ledger는 없음 |
| 필수 검색·출처·표 | [R2-12 retry 영수증](root-live-search-retry.json)은 실제 `web_search` 1회와 non-error 결과를 입증. 최종 출력은 두 bullet pipe 행이고 href가 없어 **표·clickable citation FAIL**. 전체 공식 URL provenance는 미확보. [최신 수정](citation-source-links-report.md)의 controlled production stream·회귀는 통과했지만 실제 화면 최종 재검증은 없음 |
| Wiki·인증·입력 검증 | [체크리스트](CHECKLIST.md)의 격리 실제 Wiki read/search/create/edit/save, YAML frontmatter·Git autocommit과 [코드 리뷰](final-code-review.md)의 authenticated Skills/Publish/extraction·palette stale-race·typed conversation validation 증거. 개인 vault와 모든 production UI 상태의 통과를 뜻하지 않음 |
| 정확한 상태·숫자 표시 | [체크리스트](CHECKLIST.md)의 큰 정수·단위 extraction, Studio telemetry 없음·disabled export, job run0의 `—`/`No completed runs`, Start URL/copy toast, approval deny·plugin toast 관찰. copy toast는 실제 clipboard 내용 증거가 아님 |

마지막 citation/table 수정은 [질문 기록](QUESTIONS.md)에 실행 서버 PID25430 활성화로 기록되어 있다. 활성화만으로 실제 사용자 화면의 성공을 확정하지 않는다. 저장된 localhost browser permission 때문에 최종 R2-12, R2-17 결과와 수정 후 Model UI·남은 UI 재검증이 차단되었다. 채팅의 허용 응답이 그 저장 설정을 해제하지 않았으며 우회하지 않았다.

남은 완료 조건은 다음과 같다.

- [R2-12](QUESTIONS.md)의 동일 질문에서 실제 검색 receipt, 두 행 표, 확인된 공식 URL의 클릭 가능한 링크를 수정 후 UI에서 확인하고 R2-17의 `9.5` 응답과 Model UI를 관찰한다.
- [27개 기능군](CHECKLIST.md)은 현재 모두 `partial` 또는 `unavailable`이다. attachment 수락, terminal/native 취소, 실제 history snapshot, Git UI 동작, task dispatch/reconnect, scheduler delivery 등 미실행 동작을 해당 실행 경계에서 검증한다. 화면 방문·empty/error/disabled 상태를 전체 기능 PASS로 바꾸지 않는다.
- 두 [visual 리뷰](final-visual-pixel-review.md)는 **REVISE — NEEDS EVIDENCE**다. 유효 frame은 21개 route/width 조합 중 15개이며 Models 375/768/1280, Wiki 375/768, Skills1280의 6개와 Wiki/palette/modal 상호작용 상태가 없다. 실제375×900인 [1280 mismatch 캡처](root-ui-skills-capture-mismatch-1280.jpg)는 실패 증거로 보존하며 제외한다. source/build·capture 시각·전체 기대 상태를 결속한 캡처 증거도 보완한다. [source visual 리뷰](final-visual-source-review.md), [캡처 metadata](visual-capture-metadata.json) 참조.
- 실제 STT/TTS·training·embedding·새 model load·OAuth/account·remote relay·publish·native signing/update/install·다른 플랫폼은 hardware/external 미검증으로 유지한다. 지원 범위는 QA 숫자로 확대하지 않는다.
