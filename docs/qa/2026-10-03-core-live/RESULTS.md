---
title: 실제 질문·답변 기반 코어 개선 검증 결과
date: 2026-10-03
tags: [core, live-qa, regression, evidence]
---

# 범위와 최종 후보

주 에이전트가 실행 중인 SSAK-AI 웹 대화에 직접 질문하고 실제 답변을 검토한 첫 검증·개선 회차다. 다른 에이전트는 원인 조사, 경계 수정, 회귀 및 독립 검토를 맡았다. 질문 원문과 인수 조건은 [QUESTIONS.md](QUESTIONS.md)에 둔다. 이 보고서는 일반 웹 대화에서 확인한 범위의 결과이며, 전체 코어·전 기능 완료 선언이 아니다.

- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- 최종 선택 소스·테스트 41개 파일의 후보 SHA-256: `35ed198037fc59f1458077cbb7ec4986118230642eb36351d2d655b0df912485`. [source-manifest.json](source-manifest.json)은 파일별 실제 해시를 기록한다. 기존 변경을 포함한 공유 작업 폴더이므로 HEAD만으로 검토 대상을 특정하지 않는다.
- 실행 환경: CPython 3.13, `http://127.0.0.1:8000/chat`, `qwen3.8:latest` 27.3B. 마지막 백엔드 수정 적용 서버는 PID75671이며 자동 재로딩 없이 실행했다. 마지막 소스 변경은 입력 안내문 한 줄이며, 새 production build가 같은 서버에서 제공된다.
- 헌법·Brain/Body 책임·인증·모델 선택과 기존 사용자 데이터는 유지했다. 540개 이상의 기존 변경을 되돌리거나 스테이징·커밋하지 않았다. 앱이 생성한 메모리와 실패 시 남은 사용자 턴도 삭제하지 않았다.
- 일반 웹 대화는 AgentRuntime→DirectTaskExecution→Orchestrator/ToolLoop 경로다. 별도 cognitive 전용 경로의 실행 여부와 구분한다. 읽기 전용 CLI 상태는 enabled=false/mode=off/actual_active=false였고, 인증 없는 별도 HTTP 조회는 401이었다. health의 `cov_active`만으로 cognitive 실행을 통과 처리하지 않는다. 전역 ACTIVE 전환은 하지 않았다.

# 실제 질문 결과

PASS는 아래의 실행·출력 경계에 한정한다. 모든 질문을 마지막 41파일 후보에서 다시 실행했다는 뜻은 아니다. 마지막 백엔드 변경 뒤에는 Q13 줄바꿈, Q15 Markdown 및 Q08 실제 오류를 재검증했다. 마지막 입력 안내문 변경 뒤에도 주 에이전트가 같은 Q15를 다시 질문해 최종 답변을 확인했다.

