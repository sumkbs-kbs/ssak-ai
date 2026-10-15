# Doctor 테스트 격리 수정

범위는 WT2 `tests/test_doctor.py` 한 파일입니다. 제품 소스와 WT3는 수정하지 않았고 커밋/푸시는 하지 않았습니다.

원래 사례는 `ProviderCapabilityProbe.observe`만 모의하고 실제 설정의 모델 순서에 의존했습니다. 게이트의 `yaml.safe_dump` 설정 재작성은 모델 그룹을 정렬하므로 coding이 reasoning보다 먼저 옵니다. Doctor는 provider별 첫 모델을 대표로 고르므로 Ollama의 대표가 qwen3.8에서 qwen3-coder-next로 바뀝니다. 이는 제품 오류가 아니라 테스트의 고정 모델명 전제 문제입니다.

`red-01`은 SourcePlan 기본 환경에서 통과한 기록입니다. `red-02-ambient`는 빈 외부 카탈로그에서 실패한 별도 감도 검사입니다. 실제 게이트의 추가 환경과 정렬된 설정을 적용한 `red-03-full-env`에서 기존 사례가 qwen3.8 단언으로 실패했고, 같은 조건의 `green-01-full-env`에서 수정 사례와 CLI help/runtime 인접 사례 3개가 통과했습니다. 별도 ambient 사례도 수정 후 통과했습니다.

수정은 세 provider 프로필을 담은 임시 파일로 실제 ModelRegistry를 만들고 CLI에 주입합니다. 기존 출력 단언을 모두 유지하고 관찰된 프로필 및 refresh=False의 정확한 호출 순서를 추가했습니다. 포트 확인은 모의합니다. 제품 capability/remediation 구현은 그대로 호출합니다.

정적 검사 원문은 `candidate-01-static/`에 있습니다. Ruff lint/format, Basedpyright, 메모리 compile 모두 exit 0입니다. Basedpyright는 전후 모두 오류/경고 0입니다. `task-only.patch`를 저장된 수정 전 바이트에 적용해 최종 파일과 일치함을 확인했습니다.

테스트 socket connect/bind/listen 가드 위반은 0입니다. 원래 probe는 테스트가 모의하므로 실제 provider HTTP 또는 추론을 실행하지 않습니다. Full-env 하네스는 endpoint를 고정하기 위해 포트 하나를 bind하고 listen 없이 보유했다가 닫습니다. 이 바인딩을 실제 제품 listener로 세지 않습니다.

판정은 COMPLETE_OFFLINE / 독립 검수 PENDING입니다. 전체 Python suite 및 23개 게이트 통과를 뜻하지 않습니다. 이후 상위 에이전트가 합친 후보에서 검수와 정규 게이트를 진행해야 합니다.
