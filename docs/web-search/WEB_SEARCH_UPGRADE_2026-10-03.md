---
title: 웹 검색 개선 실행계획과 저장소 비교
date: 2026-10-03
tags: [web-search, research, implementation]
---

# 현재 범위

현재 작업 폴더의 웹 검색·읽기 도구를 개선한다. 기존 Brain/Body, 번들 검색 라우팅과 실패 시 정책, URL/DNS/IP 고정, robots.txt, 이용약관 정책, 인용·비신뢰 콘텐츠 경계를 유지한다. 앞선 프론트엔드 작업의 미완료 최종 검토는 이 작업의 완료로 표시하지 않는다.

| 단계 | 상태 | 산출물 |
|---|---|---|
| 1. 세 공개 저장소와 현재 경로 대조 | completed | 정확한 커밋, 호출 경로, 채택·보류 근거 |
| 2. 본문·검색 결과 파서와 읽기 실패 처리 구현 | completed | 아래 인수 조건을 만족하는 코드·실패 재현 테스트 |
| 3. 관련 회귀·실제 도구 실행 검증 | completed | 테스트·진단·실행 기록 |
| 4. 독립 검토와 인수 문서 정리 | completed | 최종 결과·한계·운영 방법 |

## 채택한 개선과 담당

| 개선 | 담당 | 인수 조건 |
|---|---|---|
| Scrapling 파서만 사용한 본문 선택 | 파서 에이전트 | article/main 우선, 메뉴·스크립트 제거, HTML entity·한국어·코드·표 정보 보존, 길이 제한, 네트워크·브라우저·적응 선택 DB 생성 없음 |
| 검색 결과 DOM 파싱 공유 | 검색 파서 에이전트 | DuckDuckGo 속성 순서·따옴표·복수 class 변화 처리, 누락 스니펫을 다른 결과에 잘못 연결하지 않음, 동기/비동기 HTML·Lite에 같은 기준 적용 |
| 제한된 읽기와 검증 페이지 분류 | 리더 | 실제 수신 바이트 제한, 검증 페이지를 본문으로 사용하지 않음, 실패하면 스니펫 유지, 기존 수집/권한 정책 우회 없음 |

## 저장소 근거

