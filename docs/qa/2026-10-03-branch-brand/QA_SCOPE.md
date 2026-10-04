# 하단 브랜치 표시 검증 범위

사용자가 명시한 대상은 하단 Git 브랜치 표기다. codex/ 접두사를 ssak-ai/로 화면에서 표시하고 title 속성에 실제 브랜치를 보존한다. 이 별칭은 Git 브랜치 변경이 아니며 실제 환경/프로젝트 패널의 브랜치 이름, 외부 Codex 제공자, 명령어, 데이터는 바꾸지 않는다.

열거된 전체 상태: 채팅 하단 context의375/768/1280×954 변경 전후6개 및 기본757×954 최종1개=원본7개. 같은크기 비교PNG6개는 원본JPEG의 decoded RGB를 그대로 변환했다. 전3개는 baselineException이며 최종4개는 마지막소스수정/빌드후 새 캡처다. 브라우저에서 현재저장된대화의 table 클릭으로 동일본문위치를 잡았고, 새요청/삭제/저장/PIN변경은 하지 않았다. 1280sidebar는 이전스크롤과 reload후초기위치가 다르며 이 상태차이를 diff에서 설명한다. liveclock도 실제차이다.

실제 DOM 측정: 하단 ssak-ai/m1-task-events, title=실제 Git 브랜치: codex/m1-task-events, 모든document폭=viewport, branchBounds가뷰포트 안에 있음. 기존대화/모델/빈입력 유지. 기본창복원/현재탭산출물 유지. BROWSER_LOGS.json warn/error없음.

변경은 ChatPage의1줄 JSX표시식과 DESIGN계약1줄이다. anchored /^codex\//만 대체하므로 다른접두사/중간문자열은변경하지 않는다. 기존조건부emptybranch숨김/원본데이터유지. reversiblelabelchange의 구현을복제하는새테스트는추가하지 않았다. tsc와Vite배포빌드exit0; 기존pnpm실행검증문제때문에설치된실행파일직접사용. 사용자선호에따라BiomeLSP추가설치없음. Lighthouse/전체axe/OSIME/새모델실행 검증주장없음.

최종읽기전용검토자둘은 전체7원본+6비교PNG 및 모든diffhotspot을 직접 확인한다. 이전응답스타일승인은이번코드승인으로재사용하지 않는다.
