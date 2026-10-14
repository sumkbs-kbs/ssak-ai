"""Ssak-Ai: 벤치마크 과제 세트 (Built-in).

=============================================
collective-council vs 단일 모델 비교를 위한 내장 코딩 과제 정의.

난이도 1~5:
  1: 단순 함수 (피보나치, 문자열)
  2: 한국어/유틸리티
  3: 중급 알고리즘 (BST, LRU)
  4: 리팩토링/디자인 패턴
  5: 아키텍처 설계
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkCase:
    """벤치마크 과제 1건."""

    id: str
    category: str  # simple | algorithm | architecture | korean | refactor
    prompt: str
    difficulty: int  # 1-5
    expected_keywords: tuple[str, ...] = ()
    expected_tools: tuple[str, ...] = ()
    description: str = ""
    # verified_code cases: when set, the harness executes the model's generated
    # code and compares stdout to this value. Measures executed output, not keywords.
    expected_output: str = ""


# ─── 내장 과제 세트 ─────────────────────────────────────────────────

BUILTIN_CASES: tuple[BenchmarkCase, ...] = (
    # ── simple (난이도 1) ──────────────────────────────────────────
    BenchmarkCase(
        id="sim-001",
        category="simple",
        difficulty=1,
        description="피보나치 함수",
        prompt=(
            "Python으로 n번째 피보나치 수를 반환하는 함수 `fibonacci(n: int) -> int`를 작성하세요.\n"
            "- 재귀와 반복 두 가지 방법을 모두 구현하세요.\n"
            "- 각 방법의 시간복잡도를 설명하세요.\n"
            "- n이 음수일 때의 예외 처리를 포함하세요."
        ),
        expected_keywords=("def fibonacci", "O(", "raise", "return"),
    ),
    BenchmarkCase(
        id="sim-002",
        category="simple",
        difficulty=1,
        description="문자열 뒤집기 (유니코드 안전)",
        prompt=(
            "Python으로 유니코드 이모지를 포함한 문자열을 안전하게 뒤집는 함수 "
            "`reverse_unicode(s: str) -> str`를 작성하세요.\n"
            "- '안녕🌍세계' → '계세🌍녕안' 이 올바르게 동작해야 합니다.\n"
            "- grapheme cluster를 고려한 방법과 단순 슬라이싱 방법을 비교하세요."
        ),
        expected_keywords=("def reverse", "return"),
    ),
    # ── algorithm (난이도 3) ───────────────────────────────────────
    BenchmarkCase(
        id="alg-001",
        category="algorithm",
        difficulty=3,
        description="이진 탐색 트리 (BST)",
        prompt=(
            "Python으로 이진 탐색 트리(BST)를 구현하세요.\n"
            "- `insert(val)`, `search(val) -> bool`, `delete(val)` 메서드를 포함하세요.\n"
            "- delete는 자식이 0/1/2인 경우를 모두 처리하세요.\n"
            "- 중위 순회(in-order traversal) 메서드도 추가하세요.\n"
            "- 각 연산의 평균/최악 시간복잡도를 설명하세요."
        ),
        expected_keywords=("class", "insert", "search", "delete", "O("),
    ),
    BenchmarkCase(
        id="alg-002",
        category="algorithm",
        difficulty=3,
        description="LRU 캐시 구현",
        prompt=(
            "Python으로 LRU(Least Recently Used) 캐시를 구현하세요.\n"
            "- `get(key)` 과 `put(key, value)` 모두 O(1)이어야 합니다.\n"
            "- capacity를 초과하면 가장 오래 사용되지 않은 항목을 자동 제거합니다.\n"
            "- OrderedDict 사용 버전과 이중 연결 리스트 + dict 직접 구현 버전을 모두 작성하세요.\n"
            "- 두 구현의 장단점을 비교 표로 정리하세요."
        ),
        expected_keywords=("class", "get", "put", "O(1)"),
    ),
    # ── korean (난이도 2) ─────────────────────────────────────────
    BenchmarkCase(
        id="kor-001",
        category="korean",
        difficulty=2,
        description="한국어 자연수 변환",
        prompt=(
            "Python으로 정수를 한국어 읽기 문자열로 변환하는 함수 "
            "`int_to_korean(n: int) -> str`를 작성하세요.\n"
            "- 예: 12345 → '일만이천삼백사십오'\n"
            "- 1억, 1조 단위까지 지원하세요.\n"
            "- 0과 음수도 처리하세요."
        ),
        expected_keywords=("def int_to_korean", "만", "억", "return"),
    ),
    # ── refactor (난이도 4) ────────────────────────────────────────
    BenchmarkCase(
        id="ref-001",
        category="refactor",
        difficulty=4,
        description="스파게티 코드 리팩토링",
        prompt=(
            "아래의 Python 코드를 SOLID 원칙에 맞게 리팩토링하세요.\n"
            "변경 전후의 구조를 비교 설명하고, 각 원칙이 어떻게 적용되었는지 서술하세요.\n\n"
            "```python\n"
            "def process(data, mode):\n"
            "    result = []\n"
            "    for item in data:\n"
            "        if mode == 'upper':\n"
            "            result.append(item.upper())\n"
            "        elif mode == 'lower':\n"
            "            result.append(item.lower())\n"
            "        elif mode == 'title':\n"
            "            result.append(item.title())\n"
            "        elif mode == 'reverse':\n"
            "            result.append(item[::-1])\n"
            "        elif mode == 'count':\n"
            "            result.append(len(item))\n"
            "        else:\n"
            "            result.append(item)\n"
            "    return result\n"
            "```"
        ),
        expected_keywords=("class", "SOLID", "def"),
    ),
    # ── architecture (난이도 5) ────────────────────────────────────
    BenchmarkCase(
        id="arc-001",
        category="architecture",
        difficulty=5,
        description="FastAPI 플러그인 시스템 설계",
        prompt=(
            "FastAPI 기반 백엔드에 런타임 플러그인 시스템을 설계하세요.\n"
            "- 플러그인은 독립 Python 패키지로 배포되며, 서버 재시작 없이 로드/언로드 가능해야 합니다.\n"
            "- 플러그인은 새 라우트, 미들웨어, 이벤트 핸들러를 등록할 수 있어야 합니다.\n"
            "- 플러그인 간 의존성 관리, 버전 충돌 해결, 샌드박싱 전략을 포함하세요.\n"
            "- 핵심 인터페이스(Protocol/ABC)와 레지스트리 코드를 Python으로 작성하세요.\n"
            "- 아키텍처 다이어그램을 ASCII art로 그려주세요."
        ),
        expected_keywords=("class", "Plugin", "register", "load"),
    ),
    BenchmarkCase(
        id="arc-002",
        category="architecture",
        difficulty=5,
        description="이벤트 소싱 CQRS 설계",
        prompt=(
            "Python으로 이벤트 소싱(Event Sourcing) + CQRS 패턴을 설계하세요.\n"
            "- Command 핸들러, Event Store, Projection(Read Model) 핵심 컴포넌트를 구현하세요.\n"
            "- 이벤트 저장소는 append-only이며, 스냅샷을 통한 복원을 지원해야 합니다.\n"
            "- 간단한 은행 계좌 도메인(입금, 출금, 잔액 조회)으로 예시를 들어주세요.\n"
            "- 이벤트 소싱의 장점과 단점, 적합한 사용 사례를 설명하세요."
        ),
        expected_keywords=("Event", "Command", "class", "append"),
    ),
    BenchmarkCase(
        id="lh-001",
        category="long_horizon",
        difficulty=5,
        description="체크포인트 기반 장기 작업 복구",
        prompt=(
            "여러 단계로 구성된 코드 마이그레이션 작업을 계획하고 실행하는 에이전트 워크플로를 설계하세요.\n"
            "- 먼저 저장소를 분석하고, 변경 계획과 의존성 순서를 checkpoint에 저장하세요.\n"
            "- 각 단계에서 사용할 도구와 성공 조건을 명시하고, 중간 실패 시 마지막 checkpoint에서 recovery 하세요.\n"
            "- 재시작 후 이미 완료된 단계는 idempotency로 건너뛰고, 최종 검증과 rollback 절차를 포함하세요.\n"
            "- 단계별 task outcome에 성공 여부, 재시도 횟수, latency, 사용 도구를 기록하세요."
        ),
        expected_keywords=("checkpoint", "recovery", "idempotency", "rollback", "retry"),
    ),
    # ── search (난이도 1~2, Phase 1 검증) ─────────────────────────
    BenchmarkCase(
        id="srch-001",
        category="search",
        difficulty=1,
        description="주가 조회 (Fast-Path + 적응형 샘플링 검증)",
        prompt=(
            "한화에어로스페이스 오늘 종가를 알려줘.\n"
            "- 종가, 전일 대비, 거래량을 마크다운 테이블로 정리해줘.\n"
            "- 출처를 명시해줘."
        ),
        expected_keywords=("한화에어로스페이스", "종가", "|", "출처"),
        expected_tools=("web_search",),
    ),
    BenchmarkCase(
        id="srch-002",
        category="search",
        difficulty=2,
        description="실시간 뉴스 검색 + 요약",
        prompt=(
            "AI 반도체 시장의 최신 동향을 웹 검색으로 조사하고 핵심 3가지를 정리해줘.\n"
            "- 각 동향에 출처 링크를 포함해줘.\n"
            "- 마크다운 리스트 형식으로 작성해줘."
        ),
        expected_keywords=("반도체", "AI", "출처"),
        expected_tools=("web_search",),
    ),
    # ── analysis (난이도 3, Phase 2 검증) ─────────────────────────
    BenchmarkCase(
        id="anl-001",
        category="analysis",
        difficulty=3,
        description="기술 비교 분석 (품질 게이트 + 계층형 프롬프트 검증)",
        prompt=(
            "로컬 LLM 추론 프레임워크를 비교 분석해줘.\n"
            "- Ollama, LM Studio, llama.cpp, vLLM 4가지를 비교해줘.\n"
            "- 설치 편의성, 성능, GPU 지원, API 호환성 기준으로 마크다운 비교 표를 만들어줘.\n"
            "- 각각의 장단점과 추천 사용 시나리오를 설명해줘."
        ),
        expected_keywords=("Ollama", "llama.cpp", "|", "장점", "단점"),
    ),
    BenchmarkCase(
        id="anl-002",
        category="analysis",
        difficulty=3,
        description="아키텍처 분석 리포트",
        prompt=(
            "마이크로서비스 아키텍처(MSA)와 모놀리식 아키텍처의 차이를 분석해줘.\n"
            "- 확장성, 배포, 팀 구성, 복잡도 관점에서 비교 표를 작성해줘.\n"
            "- 각 아키텍처가 적합한 프로젝트 유형을 구체적으로 제시해줘.\n"
            "- 실제 마이그레이션 시 주의사항도 포함해줘."
        ),
        expected_keywords=("마이크로서비스", "모놀리식", "|", "확장"),
    ),
    # ── creative (난이도 2, 적응형 샘플링 CREATIVE 프로파일 검증) ──
    BenchmarkCase(
        id="crv-001",
        category="creative",
        difficulty=2,
        description="기술 블로그 글 작성",
        prompt=(
            "Python의 비동기 프로그래밍(asyncio)에 대한 기술 블로그 글을 작성해줘.\n"
            "- 초보자도 이해할 수 있는 수준으로 작성해줘.\n"
            "- 비유와 예제 코드를 포함해줘.\n"
            "- 1000자 이상으로 작성해줘."
        ),
        expected_keywords=("asyncio", "await", "async", "def"),
    ),
    # ── regression (Phase 1-3 회귀 검증) ─────────────────────────
    BenchmarkCase(
        id="reg-001",
        category="regression",
        difficulty=2,
        description="품질 게이트 회귀: 코드-only 응답 차단 확인",
        prompt=("Python으로 버블 정렬을 구현해줘.\n- 시간복잡도를 설명해줘.\n- 최적화 방법도 알려줘."),
        expected_keywords=("def", "O(", "최적화", "설명"),
    ),
    BenchmarkCase(
        id="reg-002",
        category="regression",
        difficulty=2,
        description="한국어 답변 품질 회귀: 외국어 오염 없음 확인",
        prompt=("TCP와 UDP의 차이를 설명하고, 각각 적합한 사용 사례를 3가지씩 들어줘."),
        expected_keywords=("TCP", "UDP", "사례"),
    ),
    BenchmarkCase(
        id="reg-003",
        category="regression",
        difficulty=1,
        description="자기소개 회귀: 없는 기능 언급 차단 확인",
        prompt="너를 소개하고 니가 할 수 있는 일과 할 수 없는 일을 알려줘.",
        expected_keywords=("할 수 있", "할 수 없"),
    ),
    # ── verified_code (난이도 1~2, 실행 결과 검증) ─────────────────
    BenchmarkCase(
        id="verf-001",
        category="verified_code",
        difficulty=1,
        description="코드 실행 결과 검증 (함수형 합계)",
        prompt=(
            "Python으로 1부터 n까지의 합을 구하는 함수 sum_to(n)을 작성하고, "
            "sum_to(100)의 결과를 print로 출력하는 실행 가능한 코드를 제출하세요.\n"
            "- 반드시 실행 가능한 단일 Python 코드 블록을 포함하세요.\n"
            "- 실행하면 5050이 출력되어야 합니다."
        ),
        expected_output="5050",
    ),
    BenchmarkCase(
        id="verf-002",
        category="verified_code",
        difficulty=2,
        description="코드 실행 결과 검증 (리스트 컴프리헨션)",
        prompt=(
            "1부터 20까지의 숫자 중 3의 배수만 골라 그 합을 구하는 Python 코드를 작성하고 "
            "결과를 print로 출력하세요.\n"
            "- 실행 가능한 단일 Python 코드 블록을 포함하세요."
        ),
        expected_output="63",
    ),
    BenchmarkCase(
        id="verf-003",
        category="verified_code",
        difficulty=3,
        description="코드 실행 결과 검증 (알고리즘: FizzBuzz)",
        prompt=(
            "FizzBuzz를 구현하는 Python 코드를 작성하고 실행하세요.\n"
            "- 1부터 15까지 숫자에 대해:\n"
            "  - 3의 배수는 Fizz, 5의 배수는 Buzz, 15의 배수는 FizzBuzz, "
            "그 외는 숫자 자체를 출력합니다.\n"
            "- 각 결과를 한 줄씩 print로 출력하세요 (총 15줄).\n"
            "- 반드시 실행 가능한 단일 Python 코드 블록을 포함하세요."
        ),
        expected_output=("1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n11\nFizz\n13\n14\nFizzBuzz"),
    ),
    BenchmarkCase(
        id="verf-004",
        category="verified_code",
        difficulty=3,
        description="코드 실행 결과 검증 (알고리즘: 소수 판별 합계)",
        prompt=(
            "1부터 20까지의 숫자 중 소수(prime number)만 찾아 그 합을 구하는 Python 코드를 작성하고 실행하세요.\n"
            "- 소수는 1과 자기 자신만 약수로 갖는 1보다 큰 정수입니다.\n"
            "- 합계를 print로 출력하세요.\n"
            "- 실행 가능한 단일 Python 코드 블록을 포함하세요."
        ),
        expected_output="77",
    ),
)

_FRONTIER_CASE_IDS = ("sim-001", "alg-001", "srch-002", "anl-001", "lh-001")


def get_suite(name: str = "all") -> list[BenchmarkCase]:
    """과제 세트를 반환합니다.

    Args:
       name: "all", "frontier", "simple", "algorithm", "architecture", "korean", "refactor",
             "search", "analysis", "creative", "regression", "long_horizon",
             또는 개별 case id (예: "sim-001")

    """
    if name == "all":
        return list(BUILTIN_CASES)

    if name == "frontier":
        cases_by_id = {case.id: case for case in BUILTIN_CASES}
        return [cases_by_id[case_id] for case_id in _FRONTIER_CASE_IDS]

    # 개별 ID 매칭
    for case in BUILTIN_CASES:
        if case.id == name:
            return [case]

    # 카테고리 매칭
    matched = [c for c in BUILTIN_CASES if c.category == name]
    if matched:
        return matched

    return list(BUILTIN_CASES)


"""Ssak-Ai Benchmark Cases — Built-in coding challenge suite."""