- Agent-Reach: `a19a171fa980a0785849596492e0af4db800c82f`. [web channel](https://github.com/Panniantong/Agent-Reach/blob/a19a171fa980a0785849596492e0af4db800c82f/agent_reach/channels/web.py)에서 제한된 읽기와 고신뢰 검증 페이지 감지 원칙을 채택한다. 설치기·쿠키 수집·모든 소셜 CLI를 함께 설치하지 않는다. Exa는 mcporter 설정도 실제 연결 검증과 구분하는 [channel](https://github.com/Panniantong/Agent-Reach/blob/a19a171fa980a0785849596492e0af4db800c82f/agent_reach/channels/exa_search.py)이다. 현재 mcporter/Exa가 구성되지 않아 이번 기본 검색에 이를 연결하지 않는다.
- Scrapling: `971d5edb9c01f000dd4befcd21742e9b22260dc7`, 0.4.15. [Selector](https://github.com/D4Vinci/Scrapling/blob/971d5edb9c01f000dd4befcd21742e9b22260dc7/scrapling/parser.py)와 [parser dependencies](https://github.com/D4Vinci/Scrapling/blob/971d5edb9c01f000dd4befcd21742e9b22260dc7/pyproject.toml)를 사용한다. fetchers/ai/rag extras는 브라우저와 별도 MCP 의존성을 가져오므로 이번 범위에 추가하지 않는다. 적응 선택의 자동 저장·오탐 가능성이 불필요한 일반 본문 읽기에는 사용하지 않는다.
- patchright-enhanced: `e38ab7ab9448db6f093f72ee097c18ca9905e84c`. [main](https://github.com/whaleyxbt/patchright-enhanced/blob/e38ab7ab9448db6f093f72ee097c18ca9905e84c/main.ts)은 병렬 브라우저 세션 반복 프로그램이다. [package](https://github.com/whaleyxbt/patchright-enhanced/blob/e38ab7ab9448db6f093f72ee097c18ca9905e84c/package.json)는 ghostprobe 1.0.0 + patchright ^1.57.0이며 검색 API가 아니다. 세션 종료·시간 제한 원칙을 참고하되 브라우저 대체, 프로필 재사용, 검증 우회는 보류한다.

## 현재 경로와 경계

`web_search`는 번들 provider 선택을 먼저 존중하고, legacy 제공자 검색→관련성/공식 출처 보강→정규화/순위→인용과 비신뢰 표식→TOP1 읽기로 이어진다. `web_scrape`는 PageScraper로 직접 읽는다. 이번 파서 개선은 PageScraper와 TOP1 읽기, DuckDuckGo 결과 파싱에 연결한다. 검색 스니펫과 검증된 본문을 혼동하지 않는다.

별도 UnifiedAgent의 배포 검색 client 통합, 구조화 검색 응답 API, JavaScript 전용 수집 서비스, 소셜 플랫폼 인증, Exa 추가는 새로운 라우팅·권한·운영 계약이 필요한 별도 후보로 남긴다.

## 구현 인수 체크리스트

- [x] 본문 DOM 파서를 `web_html.py`로 분리하고 기존 `html_to_text` import 경로 유지.
- [x] 한국어 인라인 인접성, HTML entity, article 제목, 코드 들여쓰기·리터럴, 표 셀 구분, 의미 영역의 빈 본문 폴백 검증.
- [x] 동기 DDG HTML / 비동기 HTML·Lite가 `web_search_html.py`의 같은 결과 파서를 사용.
- [x] 다른 결과의 스니펫 연결을 방지하고 class·따옴표·속성 순서·DDG 리다이렉트 변화를 처리.
- [x] CAPTCHA 단어를 포함한 정상 검색 결과를 허용하고 DDG 검증 폼·컨트롤을 구분.
- [x] Jina TOP1 / 직접 PageScraper 읽기에 실제 디코딩 후 5 MiB 응답 상한 적용. Content-Length를 신뢰해 상한을 생략하지 않음.
- [x] 검증 제목과 제공자 표식의 조합으로 검증 페이지를 거부. 제목은 앞 4096자, 해당 제목이 있으면 표식은 제한 내 본문 전체에서 확인.
- [x] 바이너리 MIME 거부, 잘못된 charset의 UTF-8 대체, 일반 텍스트·Markdown의 literal HTML 예제 보존.
- [x] IP 고정, redirect마다 공개 DNS 검증, robots.txt/이용약관, egress hook, 번들 provider 실패 정책과 인용·비신뢰 콘텐츠 경계 유지.
- [x] Scrapling 0.4.15 핵심 패키지 및 lock 추가. fetchers/브라우저/AI MCP extras와 적응 저장 사용 없음.

## 검증 결과와 인수 근거

검증 대상 HEAD는 `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`이다. HEAD에는 이번 변경이 커밋되지 않았으므로 코드 인수 기준은 [candidate.sha256](../qa/2026-10-03-web-search-upgrade/candidate.sha256)의 13개 파일 해시이며 manifest 자체 SHA256은 `c96c377d16045c9104d0ead35a7ab61c72adcec51cba195d267e5be02a9612d9`이다. 기존 사용자 변경과 이번 변경을 구분할 수 있도록 작업 전 engine/tool/의존성 스냅샷도 보관했다. 스테이징·커밋은 하지 않았다.

- 관련 검색·추출·번들 client·고정 벤치마크 회귀: [250 passed](../qa/2026-10-03-web-search-upgrade/regression-final.log). 새 파서/리더 테스트는 25 + 32 + 13개다. 고정 추출 fixture 30개가 필요한 사실을 유지했다.
- [Ruff](../qa/2026-10-03-web-search-upgrade/lint-final.log), [format](../qa/2026-10-03-web-search-upgrade/format-check-final.log), [타입 검사](../qa/2026-10-03-web-search-upgrade/typecheck-final.log), [offline lock 검증](../qa/2026-10-03-web-search-upgrade/lock-check.log) 통과.
- 실제 `WebScraperTool.execute`에서 공개 Python 3.13 문서 본문 추출, 비공개 URL 차단, 누락 인수 오류를 관찰했다. 실제 `WebSearchTool.execute`에서 Python 공식 출처와 인용·TOP1 본문을 관찰했다. [재현 드라이버](../qa/2026-10-03-web-search-upgrade/manual_driver.py)와 실행 로그를 보관한다.
- 별도 번들 라우팅 회귀는 공개 연결 점검이 가능한 실행에서 [24 passed](../qa/2026-10-03-web-search-upgrade/routing-network-enabled.log)다. 네트워크 제한 환경에서는 23 passed / 1 failed로 NETWORK_UNAVAILABLE/CIRCUIT_OPEN 분류가 달랐고 [변경 전 코드](../qa/2026-10-03-web-search-upgrade/routing-before-task.log)도 같았다. 네트워크 허용 실행으로 환경 차이를 구분했으며 런타임 코드를 바꾸거나 검증을 완화하지 않았다. 최종 검증은 서로 다른 두 묶음 합계 **274 passed**다.
- lxml의 기존 `strip_cdata` deprecated 경고가 231회 출력되지만 실패는 아니다. 이번 범위에서는 외부 패키지 코드를 변경하지 않았다.

5 MiB는 **사용 가능한 디코딩 본문 크기 상한**이다. HTTPX의 압축 해제 과정 전체에 대한 절대 메모리 상한을 보장하지 않는다. 임의의 모든 검증 페이지·JS 전용 페이지를 수집할 수 있다고 주장하지 않는다. robots/이용약관/접근 검증으로 거부된 본문은 우회하지 않는다. TOP1 리더 실패 시 기존 스니펫으로 돌아간다.

현재 프로젝트의 명시된 HTTPX 의존성 및 IP 고정 transport를 재사용했으며 별도 HTTP client factory나 httpx2 전환을 추가하지 않았다. 설치 재현은 고정 lock을 따른 프로젝트 환경에서 수행한다. Agent-Reach 1.5.0의 doctor/check-update는 점검만 했고 전역 설치·소셜 인증·mcporter 구성은 변경하지 않았다.

## 실행 반영과 최종 인수

자동 재로딩이 꺼져 있던 localhost:8000 서버를 정상 종료 후 같은 프로젝트 가상환경/host/port로 재실행했다. [시작 로그](../qa/2026-10-03-web-search-upgrade/server-restart.log)는 일회용 WebSocket 인증값을 가린 스냅샷이다. `/health` 200/ok, 기존 브라우저 대화 화면 LIVE와 Qwen3.8 27.3B 선택 유지를 확인했다. 모델은 요청 시 로드되므로 이 작업에서 새 LLM 추론 성공까지 검증했다고 주장하지 않는다.

재시작 뒤 [실제 도구 재검증](../qa/2026-10-03-web-search-upgrade/manual-after-restart.jsonl)의 공개 문서 읽기·웹검색·사설 URL 차단·누락 인수 처리 네 경우가 모두 성공했다. [코드 검토](../qa/2026-10-03-web-search-upgrade/code-review.md)와 [경계 검토](../qa/2026-10-03-web-search-upgrade/boundary-review.md)는 위 최종 manifest와 동일 HEAD에 묶여 있으며, 발견한 일반 텍스트 손실은 수정·재현 검증 후 열린 지적 없음으로 인수했다. 상세 실행 기록과 검토 ledger는 [RESULTS.md](../qa/2026-10-03-web-search-upgrade/RESULTS.md)에 있다.
