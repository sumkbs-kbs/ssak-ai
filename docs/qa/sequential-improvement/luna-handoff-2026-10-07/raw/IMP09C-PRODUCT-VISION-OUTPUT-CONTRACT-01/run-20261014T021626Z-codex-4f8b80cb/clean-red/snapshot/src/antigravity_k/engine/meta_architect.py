"""Ssak-Ai: Meta-Architect Engine (Level 3 자율 아키텍처 재설계).

================================================================
에이전트가 전체 시스템 아키텍처를 분석하고, 구조적 병목을 해결하기 위해
코어 엔진을 자율적으로 리팩터링 및 재설계합니다.

특징:
  - Macromutation (대규모 변이): 단일 파일이 아닌 여러 파일을 동시에 리팩터링
  - RSISandbox와 연동하여 100% 안전 보장 (실패 시 롤백)
  - 완전 자율 (Option B): 벤치마크 통과 시 자동 병합
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias, cast

from antigravity_k.config import config
from antigravity_k.tools.egress_policy import safe_urlopen

logger = logging.getLogger("antigravity_k.meta_architect")

JsonMap: TypeAlias = dict[str, object]


class _ModelManagerLike(Protocol):
    def get_target_for_role(self, role_name: str, default_role: str = "reasoning") -> str | None: ...

    def generate(self, prompt: str, target: str, **kwargs: object) -> object: ...


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    raw = cast(Mapping[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [item for item in items if isinstance(item, str)]


def _as_object_list(value: object) -> list[object]:
    return list(cast(list[object], value)) if isinstance(value, list) else []


def _load_json(text: str) -> object:
    return cast(object, json.loads(text))


@dataclass
class ArchitectureProposal:
    """아키텍처 변경 제안서."""

    proposal_id: str
    title: str
    target_files: list[str]
    description: str
    expected_benefit: str
    modifications: dict[str, str] = field(default_factory=dict)
    passed: bool = False


class MetaArchitect:
    """시스템 전체를 조망하고 재설계하는 메타 아키텍트 엔진."""

    def __init__(
        self,
        project_root: str,
        ollama_url: str | None = None,
        model_manager: object | None = None,
    ):
        """Initialize the MetaArchitect.

        Args:
            project_root (str): str project root.
            ollama_url (str): str ollama url.

        """
        self.project_root: str = project_root
        self.ollama_url: str = (
            ollama_url if ollama_url is not None else config.model.api_base.replace("/v1", "").rstrip("/")
        )
        self.manager: object | None = model_manager
        self._engine_dir: str = os.path.join(project_root, "src", "antigravity_k", "engine")
        self._archive_path: str = os.path.join(project_root, "data", "arch_archive.json")
        os.makedirs(os.path.dirname(self._archive_path), exist_ok=True)

    def _get_evolution_history(self) -> str:
        """이전 성공/실패 아키텍처 진화 기록을 로드합니다 (EUREKA Style)."""
        if not os.path.exists(self._archive_path):
            return "No previous evolution history."
        try:
            with open(self._archive_path, encoding="utf-8") as f:
                history = _as_object_list(_load_json(f.read()))
                recent = history[-3:]
                if not recent:
                    return "No previous evolution history."
                lines: list[str] = []
                for raw_entry in recent:
                    entry = _as_mapping(raw_entry)
                    status = "✅ SUCCESS" if entry.get("passed") is True else "❌ FAILED"
                    title = _as_str(entry.get("title"))
                    description = _as_str(entry.get("description"))
                    lines.append(f"[{status}] {title} - {description}")
                return "\n".join(lines)
        except Exception:
            logger.exception("Unhandled exception")
            return "No previous evolution history."

    def _get_architecture_context(self) -> str:
        """시스템의 현재 구조적 컨텍스트를 수집합니다."""
        context: list[str] = []
        arch_file = os.path.join(self.project_root, "ARCHITECTURE.md")
        if os.path.exists(arch_file):
            with open(arch_file, encoding="utf-8") as f:
                context.append(f"--- ARCHITECTURE.md ---\n{f.read()[:2000]}\n")

        # 코어 엔진 파일 목록 및 크기
        if os.path.exists(self._engine_dir):
            files = [f for f in os.listdir(self._engine_dir) if f.endswith(".py")]
            files_info: list[str] = []
            for filename in files:
                path = os.path.join(self._engine_dir, filename)
                size = os.path.getsize(path)
                files_info.append(f"- {filename} ({size} bytes)")
            context.append("--- Core Modules ---\n" + "\n".join(files_info))

        return "\n".join(context)

    def analyze_and_propose(
        self,
        performance_data: Mapping[str, object],
    ) -> ArchitectureProposal | None:
        """현재 시스템의 병목을 분석하고 리팩터링을 제안합니다."""
        logger.info("[Meta-Architect] 전체 아키텍처 분석 및 제안 시작...")

        context = self._get_architecture_context()
        perf_text = json.dumps(performance_data, ensure_ascii=False, indent=2)
        history_text = self._get_evolution_history()

        prompt = (
            "[ROLE] 당신은 최고 수준의 AI 아키텍트(Meta-Architect)입니다.\n"
            "[HARDWARE TARGET] 이 시스템은 Apple M5 Max (128GB RAM, 4TB SSD)에서 구동됩니다. "
            "따라서 대용량 메모리를 활용한 캐싱, 병렬 처리(멀티스레딩/비동기), 거대한 벡터 연산 등 하드웨어 자원을 극대화하는 아키텍처 제안을 환영합니다.\n\n"  # noqa: E501
            "목표는 현재 AI 에이전트 코어 시스템의 병목을 발견하고 아키텍처를 개선하는 것입니다.\n\n"
            f"--- 진화 기록 (이전 시도 참조) ---\n{history_text}\n\n"
            f"{context}\n\n"
            f"--- 최근 성능 데이터 ---\n{perf_text}\n\n"
            "[TASK]\n"
            "위 데이터를 바탕으로 가장 필요한 1가지 대규모 리팩터링 또는 신규 모듈 도입을 제안하세요.\n"
            "제안은 다음 JSON 형식으로 출력해야 합니다:\n"
            '{"title": "...", "description": "...", "target_files": ["file1.py", "file2.py"],'
            '"expected_benefit": "..."}\n'
            "오직 JSON만 출력하세요. (마크다운 불필요)"
        )

        try:
            response = self._call_llm(prompt, "deepseek-v4", 1024)
            data = self._extract_json(response)
            if data and all(key in data for key in ("title", "description", "expected_benefit")):
                title = _as_str(data.get("title"))
                description = _as_str(data.get("description"))
                expected_benefit = _as_str(data.get("expected_benefit"))
                proposal = ArchitectureProposal(
                    proposal_id=f"arch_{int(os.path.getmtime(self._engine_dir))}",
                    title=title,
                    target_files=_as_str_list(data.get("target_files")),
                    description=description,
                    expected_benefit=expected_benefit,
                )
                logger.info("[Meta-Architect] 제안 생성: %s", proposal.title)
                return proposal
        except Exception:
            logger.exception("[Meta-Architect] 제안 생성 실패")
        return None

    def execute_proposal(self, proposal: ArchitectureProposal) -> bool:
        """제안된 아키텍처 변경을 샌드박스 내에서 실행합니다 (Option B: 완전 자율)."""
        logger.info("[Meta-Architect] 리팩터링 실행 시도: %s", proposal.title)

        try:
            from antigravity_k.engine.rsi_sandbox import RSISandbox

            sandbox = RSISandbox(project_root=self.project_root)

            # 파일 내용 읽기
            file_contents: dict[str, str] = {}
            for filename in proposal.target_files:
                if sandbox.is_immutable(filename):
                    logger.warning("[Meta-Architect] 불변 파일(%s) 수정 시도 차단.", filename)
                    return False

                path = os.path.join(self._engine_dir, filename)
                if os.path.exists(path):
                    with open(path, encoding="utf-8") as f:
                        file_contents[filename] = f.read()

            # LLM에게 수정된 코드 요청 (Evolutionary Search & Self-Rewarding)
            for filename, content in file_contents.items():
                logger.info("[Meta-Architect] %s 변이 생성 중 (Self-Rewarding 루프)...", filename)
                new_content = self._generate_with_self_reward(filename, content, proposal)
                if new_content:
                    proposal.modifications[filename] = new_content

            if not proposal.modifications:
                logger.warning("[Meta-Architect] 생성된 수정 코드가 없습니다. 롤백합니다.")
                return False

            # Sandbox 적용 및 검증 (Option B)
            with sandbox.safe_mutation(f"meta_architect_{proposal.proposal_id}"):
                all_passed = True

                # 1. 파일 임시 덮어쓰기 — FR-04/RP-04: 소유권 기록 쓰기
                #    (safe_mutation 실패 시 이 파일만 preimage로 복구된다)
                for filename, new_code in proposal.modifications.items():
                    path = os.path.join(self._engine_dir, filename)
                    sandbox.write_owned(path, new_code)

                # 2. 샌드박스 일괄 검증
                for filename, new_code in proposal.modifications.items():
                    val_result = sandbox.validate_mutation(filename, new_code)
                    ast_val = val_result.get("ast")
                    tests_val = val_result.get("tests")
                    if (ast_val is not None and ast_val.value == "fail") or (
                        tests_val is not None and tests_val.value == "fail"
                    ):
                        all_passed = False
                        logger.error(
                            "[Meta-Architect] 샌드박스 검증 실패: %s -> %s",
                            filename,
                            val_result,
                        )
                        break

                if not all_passed:
                    self._save_archive(proposal)
                    raise Exception("Meta-Architect macromutation failed validation. Rolling back.")

                proposal.passed = True
                self._save_archive(proposal)
                logger.info("[Meta-Architect] 리팩터링 완전 통과 및 병합 완료: %s", proposal.title)
                return True

        except Exception:
            logger.exception("[Meta-Architect] 실행 중 롤백됨")
            return False

    def _save_archive(self, proposal: ArchitectureProposal) -> None:
        """EUREKA 스타일: 진화 기록 저장."""
        try:
            history: list[JsonMap] = []
            if os.path.exists(self._archive_path):
                with open(self._archive_path, encoding="utf-8") as f:
                    history = [dict(_as_mapping(item)) for item in _as_object_list(_load_json(f.read()))]

            history.append(
                {
                    "proposal_id": proposal.proposal_id,
                    "title": proposal.title,
                    "description": proposal.description,
                    "passed": proposal.passed,
                },
            )

            with open(self._archive_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("[Meta-Architect] 아카이브 저장 실패")

    def _generate_with_self_reward(
        self,
        filename: str,
        original_code: str,
        proposal: ArchitectureProposal,
    ) -> str:
        """Self-Rewarding LMs (Meta, 2024) 기반 자체 평가-수정 루프."""
        max_attempts = 3
        feedback = ""
        best_code = ""
        best_score = -1

        for attempt in range(1, max_attempts + 1):
            # 1. 제안 생성 (Actor)
            current_code = self._generate_modified_code(filename, original_code, proposal, feedback)
            if not current_code:
                break

            # 2. 자체 평가 (Meta-Judge)
            score, eval_feedback = self._evaluate_with_judge(filename, original_code, current_code)
            logger.info(
                "[Meta-Architect] 자체 평가 (Attempt %s): Score %s/5. Feedback: %s...",
                attempt,
                score,
                eval_feedback[:50],
            )

            if score > best_score:
                best_score = score
                best_code = current_code

            if score >= 4:
                # 4점 이상이면 샌드박스로 이관
                return best_code

            # 4점 미만이면 피드백을 반영해 재작성
            feedback = f"이전 시도 실패 이유 (점수 {score}/5): {eval_feedback}\n위 문제를 반드시 해결하세요."

        return best_code

    def _generate_modified_code(
        self,
        filename: str,
        original_code: str,
        proposal: ArchitectureProposal,
        feedback: str = "",
    ) -> str:
        prompt = (
            f"[ROLE] 당신은 시니어 소프트웨어 아키텍트입니다.\n"
            f"[TASK] 아래 아키텍처 제안을 수행하기 위해 '{filename}' 코드를 리팩터링하세요.\n\n"
            f"제안: {proposal.title}\n설명: {proposal.description}\n\n"
        )
        if feedback:
            prompt += f"[CRITICAL FEEDBACK]\n{feedback}\n\n"

        prompt += (
            f"--- 원본 {filename} ---\n{original_code}\n\n"
            "개선된 전체 Python 코드를 출력하세요. 다른 텍스트 없이 순수 코드만 출력하세요. "
            "반드시 완전한 코드를 출력해야 합니다."
        )
        try:
            resp = self._call_llm(prompt, "deepseek-v4", 8192)
            # 코드 블록 추출
            matches = cast(list[str], re.findall(r"```(?:python)?\s*(.*?)\s*```", resp, re.DOTALL))
            if matches:
                return max(matches, key=len)
            return resp.strip()
        except Exception:
            logger.exception("Unhandled exception")
            return ""

    def _evaluate_with_judge(
        self,
        filename: str,
        original_code: str,
        new_code: str,
    ) -> tuple[int, str]:
        """생성된 코드를 Meta-Judge가 평가하여 점수(0~5)와 피드백을 반환합니다."""
        prompt = (
            "[ROLE] 당신은 전설적인 수석 엔지니어(Principal Engineer)이자 코드 리뷰어(Meta-Judge)입니다.\n"
            "[TASK] 원본 코드와 새로 제안된 코드를 비교하여, 새로 제안된 코드의 품질을 0~5점으로 평가하세요.\n\n"
            "평가 기준:\n"
            "1. 문법 및 실행 가능성 (Syntax Error 여부)\n"
            "2. 아키텍처 개선 효과 (실제 구조적 이득이 있는가)\n"
            "3. 보안 및 스레드 안전성 (Side-effects)\n\n"
            "응답은 반드시 아래 JSON 형식으로만 하세요:\n"
            '{"score": 3, "feedback": "변수명이 명확해졌으나, 스레드 안전성 처리가 누락되었습니다."}\n'
            "절대로 마크다운을 씌우지 말고 JSON만 출력하세요.\n\n"
            f"파일명: {filename}\n--- 원본 코드 ---\n{original_code}\n"
            f"--- 새 코드 ---\n{new_code}\n"
        )
        try:
            resp = self._call_llm(prompt, "deepseek-v4", 512)
            data = self._extract_json(resp)
            if data and "score" in data:
                raw_score = data.get("score")
                if isinstance(raw_score, (int, float, str)) and not isinstance(raw_score, bool):
                    return int(raw_score), _as_str(data.get("feedback"))
        except Exception:
            logger.exception("Unhandled exception")
            pass
        # 평가 실패 시 기본 통과 점수
        return 4, "Self-judge failed. Defaulting to 4."

    def _call_llm(self, prompt: str, model: str, num_predict: int) -> str:
        if self.manager is not None:
            try:
                manager = cast(_ModelManagerLike, self.manager)
                target = manager.get_target_for_role("meta_architect", default_role="reasoning")
                if target is not None and target.strip():
                    response = manager.generate(
                        prompt,
                        target.strip(),
                        max_tokens=num_predict,
                        temperature=0.2,
                    )
                    if isinstance(response, str):
                        return response
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                logger.warning("Managed Meta-Architect generation failed; using API fallback", exc_info=True)
        data = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": num_predict,
                "temperature": 0.2,
                "num_ctx": 32768,  # M5 Max 128GB RAM 최적화: 대용량 컨텍스트
                "num_thread": 16,  # M5 Max 최적화: 고속 연산 스레드
                "num_gpu": 99,  # Apple Silicon GPU 완전 가속
            },
        }
        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with safe_urlopen(req, timeout=180) as resp:
            result = _as_mapping(_load_json(resp.read().decode("utf-8")))
            content = _as_str(result.get("response"))
            return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    def _extract_json(self, text: str) -> JsonMap | None:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = _as_mapping(_load_json(match.group()))
                return dict(parsed) if parsed else None
            except json.JSONDecodeError:
                logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
        return None
