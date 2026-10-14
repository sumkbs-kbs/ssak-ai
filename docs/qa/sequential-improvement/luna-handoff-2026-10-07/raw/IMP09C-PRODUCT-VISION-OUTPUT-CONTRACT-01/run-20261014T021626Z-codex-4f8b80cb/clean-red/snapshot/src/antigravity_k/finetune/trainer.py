"""Ssak-Ai: MLX LoRA/QLoRA 파인튜닝 엔진.

=============================================
Apple Silicon 128GB Unified Memory에서 로컬 파인튜닝 실행.

사용법:
    # CLI
    python -m antigravity_k.finetune.trainer --config finetune_config.yaml

    # Python API
    from antigravity_k.finetune.trainer import FineTuneEngine
    engine = FineTuneEngine(config)
    engine.train()
"""

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal, TextIO, cast

from pydantic import ValidationError

from antigravity_k.config import config
from antigravity_k.finetune.active_artifact import (
    ActiveArtifactError,
    ActiveArtifactStatus,
    ArtifactPromotionContract,
    promote_artifact,
    rollback_active_artifact,
)
from antigravity_k.finetune.artifact_lifecycle import ArtifactLifecycleError, fuse_training_artifact
from antigravity_k.finetune.dataset_contract import (
    DatasetConsent,
    DatasetContractError,
    DatasetLicense,
    DatasetSplitPolicy,
    DatasetSubjectRights,
    FinetuneDatasetContract,
    split_frozen_dataset,
)
from antigravity_k.finetune.evaluation import (
    CandidateKind,
    EvaluationCase,
    EvaluationDataset,
    EvaluationError,
    evaluate_candidates,
)
from antigravity_k.finetune.evaluation_backends import (
    EvaluationBackend,
    EvaluationInferenceError,
    MlxEvaluationInference,
    OllamaEvaluationInference,
)
from antigravity_k.finetune.evaluation_gate import PromotionGatePolicy, load_promotion_decision
from antigravity_k.finetune.promotion_probe import MlxFusedArtifactProbe
from antigravity_k.finetune.resource_admission import (
    FinetuneResourceAdmissionError,
    FinetuneResourceInvariantError,
    FinetuneResourceSettings,
    build_finetune_resource_admission,
    build_merge_admission_request,
    build_training_admission_request,
    reserve_finetune_resource,
)
from antigravity_k.finetune.training_adapter import TrainingRunResult, run_resolved_training
from antigravity_k.finetune.training_recipe import (
    TrainingRecipe,
    TrainingRecipeError,
    resolve_training_recipe,
)

logger = logging.getLogger("agk.finetune")

JsonObject = dict[str, object]


