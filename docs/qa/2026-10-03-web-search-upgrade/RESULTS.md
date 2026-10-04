---
title: 웹 검색 개선 최종 검증 및 검토 ledger
date: 2026-10-03
tags: [web-search, qa, handoff]
---

# 인수 기준

HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`

변경은 공유 작업 폴더에 있으며 새 커밋·스테이징은 하지 않았다. 검토 대상은 [candidate.sha256](candidate.sha256)의 13개 파일이다. Manifest SHA256: `c96c377d16045c9104d0ead35a7ab61c72adcec51cba195d267e5be02a9612d9`. 마지막 [해시 검증](manifest-check-final.log)도 모두 OK다. 이 인수 기록을 재사용할 때는 HEAD와 manifest를 함께 확인한다. 변경 전 코드와 의존성은 [before.tar](baseline/before.tar)와 추출 디렉토리에 있다.

# 검토 ledger

| 검토 | 전체 HEAD | 대상 manifest SHA256 | 결과 | 근거 |
|---|---|---|---|---|
| 독립 코드 검토 | `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` | `c96c377d16045c9104d0ead35a7ab61c72adcec51cba195d267e5be02a9612d9` | CLEAR / APPROVE | [code-review.md](code-review.md), 최종 stamp |
| 독립 경계 검토 | `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` | `c96c377d16045c9104d0ead35a7ab61c72adcec51cba195d267e5be02a9612d9` | 발견한 P2 수정 확인 / 열린 지적 없음 | [boundary-review.md](boundary-review.md) |
| 주 에이전트 최종 실행 | `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` | `c96c377d16045c9104d0ead35a7ab61c72adcec51cba195d267e5be02a9612d9` | PASS | 아래 테스트·실제 도구·서비스 관찰 |

# 실행 결과

- 검색/추출/client/벤치마크: [250 passed](regression-final.log).
- 번들 라우팅: [24 passed](routing-network-enabled.log). 공개 네트워크 점검을 포함하므로 네트워크 허용 실행에서 검증했다. 제한 실행의 1개 오류 분류 차이는 [변경 전 코드](routing-before-task.log)에서도 같았다. 테스트를 제거하거나 오류 분류 조건을 완화하지 않았다.
- 새 동작 경계: 본문 25, DDG 32, 리더 13개. 기존 regex의 18개 실패, DDG의 24개 실패, 리더의 7개 실패를 먼저 재현했다. 일반 텍스트 MIME 2개와 늦은 검증 표식 1개도 수정 전에 실패를 확인했다.
- [Lint](lint-final.log), [format](format-check-final.log), [타입](typecheck-final.log), [lock](lock-check.log) 모두 통과. lxml strip_cdata 경고는 외부 패키지의 deprecated 경고다.
- 실제 도구 드라이버: [재시작 후 기록](manual-after-restart.jsonl)의 네 경우 모두 PASS. 정상 Python 문서 본문, 검색 공식 출처/인용/TOP1 내용, 사설 URL 차단, 인수 누락 처리를 확인했다.
- 서버 재시작 PID 88450, localhost:8000. [시작 기록](server-restart.log), [health 200/ok](live-health-after.json). 서버는 사용자가 계속 사용할 수 있도록 실행 상태로 유지했다. raw access log는 QA 산출물에 포함하지 않고 인증값을 가린 스냅샷만 보관했다.
- 기존 IAB `/chat` 화면의 서버 LIVE와 선택 모델 `qwen3.8:latest` 27.3B를 확인하고 모델 메뉴를 닫아 원래 화면으로 돌렸다. 대화 전송·설정 변경은 하지 않았다. 새 LLM 추론 검증은 이 작업의 증거에 포함하지 않는다.

실제 검색은 외부 제공자 가용성에 영향을 받는다. 이번 인수는 브라우저 자동화, 검증 우회, 모든 JS 페이지, 모든 앱 경로에 대한 보장이 아니다. 파서/리더는 현재 정책 경계를 유지한다. 전체 조사 근거·채택/보류·코드 인수 체크리스트는 [실행계획](../../web-search/WEB_SEARCH_UPGRADE_2026-10-03.md)에 있다.
