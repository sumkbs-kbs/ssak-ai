---
title: IMP-09 Product Vision 최종 오프라인 게이트 검수 및 직접 후속 수정
tags: [qa, imp09, offline, independent-review]
date: 2026-10-14
---

검수 대상 최신 Luna 사본은 미완료였습니다. child 영수증 연결, 현재 소스 binding, delivery 해시 보존, 음성 테스트의 검증 범위에서 네 가지 문제를 확인했고, 이 실행 폴더의 전용 사본에서 모두 수정했습니다.

현재 하네스 후보의 FG 검증은 **22 passed / 실패·오류·skip 0**입니다. Ruff, format, basedpyright, 메모리 compile은 각각 exit 0이며 실제 parent→child 영수증 reducer가 유효 판정을 냈습니다. 코드 독립 검수는 APPROVE, source-bound 증거 체인은 PASS입니다. 최종 패키지 검수는 result.json의 independent_review.final_package를 따릅니다.

완료 범위는 **COMPLETE_OFFLINE_GATE**입니다. 전체 IMP-09는 PARTIAL, 제품 live vision은 NOT_RUN, live 승인은 NOT_ISSUED, 역사 원장은 NOT_RECOVERED입니다.

읽기 순서와 실행 근거:

1. [결과](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/result.json)와 [검수·수정 대응표](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/review.json)
2. [실제 최종 검증 영수증](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/checks-956ad18301aa472b81ff2e9c74263531.json)
3. [최종 JUnit](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/attempts/selector-exec-a3d015e9098e4d24822dbb5944285da6/junit.xml), 같은 child의 dispatch/precheck/pytest-result/completion/state-guard
4. [원본 launch 영수증](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/launches/gate-37df3c4d565d499d89eb7ab34f61a274/launch-receipt.json)
5. [저장 자료 대조](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/artifact-audit-final.json), [작업 패치](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/task-only.patch), [최종 manifest](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/artifact-manifest.json)
6. [남은 작업과 실행 경계](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/next-work.md)

패치는 run_harness.py, run_offline_prechecks.py, test_runtime_final_gate_contract.py 세 파일에만 적용됩니다. source-preimage의 원본 세 파일에 git apply로 패치를 적용한 patch-reconstruction 결과는 최종 파일과 바이트 단위로 같습니다. runtime_adapter와 기존 bridge/compatibility helper 세 파일은 최신 입력 사본의 바이트를 보존했고, 이전 45/18 selector를 다시 실행하지 않았습니다.

검증한 여섯 구현 소스는 실행 binding SHA **7825c406adec5ff37a8fa195e80ea788878446c66f0aadc861c6fb57a8c68733**에 고정되어 있습니다. 검증 후 구현 소스는 수정하지 않았습니다. 실행·검수 영수증을 현재 상태로 되쓰지 말고, 다음 변경은 새 소유 후보와 binding에서 진행합니다. capture_gate.py 등 네 보조 스크립트는 실행 포착·보존·아티팩트 대조·봉인 도구이며 세 파일 구현 패치의 범위와 구분됩니다.

보호 파일 21개와 기존 증거 3,769개 항목은 시작 이후 해시·타입·symlink 대상이 같습니다. 제품·설정·공용 원장을 수정하지 않았고 commit/push도 하지 않았습니다. 프로젝트 등록·auth 등 테스트 상태는 소유 폴더 안으로 격리했습니다.

실패 자료는 보존했습니다. 첫 후보의 실제 JUnit은 21/22 통과이며 강화한 binding 음성 단언 1개가 실패했습니다. 두 번째 시도는 재동결 실패 이후 binding precheck에서 중단되어 pytest가 시작되지 않았습니다. 최종 변경 후보는 22/22 통과했습니다. root checks의 0건 표기는 비성공 parent를 reducer가 거부한 요약이므로, 첫 후보의 실제 실행 건수와 혼동하지 마십시오. 후보 source snapshot·원문·receipt를 서로 연결해서 읽습니다. 보조 대조 스크립트의 초기 상대 import 타입 오류 1건도 support-checks.json에 별도로 남겼습니다.

delivery/956ad18301aa472b81ff2e9c74263531/inventory.json은 driver가 실행 중 만든 **시점 snapshot**입니다. 당시 열린 바깥 launch stdout.txt 1개는 종료 후 바이트가 달라졌습니다. 이 snapshot의 bytes/SHA는 그대로 보존되어 있고, checks가 참조하는 immutable inventory 자체의 SHA도 일치합니다. driver 단계 manifest는 history/final-driver-phase에 보존했으며, root artifact-manifest.json은 닫힌 stdout·launch receipt·최종 인계까지 포함하여 봉인합니다. 최종 봉인 후에는 파일을 추가하거나 변경하지 마십시오.

실제 HTTP/socket/listener/제품 worker/Uvicorn/Ollama/추론은 각 0회입니다. mock·synthetic fixture를 실제 호출이나 인증·모델 응답·품질 증거로 취급하지 않습니다. 기존 asyncio_mode 설정 경고 1건은 숨기지 않고 유지했습니다. 이후 실제 제품 관측은 명시된 별도 범위와 승인 조건이 충족될 때만 진행합니다.
