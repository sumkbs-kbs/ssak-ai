# 실패 원인과 테스트 보강의 구분

실제 실패 유발 요인은 full-gate 하네스의 `yaml.safe_dump` 기본 `sort_keys=True`가 원래 설정 그룹 순서를 바꾼 것입니다. Doctor의 provider별 첫 모델 선택은 원래 제품 동작입니다. 따라서 이 실패를 제품 Doctor 결함으로 분류하지 않습니다.

이 추가 실행은 저장된 원래 test preimage를 고유 overlay에서 사용하고, 같은 full-gate 환경과 endpoint 치환을 유지하되 직렬화만 `sort_keys=False`로 바꿉니다. 원래 모델 그룹 순서가 유지되는지 실행 전에 단언하며, 원본 테스트 단일 사례를 정확히 한 번 실행합니다. 실제 결과는 `receipt.json`과 `junit.xml`이 권위입니다.

현재 적용된 explicit real-registry fixture 수정은 별도의 테스트 hermeticity 보강입니다. Doctor 제품 수정이나 하네스 순서 문제의 필수 수리로 설명하지 않습니다. 하네스의 `sort_keys=False` 수정은 상위 작업 소유자가 처리합니다.

이번 작업은 기존 제품·테스트 소스, 이전 64개 산출물 및 manifest를 수정하지 않습니다. 정적 검사를 반복하지 않습니다. 기존 test guard와 provider OS profile을 사용하며, 하네스가 endpoint 예약용 포트 하나를 listen 없이 소유합니다.
