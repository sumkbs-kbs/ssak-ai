# Python 실행 인자 판별 추가 수리

부모 검수에서 일반 스크립트 인자에 포함된 `-m pytest`를 pytest 실행으로 오인하는 결함을 확인했습니다. 인터프리터 옵션을 순서대로 해석하고, 스크립트·`-c`·`--` 또는 다른 실행 대상이 시작되면 탐색을 중단하도록 좁게 수정했습니다. `-B`, `-I`, `-W`/`-X` 값 및 독립 pytest 실행은 유지합니다. seatbelt 허용 경로는 변경하지 않았습니다.

`argv-red-2/`: 같은 새 선택자에서 3 실패 / 4 통과. 일반 스크립트, `python -c`, `python -- app.py`의 인자가 변경되는 것을 실제 샌드박스 프로세스로 재현했습니다.

`argv-green/`: 7 통과. 앞의 세 일반 실행 인자 보존과 `-B`, `-I`, `-W default`, 독립 pytest의 실제 실행·`--` 이후 파일 선택을 확인했습니다. 기존 broad 선택자는 반복하지 않았습니다.

첫 `argv-red/`는 추가 테스트가 없는 이전 파일 사본을 캡처했고 수집 0건·exit 4였습니다. 그 원문과 source snapshot을 보존했으며 실패 재현 또는 성공으로 집계하지 않습니다. 새 이름 `argv-red-2/`에서 최신 테스트 소스를 묶어 실제 red 근거를 확보했습니다.

이 폴더의 checks.json은 정적 검사, task-only.patch는 현재 전체 소유 변경분입니다. 최초 red/source preimage에서 두 파일 바이트 재구성 결과는 patch-reconstruction.json에 있습니다. 기존 최초 handoff/manifest/patch는 수정하지 않았고 이번 판정은 새 7개 사례의 범위에 한정됩니다. runtime 데이터는 공개 manifest에서 제외했습니다. 추가 세 driver 실행마다 loopback 보호 socket을 bind했으므로 이전 4회와 누적 7회이며 전체 syscall 계수는 미계측입니다.

커밋·푸시하지 않았습니다. 독립 검수 PENDING입니다.
