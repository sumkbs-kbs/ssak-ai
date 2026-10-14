from collections.abc import Iterator
from pathlib import Path
from typing import Callable, cast

import pytest

from antigravity_k.engine.orchestrator import OrchestratorAgent
from antigravity_k.engine.quality_gate import QualityGate, QualityGrade


class _StubRouter:
    """라우터 더블 — 이 테스트가 재는 것은 모델 선택이 아니라 도구 루프이므로
    어떤 이름도 콤보로 판정하지 않는다(`get_combo` → None).

    툴 루프(`tool_loop.run_loop`)는 `manager.router.get_combo(...)` 를 무조건 호출해
    "콤보면 로드 여부 검사를 건너뛴다"를 판단한다 — 실제 `ModelManager` 는 생성자에서
    `self.router` 를 항상 만들므로, 더블도 같은 계약을 진다.
    """

    def get_combo(self, _name: str) -> None:
        return None


class _FakeManager:
    def __init__(self) -> None:
        self.router = _StubRouter()

    def is_loaded(self, name: str) -> bool:
        _ = name
        return True

    def stream_generate(self, *args: object, **kwargs: object) -> Iterator[str]:
        _ = args, kwargs
        yield "ok"


class _QualityRetryManager:
    def __init__(self) -> None:
        self.calls: int = 0
        self.config: dict[str, object] = {}
        self._loaded_models: dict[str, dict[str, object]] = {"model-a": {}, "model-b": {}}
        self.router = _StubRouter()

    def is_loaded(self, name: str) -> bool:
        _ = name
        return True

    def _answer(self) -> str:
        """한 번의 모델 호출 = 한 번의 증가.

        `calls` 는 **모델 호출 횟수**를 세야 한다: 스트림 경로와 동기 경로가 각각
        `_answer` 를 정확히 한 번 부르므로, 첫 답(재시도 유발) → 두 번째 답(복잡도
        포함)에서 `calls == 2` 는 "초기 1회 + 재시도 1회"라는 뜻이다.

        이전 더블은 `stream_generate` 가 `self.generate()` 를 불러 한 턴을 두 번
        세었고, 그 이중 계산이 리팩토링 뒤 단언(`calls == 2`)을 거짓으로 만들었다
        — 세는 방식이 계약이 아니라 구현 세부였다.
        """
        self.calls += 1
        if self.calls == 1:
            return """```python
def gcd(a, b):
    return a
```"""
        return (
            "GCD는 최대공약수를 구하는 함수입니다.\n\n"
            "```python\ndef gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return abs(a)\n```\n\n"
            "시간복잡도는 `O(log(min(a, b)))`, 공간복잡도는 `O(1)`입니다."
        )

    def generate(self, prompt: str = "", target: str = "", **kwargs: object) -> str:
        """동기식 generate (OrchestratorAgent._init_evolution_coordinator 등에서 사용)."""
        _ = prompt, target, kwargs
        return self._answer()

    def stream_generate(self, *args: object, **kwargs: object) -> Iterator[str]:
        _ = args, kwargs
        yield self._answer()

    def get_target_for_role(self, role_name: str = "", default_role: str = "") -> str:
        _ = role_name, default_role
        return "test-model"

    def status(self) -> dict[str, object]:
        return {"loaded_models": []}

    def get_model_info(self) -> dict[str, object]:
        """`ModelManager.get_model_info` 는 `status()` 의 별칭이며 **인자를 받지 않는다**
        (`self_capability._model_info` 가 인자 없이 호출한다).
        """
        return {"loaded_models": []}


def _requires_planning(orchestrator: OrchestratorAgent, task_type: str, messages: list[dict[str, str]]) -> bool:
    callback = cast(Callable[[str, list[dict[str, str]]], bool], getattr(orchestrator, "_requires_planning_mode"))
    return callback(task_type, messages)


