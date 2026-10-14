# revision-v4 부분 준비

live 승인 NOT_ISSUED, 제품 server 수정 게시 후 계획 재바인딩 대기. 실제 실행하지 않았습니다.

변경은 guard.py의 정확한 표준 라이브러리 read probe 허용입니다. executable은 file 또는 /usr/bin/file, argv는 정확히 [executable, -b, 실제 resolved sys.executable], PATH=/usr/bin:/bin이어야 합니다. /usr/bin/file 및 설치 platform.py SHA가 동결값과 맞아야 하며 argv와 두 해시는 기존 subprocesses 문자열 목록에 JSON으로 기록합니다. 다른 파일·옵션·추가 인자·셸·가짜 실행 경로·오염 PATH는 거절합니다. 기존 네트워크/파일쓰기/model guard는 유지합니다.

새 정책 검사 red 2 failed/6 passed, 최종 final-v2 8 passed. 정적 검사 4개 exit0. 첫 두 검사에서 import 순서 오류가 남았던 원문도 보존했습니다. 기존 ownership32 및 환경6은 재실행하지 않았습니다. final-v2/boundary.json은 process/socket/product import 0입니다.

v3 실제 실행은 전체 NO_SUCCESS이며 실패를 성공으로 승격하지 않습니다. 부모 관측의 네 HTTP 응답과 성공 종료는 해당 후보에만 적용됩니다. 원본 private 포함 파일은 보존하고 여기 복사하지 않았습니다. plan/approval은 아직 생성하지 않았습니다.
