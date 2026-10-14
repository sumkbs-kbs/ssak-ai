"""Ssak-Ai: LoRA 파인튜닝 파이프라인.

========================================
QualityGate A등급 응답을 자동 수확하여 도메인 특화 LoRA 학습 데이터를 구축하고,
Unsloth/mlx-lm 기반 파인튜닝 설정을 자동 생성합니다.

핵심 아이디어:
  - 시스템이 스스로 "좋은 답변"을 수확하여 자가 개선 데이터셋을 구축
  - 별도의 라벨링 없이 QualityGate가 라벨러 역할을 담당
  - Apple Silicon 환경에서 mlx-lm LoRA, GPU 서버에서 Unsloth QLoRA 지원

사용법:
    pipeline = LoRAPipeline(quality_gate, harvest_dir="data/lora_harvest")
    pipeline.harvest(user_request, agent_output, quality_score)  # 자동 수확
    pipeline.export_dataset("data/lora_dataset.jsonl")           # 학습 데이터 내보내기
    pipeline.generate_config("mistral-small-24b")                # 학습 설정 생성
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import shlex
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TextIO, TypeAlias, cast, final

from antigravity_k.engine.provider_adapters.unsloth_platform_policy import default_training_platform, host_platform

logger = logging.getLogger("antigravity_k.lora_pipeline")

JsonObject: TypeAlias = dict[str, Any]  # pyright: ignore[reportExplicitAny]
NumericValue: TypeAlias = str | int | float | bool


# ─── 데이터 구조 ─────────────────────────────────────────────────────


@dataclass
class HarvestEntry:
    """수확된 고품질 응답 1건."""

    user_request: str
    agent_output: str
    quality_score: float
    quality_grade: str
    task_type: str
    model_used: str
    timestamp: float
    word_count: int = 0
    metadata: JsonObject = field(default_factory=dict)

    def to_training_format(self) -> dict[str, str]:
        """SFT(Supervised Fine-Tuning) 학습용 포맷으로 변환."""
        return {
            "instruction": self.user_request,
            "output": self.agent_output,
            "input": "",  # 추가 컨텍스트 (있으면)
        }

    def to_chat_format(self) -> JsonObject:
        """ChatML 학습용 포맷으로 변환."""
        return {
            "messages": [
                {"role": "user", "content": self.user_request},
                {"role": "assistant", "content": self.agent_output},
            ],
        }


# ─── DPO 선호쌍 ──────────────────────────────────────────────────────


@dataclass
class PreferencePair:
    """DPO(Direct Preference Optimization) 학습용 선호쌍 1건.

    chosen/rejected는 동일 프롬프트에 대한 두 응답이며,
    QualityGate 점수 또는 사용자 승인이 라벨 근거가 된다.

    source: 라벨 근거 출처 ("quality_gate" | "revision" | "human")
    """

    prompt: str
    chosen: str
    rejected: str
    chosen_score: float
    rejected_score: float
    source: str = "quality_gate"
    task_type: str = "general"
    timestamp: float = field(default_factory=time.time)

    def to_dpo_format(self) -> dict[str, str]:
        """TRL DPOTrainer 표준 포맷으로 변환."""
        return {
            "prompt": self.prompt,
            "chosen": self.chosen,
            "rejected": self.rejected,
        }


@dataclass
class TrainingRunResult:
    """학습 실행 결과."""

    success: bool
    exit_code: int | None = None
    elapsed_sec: float = 0.0
    log_tail: list[str] = field(default_factory=list)
    command: str = ""
    error: str = ""
    termination: str = "completed"  # TRN-02 — completed | timeout | no_output_hang | cancelled


def mlx_lm_available() -> bool:
    """mlx-lm 패키지 설치 여부."""
    return importlib.util.find_spec("mlx_lm") is not None


def _recipe_default_overrides(recipe: object) -> dict[str, float | int | str]:
    """레시피의 기본 하이퍼파라미터 오버라이드 (TRN-01 검증 입력용)."""
    return dict(getattr(recipe, "hyperparameter_overrides", {}) or {})


def _apply_overrides_to_mlx_command(command: str, overrides: dict[str, float | int | str]) -> str:
    """mlx-lm command 문자열의 플래그 값을 검증된 오버라이드로 갱신한다 (TRN-01).

    플래그가 없으면 추가한다. typed resolve 경로(resolve_training_recipe)와
    동일 규칙 — iters=iterations, batch-size=batch_size, learning-rate,
    num-layers=num_layers, seed는 오버라이드 대상이 아니다.
    """
    flag_map = {
        "iterations": "--iters",
        "batch_size": "--batch-size",
        "learning_rate": "--learning-rate",
        "num_layers": "--num-layers",
    }
    tokens = command.split()
    for key, flag in flag_map.items():
        if key not in overrides:
            continue
        value = str(overrides[key])
        try:
            idx = tokens.index(flag)
            if idx + 1 < len(tokens):
                tokens[idx + 1] = value
            else:
                tokens.append(value)
        except ValueError:
            tokens.extend([flag, value])
    return " ".join(tokens)


def _sha256_file(path: Path) -> str:
    """단일 파일 내용의 SHA-256."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_path(path: str | Path) -> str:
    """파일(또는 디렉터리 내 jsonl 파일들) 내용의 SHA-256 (provenance용)."""
    p = Path(path)
    if p.is_dir():
        digest = hashlib.sha256()
        for child in sorted(p.glob("*.jsonl")):
            digest.update(child.name.encode("utf-8"))
            with open(child, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    digest.update(chunk)
        return digest.hexdigest()
    if not p.is_file():
        return ""
    return _sha256_file(p)


def _as_object(value: object) -> JsonObject:
    return cast(JsonObject, value) if isinstance(value, dict) else {}


def _as_float(value: object) -> float:
    return float(cast(NumericValue, value))


def _as_int(value: object) -> int:
    return int(cast(NumericValue, value))


def _harvest_entry(data: Mapping[str, object]) -> HarvestEntry:
    return HarvestEntry(
        user_request=str(data["user_request"]),
        agent_output=str(data["agent_output"]),
        quality_score=_as_float(data["quality_score"]),
        quality_grade=str(data["quality_grade"]),
        task_type=str(data["task_type"]),
        model_used=str(data["model_used"]),
        timestamp=_as_float(data["timestamp"]),
        word_count=_as_int(data.get("word_count", 0)),
        metadata=_as_object(data.get("metadata", {})),
    )


def _preference_pair(data: Mapping[str, object]) -> PreferencePair:
    return PreferencePair(
        prompt=str(data["prompt"]),
        chosen=str(data["chosen"]),
        rejected=str(data["rejected"]),
        chosen_score=_as_float(data["chosen_score"]),
        rejected_score=_as_float(data["rejected_score"]),
        source=str(data.get("source", "quality_gate")),
        task_type=str(data.get("task_type", "general")),
        timestamp=_as_float(data.get("timestamp", time.time())),
    )


# ─── 메인 파이프라인 ─────────────────────────────────────────────────


@final
class LoRAPipeline:
    """LoRA 파인튜닝 자동화 파이프라인.

    3단계 워크플로우:
    1. 수확 (Harvest): QualityGate A/B 등급 응답을 자동 저장
    2. 내보내기 (Export): JSONL 형태의 학습 데이터셋 생성
    3. 설정 생성 (Config): Unsloth/mlx-lm LoRA 학습 설정 자동 생성
    """

    # 수확 조건: 이 점수 이상만 수확
    HARVEST_THRESHOLD: float = 0.75  # B등급 이상 (score >= 0.6은 B, 0.75면 B+ 이상만)
    MAX_HARVEST_SIZE: int = 5000  # 최대 수확 건수

    def __init__(
        self,
        harvest_dir: str = "data/lora_harvest",
        min_score: float = 0.75,
    ):
        """Initialize the LoRAPipeline.

        Args:
            harvest_dir (str): str harvest dir.
            min_score (float): float min score.

        """
        self._harvest_dir: Path = Path(harvest_dir)
        self._harvest_dir.mkdir(parents=True, exist_ok=True)
        self._min_score: float = min_score
        self._harvest_file: Path = self._harvest_dir / "harvest.jsonl"
        self._pairs_file: Path = self._harvest_dir / "pairs.jsonl"
        self._entries: list[HarvestEntry] = []
        self._pairs: list[PreferencePair] = []
        self._load_existing()
        self._load_pairs()

    @property
    def pairs(self) -> list[PreferencePair]:
        return list(self._pairs)

    def _load_existing(self) -> None:
        """기존 수확 데이터를 로드합니다."""
        if not self._harvest_file.exists():
            return
        try:
            with open(self._harvest_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = _as_object(cast(object, json.loads(line)))
                        self._entries.append(_harvest_entry(data))
            logger.info("[LoRA] %s개 기존 수확 데이터 로드", len(self._entries))
        except Exception:
            logger.exception("[LoRA] 기존 수확 데이터 로드 실패")

    # ─── 1단계: 수확 (Harvest) ────────────────────────────────────

    def harvest(
        self,
        user_request: str,
        agent_output: str,
        quality_score: float,
        quality_grade: str = "",
        task_type: str = "general",
        model_used: str = "",
        metadata: JsonObject | None = None,
    ) -> bool:
        """고품질 응답을 자동 수확합니다.

        QualityGate 평가 후 호출하면, 일정 점수 이상의 응답만 자동 저장됩니다.

        Returns:
            True if harvested, False if below threshold

        """
        if quality_score < self._min_score:
            return False

        if len(self._entries) >= self.MAX_HARVEST_SIZE:
            logger.warning("[LoRA] 최대 수확 건수 도달, 수확 스킵")
            return False

        # 중복 방지: 동일 요청 + 동일 응답(앞 200자)
        for existing in self._entries[-100:]:  # 최근 100개만 검사
            if existing.user_request == user_request and existing.agent_output[:200] == agent_output[:200]:
                return False

        entry = HarvestEntry(
            user_request=user_request,
            agent_output=agent_output,
            quality_score=quality_score,
            quality_grade=quality_grade,
            task_type=task_type,
            model_used=model_used,
            timestamp=time.time(),
            word_count=len(agent_output.split()),
            metadata=metadata or {},
        )

        self._entries.append(entry)
        self._append_to_file(entry)

        logger.info(
            "[LoRA] 수확 완료: %s (%s) — %s... (총 %s건)",
            quality_grade,
            quality_score,
            user_request[:50],
            len(self._entries),
        )
        return True

    def _append_to_file(self, entry: HarvestEntry) -> None:
        """수확 데이터를 파일에 추가합니다 (append mode)."""
        try:
            with open(self._harvest_file, "a", encoding="utf-8") as f:
                _ = f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("[LoRA] 수확 데이터 저장 실패")

    # ─── 2단계: 내보내기 (Export) ─────────────────────────────────

    def export_dataset(
        self,
        output_path: str = "data/lora_dataset.jsonl",
        format: str = "chat",
        min_score: float | None = None,
        max_entries: int = 2000,
    ) -> JsonObject:
        """수확 데이터를 학습용 JSONL로 내보냅니다.

        Args:
            output_path: 출력 파일 경로
            format: "chat" (ChatML) 또는 "instruction" (Alpaca)
            min_score: 최소 점수 필터 (None이면 self._min_score)
            max_entries: 최대 내보내기 건수

        Returns:
            내보내기 통계

        """
        threshold = min_score or self._min_score
        filtered = [e for e in self._entries if e.quality_score >= threshold]

        # 점수 높은 순으로 정렬 후 상위 N개
        filtered.sort(key=lambda e: e.quality_score, reverse=True)
        selected = filtered[:max_entries]

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            for entry in selected:
                if format == "chat":
                    record = entry.to_chat_format()
                else:
                    record = entry.to_training_format()
                _ = f.write(json.dumps(record, ensure_ascii=False) + "\n")

        stats: JsonObject = {
            "total_harvested": len(self._entries),
            "exported": len(selected),
            "min_score_filter": threshold,
            "output_path": str(output),
            "format": format,
            "avg_score": (sum(e.quality_score for e in selected) / len(selected) if selected else 0),
            "avg_word_count": (sum(e.word_count for e in selected) / len(selected) if selected else 0),
        }
        logger.info("[LoRA] 데이터셋 내보내기 완료: %s건 → %s", len(selected), output)
        return stats

    # ─── 3단계: 학습 설정 생성 (Config) ───────────────────────────

    def generate_config(
        self,
        base_model: str = "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
        dataset_path: str = "data/lora_dataset.jsonl",
        output_dir: str = "data/lora_output",
        platform: str = "auto",
    ) -> JsonObject:
        """LoRA/QLoRA 학습 설정을 자동 생성합니다.

        Args:
            base_model: 베이스 모델 (HuggingFace ID 또는 로컬 경로)
            dataset_path: 학습 데이터 경로
            output_dir: 학습 결과 저장 경로
            platform: "mlx" (Apple Silicon), "unsloth" (GPU), "auto" (자동 감지)

        Returns:
            생성된 설정 dict

        """
        if platform == "auto":
            platform = default_training_platform(host_platform())

        if platform == "mlx":
            config = self._mlx_lora_config(base_model, dataset_path, output_dir)
        else:
            config = self._unsloth_config(base_model, dataset_path, output_dir)

        # 설정 파일 저장
        config_path = Path(output_dir) / "lora_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info("[LoRA] 학습 설정 생성: %s (platform: %s)", config_path, platform)
        return config

    @staticmethod
    def _mlx_lora_config(base_model: str, dataset_path: str, output_dir: str) -> JsonObject:
        """Apple Silicon mlx-lm LoRA 설정."""
        return {
            "platform": "mlx",
            "command": (
                f"python -m mlx_lm.lora "
                f"--model {base_model} "
                f"--train "
                f"--data {dataset_path} "
                f"--adapter-path {output_dir}/adapters "
                f"--iters 600 "
                f"--batch-size 4 "
                f"--num-layers 16 "
                f"--learning-rate 1e-5"
            ),
            "base_model": base_model,
            "dataset": dataset_path,
            "output_dir": output_dir,
            "hyperparameters": {
                "lora_rank": 16,
                "lora_alpha": 32,
                "learning_rate": 1e-5,
                "batch_size": 4,
                "iterations": 600,
                "num_layers": 16,
            },
            "merge_command": (
                f"python -m mlx_lm.fuse "
                f"--model {base_model} "
                f"--adapter-path {output_dir}/adapters "
                f"--save-path {output_dir}/merged"
            ),
            "notes": [
                "Apple Silicon M4 Max 환경에 최적화",
                "mlx-lm 설치: pip install mlx-lm",
                "학습 후 merged 모델을 Ollama에 등록하여 사용",
            ],
        }

    @staticmethod
    def _unsloth_config(base_model: str, dataset_path: str, output_dir: str) -> JsonObject:
        """GPU 서버 Unsloth QLoRA 설정."""
        return {
            "platform": "unsloth",
            "script": f"""
from unsloth import FastLanguageModel

import torch

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="{base_model}",
    max_seq_length=4096,
    dtype=None,
    load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    lora_alpha=32,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
)

from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset

dataset = load_dataset("json", data_files="{dataset_path}", split="train")

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=4096,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        warmup_ratio=0.03,
        num_train_epochs=1,
        learning_rate=2e-4,
        weight_decay=0.01,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=1,
        seed=3407,
        output_dir="{output_dir}",
    ),
)
trainer.train()
model.save_pretrained("{output_dir}/lora_model")
""",
            "base_model": base_model,
            "dataset": dataset_path,
            "output_dir": output_dir,
            "hyperparameters": {
                "lora_rank": 16,
                "lora_alpha": 32,
                "learning_rate": 2e-4,
                "batch_size": 2,
                "gradient_accumulation_steps": 8,
                "num_train_epochs": 1,
                "weight_decay": 0.01,
                "max_seq_length": 4096,
                "load_in_4bit": True,
            },
            "notes": [
                "Unsloth 설치: pip install unsloth",
                "CUDA GPU 필수 (24GB+ VRAM 권장)",
                "하이퍼파라미터는 unsloth.ai LoRA Hyperparameters Guide 기준",
                "(lr 2e-4, effective batch size 16 = batch 2 × grad-accum 8, 1-3 epochs)",
                "학습 완료 후 GGUF 변환하여 Ollama에 등록",
            ],
        }

    # ─── DPO 선호쌍 (Unsloth 격차 해소) ────────────────────────────

    def _load_pairs(self) -> None:
        """기존 선호쌍 데이터를 로드합니다."""
        if not self._pairs_file.exists():
            return
        try:
            with open(self._pairs_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = _as_object(cast(object, json.loads(line)))
                        self._pairs.append(_preference_pair(data))
            logger.info("[LoRA] %s개 기존 선호쌍 로드", len(self._pairs))
        except Exception:
            logger.exception("[LoRA] 기존 선호쌍 로드 실패")

    def record_pair(
        self,
        prompt: str,
        chosen: str,
        rejected: str,
        chosen_score: float,
        rejected_score: float,
        source: str = "quality_gate",
        task_type: str = "general",
    ) -> bool:
        """선호쌍을 직접 기록합니다.

        revision 흐름(재생성 전 답=rejected, 후 답=chosen)이나 사용자 승인에서 호출.

        Returns:
            True if recorded, False if scores are inverted or equal
        """
        if chosen_score <= rejected_score:
            return False
        pair = PreferencePair(
            prompt=prompt,
            chosen=chosen,
            rejected=rejected,
            chosen_score=chosen_score,
            rejected_score=rejected_score,
            source=source,
            task_type=task_type,
        )
        self._pairs.append(pair)
        try:
            with open(self._pairs_file, "a", encoding="utf-8") as f:
                _ = f.write(json.dumps(asdict(pair), ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("[LoRA] 선호쌍 저장 실패")
        return True

    def build_preference_pairs(
        self,
        min_score_gap: float = 0.15,
    ) -> int:
        """수확 데이터에서 동일 프롬프트 그룹별로 선호쌍을 자동 추출합니다.

        같은 user_request에 대해 점수 차이가 min_score_gap 이상인 응답 쌍이
        있으면 (최고점=chosen, 최저점=rejected) 페어를 생성합니다.
        QualityGate가 암묵적 라벨러 역할을 하는 자가 개선 경로입니다.

        Returns:
            새로 추가된 페어 수
        """
        groups: dict[str, list[HarvestEntry]] = {}
        for e in self._entries:
            groups.setdefault(e.user_request, []).append(e)

        added = 0
        for prompt, entries in groups.items():
            if len(entries) < 2:
                continue
            best = max(entries, key=lambda e: e.quality_score)
            worst = min(entries, key=lambda e: e.quality_score)
            if best.quality_score - worst.quality_score < min_score_gap:
                continue
            if best.agent_output == worst.agent_output:
                continue
            if self.record_pair(
                prompt=prompt,
                chosen=best.agent_output,
                rejected=worst.agent_output,
                chosen_score=best.quality_score,
                rejected_score=worst.quality_score,
                source="quality_gate",
                task_type=best.task_type,
            ):
                added += 1

        logger.info("[LoRA] 수확 데이터에서 선호쌍 %s건 추출", added)
        return added

    def export_dpo_dataset(
        self,
        output_path: str = "data/dpo_dataset.jsonl",
        max_pairs: int = 2000,
    ) -> JsonObject:
        """선호쌍을 TRL DPOTrainer 호환 JSONL로 내보냅니다."""
        selected = sorted(self._pairs, key=lambda p: p.chosen_score - p.rejected_score, reverse=True)
        selected = selected[:max_pairs]

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            for pair in selected:
                _ = f.write(json.dumps(pair.to_dpo_format(), ensure_ascii=False) + "\n")

        stats: JsonObject = {
            "total_pairs": len(self._pairs),
            "exported": len(selected),
            "output_path": str(output),
            "avg_score_gap": (
                sum(p.chosen_score - p.rejected_score for p in selected) / len(selected) if selected else 0
            ),
        }
        logger.info("[LoRA] DPO 데이터셋 내보내기 완료: %s건 → %s", len(selected), output)
        return stats

    def generate_dpo_config(
        self,
        base_model: str = "mlx-community/Qwen2.5-Coder-32B-Instruct-4bit",
        dataset_path: str = "data/dpo_dataset.jsonl",
        output_dir: str = "data/dpo_output",
        platform: str = "auto",
    ) -> JsonObject:
        """DPO 학습 설정을 생성합니다 (mlx-lm / Unsloth).

        SFT로 정렬된 베이스 위에 선호 정렬을 얹는 2단계 훈련의 2단계 설정.
        """
        if platform == "auto":
            platform = default_training_platform(host_platform())

        config_path = Path(output_dir) / "dpo_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        if platform == "mlx":
            config: JsonObject = {
                "platform": "mlx",
                "command": (
                    f"python -m mlx_lm.lora "
                    f"--model {base_model} "
                    f"--train "
                    f"--fine-tune-type dora "
                    f"--data {dataset_path} "
                    f"--adapter-path {output_dir}/adapters "
                    f"--iters 400 "
                    f"--batch-size 2 "
                    f"--learning-rate 5e-6 "
                    f"--num-layers 16"
                ),
                "notes": [
                    "mlx-lm 0.31.x는 전용 DPO 트레이너가 없어 DoRA로 근사합니다.",
                    "선호 정렬이 목적이면 GPU 환경의 unsloth DPOTrainer 플랫폼을 권장.",
                    "DPO/RL 계열 학습률 권장값은 5e-6 (unsloth 가이드; SFT 2e-4보다 작게).",
                    "export 시 chosen/rejected를 assistant 턴으로 감싸야 할 수 있습니다.",
                ],
            }
        else:
            config = {
                "platform": "unsloth",
                "script": f"""
from unsloth import FastLanguageModel
from unsloth import is_bfloat16_supported
from trl import DPOTrainer, DPOConfig
from datasets import load_dataset

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="{base_model}",
    max_seq_length=4096,
    dtype=None,
    load_in_4bit=True,
)

dataset = load_dataset("json", data_files="{dataset_path}", split="train")
trainer = DPOTrainer(
    model=model,
    ref_model=None,
    train_dataset=dataset,
    tokenizer=tokenizer,
    args=DPOConfig(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=8,
        warmup_ratio=0.1,
        num_train_epochs=1,
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        optim="adamw_8bit",
        seed=3407,
        learning_rate=5e-6,
        beta=0.1,
        logging_steps=1,
        output_dir="{output_dir}",
    ),
)
trainer.train()
model.save_pretrained("{output_dir}/dpo_model")
""",
                "notes": [
                    "Unsloth DPOTrainer은 CUDA GPU 필수 (24GB+ 권장)",
                    "SFT 어댑터 위에 실행하는 것을 권장 (2단계 정렬)",
                ],
            }

        config["base_model"] = base_model
        config["dataset"] = dataset_path
        config["output_dir"] = output_dir
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info("[LoRA] DPO 학습 설정 생성: %s (platform: %s)", config_path, platform)
        return config

    # ─── 학습 실행 (Unsloth 격차: 설정 생성 → 실제 실행) ──────────

    def run_training(
        self,
        config: Mapping[str, object],
        on_log: Callable[[str], None] | None = None,
        timeout_sec: float | None = None,
        no_output_timeout_sec: float | None = None,
        cancel_event: threading.Event | None = None,
        on_proc_start: Callable[[subprocess.Popen[str]], None] | None = None,
    ) -> TrainingRunResult:
        """생성된 mlx-lm 학습 설정을 실제로 실행합니다. (TRN-02 감독 포함)

        platform이 "mlx"면 command를 파싱해 서브프로세스로 실행하고
        로그를 on_log 콜백으로 스트리밍합니다. "unsloth"는 CUDA GPU가 필요해
        스크립트를 디스크에 저장한 뒤 안내 에러와 함께 실패 결과를 반환합니다.

        TRN-02: 프로세스는 새 프로세스 그룹(start_new_session)으로 실행되고
        watchdog이 timeout_sec / no_output_timeout_sec / cancel_event를 감독해
        그룹 전체를 함께 종료합니다. 결과의 termination 필드로 사유가 기록됩니다.
        """
        started = time.monotonic()
        platform = str(config.get("platform", ""))

        if platform == "unsloth":
            script_path = self._persist_unsloth_script(config)
            return TrainingRunResult(
                success=False,
                error=(f"Unsloth 학습은 CUDA GPU 호스트에서 실행하세요. 스크립트 저장됨: {script_path}"),
                elapsed_sec=time.monotonic() - started,
            )

        command = str(config.get("command", ""))
        if not command:
            return TrainingRunResult(success=False, error="config에 command가 없습니다", elapsed_sec=0.0)

        if not mlx_lm_available():
            return TrainingRunResult(
                success=False,
                error="mlx-lm 미설치 — `uv sync --extra mlx` 또는 `pip install mlx-lm` 후 재시도",
                elapsed_sec=time.monotonic() - started,
            )

        from antigravity_k.finetune.training_supervision import (
            supervise_command,
        )

        argv = shlex.split(command)
        tail: list[str] = []
        try:
            outcome = supervise_command(
                argv,
                timeout_sec=timeout_sec,
                no_output_timeout_sec=no_output_timeout_sec,
                cancel_event=cancel_event,
                on_output=on_log,
                on_proc_start=on_proc_start,
            )
        except OSError as exc:
            return TrainingRunResult(
                success=False,
                error=f"프로세스 시작 실패: {exc}",
                command=command,
                elapsed_sec=time.monotonic() - started,
            )

        tail = outcome.output[-50:]
        return TrainingRunResult(
            success=outcome.success,
            exit_code=outcome.return_code,
            elapsed_sec=time.monotonic() - started,
            log_tail=tail,
            command=command,
            error=outcome.detail if outcome.reason != "completed" else "",
            termination=outcome.reason,
        )

    @staticmethod
    def _persist_unsloth_script(config: Mapping[str, object]) -> Path | None:
        """Unsloth 학습 스크립트를 output_dir에 저장한다 (GPU 호스트 이전용)."""
        output_dir = Path(str(config.get("output_dir", "data/lora_output")))
        output_dir.mkdir(parents=True, exist_ok=True)
        script_path = output_dir / ("train_dpo.py" if "DPOTrainer" in str(config.get("script", "")) else "train_sft.py")
        try:
            _ = script_path.write_text(str(config.get("script", "")), encoding="utf-8")
        except Exception:
            logger.exception("[LoRA] Unsloth 스크립트 저장 실패")
            return None
        logger.info("[LoRA] Unsloth 스크립트 저장: %s", script_path)
        return script_path

    @staticmethod
    def resolve_local_model_path(base_model: str) -> str:
        """베이스 모델을 로컬 파일시스템 스냅샷 경로로 확인합니다.

        1. base_model이 로컬 파일/디렉터리로 이미 존재하면 해당 절대 경로를 반환합니다.
        2. Hugging Face 허브 캐시(~/.cache/huggingface/hub/models--.../snapshots/...)에
           스냅샷이 존재하면 최신 스냅샷 디렉터리 경로를 반환하여 온라인 검증 및
           IncompleteSnapshotError를 방지합니다.
        3. 그 외의 경우 base_model 문자열을 그대로 반환합니다.
        """
        p = Path(base_model).expanduser()
        if p.exists():
            return str(p.resolve())

        hf_slug = base_model.replace("/", "--")
        snapshots_dir = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{hf_slug}" / "snapshots"
        if snapshots_dir.is_dir():
            snapshots = [d for d in snapshots_dir.iterdir() if d.is_dir()]
            if snapshots:
                snapshots.sort(key=lambda s: s.stat().st_mtime, reverse=True)
                return str(snapshots[0].resolve())

        return base_model

    _resolve_local_model_path = resolve_local_model_path

    def fuse_adapter(
        self,
        base_model: str,
        adapter_path: str | Path,
        save_path: str | Path,
        de_quantize: bool = False,
        on_log: Callable[[str], None] | None = None,
    ) -> TrainingRunResult:
        """mlx_lm.fuse를 실행하여 베이스 모델과 LoRA 어댑터를 단일 가중치로 병합합니다.

        Args:
            base_model: 베이스 모델 ID 또는 경로
            adapter_path: 학습된 LoRA 어댑터 디렉터리 경로
            save_path: 병합된 모델이 저장될 디렉터리 경로
            de_quantize: float16으로 역양자화(de-quantize) 여부
            on_log: 실시간 로그 출력 콜백

        Returns:
            TrainingRunResult
        """
        started = time.monotonic()
        if not mlx_lm_available():
            return TrainingRunResult(
                success=False,
                error="mlx-lm 미설치 — `uv sync --extra mlx` 또는 `pip install mlx-lm` 후 재시도",
                elapsed_sec=time.monotonic() - started,
            )

        adapter_p = Path(adapter_path).expanduser().resolve()
        if not adapter_p.exists():
            return TrainingRunResult(
                success=False,
                error=f"어댑터 경로를 찾을 수 없습니다: {adapter_path}",
                elapsed_sec=time.monotonic() - started,
            )

        resolved_model = self.resolve_local_model_path(base_model)
        save_p = Path(save_path).expanduser().resolve()
        save_p.parent.mkdir(parents=True, exist_ok=True)

        cmd_parts = [
            "python",
            "-m",
            "mlx_lm.fuse",
            "--model",
            resolved_model,
            "--adapter-path",
            str(adapter_p),
            "--save-path",
            str(save_p),
        ]
        if de_quantize:
            cmd_parts.append("--de-quantize")

        cmd_str = " ".join(shlex.quote(p) for p in cmd_parts)
        tail: list[str] = []

        try:
            proc: subprocess.Popen[str] = subprocess.Popen(
                cmd_parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            return TrainingRunResult(
                success=False,
                error=f"mlx_lm.fuse 프로세스 시작 실패: {exc}",
                command=cmd_str,
                elapsed_sec=time.monotonic() - started,
            )

        assert proc.stdout is not None
        stdout: TextIO = cast(TextIO, proc.stdout)
        with proc:
            for raw_line in stdout:
                line = raw_line.rstrip()
                tail.append(line)
                if len(tail) > 50:
                    _ = tail.pop(0)
                if on_log is not None:
                    on_log(line)

        exit_code = proc.wait() if proc.poll() is None else proc.returncode
        return TrainingRunResult(
            success=exit_code == 0,
            exit_code=exit_code,
            elapsed_sec=time.monotonic() - started,
            log_tail=tail,
            command=cmd_str,
            error="" if exit_code == 0 else f"mlx_lm.fuse 실패 (코드 {exit_code})",
        )

    @staticmethod
    def create_modelfile(
        model_path: str | Path,
        output_path: str | Path,
        system_prompt: str = "",
        template: str = "",
        stop_tokens: Sequence[str] | None = None,
    ) -> Path:
        """Ollama 등록용 Modelfile을 생성합니다.

        Args:
            model_path: Ollama가 로드할 GGUF 파일 또는 병합 모델 디렉터리 경로
            output_path: 생성될 Modelfile 파일 경로
            system_prompt: 기본 시스템 프롬프트
            template: ChatML 등 템플릿 정의
            stop_tokens: 종료 토큰 목록

        Returns:
            생성된 Modelfile의 Path 객체
        """
        out_p = Path(output_path).expanduser().resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        target_path_str = str(model_path)

        lines: list[str] = [f"FROM {target_path_str}"]
        if template:
            lines.append(f'TEMPLATE """{template}"""')
        elif not any(target_path_str.endswith(ext) for ext in (".gguf", ".bin")):
            lines.append(
                'TEMPLATE """{{ if .System }}<|im_start|>system\n'
                "{{ .System }}<|im_end|>\n"
                "{{ end }}{{ if .Prompt }}<|im_start|>user\n"
                "{{ .Prompt }}<|im_end|>\n"
                "{{ end }}<|im_start|>assistant\n"
                "{{ .Response }}<|im_end|>\n"
                '"""'
            )

        if system_prompt:
            lines.append(f'SYSTEM """{system_prompt}"""')

        stops = stop_tokens if stop_tokens is not None else ["<|im_start|>", "<|im_end|>"]
        for st in stops:
            lines.append(f'PARAMETER stop "{st}"')

        content = "\n".join(lines) + "\n"
        out_p.write_text(content, encoding="utf-8")
        logger.info("[LoRA] Modelfile 생성 완료: %s", out_p)
        return out_p

    def register_ollama(
        self,
        model_name: str,
        modelfile_path: str | Path,
        on_log: Callable[[str], None] | None = None,
    ) -> JsonObject:
        """Modelfile을 기반으로 Ollama에 모델을 등록합니다 (`ollama create`)."""
        mf_p = Path(modelfile_path).expanduser().resolve()
        if not mf_p.is_file():
            return {
                "success": False,
                "model_name": model_name,
                "error": f"Modelfile을 찾을 수 없습니다: {modelfile_path}",
                "log_tail": [],
            }

        ollama_bin = shutil.which("ollama")
        if not ollama_bin:
            return {
                "success": False,
                "model_name": model_name,
                "error": "ollama CLI 명령어가 PATH에 없습니다. (https://ollama.com 설치 필요)",
                "log_tail": [],
            }

        cmd = [ollama_bin, "create", model_name, "-f", str(mf_p)]
        tail: list[str] = []
        try:
            proc: subprocess.Popen[str] = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            stdout: TextIO = cast(TextIO, proc.stdout)
            with proc:
                for raw_line in stdout:
                    line = raw_line.rstrip()
                    tail.append(line)
                    if len(tail) > 50:
                        _ = tail.pop(0)
                    if on_log is not None:
                        on_log(line)
            exit_code = proc.wait() if proc.poll() is None else proc.returncode
        except OSError as exc:
            return {
                "success": False,
                "model_name": model_name,
                "error": f"ollama create 실행 실패: {exc}",
                "log_tail": tail,
            }

        return {
            "success": exit_code == 0,
            "model_name": model_name,
            "error": "" if exit_code == 0 else f"ollama create 실패 (코드 {exit_code})",
            "log_tail": tail,
        }

    def fuse_and_register_ollama(
        self,
        base_model: str,
        adapter_path: str | Path,
        output_dir: str | Path,
        ollama_model_name: str,
        de_quantize: bool = False,
        skip_fuse: bool = False,
        gguf_path: str | Path | None = None,
        system_prompt: str = "",
        on_log: Callable[[str], None] | None = None,
    ) -> JsonObject:
        """학습된 어댑터를 베이스 모델과 병합하고 Ollama에 등록하는 통합 파이프라인.

        Train-to-Serve 완성:
        1. (skip_fuse가 아닌 경우) mlx_lm.fuse 실행
        2. GGUF 파일 또는 병합 디렉터리 기반 Modelfile 생성
        3. `ollama create` 호출하여 로컬 서빙 모델 등록
        """
        started = time.monotonic()
        out_p = Path(output_dir).expanduser().resolve()
        out_p.mkdir(parents=True, exist_ok=True)
        if out_p.name == "merged":
            merged_p = out_p
            modelfile_p = out_p.parent / "Modelfile"
        else:
            merged_p = out_p / "merged"
            modelfile_p = out_p / "Modelfile"

        fuse_result: TrainingRunResult | None = None
        if not skip_fuse:
            fuse_result = self.fuse_adapter(
                base_model=base_model,
                adapter_path=adapter_path,
                save_path=merged_p,
                de_quantize=de_quantize,
                on_log=on_log,
            )
            if not fuse_result.success:
                return {
                    "success": False,
                    "stage": "fuse",
                    "error": fuse_result.error,
                    "fuse_result": asdict(fuse_result),
                    "elapsed_sec": time.monotonic() - started,
                }

        target_model_path: str | Path = merged_p
        if gguf_path and Path(gguf_path).exists():
            target_model_path = Path(gguf_path).expanduser().resolve()
        else:
            gguf_files = list(merged_p.glob("*.gguf"))
            if not gguf_files:
                gguf_files = list(out_p.glob("*.gguf"))
            if gguf_files:
                target_model_path = gguf_files[0]

        _ = self.create_modelfile(
            model_path=target_model_path,
            output_path=modelfile_p,
            system_prompt=system_prompt,
        )

        reg_result = self.register_ollama(
            model_name=ollama_model_name,
            modelfile_path=modelfile_p,
            on_log=on_log,
        )

        return {
            "success": bool(reg_result.get("success", False)),
            "stage": "completed" if reg_result.get("success") else "register",
            "ollama_model_name": ollama_model_name,
            "merged_path": str(merged_p),
            "target_model_path": str(target_model_path),
            "modelfile_path": str(modelfile_p),
            "fuse_result": asdict(fuse_result) if fuse_result else None,
            "ollama_result": reg_result,
            "elapsed_sec": time.monotonic() - started,
        }

    @staticmethod
    def split_dataset_for_mlx(
        input_jsonl: str | Path,
        output_dir: str | Path,
        batch_size: int = 4,
        train_ratio: float = 0.9,
        seed: int = 42,
    ) -> tuple[Path, Path]:
        """mlx-lm용 train/valid 디렉터리 구조 생성 (Phase 23 P2 해결).

        mlx-lm은 --data로 디렉터리를 받고, 내부에서 train.jsonl과 valid.jsonl을
        필요로 한다 (test.jsonl은 비어있으면 에러이므로 생성하지 않음).
        또한 각 분할은 최소 batch_size 이상의 레코드를 포함해야 한다.

        - 레코드 수가 2 * batch_size 미만인 경우:
          분할 시 valid가 batch_size 미만이 되어 validator 에러가 발생하므로,
          Phase 23 E2E 우회 방식처럼 train과 valid 양쪽에 전체 레코드를 재사용한다.
        - 레코드 수가 2 * batch_size 이상인 경우:
          train_ratio(기본 0.9)로 분할하되, valid에 최소 batch_size개가 배정되도록 보장한다.

        Args:
            input_jsonl: 원본 단일 JSONL 파일 경로
            output_dir: train.jsonl, valid.jsonl이 생성될 디렉터리 (예: mlx_dataset)
            batch_size: 배치 크기 (기본값 4)
            train_ratio: 학습 데이터 분할 비율 (기본값 0.9)
            seed: 재현 가능한 분할을 위한 시드

        Returns:
            (train_path, valid_path) 튜플
        """
        import random

        in_path = Path(input_jsonl)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        if in_path.is_file():
            with open(in_path, encoding="utf-8") as f:
                lines = [line for line in f if line.strip()]

        total = len(lines)
        if total == 0:
            train_lines: list[str] = []
            valid_lines: list[str] = []
        elif total < 2 * batch_size:
            # 적은 데이터(예: 6건, batch_size=4)인 경우 동일 데이터 재사용
            train_lines = list(lines)
            valid_lines = list(lines)
        else:
            rng = random.Random(seed)
            shuffled = list(lines)
            rng.shuffle(shuffled)

            split_idx = int(total * train_ratio)
            # valid가 최소 batch_size 이상, train도 최소 batch_size 이상
            split_idx = max(batch_size, min(total - batch_size, split_idx))
            train_lines = shuffled[:split_idx]
            valid_lines = shuffled[split_idx:]

        train_path = out_dir / "train.jsonl"
        valid_path = out_dir / "valid.jsonl"

        with open(train_path, "w", encoding="utf-8") as f:
            for line in train_lines:
                f.write(line if line.endswith("\n") else line + "\n")

        with open(valid_path, "w", encoding="utf-8") as f:
            for line in valid_lines:
                f.write(line if line.endswith("\n") else line + "\n")

        return train_path, valid_path

    # ─── 데이터 레시피 (unsloth Data Recipes 벤치마킹) ──────────────

    def apply_recipe(
        self,
        recipe_name: str,
        base_model: str,
        output_dir: str,
        source: str = "",
        platform: str = "auto",
        pdf_pages: str = "",
        pdf_header_filter: str = "",
        pdf_question_template: str = "",
        hyperparameter_overrides: dict[str, float | int | str] | None = None,
    ) -> JsonObject:
        """데이터 레시피를 적용해 소스→데이터셋→학습 설정까지 한 번에 구성.

        소스가 비으면(또는 'harvest'면) 기존 수확 데이터를 사용하고,
        파일 경로(csv/jsonl/txt/md)면 레시피 포맷으로 변환한다.
        platform="mlx"인 경우 mlx-lm용 train/valid 디렉터리 구조로 자동 분할한다.

        Args:
            recipe_name: 레시피 이름 (data_recipes.RECIPES 참조)
            base_model: 베이스 모델 (HuggingFace ID 또는 로컬 경로)
            output_dir: 데이터셋·학습 설정·결과가 저장될 디렉터리
            source: 파일 경로(쉼표 목록), "harvest", 또는 빈 값(수확 데이터 사용)
            platform: "mlx" / "unsloth" / "auto"
            pdf_pages: 문서 소스 선택 범위 (예: "1-5,8", 빈 값=전체) —
                PDF는 페이지 번호, DOCX는 헤딩 섹션 번호로 해석 (Phase 47 parity)
            pdf_header_filter: 문서 소스 헤더/헤딩 필터 정규식 ("!" 접두사=제외, 빈 값=필터 없음)
            pdf_question_template: 질문 강제 템플릿 (Phase 48). 플레이스홀더 {page}/{title}/
                {header}/{body}. 빈 값=기본 동작(헤더가 제목이면 헤더를 질문으로 사용)
            hyperparameter_overrides: 레시피 기본 오버라이드 위에 최종 병합되는 사용자 지정 값
                (대시보드 학습 UI의 편집 필드에서 전달됨)

        Returns:
            {recipe, stats, dataset_path, config, ...} 구성 결과

        Raises:
            UnknownRecipeError: 존재하지 않는 레시피
            FileNotFoundError: 소스 파일 없음
            ValueError: 지원하지 않는 소스 형식

        """
        from antigravity_k.engine.data_recipes import (
            DataRecipe,
            get_recipe,
            load_records_from_source,
            records_to_training_jsonl,
        )
        from antigravity_k.engine.pdf_source_options import PdfSourceOptions
        from antigravity_k.finetune.hyperparameters import (
            compute_recipe_digest,
            validate_hyperparameters,
        )

        if platform == "auto":
            from antigravity_k.engine.provider_adapters.unsloth_platform_policy import (
                default_training_platform,
                host_platform,
            )

            platform = str(default_training_platform(host_platform()))

        # TRN-01: 검증은 모든 파일 IO 전에 — 0/음수/과대 값·미지원 키를 조용히 무시하지 않는다
        #  - 레시피 기본값: 백엔드가 미지원하는 키는 제거 (unsloth 전용 기본값이 mlx에 유입되지 않게)
        #  - 사용자 오버라이드: 미지원 키는 엄격히 거절 (실행 전 fail-fast)
        from antigravity_k.finetune.hyperparameters import backend_capabilities

        recipe0: DataRecipe = get_recipe(recipe_name)
        resolved_platform = "mlx" if platform == "mlx" else platform
        raw_supported = backend_capabilities(resolved_platform)["supported_keys"]
        supported = {str(k) for k in cast("Sequence[object]", raw_supported)}
        recipe_defaults = {k: v for k, v in _recipe_default_overrides(recipe0).items() if k in supported}
        merged_overrides = validate_hyperparameters(
            {**recipe_defaults, **(hyperparameter_overrides or {})},
            backend=resolved_platform,
        )
        recipe_digest = compute_recipe_digest(
            recipe=recipe_name,
            base_model=base_model,
            platform=resolved_platform,
            overrides=merged_overrides,
        )

        recipe: DataRecipe = recipe0
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        if recipe.format == "dpo":
            # DPO: 수확 선호쌍을 그대로 사용 (파일 소스 변환은 미지원)
            raw_dataset_path = str(out / "dpo_dataset.jsonl")
            stats = self.export_dpo_dataset(output_path=raw_dataset_path)
            applied_records = int(stats.get("exported", 0))
        elif source and source != "harvest":
            pdf_options = PdfSourceOptions(
                pages=pdf_pages,
                header_filter=pdf_header_filter,
                question_template=pdf_question_template,
            )
            records = load_records_from_source(source, pdf_options=pdf_options)
            raw_dataset_path = str(out / "recipe_dataset.jsonl")
            applied_records = records_to_training_jsonl(records, raw_dataset_path, fmt="chat")
        else:
            # 수확 데이터 경로 (기본)
            raw_dataset_path = str(out / "lora_dataset.jsonl")
            stats = self.export_dataset(
                output_path=raw_dataset_path,
                format="chat" if recipe.format == "chat" else "instruction",
            )
            applied_records = int(stats.get("exported", 0))

        if platform == "mlx":
            mlx_dir = out / "mlx_dataset"
            bs = 2 if recipe.format == "dpo" else 4
            if "batch_size" in recipe.hyperparameter_overrides:
                try:
                    bs = int(recipe.hyperparameter_overrides["batch_size"])
                except (ValueError, TypeError):
                    pass
            if hyperparameter_overrides and "batch_size" in hyperparameter_overrides:
                try:
                    bs = int(hyperparameter_overrides["batch_size"])
                except (ValueError, TypeError):
                    pass

            self.split_dataset_for_mlx(
                raw_dataset_path,
                mlx_dir,
                batch_size=bs,
            )
            dataset_path = str(mlx_dir)
        else:
            dataset_path = raw_dataset_path

        if recipe.format == "dpo":
            config = self.generate_dpo_config(
                base_model=base_model,
                dataset_path=dataset_path,
                output_dir=output_dir,
                platform=platform,
            )
        else:
            config = self.generate_config(
                base_model=base_model,
                dataset_path=dataset_path,
                output_dir=output_dir,
                platform=platform,
            )

        # 레시피 하이퍼파라미터 병합 — TRN-01: 검증·정규화된 값을 단일 경로로 사용한다
        hyper: dict[str, object] = (
            dict(config.get("hyperparameters", {})) if isinstance(config.get("hyperparameters", {}), dict) else {}
        )
        for key, value in merged_overrides.items():
            hyper[key] = value
        if hyper:
            config["hyperparameters"] = hyper
        config["recipe"] = recipe.name
        config["recipe_sha256"] = recipe_digest

        # TRN-01 mlx argv 일치: config command의 --iters/--batch-size/--learning-rate를
        # 검증·정규화된 오버라이드로 갱신 (resolve 단일 경로 — typed recipe와 동일 규칙)
        if resolved_platform == "mlx" and isinstance(config.get("command"), str):
            config["command"] = _apply_overrides_to_mlx_command(str(config["command"]), merged_overrides)

        if platform == "mlx":
            config["train_path"] = str(out / "mlx_dataset" / "train.jsonl")
            config["valid_path"] = str(out / "mlx_dataset" / "valid.jsonl")
            config["source_dataset_path"] = raw_dataset_path

        config_path = Path(output_dir) / "lora_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # TRN-01 재실행 provenance — digest/입력/데이터 통계를 디스크에 기록
        provenance: JsonObject = {
            "recipe": recipe.name,
            "recipe_sha256": recipe_digest,
            "base_model": base_model,
            "platform": resolved_platform,
            "overrides": dict(merged_overrides),
            "records": applied_records,
            # mlx는 train/valid 분할 디렉터리를 쓰므로 디렉터리(jsonl 집합) digest를 계산한다.
            "dataset_sha256": _sha256_path(dataset_path),
            "config_path": str(config_path),
        }
        provenance_path = Path(output_dir) / "recipe_provenance.json"
        with open(provenance_path, "w", encoding="utf-8") as f:
            json.dump(provenance, f, ensure_ascii=False, indent=2)

        ret: JsonObject = {
            "recipe": recipe.name,
            "format": recipe.format,
            "records": applied_records,
            "min_records": recipe.min_records,
            "sufficient": applied_records >= recipe.min_records,
            "dataset_path": dataset_path,
            "config_path": str(config_path),
            "recipe_sha256": recipe_digest,
            "config": config,
        }
        if platform == "mlx":
            ret["train_path"] = str(out / "mlx_dataset" / "train.jsonl")
            ret["valid_path"] = str(out / "mlx_dataset" / "valid.jsonl")
            ret["source_dataset_path"] = raw_dataset_path

        return ret

    # ─── 유틸리티 ─────────────────────────────────────────────────

    def stats(self) -> JsonObject:
        """수확 통계를 반환합니다."""
        if not self._entries:
            return {"total": 0, "message": "수확 데이터 없음"}

        scores = [e.quality_score for e in self._entries]
        task_types: dict[str, int] = {}
        for e in self._entries:
            task_types[e.task_type] = task_types.get(e.task_type, 0) + 1

        return {
            "total": len(self._entries),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "by_task_type": task_types,
            "harvest_dir": str(self._harvest_dir),
        }

    def clear(self) -> None:
        """수확 데이터를 초기화합니다."""
        self._entries.clear()
        if self._harvest_file.exists():
            self._harvest_file.unlink()
        logger.info("[LoRA] 수확 데이터 초기화")


"""Ssak-Ai LoRA Pipeline — Self-improving training data harvester."""
