# 갱신 의존성 SBOM

기존 release_sbom generate 명령으로 현재 잠금 파일의 Python SBOM과 notices를 생성했습니다. 대시보드 SBOM은 불변입니다. 생성 영수증 및 잠금 파일 SHA를 보존했고, 관련27개 회귀가 통과했습니다. 변경된 두 파일의 패치를 시작 preimage에서 재구성해 바이트 일치를 확인했습니다. 전체 wheel/sdist 소비·GA 승인은 이 집중 검사로 주장하지 않습니다.