# ─── 설정 ────────────────────────────────────────────────────────────
@dataclass
class LoRAConfig:
    """LoRA 어댑터 하이퍼파라미터."""

    rank: int = 16  # LoRA rank (8, 16, 32, 64)
    alpha: float = 32.0  # LoRA alpha (보통 rank * 2)
    dropout: float = 0.05  # 드롭아웃 확률
    target_modules: list[str] = field(
        default_factory=lambda: [
            "q_proj",
            "v_proj",
            "k_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )


@dataclass
class TrainingConfig:
    """학습 설정."""

    # 모델
    base_model: str = ""  # 베이스 모델 경로 (models/glm 등)
    output_dir: str = ""  # 어댑터 저장 경로

    # 데이터
    train_data: str = ""  # 학습 데이터 (JSONL 경로)
    valid_data: str = ""  # 검증 데이터 (JSONL 경로, 선택)

    # 학습 하이퍼파라미터
    num_epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 1e-5
    warmup_steps: int = 100
    max_seq_length: int = 2048
    gradient_accumulation_steps: int = 4
    save_every: int = 100  # N 스텝마다 체크포인트 저장
    eval_every: int = 200  # N 스텝마다 검증

    # LoRA
    lora: LoRAConfig = field(default_factory=LoRAConfig)

    # 리소스
    use_quantized_training: bool = True  # QLoRA (4-bit base + LoRA)
    seed: int = 42


# ─── 데이터 준비 도구 ────────────────────────────────────────────────
class DatasetPreparer:
    """다양한 소스 데이터를 MLX 파인튜닝용 JSONL로 변환.

    지원 포맷:
        1. ChatML: {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
        2. Instruction: {"instruction": "...", "input": "...", "output": "..."}
        3. QA: {"question": "...", "answer": "..."}
        4. Raw text: {"text": "..."}
    """

    SYSTEM_PROMPT: str = (
        "당신은 삼성중공업의 시니어 소프트웨어 엔지니어입니다. "
        "조선/해양 플랜트 도메인에 대한 깊은 이해를 바탕으로 "
        "정확하고 실용적인 기술 답변을 제공합니다."
    )

    @staticmethod
    def from_instruction(
        input_path: str,
        output_path: str,
        system_prompt: str | None = None,
    ) -> int:
        """Instruction 포맷 → ChatML JSONL 변환."""
        system = system_prompt or DatasetPreparer.SYSTEM_PROMPT
        count = 0

        with (
            open(input_path, encoding="utf-8") as fin,
            open(output_path, "w", encoding="utf-8") as fout,
        ):
            for line in fin:
                line = line.strip()
                if not line:
                    continue

                try:
                    item = cast(JsonObject, json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("JSON 파싱 실패, 건너뜀: %s", line[:80])
                    continue

                # Instruction 포맷
                if "instruction" in item:
                    instruction = item["instruction"]
                    if not isinstance(instruction, str):
                        logger.warning("instruction이 문자열이 아니어서 건너뜀")
                        continue
                    user_content = instruction
                    input_value = item.get("input")
                    if input_value:
                        user_content += f"\n\n입력:\n{input_value}"
                    output_value = item.get("output", "")
                    assistant_content = output_value if isinstance(output_value, str) else str(output_value)

                # QA 포맷
                elif "question" in item:
                    question = item["question"]
                    if not isinstance(question, str):
                        logger.warning("question이 문자열이 아니어서 건너뜀")
                        continue
                    user_content = question
                    answer = item.get("answer", "")
                    assistant_content = answer if isinstance(answer, str) else str(answer)

                # ChatML (그대로 통과)
                elif "messages" in item:
                    _ = fout.write(json.dumps(item, ensure_ascii=False) + "\n")
                    count += 1
                    continue

                # Raw text
                elif "text" in item:
                    _ = fout.write(json.dumps({"text": item["text"]}, ensure_ascii=False) + "\n")
                    count += 1
                    continue

                else:
                    logger.warning("알 수 없는 포맷, 건너뜀: %s", list(item.keys()))
                    continue

                chatml = {
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                        {"role": "assistant", "content": assistant_content},
                    ],
                }
                _ = fout.write(json.dumps(chatml, ensure_ascii=False) + "\n")
                count += 1

        logger.info("변환 완료: %s개 → %s", count, output_path)
        return count

    @staticmethod
    def from_code_files(
        source_dir: str,
        output_path: str,
        extensions: tuple[str, ...] = (".py", ".js", ".ts", ".dart", ".java"),
        min_lines: int = 10,
    ) -> int:
        """소스코드 파일 → 코드 이해/생성 학습 데이터로 변환."""
        count = 0

        with open(output_path, "w", encoding="utf-8") as fout:
            for root, _, files in os.walk(source_dir):
                for fname in files:
                    if not any(fname.endswith(ext) for ext in extensions):
                        continue

                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, encoding="utf-8", errors="ignore") as f:
                            code = f.read()
                    except Exception:
                        logger.exception("Unhandled exception")
                        continue

                    lines = code.strip().split("\n")
                    if len(lines) < min_lines:
                        continue

                    rel_path = os.path.relpath(fpath, source_dir)
                    ext = os.path.splitext(fname)[1]

                    chatml = {
                        "messages": [
                            {
                                "role": "system",
                                "content": "당신은 코드 분석 전문가입니다.",
                            },
                            {
                                "role": "user",
                                "content": f"다음 {ext} 파일을 분석하고 핵심 기능을 설명해주세요:\n\n파일: {rel_path}\n```{ext[1:]}\n{code[:3000]}\n```",
                            },
                            {
                                "role": "assistant",
                                "content": f"## {rel_path} 분석\n\n이 파일은 {len(lines)}줄의 {ext} 코드입니다.",
                            },
                        ],
                    }
                    _ = fout.write(json.dumps(chatml, ensure_ascii=False) + "\n")
                    count += 1

        logger.info("코드 파일 변환: %s개 → %s", count, output_path)
        return count

    @staticmethod
    def split_dataset(
        input_path: str,
        train_ratio: float = 0.9,
        seed: int = 42,
    ) -> tuple[str, str]:
        """데이터셋을 train/valid로 분할."""
        import random

        random.seed(seed)

        with open(input_path, encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]

        random.shuffle(lines)
        split_idx = int(len(lines) * train_ratio)

        train_path = input_path.replace(".jsonl", "_train.jsonl")
        valid_path = input_path.replace(".jsonl", "_valid.jsonl")

        with open(train_path, "w", encoding="utf-8") as f:
            f.writelines(lines[:split_idx])
        with open(valid_path, "w", encoding="utf-8") as f:
            f.writelines(lines[split_idx:])

        logger.info("분할 완료: train=%s, valid=%s", split_idx, len(lines) - split_idx)
        return train_path, valid_path


# ─── 파인튜닝 엔진 ──────────────────────────────────────────────────
class FineTuneEngine:
    """MLX LoRA 파인튜닝 엔진."""

    def __init__(self, config: TrainingConfig):
        """Initialize the FineTuneEngine.

        Args:
            config (TrainingConfig): TrainingConfig config.

        """
        self.config: TrainingConfig = config
        self.output_dir: Path = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 학습 상태
        self.current_step: int = 0
        self.current_epoch: int = 0
        self.best_val_loss: float = float("inf")
        self.training_log: list[str] = []

    def train(self) -> dict[str, object]:
        """파인튜닝 실행."""
        import subprocess
        import sys

        logger.info("=" * 60)
        logger.info("Ssak-Ai LoRA 파인튜닝 시작")
        logger.info("=" * 60)
        logger.info("  베이스 모델: %s", self.config.base_model)
        logger.info("  학습 데이터: %s", self.config.train_data)
        logger.info("  LoRA Rank:   %s", self.config.lora.rank)
        logger.info("  Epochs:      %s", self.config.num_epochs)
        logger.info("  Batch Size:  %s", self.config.batch_size)
        logger.info("  LR:          %s", self.config.learning_rate)
        logger.info("  출력 경로:   %s", self.output_dir)
        logger.info("=" * 60)

        start_time = time.time()

        # mlx_lm.lora CLI 호출
        cmd = [
            sys.executable,
            "-m",
            "mlx_lm.lora",
            "--model",
            self.config.base_model,
            "--data",
            str(Path(self.config.train_data).parent),
            "--train",
            "--adapter-path",
            str(self.output_dir / "adapters"),
            "--iters",
            str(self._calculate_total_iters()),
            "--batch-size",
            str(self.config.batch_size),
            "--learning-rate",
            str(self.config.learning_rate),
            "--lora-layers",
            str(self.config.lora.rank),
            "--save-every",
            str(self.config.save_every),
            "--seed",
            str(self.config.seed),
        ]

        if self.config.valid_data:
            cmd.extend(["--val-batches", "25"])

        logger.info("실행 명령: %s", " ".join(cmd))

        try:
            process: subprocess.Popen[str] = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # 실시간 로그 출력 + 수집
            assert process.stdout is not None
            stdout: TextIO = cast(TextIO, process.stdout)
            for raw_line in iter(stdout.readline, ""):
                line = raw_line.rstrip()
                if line:
                    logger.info("  [MLX] %s", line)
                    self.training_log.append(line)

                    # 진행 상황 파싱
                    if "Iter" in line and "loss" in line:
                        self._parse_training_line(line)

            _ = process.wait()

            elapsed = time.time() - start_time
            result: dict[str, object] = {
                "status": "success" if process.returncode == 0 else "failed",
                "return_code": process.returncode,
                "elapsed_seconds": round(elapsed, 1),
                "adapter_path": str(self.output_dir / "adapters"),
                "total_steps": self.current_step,
                "best_val_loss": (self.best_val_loss if self.best_val_loss < float("inf") else None),
            }

            if process.returncode == 0:
                logger.info("✓ 파인튜닝 완료! (%s초)", elapsed)
                self._save_training_info(result)
            else:
                logger.error("✗ 파인튜닝 실패 (exit code: %s)", process.returncode)

            return result

        except Exception as e:
            logger.exception("파인튜닝 오류")
            return {"status": "error", "error": str(e)}

    def merge_and_export(self, export_name: str | None = None) -> str:
        """LoRA 어댑터를 베이스 모델에 병합하여 독립 모델 생성."""
        import subprocess
        import sys

        adapter_path = self.output_dir / "adapters"
        name = export_name or f"finetuned-{int(time.time())}"
        export_path = Path(self.config.base_model).parent.parent / "finetuned" / name

        logger.info("모델 병합: %s → %s", adapter_path, export_path)

        cmd = [
            sys.executable,
            "-m",
            "mlx_lm.fuse",
            "--model",
            self.config.base_model,
            "--adapter-path",
            str(adapter_path),
            "--save-path",
            str(export_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            logger.info("✓ 병합 완료: %s", export_path)

            # api_forwarder 자동 등록을 위한 메타데이터 저장
            meta = {
                "name": name,
                "base_model": self.config.base_model,
                "type": "finetuned",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "lora_config": asdict(self.config.lora),
            }
            meta_path = export_path / "agk_model_meta.json"
            export_path.mkdir(parents=True, exist_ok=True)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            return str(export_path)
        else:
            logger.error("병합 실패: %s", result.stderr)
            raise RuntimeError(result.stderr)

    def _calculate_total_iters(self) -> int:
        """전체 학습 스텝 수 계산."""
        try:
            with open(self.config.train_data) as f:
                num_samples = sum(1 for _ in f)
        except Exception:
            logger.exception("Unhandled exception")
            num_samples = 1000  # 기본값

        steps_per_epoch = max(
            1,
            num_samples // (self.config.batch_size * self.config.gradient_accumulation_steps),
        )
        return steps_per_epoch * self.config.num_epochs

    def _parse_training_line(self, line: str):
        """학습 로그에서 스텝/loss 파싱."""
        try:
            # 예: "Iter 100: train loss 2.345, ..."
            if "Iter" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "Iter":
                        step_str = parts[i + 1].rstrip(":")
                        self.current_step = int(step_str)
                    if p == "loss":
                        loss_val = float(parts[i + 1].rstrip(","))
                        if "val" in line.lower() and loss_val < self.best_val_loss:
                            self.best_val_loss = loss_val
        except (IndexError, ValueError):
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)

    def _save_training_info(self, result: dict[str, object]) -> None:
        """학습 결과 메타데이터 저장."""
        info = {
            **result,
            "config": asdict(self.config),
            "training_log_lines": len(self.training_log),
        }
        info_path = self.output_dir / "training_info.json"
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        logger.info("학습 정보 저장: %s", info_path)


# ─── CLI 진입점 ──────────────────────────────────────────────────────
def main() -> None:
    """Run the main program."""
    import argparse

    class ParsedArgs(argparse.Namespace):
        command: str | None = None
        model: str = ""
        base_revision: str = ""
        data: str = ""
        output: str = ""
        epochs: int = 0
        batch_size: int = 0
        lr: float = 0.0
        lora_rank: int = 0
        manifest: str = ""
        resume: bool = False
        dry_run: bool = False
        estimated_peak_bytes: int | None = None
        resource_db: Path = Path()
        resource_idempotency_key: str | None = None
        input: str = ""
        format: str = ""
        split: Literal["90/10", "80/20"] = "90/10"
        seed: int = 0
        consent: str = ""
        subject_rights: str = ""
        license: str = ""
        run: str = ""
        evaluation: str | None = None
        artifact: str = ""
        state: str = ""
        decision: str = ""
        recipe_sha256: str = ""
        evaluation_sha256: str = ""
        dataset: str = ""
        backend: str = ""
        endpoint: str = ""
        tuned_model: str | None = None
        max_tokens: int = 0
        temperature: float = 0.0
        routing_model_name: str | None = None
        minimum_category_score: float = 0.0
        maximum_category_regression: float = 0.0
        minimum_overall_improvement: float = 0.0

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Ssak-Ai LoRA 파인튜닝")
    sub = parser.add_subparsers(dest="command", help="명령")

    # train
    train_p = sub.add_parser("train", help="파인튜닝 실행")
    _ = train_p.add_argument("--model", required=True, help="베이스 모델 경로")
    _ = train_p.add_argument("--base-revision", required=True, help="베이스 모델 revision digest")
    _ = train_p.add_argument("--data", required=True, help="학습 데이터 (JSONL)")
    _ = train_p.add_argument("--output", default="./output/finetune", help="출력 경로")
    _ = train_p.add_argument("--epochs", type=int, default=3)
    _ = train_p.add_argument("--batch-size", type=int, default=4)
    _ = train_p.add_argument("--lr", type=float, default=1e-5)
    _ = train_p.add_argument("--lora-rank", type=int, default=16)
    _ = train_p.add_argument("--manifest", required=True, help="Frozen dataset split manifest")
    _ = train_p.add_argument("--resume", action="store_true", help="최신 체크포인트에서 학습 재개")
    _ = train_p.add_argument("--dry-run", action="store_true", help="해석된 학습 설정만 출력")
    _ = train_p.add_argument("--estimated-peak-bytes", type=int, help="예상 최대 unified-memory 사용량")
    _ = train_p.add_argument(
        "--resource-db",
        type=Path,
        default=config.paths.data_dir / "unsloth_resources.sqlite3",
        help="공용 capability/resource broker DB 경로",
    )
    _ = train_p.add_argument("--resource-idempotency-key", help="재시도 중복 실행 방지 키")
    _ = train_p.add_argument(
        "--timeout-sec",
        type=float,
        help="TRN-02 — 학습 wall-clock 상한 (초). 초과 시 프로세스 그룹이 종료된다",
    )
    _ = train_p.add_argument(
        "--no-output-timeout-sec",
        type=float,
        help="TRN-02 — 무출력 hang 감지 상한 (초). stdout 정체 시 프로세스 그룹이 종료된다",
    )

    # prepare
    prep_p = sub.add_parser("prepare", help="데이터 준비")
    _ = prep_p.add_argument("--input", required=True, help="입력 데이터 경로")
    _ = prep_p.add_argument("--output", required=True, help="출력 JSONL 경로")
    _ = prep_p.add_argument("--format", choices=["instruction", "code"], default="instruction")
    _ = prep_p.add_argument("--split", choices=["90/10", "80/20"], required=True, help="train/valid 비율")
    _ = prep_p.add_argument("--seed", type=int, required=True, help="불변 split seed")
    _ = prep_p.add_argument(
        "--consent",
        choices=[member.value for member in DatasetConsent],
        required=True,
        help="데이터 사용 동의 상태",
    )
    _ = prep_p.add_argument(
        "--subject-rights",
        choices=[member.value for member in DatasetSubjectRights],
        required=True,
        help="데이터 주체 권리 처리 상태",
    )
    _ = prep_p.add_argument(
        "--license",
        choices=[member.value for member in DatasetLicense],
        required=True,
        help="데이터 라이선스",
    )

    # merge
    merge_p = sub.add_parser("merge", help="어댑터 병합")
    _ = merge_p.add_argument("--run", required=True, help="training_result.json 경로")
    _ = merge_p.add_argument("--output", required=True, help="병합 결과 경로")
    _ = merge_p.add_argument("--evaluation", help="base/tuned evaluation_result.json 경로")
    _ = merge_p.add_argument("--estimated-peak-bytes", type=int, help="예상 최대 unified-memory 사용량")
    _ = merge_p.add_argument(
        "--resource-db",
        type=Path,
        default=config.paths.data_dir / "unsloth_resources.sqlite3",
        help="공용 capability/resource broker DB 경로",
    )
    _ = merge_p.add_argument("--resource-idempotency-key", help="재시도 중복 실행 방지 키")

    promote_p = sub.add_parser("promote", help="검증된 artifact를 active pointer로 승격")
    _ = promote_p.add_argument("--artifact", required=True, help="병합 artifact 디렉터리")
    _ = promote_p.add_argument("--state", required=True, help="active artifact pointer JSON 경로")
    _ = promote_p.add_argument("--decision", required=True, help="eligible promotion_decision.json 경로")
    _ = promote_p.add_argument("--recipe-sha256", required=True, help="승격할 recipe SHA-256")
    _ = promote_p.add_argument("--evaluation-sha256", required=True, help="승격할 evaluation SHA-256")

    rollback_p = sub.add_parser("rollback", help="직전 active artifact로 복원")
    _ = rollback_p.add_argument("--state", required=True, help="active artifact pointer JSON 경로")

    evaluate_p = sub.add_parser("evaluate", help="base/tuned 후보를 실제 backend로 평가")
    _ = evaluate_p.add_argument("--run", required=True, help="training_result.json 경로")
    _ = evaluate_p.add_argument("--dataset", required=True, help="frozen held_out_v1.jsonl 경로")
    _ = evaluate_p.add_argument("--backend", choices=[member.value for member in EvaluationBackend], required=True)
    _ = evaluate_p.add_argument("--output", required=True, help="evaluation_result.json 경로")
    _ = evaluate_p.add_argument("--endpoint", default="http://127.0.0.1:11434", help="Ollama API endpoint")
    _ = evaluate_p.add_argument("--tuned-model", help="Ollama tuned model name")
    _ = evaluate_p.add_argument("--max-tokens", type=int, default=256)
    _ = evaluate_p.add_argument("--temperature", type=float, default=0.0)

    gate_p = sub.add_parser("evaluate-gate", help="held-out base/tuned 결과의 artifact 승격 가능 여부 판정")
    _ = gate_p.add_argument("--evaluation", required=True, help="evaluation_result.json 경로")
    _ = gate_p.add_argument("--output", required=True, help="promotion_decision.json 경로")
    _ = gate_p.add_argument("--routing-model-name", help="router calibration에서 사용할 모델 이름")
    _ = gate_p.add_argument("--minimum-category-score", type=float, default=0.5)
    _ = gate_p.add_argument("--maximum-category-regression", type=float, default=0.0)
    _ = gate_p.add_argument("--minimum-overall-improvement", type=float, default=0.01)

    args: ParsedArgs = parser.parse_args(namespace=ParsedArgs())

    if args.command == "train":
        manifest_path = Path(args.manifest)
        manifest: JsonObject = cast(JsonObject, json.loads(manifest_path.read_text(encoding="utf-8")))
        recipe = TrainingRecipe(
            base_model=args.model,
            base_revision=args.base_revision,
            output_dir=Path(args.output),
            dataset=FinetuneDatasetContract(
                path=Path(args.data),
                consent=DatasetConsent.EXPLICIT,
                subject_rights=DatasetSubjectRights.HONORED,
                license_id=DatasetLicense(cast(str, manifest.get("license", "MIT"))),
                split_policy=DatasetSplitPolicy(
                    seed=cast(int, manifest["seed"]),
                    train_ratio=cast(Literal["90/10", "80/20"], manifest["train_ratio"]),
                    manifest_path=manifest_path,
                ),
            ),
            epochs=args.epochs,
            batch_size=args.batch_size,
            gradient_accumulation_steps=4,
            learning_rate=Decimal(str(args.lr)),
            lora_rank=args.lora_rank,
            lora_alpha=args.lora_rank * 2,
            save_every=100,
            seed=42,
        )
        try:
            resolved = resolve_training_recipe(recipe, resume=args.resume)
        except TrainingRecipeError as error:
            logger.error("학습 레시피 검증 실패: %s", error)
            raise SystemExit(2) from error
        if args.dry_run:
            print(resolved.model_dump_json(indent=2))
            return
        if args.estimated_peak_bytes is None:
            parser.error("--estimated-peak-bytes is required for non-dry-run training")
        try:
            resource_settings = FinetuneResourceSettings(
                database_path=args.resource_db,
                estimated_peak_bytes=args.estimated_peak_bytes,
                idempotency_key=args.resource_idempotency_key,
            )
            admission = build_finetune_resource_admission(
                build_training_admission_request(resolved, resource_settings),
                resource_settings,
            )
            with reserve_finetune_resource(admission):
                result = run_resolved_training(
                    resolved,
                    timeout_sec=args.timeout_sec,
                    no_output_timeout_sec=args.no_output_timeout_sec,
                )
        except ValidationError as error:
            logger.error("학습 자원 설정 검증 실패")
            raise SystemExit(2) from error
        except (FinetuneResourceAdmissionError, FinetuneResourceInvariantError) as error:
            logger.error("학습 자원 승인 실패: %s", error)
            raise SystemExit(2) from error
        print(result.model_dump_json(indent=2))

    elif args.command == "prepare":
        try:
            if args.format == "instruction":
                count = DatasetPreparer.from_instruction(args.input, args.output)
            elif args.format == "code":
                count = DatasetPreparer.from_code_files(args.input, args.output)
            else:
                print(f"알 수 없는 포맷: {args.format}")
                return

            contract = FinetuneDatasetContract(
                path=Path(args.output),
                consent=DatasetConsent(args.consent),
                subject_rights=DatasetSubjectRights(args.subject_rights),
                license_id=DatasetLicense(args.license),
                split_policy=DatasetSplitPolicy(
                    seed=args.seed,
                    train_ratio=args.split,
                    manifest_path=Path(args.output).with_name("split_manifest.json"),
                ),
            )
            split_paths = split_frozen_dataset(contract)
            print(f"✓ {count}개 샘플 변환 및 계약 검증 완료: {args.output}")
            print(f"✓ 분할 완료: {split_paths.train_path}, {split_paths.valid_path}")
        except DatasetContractError as error:
            logger.error("데이터 계약 검증 실패: %s", error)
            raise SystemExit(2) from error

    elif args.command == "merge":
        run_path = Path(args.run)
        training = TrainingRunResult.model_validate_json(run_path.read_text(encoding="utf-8"))
        if args.estimated_peak_bytes is None:
            parser.error("--estimated-peak-bytes is required for merge")
        try:
            resource_settings = FinetuneResourceSettings(
                database_path=args.resource_db,
                estimated_peak_bytes=args.estimated_peak_bytes,
                idempotency_key=args.resource_idempotency_key,
            )
            admission = build_finetune_resource_admission(
                build_merge_admission_request(run_path, training, resource_settings),
                resource_settings,
            )
            with reserve_finetune_resource(admission):
                fused = fuse_training_artifact(
                    training,
                    output_path=Path(args.output),
                    evaluation_path=None if args.evaluation is None else Path(args.evaluation),
                )
        except ValidationError as error:
            logger.error("병합 자원 설정 검증 실패")
            raise SystemExit(2) from error
        except (ArtifactLifecycleError, FinetuneResourceAdmissionError, FinetuneResourceInvariantError) as error:
            logger.error("학습 artifact 병합 실패: %s", error)
            raise SystemExit(2) from error
        print(fused.model_dump_json(indent=2))

    elif args.command == "promote":
        try:
            outcome = promote_artifact(
                Path(args.artifact),
                state_path=Path(args.state),
                contract=ArtifactPromotionContract(
                    recipe_sha256=args.recipe_sha256,
                    evaluation_sha256=args.evaluation_sha256,
                ),
                decision_path=Path(args.decision),
                probe=MlxFusedArtifactProbe(),
            )
        except ActiveArtifactError as error:
            logger.error("Active artifact 승격 실패: %s", error)
            raise SystemExit(2) from error
        print(outcome.model_dump_json(indent=2))
        if outcome.status is ActiveArtifactStatus.ROLLED_BACK:
            raise SystemExit(4)

    elif args.command == "rollback":
        try:
            active = rollback_active_artifact(Path(args.state))
        except ActiveArtifactError as error:
            logger.error("Active artifact 복원 실패: %s", error)
            raise SystemExit(2) from error
        print(active.model_dump_json(indent=2))

    elif args.command == "evaluate":
        training = TrainingRunResult.model_validate_json(Path(args.run).read_text(encoding="utf-8"))
        dataset_path = Path(args.dataset)
        dataset = EvaluationDataset(
            path=dataset_path,
            sha256=hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            case_ids=tuple(
                json.loads(line)["id"] for line in dataset_path.read_text(encoding="utf-8").splitlines() if line
            ),
        )
        backend = EvaluationBackend(args.backend)
        inference: Callable[[EvaluationCase, CandidateKind], str]
        match backend:
            case EvaluationBackend.MLX:
                inference = MlxEvaluationInference(
                    base_model=training.base_model,
                    base_revision=training.base_revision,
                    adapter_path=training.adapter_path,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                )
            case EvaluationBackend.OLLAMA:
                if args.tuned_model is None:
                    parser.error("--tuned-model is required for the ollama backend")
                inference = OllamaEvaluationInference(
                    endpoint=args.endpoint,
                    base_model=training.base_model,
                    tuned_model=args.tuned_model,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                )
        try:
            pair = evaluate_candidates(
                dataset=dataset,
                model=training.base_model,
                model_revision=training.base_revision,
                adapter_path=training.adapter_path,
                recipe_sha256=training.recipe_sha256,
                environment=training.environment,
                inference=inference,
            )
        except EvaluationInferenceError as error:
            logger.error("평가 추론 실패: %s", error)
            raise SystemExit(2) from error
        _ = Path(args.output).write_text(pair.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(pair.model_dump_json(indent=2))

    elif args.command == "evaluate-gate":
        if args.evaluation is None:
            parser.error("--evaluation is required for evaluate-gate")
        try:
            decision = load_promotion_decision(
                Path(args.evaluation),
                policy=PromotionGatePolicy(
                    minimum_category_score=args.minimum_category_score,
                    maximum_category_regression=args.maximum_category_regression,
                    minimum_overall_improvement=args.minimum_overall_improvement,
                ),
                routing_model_name=args.routing_model_name,
            )
        except (EvaluationError, ValidationError) as error:
            logger.error("평가 승격 게이트 실패: %s", error)
            raise SystemExit(2) from error
        _ = Path(args.output).write_text(decision.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(decision.model_dump_json(indent=2))
        if not decision.eligible:
            raise SystemExit(3)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