| 질문 | 발견한 문제와 수정 후 실제 관찰 | 판정·범위 |
|---|---|---|
| Q00 지정 문장 | 처음에는 검색 OFF에도 빠른 검색과 진행 문구, literal `\n\n`이 답변에 섞였다. 경계 수정 후 PID65950 재실행에서 `검증 준비 완료`만 출력했다. | 최종 텍스트 PASS. 자연어 금지가 모든 도구를 강제 차단한다는 판정은 아님. |
| Q01 계산/JSON | 다음 턴 409와 이전 질문 재전송, 진행·품질·메모리 문구 혼합이 있었다. PID65950 재실행에서 `{"subtotal":38400,"discount":5760,"total":35140}` 한 객체로 답했다. | 계산·JSON 출력·연속 요청 PASS. |
| Q02 인용 자료 | 최초 실사용 답변은 `6`이었다. | 최초 관찰 PASS, 마지막 후보 재실행은 하지 않음. 전반적인 인젝션 안전성으로 확대하지 않음. |
| Q03 미제공 출시일 | 초기에는 설명을 붙이고 청록이라는 이름을 바꿨다. PID65950 재실행은 `확인 불가`만 출력했다. | 해당 질문의 불확실성·정확한 짧은 출력 PASS. 일반 고유명사·형식 전체 보장은 아님. |
| Q04 정정 다중 턴 | 승인 대기 뒤 후처리가 계속되어 관계없는 프로젝트/예산/날짜를 생성했다. 수정 후 PID24289에서 종달새/600000/2026-10-18/내부 직원 JSON을 답했고, 새로고침 후 정식 이력에도 같은 답변이 남았다. | 문맥·정정·저장 PASS. 마지막 후보에서 새 다중 턴 재실행은 하지 않음. 승인은 누르지 않았다. |
| Q07 프로젝트 문서 | 실제 읽기 뒤 필수 필드 GOAL/CURRENT_STATE/HARD_CONSTRAINTS/CRITICAL_EVIDENCE/MATERIAL_UNKNOWNS를 맞췄지만 닫는 코드 펜스와 설명의 줄바꿈이 잘못됐다. | 읽기·내용 PASS, 해당 실행의 Markdown FAIL. 마지막 수정 뒤 같은 Q07은 재실행하지 않음. |
| Q08 없는 파일 | 처음에는 READ_ONLY/Code OFF 요청을 TDD로 실행했고, guard 수정 뒤에는 QA 자기소개로 질문을 잃었다. 원문·예산·공백 경계 수정 후 PID75671에서 정확한 대상의 실제 `File not found at …` 오류와 확인 가능한 사실만 답했다. 제목·목록·영문 공백도 정상이다. | 실제 읽기 1건·오류 응답 1건·최종 의미와 렌더링 PASS. 기록이 없는 provider 원문까지 입증하지는 않음. |
| Q13 취소 후 새 요청 | PID65950에서 숫자 초안 이후 품질 재작성 중 직접 중지했다. 바로 보낸 새 질문은 `새 요청 정상`만 답했고 409나 이전 스트림 혼입을 관찰하지 않았다. 취소 전 생성된 초안은 저장에 남았다. | 작업 중 취소·새 요청 최종 출력 PASS. 취소된 턴이 항상 user-only라는 주장은 하지 않음. |
| Q13 줄바꿈 재검증 | PID75671에서 같은 숫자 질문을 중지하지 않고 완료했다. 1~300이 순서대로 한 줄에 하나씩 있고 렌더링 줄바꿈은 299개였다. | 공백·줄바꿈 PASS. 완료 후의 이 실행을 새로운 취소 증거로 사용하지 않음. |
| Q14 이력 복원 | 앞선 중단 변형에서는 다음 요청이 server r16과 충돌했다. 접수 revision 전달 수정 후 PID65950에서 확인 응답 완료→새로고침→같은 대화 선택→`QA-HISTORY-20261003-C9` 정확한 출력과 모델 유지가 확인됐다. | 완료 이력 복원·연속 요청 PASS. |
| Q15 Markdown | PID75671 실제 답변에서 `확인한 사실` h3, 두 목록 항목, `첫 줄\n둘째 줄` 코드 블록을 확인했다. 마지막 안내문 수정 뒤 같은 질문의 최종 답변도 일치했다. | 최종 렌더링 계약 PASS. 일시적 초안과 최종 canonical 답변을 구분하며 raw 바이트 동일성은 주장하지 않음. |
| Q09 공식 출처 검색 / Q11 날짜 자료 | 이번 회차에 실제 질문을 실행하지 않았다. | UNTESTED. |

Q04 전용 대화는 `mus8bwvziz9z2dhh`다. 반복된 `확인`을 본문 기반 React key로 처리해 화면 맨 앞에 잔여 답변이 생겼던 문제는 대화·순서로 구분한 key와 실제 DOM 회귀로 수정했다. 새 빌드의 새로고침에서 user부터 시작하는 정식 순서와 중복 제거를 직접 확인했다. 기존 이력은 보존했다.

[final-numeric-lines.json](final-numeric-lines.json)은 300개 숫자, 누락 없음, 순서 일치 및 299개 BR을 기록한다. [final-markdown-dom.json](final-markdown-dom.json)은 마지막 백엔드 수정 뒤 Q15, [final-markdown-dom-after-copy.json](final-markdown-dom-after-copy.json)은 마지막 안내문 수정 뒤 41파일 후보의 실제 heading/list/code DOM을 기록한다. 렌더링 관찰은 미저장 provider 응답의 모든 바이트가 동일했다는 증거와 구분한다.

