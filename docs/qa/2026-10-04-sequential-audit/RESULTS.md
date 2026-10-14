---
title: SSAK-AI 순차 기능 검증 및 개선 결과
date: 2026-10-04
tags: [qa, runtime, fixes, coverage]
status: completed-executed-scope
---

사용자 요청에 따라 실제 질문→답/동작→기대 비교→수정→동일 사례 재실행을 진행했다. 실제 Ollama qwen3.8 모델, production API/dashboard/임시 저장소를 사용했다. 개인 메모리·로그·자격증명·외부 계정으로 시험하지 않았다. 아래의 실행 범위 통과는 모든 환경/모든 기능 조합의 완전 보장을 뜻하지 않는다.

| 기능군 | 직접 검증한 범위/증거 | 판정/경계 |
| --- | --- | --- |
| 1 코어 답변 | QA01..08 숫자/JSON/정정/불확실성/자료지시 무시/실제 파일 읽기 | 실행 통과; 한Ollama500후 동일UI/별도실제runtime 모두PASS, upstream parser 안정성은 별도 |
| 2 대화 관리 | 실제 분기 원본유지/짧은 압축r4; 출력중 중단 후 cancelled/errornull/terminal1회/연속seq, 같은대화 후속42; API append/revision/fork/compact/history/export | ContextVar/ASGI 정리와 취소 event 수정 후 실제Qwen 통과; 긴 대화 압축 품질 전체 미검증 |
| 3 이미지 첨부·vision | 실제 JPEG의100%/4성공/0실패 JSON, unsupported text/plain 거절 | 실행 통과; 이미지4형식 표시 개선 |
| 4 도구·접근 정책 | required read_file 실제 실행, 승인 차단/도구 허용범위 API, QA09B/12 금지조건 실제 재실행 | 명시적 금지 조건 수정 후 통과; 임의shell의파일변경전부 의미분석하는 보장은 아님 |
| 5 모니터링·durable task | 실제 Qwen task submitted→done/정확히42; terminal1회/버전연속/20seq; 수정 후68사례 | 수정 후 실제모델·HTTP/WS 통과 |
| 6 지속 agency | 실제 off/unavailable 화면·disabled입력, API 상태 | 비활성 경계만 확인, 상시 자율운영 미검증 |
| 7 legacy Kanban | 전체 backend 회귀 조사 및 현재API 계약검사; auxiliary4모듈14통과 | UI 없는 별도 계약; durable task와 동일시하지 않음 |
| 8 예약 작업 | 실제printf/exit7 run·health·retry9사례, scheduler15s tick/finite soak 자기검사 | 실행 통과, 외부 delivery/8시간 soak 아님 |
| 9 메모리·privacy | real Chroma/GraphML2nodes1edge2vectors 생성→purge→재열기0; recall/budget/redaction/restore API | 실행 통과, embedding/recall 일부 포트 합성 |
| 10 위키·palette | 실제YAML문서 생성·편집·Git저장877ab04·재열기·검색결과열기;3너비Tab/Escape | 실행 통과 |
| 11 workspace·RAG | 설정된 임시 project3파일색인/재열기3chunk/marker, Root 동시Chroma8/8/peer유지/registry0, 새UIboot 초기화오류0 | 동시초기화와전역cache삭제 수정 후 통과; embedding/IDE launch 대체 |
| 12 editor·code intelligence | 실제 read_file로 editor 열림/source표시/문제없음; 실제FS15사례 | 파일 실행 통과; 모델 inline completion 전체 미검증 |
| 13 terminal | 실제 인증/Origin/printf split-output/close-shellPID4WS사례 | 실행 통과, 사용자 native 자식 트리 전체 아님 |
| 14 Git | remote없는 실제임시repo18사례 stage/commit/branch/checkout/log/readback | 실행 통과, remote push/PR 미실행 |
| 15 로컬 파일 이력 | history 화면3너비/기존회귀 | 빈 상태·회귀만 확인, 사용자 이력 삭제하지 않음 |
| 16 모델 | 실제6개목록/Embedding필터/selector,0.494B 표시/현재Qwen 실행 | 수정 후 통과, 다른 모든 모델 load 미실행 |
| 17 학습·recipes | Studio 실제 capability/disabledexport, API, 실제signal-gated child cancel/동시GET4.07ms | 계약 통과; 실제weight학습·export 미검증 |
| 18 음성 | API validPCM 합성 transcriber/형식·용량·422/413,21테스트 격리회귀 | 실제 마이크/STT/TTS 미검증 |
| 19 검색·추출·금융숫자 | 공식검색 표·근거·문법 검증 수정 후 동일 질문 실제UI 연속2회 통과; 같은4입력20필드100%;검색benchmark100×3paired | 검색·추출 실행 범위 통과; DCF/comps 계산 미구현 |
| 20 skills·market·MCP | 실제catalog/empty/health/oauth대상0/허용범위/API권한회귀 | 사용가능·비활성경계 확인; 외부 install/publish/OAuth 미실행 |
| 21 frontend plugins | 실제plugin목록/job-operationsroute3너비 | 화면·등록경로 확인; 실제외부plugin설치 미실행 |
| 22 평가·cognitive | actualdecision JSON/API/finiteSSE/cognitive-off,mutation snapshot 출처/시점;QualityGate97회귀 | 계약통과; 과거snapshot은 현재mutation결과 아님 |
| 23 browser·approval | 실Chromium186회귀,88이전실패 모두통과,118API의owner/deny/once/withdraw | 로컬실행 통과; 외부메시지/실계정 브라우저 미실행 |
| 24 관리자·보안 | 임시PIN/auth/WS/health/readiness/configAPI,defaultconfigbyte일치/MCP375제어복구 | 실행통과; 개인credential/PIN변경·LAN공개 미실행 |
| 25 호환·remote·provenance | 실제start CLI명령copy/상태미확인표시,compatinvalid/modelunavailable API 및 현재auxiliary검사 | 스키마/가용경계만 확인; externalagent/remote계정 미실행 |
| 26 CLI | 격리9/9 help/catalog/badinput/evaluation | 실행 범위 통과, 모든대화형TUI/hardware명령 아님 |
| 27 패키지·release | lock 기반SBOM6종보완/notices,config일치67관련검사,readme포트drift controls | artifact통과; historical release pins/문서9실패는 별도미해결 |

