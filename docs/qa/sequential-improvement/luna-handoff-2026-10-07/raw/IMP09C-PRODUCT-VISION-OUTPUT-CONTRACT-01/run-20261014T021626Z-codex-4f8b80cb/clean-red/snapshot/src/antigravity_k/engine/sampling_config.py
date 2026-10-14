"""Ssak-Ai: 중앙 집중형 샘플링 프로파일 (Single Source of Truth).

================================================================
모든 모듈은 이 모듈에서 SAMPLING_PROFILES를 임포트해야 합니다.
model_manager, tool_executor 등에서 중복 정의를 제거합니다.
"""

from dataclasses import dataclass


@dataclass
class SamplingProfile:
    """작업 유형별 최적 샘플링 파라미터.

    연구 근거:
      - Min-P는 Top-P보다 저확률 토큰(환각 원인)을 효과적으로 가지치기
      - 사실 기반 작업에는 낮은 temperature, 창의적 작업에는 높은 temperature
    """

    temperature: float
    min_p: float
    repeat_penalty: float
    top_p: float = 0.9
    description: str = ""


SAMPLING_PROFILES: dict[str, SamplingProfile] = {
    "SEARCH": SamplingProfile(
        temperature=0.15,
        min_p=0.05,
        repeat_penalty=1.3,
        description="사실 기반 검색/조회 (환각 최소화)",
    ),
    "CODE": SamplingProfile(
        temperature=0.25,
        min_p=0.1,
        repeat_penalty=1.2,
        description="코드 생성/디버깅 (정확도 우선)",
    ),
    "ANALYSIS": SamplingProfile(
        temperature=0.35,
        min_p=0.08,
        repeat_penalty=1.3,
        description="분석/리포트 (논리적 추론)",
    ),
    "CREATIVE": SamplingProfile(
        temperature=0.7,
        min_p=0.02,
        repeat_penalty=1.1,
        description="창의적 글쓰기 (다양성 우선)",
    ),
    "GENERAL": SamplingProfile(
        temperature=0.5,
        min_p=0.05,
        repeat_penalty=1.3,
        description="일반 대화 (균형)",
    ),
}


def resolve_sampling_profile(task_type: object) -> SamplingProfile:
    """작업 유형에 대응하는 샘플링 프로파일을 반환한다.

    라이브 경로의 task_type은 소문자("code", "chat", "search")로 전달되는데
    프로파일 키는 대문자이므로 정규화 없으면 항상 GENERAL로 폴백된다.
    모든 조회는 이 함수를 통해서만 수행한다 (Single Source of Truth).
    """
    if not isinstance(task_type, str) or not task_type.strip():
        return SAMPLING_PROFILES["GENERAL"]
    return SAMPLING_PROFILES.get(task_type.strip().upper(), SAMPLING_PROFILES["GENERAL"])