# 실제 도구 실행 근거와 관측 한계

[tool-receipts.jsonl](tool-receipts.jsonl)은 주 에이전트의 정확한 질문·시각에 결박한 읽기 전용 감사다. direct task 저장소에는 대화 ID 외래키가 없어 정확한 질문과 실행 시각을 사용했다. 단순 `used_tools` 명칭이나 모델의 “읽었다”는 문장만으로 실행 성공을 판정하지 않았다. 사용자 데이터베이스는 읽기 전용으로 열었고 앱 import·store 초기화·사용자 자료 내보내기를 하지 않았다.

- Q07 `direct_260925b26c18`: 2026-10-03 10:25:10.177523~10:26:19.652035 UTC. `read_file` checkpoint의 3726자 결과와 문서 SHA-256 `ee6b0856bcc4e1ef2a61ea066c27ae292870bba157254b7f8cc0c4c547245fa8`, 독립 FileOpened hook를 대조했다.
- Q08 실패 `direct_031cd421738a`: 처음 저장된 사용자 원문은 정확했지만 최종 답변은 QA 자기소개였다. 압축 digest는 선택 component 표현의 해시이며 provider wire 해시가 아니다. input component 7994/skills7888/system104/messages2/tools0이라는 metadata만으로 어느 최종 provider 분기가 원인이었는지 단정하지 않았다.
- Q08 수정 후 `direct_f641d9302c1a`: PID65950, 11:39:42.526941~11:40:17.617747 UTC. 정확한 파일에 대한 기록된 읽기 요청 1건·오류 결과 1건을 ToolPathAudit/FailureDetected와 대조했다. 이 실행은 의미상 성공했지만 초기 화면 공백 문제가 남아 있었다.
- Q08 마지막 백엔드 재검증 `direct_a2eac36a7699`: PID75671, 12:09:08.399495~12:09:46.271070 UTC. 기록된 읽기 요청 1건·오류 결과 1건, 정확한 경로의 독립 hook, post-tool 원문 helper 일치, 정상 최종 제목·목록·영문 공백을 확인했다. 감사 당시 대상 파일과 symlink가 없고 다른 도구·쓰기 기록은 없었다.

마지막 두 Q08의 final compression ledger는 **NOT_RECORDED**, provider wire 본문도 미저장이다. 관측 부재를 압축 미실행 또는 원문 provider 전송 증명으로 해석하지 않는다. 파일 부재와 쓰기 기록 부재는 실행 내내 생성 후 삭제가 절대로 없었다는 증명도 아니다. 예산 보존은 별도의 실제 ToolLoop/provider 호출 seam 회귀로 입증하고, 실사용 감사는 기록된 요청·결과 범위로 한정했다.

# 반영한 앱 경계