주요 개선: 필수 도구 실행 누락, 공식 도메인 검색·관련 근거 추출·표 보존, Markdown URL 소실, generic 추출 필드 누락, 설정workspace 바깥 startup RAG/영속store 누락 및 Chroma동시초기화/다른clientcache파괴, task lifecycle event/실제완료handoff, 출력중 취소의 ContextVar/ASGI 정리 오류, 낮은 어휘 반복 평가 우회, 테스트 전역HOME 누수, 숫자 긴 소수 표시, 위키 키보드/접근성, 모바일 MCP/한글/표 가독성,SBOM/config/검증fixture drift. no-tools/명시적 파일금지 및 실제 task 완료 handoff·coldRAG동시초기화는 재실행에서 통과했다. 검색 표/근거·실패표시 및 결과없는상태의완료판정도 아래 최종 실제 재검증에서 통과했다. 파일읽기후 한번발생한500은 Ollama native parser EOF 로그이며 동일UI/별도실제runtime 재실행 모두통과했다. 근거없는제품수정을하지않았고 upstream원인완전해결로 세지 않는다.

최종 검색은 실제 Ollama Qwen3.8, Search ON, 새 대화마다 동일한 QA09 질문으로 연속2회 실행했다. 각각 표1개/데이터2행, 올바른 mutable·immutable 구분과 문법 예시, 렌더링된 공식 href1개를 Root가 직접 확인했다. 화면 복사 원문과 저장된 완료 출력이 일치하며 두 task 모두 done/error null, web_search만 실행, terminal event1회이다. 마지막 citation/table/presentation 세 판정도 모두 true였다. 실제 소요시간32.58초/27.52초이며 일반 latency SLA로 확대하지 않는다. [계산 검증](search-final-live-verified.json), [첫 화면](search-final-live-1.jpg), [두 번째 화면](search-final-live-2.jpg), [독립 코드검토](backend-fix-review.md), [검색 수정·실패 이력](../../../.omo/evidence/web-search-answer/web-search-answer-fix.md)에 근거를 보존했다.

