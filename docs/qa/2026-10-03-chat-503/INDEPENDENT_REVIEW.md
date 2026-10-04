---
title: "실제 대화 복구 독립 기능·화면 인수"
date: 2026-10-03
status: passed-scoped-chat-recovery
tags: [qa, independent-review, chat]
---

# 독립 인수 기록

아래는 리더가 수신한 두 read-only 검토 결과를 보존한 요약이다. 검토자들은 파일을 수정하거나 추론·재시작을 수행하지 않았다. 리더의 실제 브라우저 조작과 런타임 증거를 현재 소스·캡처로 독립 대조했다.

기준 HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` + dirty 사용자 작업 및 이번 수정. 이 HEAD 단독으로 현재 변경을 식별하지 않으며 아래 현재 해시를 함께 사용한다.

| 검토 이름 | 에이전트 | 판정 | 신뢰 | BLOCKING |
|---|---|---|---|---|
| Pass A: 기능·구현 정합성 | `/root/chat_recovery_functional_review` | PASS | HIGH | 0 |
| Pass B: 화면·한글 정밀 확인 | `/root/chat_recovery_visual_review` | PASS | HIGH | 0 |

## 공통 인수 대상

chat 페이지 1개, 757×954 RGB JPEG 4개, 환경 패널 닫힘 상태를 두 검토자가 모두 직접 열었다.

| 상태 | 캡처 | SHA-256 |
|---|---|---|
| 준비 | `ready-27b.jpg` | `609d8f379d3c504048dfc72d95bf0952d55c5b46173ccad144d47628e49c40c6` |
| 선택 목록 | `model-list.jpg` | `22cb1b56d16efb9d5f5cbb8ace3cd82474cf153a5537843368b8b8adad233734` |
| 실제 생성 | `chat-in-progress.jpg` | `f9ec54431ba56ded46e83d0ff95b2e3fe510e00df4927912d3441607a63ef11d` |
| 완료 | `chat-success.jpg` | `2a68b87e448bf82afe608b0c910771da77c0f225da3e24b6a281c86d6aac4be2` |

두 검토자가 다음 현재 소스와 실제 번들을 대응했다. Pass A는 회귀 파일 2개 및 번들 manifest 103개도 모두 대응했다.

| 항목 | 현재 SHA-256 |
|---|---|
| `dashboard/src/stores/chatStore.ts` | `9198078dea08610ebd248020c602a4c5f34ddbbb02ce504364616531d31ad5e8` |
| `dashboard/src/stores/__tests__/chatStore.modelPreference.test.ts` | `a2a7388c8327c436070a1d37388fe81eb196d32fbda35a47ffc9f18e1abaa104` |
| `src/antigravity_k/api/routes/models_api.py` | `6ef55819126ce691d975320f87b970608fc3d6cafa0318176177d9ff3763111a` |
| `tests/test_local_models_default.py` | `b578fd684e3a19a933c346c87fa2ca174fa47a9fb59c77c28810a7702e28fa4f` |
| 실제 `assets/index-Bh-w7yNi.js` | `6e2ccdadde60524cffe5193000c943badb8ffce9f55f9f2745be5a901c65320b` |

## Pass A 결과

`setSelectedModel`이 모델 ID를 제한하지 않고 저장하며 `loadFromStorage`가 이를 동기적으로 복원함을 확인했다. `ChatPage`는 복원된 ID가 발견 목록에 없을 때만 추천값을 적용한다. 125B는 목록에 남아 있어 명시 선택을 덮어쓰지 않는다. `list_local_models`는 기존 registry 별칭 대응으로 설정된 `qwen3.8`을 발견된 `qwen3.8:latest`와 연결하고, 사용할 수 없거나 역할이 맞지 않으면 기존 fallback을 유지한다.

실제 DOM·실제 번들·추론 HTTP 200·진행/완료 캡처가 일치하며 fake response나 screenshot 대체 구현은 발견하지 않았다. 현재 번들에 저장 preference 키와 storage 오류 처리 문자열이 포함돼 있다. 소스 변경→빌드→호스트 재시작→09:10 실제 대화 캡처 순서가 현재 산출물과 일치한다.

red/green, typecheck, 938개 대시보드 검사, production build, 대화 32개 및 기본 모델 13개 검사를 대조했다. 기존 config 사본 불일치 1건은 별도 단독 재현이며 이번 수정으로 생성되지 않았다. 데이터 보존 receipt의 원본·백업 4개 일치도 대응했다. 새 테스트는 reload·프로젝트 전환·서버 snapshot 공존·별칭·역할·상태·fallback의 행동 경계를 검증하며 구현 문자열 고정이나 삭제만으로 통과하는 시험이 아니다.

비차단 메모: optional TypeScript checker 로그와 보고서 표현이 달랐다. 실제 로그는 caller project에서 TypeScript resolve 실패이며, 리더가 원시 로그에 맞게 두 보고서의 설명을 정정했다. 기존 큰 store/route와 기존 casts를 이번 좁은 수정이 새로 만들지는 않았다.

## Pass B 결과

준비 화면의 27B 모델 표시와 선택 목록의 `현재 선택` 및 125B 옵션이 읽힌다. 한글 prompt 전체, `정상 연결입니다.`, 품질 표시 및 토큰 In 35 / Out 9가 잘림·겹침·깨진 글자 없이 보인다. 완료 화면에는 오류 alert나 생성 중단 상태가 남지 않는다.

생성 중 캡처는 `Working… 0s`와 기존 300ms message-in fade 초기에 촬영돼 prompt가 순간적으로 옅다. 완료 캡처에서 정상 대비와 글자 표시를 확인했다. 다른 모델의 `0.49402999999999997B` badge는 기존 정밀도 표현이며 영역 안에 들어가므로 이번 복구의 차단 항목이 아니다.

상태 diff의 모든 필드를 소비했다: `dimensionsMatch=true`, 양쪽 757×954, `totalPixels=722178`, `diffPixels=62262`, `diffRatio=0.0862`, `similarityScore=91`, `alphaChannelIntact=true`. 두 RGB 캡처의 인코딩만 PNG로 변환했으며 투명 배경 요건은 없다. 디자인 fidelity 점수로 간주하지 않았다.

23개 hotspot의 원인은 다음과 같이 픽셀·DOM과 대응한다.

| 원인 | gridX,gridY 및 diffRatio |
|---|---|
| user bubble 표시 완료, Working 제거, assistant·응답·품질·토큰 표시 추가 (y119–477) | (1,1) .8066; (1,2) .6612; (2,1) .5854; (3,1) .5422; (4,1) .5210; (2,2) .5122; (2,3) .2216; (0,1) .1903; (1,3) .1839; (5,1) .1587; (3,3) .1032; (3,2) .0760 |
| stop→완료 control 및 하단 bar 상태 변화 (y834–954) | (7,7) .1915; (6,7) .0983; (5,7) .0741; (1,7) .0460; (0,7) .0402 |
| 44초 사이 clock·uptime·CPU/memory·link·header 상태 변화 (y0–119) | (7,0) .1739; (6,0) .1370; (5,0) .1231; (4,0) .0350; (2,0) .0219; (1,0) .0216 |

## 범위와 완료 게이트

기능, 실제 DOM 구현, 현재 빌드 대응, 표시 내용, 한글 가독성은 scoped PASS다. native Electron 권한·다른 viewport·환경 패널을 연 좁은 layout·활성 대화 자동 복원은 검증하지 않았고 PASS로 추론하지 않는다. 레퍼런스 clone 작업이 아니며 픽셀 일치 요구도 없다. 두 독립 검토가 같은 현재 빌드의 4개 fresh 상태를 모두 승인했고 BLOCKING이 없으므로 이 범위의 화면 완료 게이트를 충족했다.

원시 근거는 [복구 보고서](REPORT.md), 현재 source/bundle hashes, capture metadata, 실제 DOM·runtime·console 기록, red/green/typecheck/build 로그다. 새 소스나 새 번들이 생기면 이 해시 대응과 판정을 자동 승계하지 않는다.