1. revision 요청과 명시적인 검색 OFF는 정책·저장소를 우회하던 빠른 검색 경로를 사용하지 않는다. 구형 클라이언트의 검색 tri-state는 유지한다. access mode는 요청 접수 때 snapshot으로 고정해 분류 후에도 같은 정책을 사용한다.
2. ProgressChunk와 FinalChunk를 생산 단계부터 normalizer/DirectTask/HTTP/SSE/React까지 보존한다. 진행 상태는 작업 중 표시에만 전달하고, 검증된 최종 내용은 초안을 교체해 저장한다. 답변 정규식 삭제나 QA 질문별 정답 삽입은 사용하지 않았다.
3. 409 재시도는 실패한 턴의 원문·첨부·프로젝트를 보존하고 최신 revision으로 같은 요청을 보낸다. 오래된 스트림 콜백이 다른 대화를 바꾸지 못하도록 소유권을 확인한다. 접수된 user revision은 실행 전에 첫 SSE로 전달하므로 중단 후 남은 사용자 턴을 다음 요청이 인식한다.
4. refinement/RAG는 보조 자료로 남기고 원래 사용자 요청을 실행 prompt의 권위 있는 지시로 보존한다. 품질 재작성은 이전 대화의 복사본과 최신 정정을 전달한다. 승인 대기에서는 품질 재작성·검증·메모리 기록·sync_all로 진행하지 않는다.
5. READ_ONLY는 MemoryRecorder와 MemoryManager의 요약 모델 호출·Vault/provider 기록을 차단한다. 실제 임시 Episodic 파일이 생성되던 RED를 재현한 뒤 GREEN을 확인했다. 일반 허용 모드의 기록 계약은 유지한다.
6. 자동 및 명시적 TDD는 READ_ONLY/Code OFF를 먼저 확인한다. 허용된 revision TDD는 최종 답변·assistant 저장·revision을 DONE 전에 전달하고 CAS 경쟁을 typed conflict로 알린다. 기존 OS sandbox 보호를 약화하지 않았다.
7. 활성 reconnect는 길이가 줄어드는 최종 snapshot을 final 이벤트로 전달하고 종료 직전 tail을 배출한다. 이미 완료된 세션의 기존 DONE 계약은 유지한다. 이는 자동 경계 검증이며 실제 네트워크 단절·재연결 전체 시험을 뜻하지 않는다.
8. 최종 prompt 예산은 전체 system/guard, 최신 실제 사용자 지시, 선택된 도구 안내·schema와 가장 최근의 짝을 이룬 도구 호출·결과를 보호한다. artifacts→memory→skills→옛 이력 순으로 선택 자료를 줄이고, 필수 부분을 모두 담지 못하면 provider 호출 전에 PromptBudgetExceededError로 종료한다. system stub·부분 JSON·전체 serialized prompt 잘라내기로 정상 호출을 가장하지 않는다. user role의 도구 결과를 최신 사용자 지시로 잘못 선택하지 않는다.
9. StreamProcessor의 whitespace-only 출력/flush와 ToolLoop 종료 flush에서 의미 있는 공백을 버리던 세 곳의 조건을 수정했다. 숨겨진 thought/scratch/tool 구문, 반복 탐지, 승인 상태 필터는 유지했다. 숫자 줄·CJK·제목·목록·코드 펜스의 분할 chunk 및 지연 flush를 RED→GREEN으로 검증했다. 과거 실답변의 provider 원문이 없어 그 답변의 모든 공백 손실이 이 경로였다고 단정하지 않는다.
10. canonical history의 반복 본문 key 충돌, 모바일 긴 경로 가로 넘침, 진행 상태와 시간·중지 버튼의 충돌을 수정했다. 375px에서 user article/client/scroll은 332/332, feed는 364/364였다. 최종 입력 안내문은 `질문이나 작업 내용을 입력하세요`로 줄여 한국어 보조 표현의 홀로 남는 줄을 없앴다. 기존 글꼴·색·토큰·입력 동작은 유지했다.

# 자동 검증

| 검증 | 최종 결과 | 근거 |
|---|---|---|
| Python 관련 28개 파일 | **425 passed / 2 skipped / 1 기존 경고**, 15.50s | [final-python-regression-all.log](final-python-regression-all.log) |
| 프런트엔드 API/Chat 22개 파일 | **202 passed**, 3.77s | [final-frontend-regression-after-copy.log](final-frontend-regression-after-copy.log) |
| TypeScript 및 Vite production build | **종료 0**, Vite 21.31s. 기존 500kB 이상 chunk 경고 유지 | [final-dashboard-build-after-copy.log](final-dashboard-build-after-copy.log) |
| 관련 Python 정적 검사 | Ruff 통과. 새 budget·whitespace 좁은 strict 검사 오류 0/경고 0 | [final-root-static.log](final-root-static.log), [final-budget-static.log](final-budget-static.log), [stream-whitespace-static.log](stream-whitespace-static.log) |
| 확대 타입 검사 | 오류 0, 기존 경고 24개 유지 | [root-types.log](root-types.log) |
| 새 budget/stream 경계 LSP | 오류 0 | [final-budget-lsp.json](final-budget-lsp.json), [final-stream-lsp.md](final-stream-lsp.md) |

