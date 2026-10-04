---
title: oh-my-jev 적용 검토·실행 증거 원장
date: 2026-10-03
tags: [qa, evidence-ledger, calibration]
---

전체 Git HEAD는 `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`다. 공유 폴더의
기존 미커밋 수정을 보존했으므로 실제 후보는 [source.sha256](source.sha256)의
8개 파일과 manifest SHA256
`0d19f8f285706674ef9326e6a0e649d5c4a93804ed0f22b5312893cee1a414aa`로 함께
식별한다. 후보 파일이 바뀌면 해당 범위 판정을 재사용하지 않는다.

| 검토/실행 | 판정 | 범위와 증거 |
| --- | --- | --- |
| 최초 독립 engine 코드 검토 | CLEAR / APPROVE, 이력 | 최초 manifest `7f095450…0777c`, [engine-review-initial.md](engine-review-initial.md), 보고서 SHA256 `4c4865b72b02c95b3302a6e07ce4f49583f780c48388aff1918a6671fa4714fe` |
| 최초 독립 API·CLI 코드 검토 | CLEAR / APPROVE, 이력 | 최초 manifest `7f095450…0777c`, [surface-review-initial.md](surface-review-initial.md), 보고서 SHA256 `8b4cb120999c0971916791147d3b1369b45dfe4cb253227297224e776210c781` |
| 타입 보완 후 독립 engine 검토 | CLEAR / APPROVE, 이력 | OpenAPI 수정 전 후보. [engine-review-before-openapi.md](engine-review-before-openapi.md), SHA256 `e2759270a0ecc093f63ed4a6e89c3cc1a962b8e66d998d4155861d27675437ef` |
| 타입 보완 후 독립 API·CLI 검토 | CLEAR / APPROVE, 이력 | OpenAPI 수정 전 후보. [surface-review-before-openapi.md](surface-review-before-openapi.md), SHA256 `da452f5595e7a4e35e4e93e2a978c063f7e854708bdebefc55d6e199cad5cf2d` |
| 최종 독립 engine 코드 검토 | CLEAR / APPROVE | 같은 full HEAD·최종 후보, 모델/계산기/시험 3파일. [engine-review.md](engine-review.md), 보고서 SHA256 `3d84774cb9d3a5a997f829f2c5e84bcc013d7ecf2c9789066709c3a12c56bfbe` |
| 최종 독립 API·CLI 코드 검토 | CLEAR / APPROVE | 같은 full HEAD·최종 후보, adapter/등록/시험 5파일. [surface-review.md](surface-review.md), 보고서 SHA256 `7b84d49bfa5313e818096f1fd3a7eb3cb9448eb7f3240e6bd66326930ca2f650` |
| 구현 A 경계 회귀 | PASS, 50 cases | [worker-a-green.txt](worker-a-green.txt), RED/정적 검사/수계산 증거도 같은 디렉터리 |
| 구현 B 표면 회귀 | PASS, 21 cases | [worker-b-openapi-green.txt](worker-b-openapi-green.txt), 실제 등록 app·ephemeral bearer·CLI 입력 경계·공개 오류 계약 |
| Root 최종 합본 회귀 | PASS, 160 cases | [root-openapi-final-regression.log](root-openapi-final-regression.log), 새71개+기존89개. 같은 full HEAD·최종 manifest |
| Root 최종 정적 검사 | PASS | [root-frozen-ruff.log](root-frozen-ruff.log), [root-frozen-types.log](root-frozen-types.log): 무필터0오류0경고. LSP 변경8파일 error 진단 없음 |
| Root CLI 직접 사용 | PASS | [root-cli-help.txt](root-cli-help.txt), [root-cli-report.json](root-cli-report.json), 오류 stderr와 종료 코드 2 |
| Root 실제 HTTP 사용 | PASS for observed requests | 별도 loopback 생산 app·실제 middleware·임시 auth, 인증 없음401/정상200/NaN422/잘못된 JSON422/빈 입력200. CLI와 report JSON 구조 동일 |
| Root OpenAPI runtime audit | PASS | 실제문서의422 모델 불일치 RED→GREEN, 최종 HTTP 문서/응답 일치. [openapi-runtime-audit.md](openapi-runtime-audit.md) |
| Root 현재 앱 반영·정리 | PASS | 현재 PID64370·8000앱 health200와 typed route등록·인증401. 임시8018서버 종료 및 합성 header 파일 제거 확인. [root-manual-qa.md](root-manual-qa.md) |

초기 `root-regression.log`는 uv 사용자 캐시 접근 차단 10실패, 다음
`root-final-regression.log`는 로컬 backend 연결 차단 1실패였다. 둘은 통과 근거가
아니며 실행 환경 제한의 이력이다. OpenAPI 수정 전 `root-approved-regression.log`와
`root-frozen-regression.log`는 모두159통과였고 최종은160통과다. 최초 무필터 타입 검사의 경고는
API override·시험 타입·QA helper에서 해결했고 최종 무필터 검사를 따로 보존했다. HTTP 서버의
lifespan은 끄고 평가/인증/라우팅만 실행했으며 모델·사용자 저장소를 시작하지 않았다.
본 증거 디렉터리의 로그와 문서에는 JWT/PIN 등 실제 자격증명을 보관하지 않는다.
실행 앱의 raw 로그는 증거로 복사하거나 출력하지 않았다.
