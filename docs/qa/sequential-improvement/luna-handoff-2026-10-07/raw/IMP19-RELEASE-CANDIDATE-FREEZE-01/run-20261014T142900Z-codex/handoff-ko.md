# 공식 게이트용 후보 동결 준비

선택 후보는 사용자 작업 폴더의 모든 변경을 합친 트리가 아니라, 검증한 개선만 게시한 managed clean 사본입니다. ROOT의 기존 별도 UI·bundle·SBOM 변경과 staged97개는 보존합니다. 현재 ROOT 브라우저 검수 결과를 이 clean 번들의 전체 UI 검증으로 승계하지 않습니다.

source 기준 `c472d4fcd7c52a045f9bd0a0c07bba582ff51b54`에서 dashboard provenance를 고정하고 번들을 생성했습니다. TypeScript build는 통과했고 provenance 시각을 준비 시점의 UTC로 확정한 Vite 생성 원문은 bundle.stdout.txt/bundle.stderr.txt에 보존합니다. 기존 500kB chunk 경고는 유지합니다. Python SBOM 67개, dashboard SBOM 241개와 notices를 생성했습니다.

이는 정식 23gate 및 새8시간 soak의 통과가 아닙니다. 생성 산출물을 커밋한 뒤 후보 SHA·manifest·작업 트리 코드 지문을 고정하고 gate 명령을 수행해야 합니다. Docker daemon은 실제 info에서 29.8.1로 관찰했으며 공개 배포나 릴리스 승인은 별도입니다.