Python 두 skip은 격리된 테스트 환경에서 PIN이 설정되지 않은 인증 테스트다. 실제 서버 인증을 끈 것이 아니다. 경고는 기존 Starlette/httpx 전환 경고다. 테스트 초기화는 collection 전에 임시 Path.home을 사용해 사용자 실제 GBrain/메모리/인증을 변경하지 않았다. CSS/JSON LSP의 biome은 이전 사용자 설치 거절에 따라 설치하지 않았고, TypeScript·빌드·실제 브라우저 검증으로 보완했다. 전체 프로젝트 타입 검사가 경고 없이 통과했다고 주장하지 않는다.

실제 실패를 재현한 회귀와 수정 후 결과를 모두 보존한다. [request-preservation-red.log](request-preservation-red.log)/[request-preservation-green.log](request-preservation-green.log)은 원문 보존 11개 경계, [final-budget-red.log](final-budget-red.log)/[final-budget-green.log](final-budget-green.log)은 필수 지시와 tool call/receipt의 보존 또는 호출 전 거절을 검증한다. 기존 oversized-system 시험은 system stub 성공 대신 typed 거절로 강화했고, CTX02 F3 두 시험은 oversized skills를 사용해 원래 다단계 aux write-back·재팽창 방지 목적과 full system/tools 보존을 함께 확인했다. 이전 실패 로그도 남겼으며 테스트를 지우거나 약화하지 않았다.

[stream-whitespace-red.log](stream-whitespace-red.log)은 9 failed/6 passed, 종료 flush 잔여 RED는 1 failed/2 passed였고, [stream-whitespace-green.log](stream-whitespace-green.log)은 15 passed, [stream-whitespace-regression.log](stream-whitespace-regression.log)은 관련 213 passed다. 실제 Q13/Q15/Q08 답변을 다시 관찰해 자동 검증만으로 완료 처리하지 않았다.

Codex의 중첩 seatbelt 안에서 기존 mandatory OS sandbox 시험은 `sandbox_apply: Operation not permitted`로 실패했다. [tdd-boundary-sandbox-diagnostic.log](tdd-boundary-sandbox-diagnostic.log)에 제약을 기록했고, 보호를 바꾸지 않은 같은 기존 시험을 승인된 별도 실행 환경에서 실행해 [tdd-boundary-sandbox-verification.log](tdd-boundary-sandbox-verification.log)의 1 passed를 확인했다.

# 독립 검토와 화면 판정

[code-review.md](code-review.md)는 위의 41파일 후보와 모든 파일 해시를 독립 대조한 **CLEAR/APPROVE**다. [runtime-audit.json](runtime-audit.json)은 주 에이전트의 실제 질문·도구·DOM·서버 검증을 같은 최종 후보에 결박한다. 이전 후보의 보고서는 별도 파일로 보존했고, 판정·후보·산출물은 [evidence-ledger.jsonl](evidence-ledger.jsonl)에 기록한다. source bytes가 바뀌면 현재 판정을 재사용하지 않는다.

40파일 후보의 화면 검토에서는 A가 375px 안내문의 `적어 / 주세요` 보조 표현 분리를 BLOCK으로 판정했고 B는 유한한 캡처 범위에서 PASS를 내렸다. 기존 문구라는 이유로 BLOCK을 무시하지 않고 안내문 한 줄만 수정했다. 이전 이미지·manifest·판정은 `pre-copy-*`, [visual-manifest-before-copy.json](visual-manifest-before-copy.json), [visual-review-a-before-copy.md](visual-review-a-before-copy.md), [visual-review-b-before-copy.md](visual-review-b-before-copy.md)에 정확한 해시와 함께 보존한다.

**최종 화면 게이트: 41파일 후보에 결박한 새 캡처 전체에 대해 A/B 독립 검토가 모두 PASS다.** 안내문 수정 뒤 375/768/1280px 최종 화면과 375px 작업 중 화면을 새로 촬영했고, 두 검토자가 5개 이미지(4개 고유 화면)의 실제 pixels·해시·형식·크기·최종 수정 이후 시각을 확인했다. 짧은 안내문은 375px에서도 한 줄이며 이전 보조 표현 분리가 해결됐다. 최종 이미지와 유한한 범위는 [visual-manifest.json](visual-manifest.json), 판정은 [visual-review-a.md](visual-review-a.md)/[visual-review-b.md](visual-review-b.md)에 있다. 더 큰 JPEG의 미세 글꼴 검증 신뢰도는 MEDIUM이며, PASS는 캡처된 `/chat` 상태에 한정한다. 이전 후보의 PASS를 재사용하지 않고 두 최종 판정과 정확한 후보 해시를 ledger에 새로 기록했다.

