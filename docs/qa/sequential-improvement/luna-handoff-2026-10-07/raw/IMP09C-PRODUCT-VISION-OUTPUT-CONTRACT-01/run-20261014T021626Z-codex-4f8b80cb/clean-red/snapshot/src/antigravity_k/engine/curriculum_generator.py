"""
Ssak-Ai: Self-Play Curriculum Generator (Level 3 자가 학습 엔진)
=====================================================================
AI가 스스로 새로운 벤치마크(테스트 코드)를 생성하여 자신의 능력을 무한 확장합니다.

특징:
  - 기존 능력을 분석하여 더 어려운 경계 조건(Edge cases)이나
    새로운 도메인의 Pytest 파일을 동적으로 생성합니다.
  - OmniTDDEngine을 연동해 스스로 코드를 구현(Green)해 봅니다.
  - 통과 시 영구 역량으로 편입, 실패 시 LoRA 훈련 데이터로 기록(Red).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from antigravity_k.config import config
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.tools.egress_policy import safe_urlopen


class _DatasetLike(Protocol):
    def __len__(self) -> int: ...

    def __getitem__(self, index: int) -> dict[str, object]: ...


class _DatasetLoader(Protocol):
    def __call__(self, dataset_name: str, **kwargs: object) -> object: ...


class _ModelManagerLike(Protocol):
    def get_target_for_role(self, role: str, *, default_role: str) -> str | None: ...

    def generate(self, prompt: str, target: str, **kwargs: object) -> str: ...


def _as_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    raw = cast(Mapping[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _as_string_mapping(value: object) -> dict[str, str]:
    return {key: item for key, raw in _as_mapping(value).items() if isinstance(item := raw, str)}


def _as_nested_string_mapping(value: object) -> dict[str, dict[str, str]]:
    return {key: _as_string_mapping(raw) for key, raw in _as_mapping(value).items()}


def _as_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [item for item in items if isinstance(item, str)]


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


load_dataset: _DatasetLoader | None = None
_has_datasets = False
try:
    load_dataset = cast(_DatasetLoader, import_module("datasets").__dict__["load_dataset"])

    _has_datasets = True
except ImportError:
    pass

HAS_DATASETS = _has_datasets

logger = logging.getLogger("antigravity_k.curriculum_generator")


@dataclass
class CurriculumTask:
    """자율 생성된 학습 과제"""

    task_id: str
    domain: str
    difficulty: int  # 1 to 10
    prompt_requirement: str
    generated_test_code: str
    passed: bool = False
    ground_truth_code: str | None = None
    is_hf_dataset: bool = False


class SkillLibrary:
    """Voyager 스타일: 성공한 코드 스니펫(스킬)을 누적하는 로컬 라이브러리."""

    def __init__(self, root_dir: str):
        self.library_dir: str = os.path.join(root_dir, "data", "skill_library")
        os.makedirs(self.library_dir, exist_ok=True)
        self.index_file: str = os.path.join(self.library_dir, "skills_index.json")

    def get_known_skills(self) -> list[str]:
        if not os.path.exists(self.index_file):
            return []
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                return _as_text_list(cast(object, json.load(f)))
        except Exception:
            logger.exception("Unhandled exception")
            return []

    def add_skill(self, task_id: str, domain: str, description: str, code: str) -> None:
        skills = self.get_known_skills()
        skill_name = f"{domain}_{task_id}"
        skills.append(description)

        # 스킬 인덱스 업데이트
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(skills, f, ensure_ascii=False, indent=2)

        # 스킬 코드 저장
        skill_path = os.path.join(self.library_dir, f"{skill_name}.py")
        with open(skill_path, "w", encoding="utf-8") as f:
            _ = f.write(f'"""\nDescription: {description}\n"""\n\n{code}')


class DatasetIngestor:
    """Hugging Face 데이터셋을 로드하고 미해결 문제를 샘플링하는 인제스터 (Auto-Mapper 기능 포함)."""

    def __init__(self, project_root: str, ollama_url: str, model_manager: _ModelManagerLike | None = None):
        self.project_root: str = project_root
        self.ollama_url: str = ollama_url
        self.model_manager: _ModelManagerLike | None = model_manager
        self.dataset_name: str = "openai/openai_humaneval"
        self.dataset: _DatasetLike | None = None
        self.mappings_file: str = os.path.join(project_root, "data", "dataset_mappings.json")
        os.makedirs(os.path.dirname(self.mappings_file), exist_ok=True)
        self.mappings: dict[str, dict[str, str]] = self._load_mappings()

    def _load_mappings(self) -> dict[str, dict[str, str]]:
        if os.path.exists(self.mappings_file):
            try:
                with open(self.mappings_file, "r", encoding="utf-8") as f:
                    return _as_nested_string_mapping(cast(object, json.load(f)))
            except Exception:
                logger.exception("Unhandled exception")
        return {}

    def _save_mappings(self) -> None:
        try:
            with open(self.mappings_file, "w", encoding="utf-8") as f:
                json.dump(self.mappings, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("[Curriculum] 데이터셋 매핑 저장 실패")

    def set_dataset(self, dataset_name: str) -> None:
        self.dataset_name = dataset_name
        self.dataset = None

    def load(self) -> bool:
        loader = load_dataset
        if not _has_datasets or loader is None:
            logger.warning("[Curriculum] Hugging Face 'datasets' 라이브러리가 설치되지 않았습니다.")
            return False
        try:
            logger.info("[Curriculum] 데이터셋 로드 중: %s...", self.dataset_name)
            # 우선 전체 데이터셋 메타를 로드하여 가능한 분할을 확인 (streaming=True로 빠르게 확인)
            try:
                ds = loader(self.dataset_name, streaming=True)
                splits = [str(key) for key in _as_mapping(ds)]
                target_split = "test" if "test" in splits else ("train" if "train" in splits else splits[0])
            except Exception:
                logger.exception("Unhandled exception")
                target_split = "test"

            self.dataset = cast(_DatasetLike, loader(self.dataset_name, split=target_split))
            logger.info("[Curriculum] '%s' 분할 데이터셋 로드 완료.", target_split)
            return True
        except Exception:
            logger.exception("[Curriculum] 데이터셋 로드 실패")
            return False

    def _analyze_schema_with_llm(self, sample_item: dict[str, object]) -> dict[str, str]:
        """LLM을 사용하여 알 수 없는 데이터셋의 스키마를 자율적으로 분석하고 매핑합니다."""
        logger.info("[Curriculum] '%s' 데이터셋 스키마 자율 분석 중...", self.dataset_name)
        sample_json = json.dumps(sample_item, ensure_ascii=False, indent=2)

        prompt = (
            "[ROLE] 당신은 데이터 엔지니어입니다.\n"
            "[TASK] 아래는 허깅페이스 데이터셋의 레코드 1개 샘플입니다.\n"
            "이 구조를 분석하여 코딩 테스트(또는 문제 풀이) 파이프라인에서 사용할 핵심 컬럼 3개의 이름을 찾아내세요.\n\n"
            f"--- JSON SAMPLE ---\n{sample_json[:2000]}\n\n"
            "[REQUIREMENTS]\n"
            "1. prompt_col: 문제의 지시사항이나 설명이 들어간 컬럼명 (예: text, prompt, question, instruction)\n"
            "2. test_col: 작성한 코드를 검증할 테스트 코드가 들어간 컬럼명 (없으면 빈 문자열). (예: test, test_list)\n"
            "3. ground_truth_col: 완벽한 정답 코드가 들어간 컬럼명 (예: code, answer, solution, canonical_solution)\n\n"
            "아래 JSON 형식으로만 응답하세요:\n"
            '{"prompt_col": "...", "test_col": "...", "ground_truth_col": "..."}'
        )

        try:
            if self.model_manager is not None:
                target = (
                    os.environ.get("AGK_DATASET_SCHEMA_MODEL")
                    or self.model_manager.get_target_for_role("dataset_ingestor", default_role="reasoning")
                    or ""
                )
                try:
                    content = self.model_manager.generate(
                        prompt,
                        target=target,
                        max_tokens=512,
                        temperature=0.1,
                    )
                    if content.strip():
                        match = re.search(r"\{.*\}", content, re.DOTALL)
                        if match:
                            mapping = _as_string_mapping(cast(object, json.loads(match.group())))
                            logger.info("[Curriculum] 스키마 분석 성공: %s", mapping)
                            return mapping
                except Exception:
                    logger.warning("[Curriculum] ModelManager 스키마 분석 실패, Ollama 폴백", exc_info=True)

            data = {
                "model": "deepseek-r1:32b",
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 512, "temperature": 0.1},
            }
            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with safe_urlopen(req, timeout=60) as resp:
                result = _as_mapping(cast(object, json.loads(resp.read().decode("utf-8"))))
                raw_content = result.get("response", "")
                content = raw_content if isinstance(raw_content, str) else ""
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    mapping = _as_string_mapping(cast(object, json.loads(match.group())))
                    logger.info("[Curriculum] 스키마 분석 성공: %s", mapping)
                    return mapping
        except Exception:
            logger.exception("[Curriculum] 스키마 자율 분석 실패")

        # 분석 실패 시 휴리스틱 폴백
        return {"prompt_col": "prompt", "test_col": "test", "ground_truth_col": "canonical_solution"}

    def sample_task(self) -> CurriculumTask | None:
        if not self.dataset and not self.load():
            return None

        # 무작위 샘플링
        assert self.dataset is not None  # load() 성공 후에는 None이 아님
        idx = random.randint(0, len(self.dataset) - 1)
        item = self.dataset[idx]

        # 스키마 매핑 획득 (Auto-Mapping)
        if self.dataset_name not in self.mappings:
            self.mappings[self.dataset_name] = self._analyze_schema_with_llm(item)
            self._save_mappings()

        mapping = self.mappings[self.dataset_name]

        task_id = f"hf_{self.dataset_name.replace('/', '_')}_{item.get('task_id', idx)}"
        prompt_req = item.get(mapping.get("prompt_col", ""), "")
        tests = item.get(mapping.get("test_col", ""), "")
        ground_truth = item.get(mapping.get("ground_truth_col", ""), "")

        # 테스트 코드가 있으면 변환, 없으면 빈 테스트
        pytest_code = tests if tests else "import pytest\n\ndef test_placeholder():\n    pass\n"

        return CurriculumTask(
            task_id=task_id,
            domain="huggingface_dataset",
            difficulty=6,  # 기본 난이도
            prompt_requirement=str(prompt_req),
            generated_test_code=str(pytest_code),
            ground_truth_code=str(ground_truth) if ground_truth else None,
            is_hf_dataset=True,
        )


class CurriculumGenerator:
    """자가 벤치마크 생성기 (Voyager & Frontier 기반)."""

    def __init__(
        self,
        project_root: str,
        ollama_url: str | None = None,
        model_manager: _ModelManagerLike | None = None,
    ):
        self.project_root: str = project_root
        self.ollama_url: str = ollama_url or config.model.api_base.replace("/v1", "").rstrip("/")
        self.model_manager: _ModelManagerLike | None = model_manager
        self.benchmark_dir: str = os.path.join(project_root, "tests", "curriculum")
        os.makedirs(self.benchmark_dir, exist_ok=True)
        self.skill_library: SkillLibrary = SkillLibrary(project_root)
        self.dataset_ingestor: DatasetIngestor = DatasetIngestor(
            project_root, self.ollama_url, model_manager=model_manager
        )

    def generate_new_challenge(
        self, domain: str = "algorithm", force_synthetic: bool = False, dataset_name: str | None = None
    ) -> CurriculumTask | None:
        """듀얼 모드: HF 데이터셋(Mode B)과 자율 창작(Mode A) 중 하나를 선택해 과제를 생성합니다."""

        if dataset_name:
            self.dataset_ingestor.set_dataset(dataset_name)

        # 50% 확률로 Hugging Face 데이터셋 활용 (Mode B) 또는 데이터셋 이름이 명시된 경우
        if dataset_name or (not force_synthetic and _has_datasets and random.random() < 0.5):
            logger.info("[Curriculum] Mode B: Hugging Face 데이터셋에서 샘플링합니다.")
            task = self.dataset_ingestor.sample_task()
            if task:
                return task

        # Mode A (Synthetic Frontier)
        logger.info("[Curriculum] Mode A: '%s' 도메인에서 Synthetic Frontier 과제 탐색 중...", domain)

        known_skills = self.skill_library.get_known_skills()
        skills_text = (
            "\n".join([f"- {s}" for s in known_skills[-10:]]) if known_skills else "아직 획득한 특수 스킬이 없습니다."
        )

        prompt = (
            f"[ROLE] 당신은 최고 수준의 AI 트레이너입니다.\n"
            f"[HARDWARE TARGET] 시스템은 M5 Max (128GB RAM)에서 구동됩니다. 매우 무거운 병렬 연산이나 대규모 메모리를 쓰는 과제도 충분히 소화할 수 있습니다.\n"
            f"[TASK] AI 에이전트의 현재 한계(Frontier)를 넓힐 '{domain}' 관련 새로운 파이썬 코딩 과제를 만들어주세요.\n"
            f"에이전트가 최근 성공한 스킬 목록은 다음과 같습니다:\n{skills_text}\n\n"
            "위 스킬들을 바탕으로 **단 한 단계 더 복잡하거나 새로운 개념이 추가된(Frontier)** 엣지 케이스 과제를 설계하세요.\n"
            "M5 Max 하드웨어의 이점을 살릴 수 있는 대용량 데이터 처리, 멀티스레딩, 극단적 비동기 처리 관련 주제를 권장합니다.\n"
            "아래 JSON 형식으로만 응답하세요:\n"
            '{"requirement": "에이전트가 풀어야 할 자연어 요구사항", '
            '"difficulty": 8, '
            '"pytest_code": "import pytest\\n\\ndef test_something():..."}\n'
            "주의: pytest_code는 'solution' 모듈에서 함수를 임포트한다고 가정하세요."
        )

        try:
            resp = self._call_llm(prompt, "deepseek-v4")
            data = self._extract_json(resp)

            if data and "requirement" in data and "pytest_code" in data:
                import time

                task_id = f"challenge_{int(time.time())}"
                task = CurriculumTask(
                    task_id=task_id,
                    domain=domain,
                    difficulty=_as_int(data.get("difficulty"), 5),
                    prompt_requirement=str(data["requirement"]),
                    generated_test_code=str(data["pytest_code"]),
                )
                logger.info(
                    "[Curriculum] 과제 생성됨: 난이도 %s - %s...", task.difficulty, task.prompt_requirement[:30]
                )
                return task
        except Exception:
            logger.exception("[Curriculum] 과제 생성 실패")
        return None

    async def self_play(self, task: CurriculumTask) -> bool:
        """생성된 과제를 OmniTDDEngine을 통해 스스로 풀어봅니다."""
        logger.info("[Curriculum] Self-Play 시작: %s", task.task_id)

        try:
            from antigravity_k.engine.tdd_engine import OmniTDDEngine

            dependencies = import_module("antigravity_k.api.dependencies")
            get_model_manager = cast(Callable[[], ModelManager], dependencies.__dict__["get_model_manager"])

            # 임시 테스트 파일 저장
            test_file_path = os.path.join(self.benchmark_dir, f"test_{task.task_id}.py")
            _ = await asyncio.to_thread(
                Path(test_file_path).write_text,
                task.generated_test_code,
                encoding="utf-8",
            )

            # TDD 엔진 구동
            engine = OmniTDDEngine(
                model_manager=get_model_manager(), workspace_dir=os.path.join(self.benchmark_dir, "workspace")
            )
            report = await engine.run_tdd_loop(
                task.prompt_requirement,
                test_file_path=test_file_path,
            )

            task.passed = report.status.value == "passed"

            if task.passed:
                logger.info("[Curriculum] 🏆 챌린지 성공! 새로운 능력 획득. (%s)", task.task_id)
                # 성공 시 벤치마크 아카이브에 영구 저장
                archive_path = os.path.join(self.benchmark_dir, "passed", f"test_{task.task_id}.py")
                os.makedirs(os.path.dirname(archive_path), exist_ok=True)
                os.rename(test_file_path, archive_path)

                # 스킬 라이브러리에 성공한 코드(스킬) 저장 (Voyager 방식)
                if report.final_code:
                    self.skill_library.add_skill(
                        task_id=task.task_id,
                        domain=task.domain,
                        description=task.prompt_requirement[:100],
                        code=report.final_code,
                    )
            else:
                logger.warning("[Curriculum] 💥 챌린지 실패. LoRA 파인튜닝 대기열에 추가. (%s)", task.task_id)
                fail_log = os.path.join(self.benchmark_dir, "failed", f"{task.task_id}.json")
                os.makedirs(os.path.dirname(fail_log), exist_ok=True)

                # 정답(Ground Truth)이 존재한다면 초고품질 LoRA 페이로드로 변환
                log_data = report.to_dict()
                if task.is_hf_dataset and task.ground_truth_code:
                    logger.info("[Curriculum] 정답지(Ground Truth)를 포함한 고품질 LoRA 훈련 데이터셋을 생성합니다.")
                    log_data["lora_payload"] = {
                        "instruction": task.prompt_requirement,
                        "failed_attempt": report.final_code,
                        "ground_truth_solution": task.ground_truth_code,
                        "tests": task.generated_test_code,
                    }

                _ = await asyncio.to_thread(
                    Path(fail_log).write_text,
                    json.dumps(log_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            return task.passed

        except Exception:
            logger.exception("[Curriculum] Self-Play 오류")
            return False

    def _call_llm(self, prompt: str, model: str) -> str:
        if self.model_manager is not None:
            target = (
                os.environ.get("AGK_CURRICULUM_MODEL")
                or self.model_manager.get_target_for_role("curriculum", default_role="reasoning")
                or ""
            )
            try:
                content = self.model_manager.generate(
                    prompt,
                    target=target,
                    max_tokens=1024,
                    temperature=0.4,
                )
                if content.strip():
                    return content.strip()
            except Exception:
                logger.warning("[Curriculum] ModelManager 생성 실패, Ollama 폴백", exc_info=True)

        data = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 1024,
                "temperature": 0.4,
                "num_ctx": 32768,  # M5 Max 128GB RAM 최적화
                "num_thread": 16,  # M5 Max 최적화
                "num_gpu": 99,  # Apple Silicon GPU 완전 가속
            },
        }
        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with safe_urlopen(req, timeout=120) as resp:
            result = _as_mapping(cast(object, json.loads(resp.read().decode("utf-8"))))
            raw_content = result.get("response", "")
            content = raw_content if isinstance(raw_content, str) else ""
            return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    def _extract_json(self, text: str) -> dict[str, object] | None:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return _as_mapping(cast(object, json.loads(match.group())))
            except json.JSONDecodeError:
                logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
        return None