검색 보정은 실제 표 행 안의 인용 범위를 유지하되 각 문장의 기존 근거 기준을 그대로 적용한다. 코드셀은 백틱 유무와 관계없이 Python 문법을 검사하며, 유효한 원본 비교식/문자열을 바꾸지 않는다. 오류 출력의 코드 표시만 제거할 때는 같은 행의 알려진 출처에 그 전체 오류 문장이 존재하고, 유효한 앞선 예시와 명시적 출력 표시가 있어야 한다. 근거·문법·행 수 검증을 다시 거치며 재생성 예산은 기존2회이다. 마지막 관련75검사와 독립39검사/별도5경계 검사는 통과했다. 과거 실패한 실제 재실행 및 처음 event sequence를 task마다1부터로 잘못 가정한 계산 검사도 원본으로 남겼다. 실제 sequence는 store 전체에서1..9/10..18로 연속이다. 이 결과는 모든 질문의 사실 정확도를 보장하지 않는다.

최종 실제 연속 실행 전후 [30개 제품 파일 SHA256](source-final-marker-after.json)과 HEAD `02b9cde7fb0e890330ddebfec5ff8ad9ddc50435`가 같았다. 이전 실행 중 공유 HEAD가 변한 검사와 이 최종 고정 실행을 구분한다.

검사 수는 합산하지 않는다. [실제 질문 원장](QUESTIONS.md),[118API](api-current.json),[수정 후68HTTP/WS](extended_root_final.json),[추가계약14](auxiliary-current-tests.txt),[실제task완료](real-task-final-check.txt),[출력중 중단/후속 상태](cancel-final-durable.json),[취소 수정과87회귀](streaming-cancel-fix.md),[CLI9](cli-current.jsonl),[현재UI1243](dashboard-responsive-tests.log),[실제추출화면](extraction-final.jpg),[최종startup](startup-workspace-root-final.txt),[동시client8](vector-lifecycle-root-final-green.txt),[RAG수정](vector-lifecycle-fix.md),[메모리purge](memory-purge-root.txt),[브라우저 재확인](backend-recheck-report.md),[시각 검증](VISUAL.md)에 각 범위와 실제/합성 포트를 명시했다.

일반 backend baseline은7,846pass/113fail/11error/19skip/20xfail이었으나 실행중HEAD·소스가 변했으므로 현재전체green으로 사용할 수 없다. 이후88browser·13searchfixture·config·GBrain·trainingfixture·quality 및5artifact/testcontract 실패를 별도로 재검증했다. profiler/crashloop/finite-soak는 현재통과했지만 역사적실패원인까지 규명한 수정으로 세지 않는다. 기존출시candidate/현재fingerprint와 EX05의PASS대INCONCLUSIVE 충돌 등9문서계약은 현재런타임수정으로 과거GO를 재발급하지 않았다.

새로 만든UI의 최종125파일1,243테스트,types/lint/build통과. 기존lint warning36개와큰bundle경고가 남아 있다. backend scoped diagnostics의기존/protected warning은 각작업보고서에 남겼고0warning전체통과라고 주장하지 않는다. 공유checkout의다른변경과staged문서는 보존했다. 이번작업에서 commit/push/공개배포는 하지 않았다.

검증용 서버는 정상 종료(exit0)했다. [소유한 임시 runtime 정리](final-owned-runtime-cleanup.json)는 15개 임시 root·합성 인증 header 제거, 해당 PID 종료,8000 listener 없음까지 확인했다. 사용자 Ollama는 종료하지 않았다. [브라우저 정리](final-browser-cleanup.json)는 viewport 복원과 실제 검증 탭2개 종료를 기록한다. 초기 연결거절 오류 탭1개는 data URL 정책으로 명시적 닫기가 차단되어 turn 종료시 자동 정리되는 임시 탭으로 남겼다.