def test_orchestrator_planning_mode_skips_simple_coding_request(tmp_path: Path) -> None:
    orchestrator = OrchestratorAgent(
        model_manager=_FakeManager(),
        vault_engine=None,
        project_root=str(tmp_path),
    )

    assert (
        _requires_planning(orchestrator, "coding", [{"role": "user", "content": "Python으로 GCD 함수를 작성해줘"}])
        is False
    )


def test_orchestrator_planning_mode_keeps_large_refactor_guard(tmp_path: Path) -> None:
    orchestrator = OrchestratorAgent(
        model_manager=_FakeManager(),
        vault_engine=None,
        project_root=str(tmp_path),
    )

    assert (
        _requires_planning(
            orchestrator,
            "coding",
            [
                {
                    "role": "user",
                    "content": "플러그인 시스템을 추가하고 아키텍처를 대규모 리팩토링해줘",
                }
            ],
        )
        is True
    )


def test_quality_gate_does_not_force_planning_for_small_code_answer() -> None:
    output = """GCD는 두 수의 최대공약수를 구하는 함수입니다.

```python
def gcd(a, b):
    a, b = abs(a), abs(b)
    while b:
        a, b = b, a % b
    return a
```

시간복잡도는 `O(log(min(a, b)))`, 공간복잡도는 `O(1)`입니다. 입력값 0과 음수도
함께 테스트하면 실제 사용 시 안정성을 높일 수 있습니다.
"""

    score = QualityGate().evaluate("coding", "Python으로 GCD 함수를 작성하고 복잡도도 알려줘", output)

    assert score.grade in (QualityGrade.A, QualityGrade.B)
    assert "복잡한 태스크에서 Planning Mode(계획안 및 승인 요청) 누락 (재시도 필요)" not in score.issues


def test_dashboard_chat_output_uses_codex_like_reading_style() -> None:
    source = Path("dashboard/src/styles/index.css").read_text(encoding="utf-8")

    assert "--sidebar-width: 240px;" in source
    assert ".glass-panel" in source
    assert ".btn-primary" in source
    assert ".btn-secondary" in source
    assert ".btn-ghost" in source
    assert ".status-dot" in source
    assert ".sidebar" in source
    assert ".nav-item" in source
    # 과도한 음수 letter-spacing만 금지 (헤드라인용 미세 조정은 허용)
    assert "letter-spacing: -0.1" not in source


def test_orchestrator_runs_quality_retry_for_code_only_answer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _QualityRetryManager()

    def fake_ceo_analyze(self: object, user_message: str, target_model: str) -> Iterator[dict[str, str]]:
        _ = self, target_model
        yield {
            "task_type": "coding",
            "delegate_to": "WORKER",
            "reasoning": "quality retry test",
            "refined_prompt": user_message,
        }

    monkeypatch.setattr(OrchestratorAgent, "_ceo_analyze", fake_ceo_analyze)

    orchestrator = OrchestratorAgent(
        model_manager=manager,
        vault_engine=None,
        project_root=str(tmp_path),
    )

    # 재시도 예산을 1로 고정한다. 패키지 기본 config 는 `quality_gate.max_retries: 2`
    # 이므로, 예산을 고정하지 않으면 단언이 환경(워크스페이스 config 유무)에 따라
    # 흔들린다. 예산 준수도 이 테스트가 재는 계약의 일부다.
    cast(QualityGate, getattr(orchestrator.ctx, "quality_gate")).max_retries = 1

    output = "".join(
        orchestrator.run_stream(
            [
                {
                    "role": "user",
                    "content": "Python으로 GCD 함수를 작성하고 시간복잡도도 알려줘",
                }
            ],
            target_model="test-model",
            max_steps=2,
        )
    )

    # 초기 1턴 + 재시도 1턴 — 첫 답은 미달로 판정됐고, 재시도가 모델을 다시 불렀다.
    assert manager.calls == 2
    assert "품질 미달" in output
    assert "O(log(min(a, b)))" in output