baseline 실패 이미지, 이전 재시도·취소 이미지, 불완전 resize/fullPage 캡처는 최종 화면 인수 근거에서 제외한다. 이번 작업은 screenshot clone이 아니며 픽셀 일치 점수나 전체 앱 디자인 인증을 주장하지 않는다. JPEG의 미세 글자 경계·대비 한계와 정적인 화면으로 증명할 수 없는 hover/키보드/시간 변화·실제 중지 동작을 구분한다.

# 남은 기능별 개선 큐

| 우선순위 | 상태와 항목 | 다음 실행·인수 조건 |
|---|---|---|
| P1 | UNTESTED: 의미 기반 답변/실행 분류와 MAX selector | 숫자·JSON·정정 추출을 불필요한 실행 계획으로 승격하지 않음. 원문 보존 뒤에도 남은 selector의 `prompt[:500]` 경계를 긴 보조 문맥과 실제 요청으로 시험. 질문 키워드로 권한·정답을 추정하지 않는 typed intent 계약. |
| P1 | PARTIAL: 정밀 출력 요청의 품질 재작성 | 현재 지정 문장·JSON·불확실성·Markdown 샘플은 통과했지만 일반 품질 검사의 긴 답변 선호/불필요한 재작성은 남아 있다. 단계별 초안·최종 답변을 비교해 한 문장/한 객체 계약, 고유명사 및 Q07 형식을 재시험. |
| P2 | UNTESTED: 공식 출처 웹검색 Q09 / 날짜 자료 Q11 | 검색을 실제 켜고 도구 결과·공식 링크의 주장 일치를 직접 검토. 과거 재고를 현재 수량으로 확정하지 않는 두 문장 답변도 별도 실행. |
| P2 | UNTESTED: 긴 문맥·다른 대화 격리·최초/현재 조건 동시 조회 | 새 대화 및 긴 이력 매트릭스에서 교차 오염·정정 누락·예산 초과 처리를 실제 시험. 현재 예산 회귀 PASS를 모든 긴 대화의 품질 PASS로 확대하지 않음. |
| P2 | UNTESTED: 실제 연결 단절·승인 후 재개·모델 환경 실패 | reconnect/승인 대기 경계 자동 시험과 별도로 원래 사용 표면에서 실행. 이번 실제 승인 요구는 승인하지 않았으므로 승인 후 재개는 미검증. |
| P2 | UNTESTED: cognitive 전용 경로 | 현재 모드·권한을 별도로 확인하고 전용 실행 surface를 시험. 일반 웹 대화와 health 플래그에서 활성화를 추정하지 않음. |

전체 액세스의 자동 기록과 자연어 “도구 없이”는 같은 권한 설정이 아니다. 이번 수정은 READ_ONLY와 검색/코드 토글, 승인 대기 및 출력·저장 경계를 강화했다. 모든 자연어 금지 표현을 강제로 집행한다고 주장하지 않는다. 서버 재시작 때 전역 access mode가 초기화되어 이전 화면의 READ_ONLY와 실제 FULL이 일시적으로 달랐던 실행은 구분했고, 후속 실제 검증은 READ_ONLY를 다시 선택했다.

주 에이전트는 최종 QA 뒤 원래 FULL access로 복원했고 검색 OFF·Code OFF·27B 모델은 유지했다. 임시 viewport를 해제하고 원래 IAB 탭 하나를 남겼다. 서버 PID75671은 살아 있고 읽기 전용 health가 status=ok이며 `git diff --check`가 통과했다. 임시 `.debug-journal.md`의 주요 실패·판정·수정·실행 한계를 이 보고서로 옮긴 뒤 주 에이전트가 만든 그 파일만 제거했다. 최종 화면 게이트는 위와 같이 통과했다. 지속 질문·결과·계획·회귀 근거와 기존 사용자 데이터는 유지한다. 최종 정리 근거는 [cleanup-receipt.json](cleanup-receipt.json)에 둔다.
