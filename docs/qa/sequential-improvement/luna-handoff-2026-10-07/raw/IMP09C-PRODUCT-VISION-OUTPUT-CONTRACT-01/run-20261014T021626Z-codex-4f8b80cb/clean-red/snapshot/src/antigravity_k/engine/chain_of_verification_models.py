from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class VerificationResult:
    issues_found: list[str] = field(default_factory=list)
    severity: str = "none"
    suggested_fixes: list[str] = field(default_factory=list)
    verification_reasoning: str = ""
    passed: bool = True


@dataclass(frozen=True, slots=True)
class CoVTrace:
    original_response: str = ""
    verification_result: VerificationResult | None = None
    revised_response: str = ""
    total_passes: int = 1
    total_latency_ms: float = 0.0
    skipped: bool = False
    skip_reason: str = ""


COMPLEX_INDICATORS = [
    "아키텍처",
    "설계",
    "리팩토링",
    "마이그레이션",
    "최적화",
    "architecture",
    "design",
    "refactor",
    "migrate",
    "optimize",
    "알고리즘",
    "algorithm",
    "시간복잡도",
    "time complexity",
    "보안",
    "security",
    "취약점",
    "vulnerability",
    "데이터베이스",
    "database",
    "스키마",
    "schema",
    "동시성",
    "concurrency",
    "비동기",
    "async",
    "분산",
    "distributed",
    "캐시",
    "cache",
]

SIMPLE_INDICATORS = [
    "안녕",
    "hello",
    "hi",
    "도움",
    "help",
    "파일 읽",
    "파일 보",
    "목록",
    "list",
    "간단한",
    "simple",
    "basic",
]


def estimate_complexity(task: str) -> float:
    task_lower = (task or "").lower()
    simple_hits = sum(1 for ind in SIMPLE_INDICATORS if ind in task_lower)
    if simple_hits >= 2:
        return 0.1
    complex_hits = sum(1 for ind in COMPLEX_INDICATORS if ind in task_lower)
    has_code_request = any(
        kw in task_lower for kw in ["코드", "code", "함수", "function", "클래스", "class", "구현", "implement"]
    )
    length_factor = min(len(task) / 500, 1.0) * 0.2
    return min((complex_hits * 0.15) + (0.2 if has_code_request else 0.0) + length_factor, 1.0)
