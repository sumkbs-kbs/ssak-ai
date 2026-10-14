# IMP-03-NATIVE-TRANSPORT-ERROR-01 구현 인계

상태: COMPLETE_OFFLINE / 독립 검수 대기. 본 문서는 worker의 오프라인 범위만 다룹니다. root 소유 controlled-wire/ 결과는 별도입니다. commit/stage/push 및 실제 HTTP·Ollama·추론 실행은 하지 않았습니다.

## 오류 계약과 변경

- native nonstream Ollama의 HTTP 오류는 `NativeTransportError`로 전파됩니다. HTTP upstream 실패는 제품 502와 `provider_transport_error`, `upstream_status` 숫자를 반환합니다. 연결 거절/기타 OSError·URLError는 503, 직접 TimeoutError 또는 URLError.reason TimeoutError는 504입니다.
- 공개 응답은 고정 안전 문구이며 원래 주소·body·예외 문자열을 답변에 넣지 않습니다. chat은 기존 detail envelope, Messages는 기존 error envelope를 유지합니다.
- ModelManager 기존 실패 usage 기록 및 직접 재throw를 사용합니다. manager 소스는 변경하지 않았습니다. 실패 이후 assistant turn 저장은 일어나지 않습니다.
- 정상 `[API Error ...]` 문자열은 단일 모델 응답에서 그대로 성공합니다. 기존 combo prefix 휴리스틱은 이번 범위 밖이며 변경하지 않았습니다. 실제 combo의 typed 예외→다음 모델 fallback은 회귀로 확인했습니다.
- structured validation 오류와 transport 오류는 별도 타입입니다. streaming 경로는 변경하지 않았습니다. 예외 타입은 frozen dataclass가 아니므로 contextmanager의 traceback 재지정이 가능합니다.
- 소유 패치 5개 파일: inference_providers.py, transport_errors.py, chat.py, messages_api.py, test_native_transport_error_contract.py. 시작 dirty preimage 대비 patch이므로 기존 agent streaming 및 Messages 이미지 변경은 포함하지 않습니다.

## 실행 및 관측

최종 실행 명령은 `.venv/bin/python <이 폴더>/verify.py final-v2`이며 실제 하위 argv/cwd/종료 코드는 `final-v2/checks.json`에 있습니다. 새 source snapshot은 `final-v2/source/`입니다.

- final-v2/junit.xml: 새 transport 17개 + 기존 provider 10개 + structured 36개 = 63 passed, 실패/오류/skip 0.
- final-v2/focused.stdout 및 stderr: 원문 로그. pytest asyncio_mode 경고, Starlette TestClient deprecation 경고 2건을 유지했습니다.
- final-v2/lint, format, types, compile stdout/stderr: 4개 검사 모두 exit 0. basedpyright는 --level error이며 이번 출력은 errors/warnings/notes 모두 0입니다.
- final-v2/socket-attempts.json: import 전에 connect/connect_ex/create_connection/bind/listen을 차단한 새 프로세스에서 시도 0.
- final-v2/transport-captures/: fixture 기반 16개 사례, terminal 모의 호출 17회, 성공 usage 5/실패 usage 12. 직접 오류 11개 사례는 각 호출1/실패usage1/저장0, 정상4개 사례는 각 호출1/성공usage1, combo1개는 두 호출/실패1/성공1. 남은 contextmanager1개는 제품 호출 없이 동일 오류 객체 전파를 확인합니다.
- final-v2/route-captures/: 요청/원문 응답과 manager 호출이 저장됩니다. transport 테스트는 terminal을 교체하므로 이 공용 fixture의 provider_calls=0을 실제 무호출 근거로 사용하면 안 됩니다. transport terminal 계수는 위 전용 캡처가 권위입니다.
- task-only.patch / patch-reconstruction.json: dirty preimage에서 5개 파일 재구성 후 현재 소스와 byte-identical. root controlled-wire/는 이 패치/manifest의 소유 범위가 아닙니다.

## 과거 시도와 한계

- 수정 전 red-junit.xml 및 red-stdout/stderr: 9 failed / 4 passed. HTTP 오류가 성공 텍스트가 되는 기존 결함을 보존했습니다. 실행 명령은 PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_native_transport_error_contract.py -q --junitxml=<이 폴더>/red-junit.xml, stdout/stderr를 같은 접두사 파일로 리다이렉트했습니다. 초기 test 소스 별도 snapshot은 없으므로 최종 테스트와 동일 source-bound red라고 주장하지 않습니다. production preimage 3개는 source-preimage/에 있습니다.
- green-v1-junit.xml: 13 passed. 이후 raw refusal/contextmanager/combo 회귀와 캡처를 추가하고 frozen exception을 수정했으므로 최종 승인 근거는 final-v2입니다.
- frozen exception의 traceback 대입 실패는 root의 독립 도구 transcript에서 관측됐으며 worker 원문 로그가 있는 것처럼 재구성하지 않았습니다. 최종 contextmanager 회귀가 수정 경계를 검증합니다.
- 예상하지 못한 decode/protocol/programming 예외는 더 이상 native catch에서 성공 문자열이 되지 않고 상위 기존 일반 오류 처리로 전파됩니다. 이를 새 transport 오류라고 분류하지 않습니다.
- 전체 테스트 suite, 실제 provider, 인증, listener/lifespan, streaming 장애 계약 확장은 이번 검증 범위 밖입니다. final-v2 PASS는 범위 내 오프라인 계약만 증명합니다.
