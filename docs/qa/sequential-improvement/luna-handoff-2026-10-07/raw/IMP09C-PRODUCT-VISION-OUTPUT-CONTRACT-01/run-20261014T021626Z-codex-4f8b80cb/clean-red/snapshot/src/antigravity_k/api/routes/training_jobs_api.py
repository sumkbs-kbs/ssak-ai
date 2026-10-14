"""학습 잡 API — StudioPage Start Training의 실제 백엔드 (Phase 59).

기존 POST /v1/integrations/unsloth/training/start는 Unsloth MCP 원격 런처라
로컬 mlx 파이프라인과 무관했다. 이 라우터는 ``LoRAPipeline.apply_recipe``로
레시피→데이터셋→설정을 구성하고 ``run_training``을 백그라운드 스레드로 실행해
``GET /api/training-jobs/{id}`` 폴링으로 진행/로그를 회수한다.

시뮬레이션 없음: progress는 실제 로그 라인 수 / 예상 반복 수 기반,
loss는 mlx-lm 로그에서 파싱한 실제 값 (파싱 실패 시 마지막 값 유지).
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
import uuid
from typing import Any, TypedDict

from fastapi import APIRouter, HTTPException

from antigravity_k.finetune.training_supervision import TERMINATION_GRACE_SEC
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission, ToolInvocation, ToolSpec

logger = logging.getLogger("antigravity_k.api.training_jobs")
router = APIRouter(prefix="/api/training-jobs")


class TrainingJobStartRequest(TypedDict, total=False):
    recipe: str
    base_model: str
    source: str
    platform: str
    hyperparameters: dict[str, float | int | str]
    pdf_pages: str
    pdf_header_filter: str
    pdf_question_template: str
    timeout_sec: float | None  # TRN-02 — 학습 wall-clock 상한 (None=무제한)
    no_output_timeout_sec: float | None  # TRN-02 — 무출력 hang 감지 상한 (None=비활성)


class TrainingJobView(TypedDict):
    job_id: str
    status: str  # running | completed | failed
    recipe: str
    platform: str
    dataset_path: str
    config_path: str
    records: int
    sufficient: bool
    progress: int  # 0-100 (config 생성 완료 후 실제 반복 진행률)
    loss: float | None
    log_tail: list[str]
    error: str
    started_at: float
    finished_at: float | None
    recipe_sha256: str  # TRN-01 — 재실행 provenance 키
    iterations: int  # TRN-01 — child argv의 --iters와 동일 (progress denominator)
    termination: str  # TRN-02 — completed | timeout | no_output_hang | cancelled


# TRN-02/F-16 — 종결 상태를 뜻하는 값들. 이 값에 도달한 뒤에는 진행 필드도 바뀌지 않는다.
_TERMINAL_STATUSES = frozenset({"completed", "failed"})


class _Job:
    """단일 학습 잡의 가변 상태. 스레드에서 갱신, 라우터에서 읽는다.

    **쓰기 단일 지점**: 뷰를 만지는 모든 경로가 ``self._lock`` 을 통과한다. 종결 상태
    (``status``/``termination``/``error``/``finished_at``)는 ``finalize()`` 만 쓴다.

    왜 규칙이 필요한가(F-16): 취소 핸들러와 잡 스레드가 같은 dict 를 잠금 없이 쓰면
    **나중에 쓴 쪽이 이긴다.** 취소와 watchdog 의 timeout 이 거의 같은 순간에 확정되면
    (둘 다 사실이다) 기록을 정하는 것은 스레드 스케줄링이고, 진 쪽의 사실은 조용히
    사라진다 — 사용자는 취소했고 API 는 ``ok: true`` 로 답했는데 뷰는 ``timeout`` 이 된다.
    """

    def __init__(self, job_id: str, recipe: str, platform: str) -> None:
        self._lock = threading.Lock()
        self.view: TrainingJobView = {
            "job_id": job_id,
            "status": "running",
            "recipe": recipe,
            "platform": platform,
            "dataset_path": "",
            "config_path": "",
            "records": 0,
            "sufficient": False,
            "progress": 0,
            "loss": None,
            "log_tail": [],
            "error": "",
            "started_at": time.time(),
            "finished_at": None,
            "recipe_sha256": "",
            "iterations": 0,
            "termination": "completed",
        }
        self.iterations = 0  # mlx-lm --iterations (진행률 분모)
        self.cancel_event = threading.Event()  # TRN-02 — watchdog cancel 신호
        self.proc: subprocess.Popen[str] | None = None  # run_training의 Popen — 취소용 (on_proc_start 콜백)
        self._cancelled = False

    @property
    def status(self) -> str:
        with self._lock:
            return self.view["status"]

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def claim_cancel(self) -> bool:
        """취소를 **한 번만** 접수한다 — 이중 취소가 프로세스 그룹을 두 번 종료하지 않게."""
        with self._lock:
            if self._cancelled:
                return False
            self._cancelled = True
            return True

    def note(self, **fields: object) -> None:
        """진행 중 갱신 — 종결이 확정된 뒤에는 아무것도 바꾸지 않는다."""
        with self._lock:
            if self.view["status"] in _TERMINAL_STATUSES:
                return
            # TypedDict 는 임의 키에 값을 쓰는 경로의 타입을 표현하지 못한다 — 키는 호출부가
            # 리터럴로 주고, 값 검증은 회귀(TestTerminalRecordOwnership)가 한다.
            target: Any = self.view
            target.update(fields)

    def finalize(
        self,
        *,
        success: bool,
        termination: str | None = None,
        error: str = "",
        progress: int | None = None,
    ) -> bool:
        """종결 전이 **단일 지점** — 먼저 확정한 쪽이 기록을 소유한다(멱등).

        늦게 도착한 사실은 기록을 덮지 않는다. 반환값이 ``False`` 면 이미 다른 주체가
        종결을 확정했다는 뜻이고, 호출자는 그 사실을 자기 응답에 반영해야 한다.
        """
        with self._lock:
            if self.view["status"] in _TERMINAL_STATUSES:
                return False
            if termination is not None:
                self.view["termination"] = termination
            self.view["status"] = "completed" if success else "failed"
            self.view["error"] = error
            if progress is not None:
                self.view["progress"] = progress
            self.view["finished_at"] = time.time()
            return True

    def snapshot(self) -> TrainingJobView:
        """라우터가 돌려주는 **일관된 복사본** — 살아 있는 dict/list 를 넘기지 않는다."""
        with self._lock:
            view: Any = dict(self.view)
            view["log_tail"] = list(self.view["log_tail"])
            return view

    def append_log(self, line: str) -> None:
        with self._lock:
            tail = self.view["log_tail"]
            tail.append(line)
            if len(tail) > 80:
                del tail[: len(tail) - 80]
            if self.view["status"] in _TERMINAL_STATUSES:
                return  # 종결 뒤의 진행 갱신은 기록을 흔들지 않는다
            if self.iterations > 0:
                m = re.search(r"^iter(?:ation)?\s+(\d+)", line)
                if m:
                    self.view["progress"] = min(99, int(m.group(1)) * 100 // self.iterations)
            loss_match = re.search(r"(?:loss|train_loss)[=:]\s*([0-9.]+)", line, re.IGNORECASE)
            if loss_match:
                self.view["loss"] = float(loss_match.group(1))


# 프로세스 내 잡 저장 — 서버 재시작 시 사라지는 것이 정책 (학습 재개는 run_training 재실행으로)
_JOBS: dict[str, _Job] = {}
_JOBS_LOCK = threading.Lock()
_MAX_JOBS = 20


def _permission_gate() -> PermissionGate:
    from antigravity_k.api.routes.filesystem import WORKSPACE_ROOT

    return PermissionGate(project_root=WORKSPACE_ROOT, mode="auto-pilot")


def _require_allowed(tool_name: str, args: dict[str, str], risk_level: str) -> None:
    decision = _permission_gate().decide(
        ToolInvocation(ToolSpec(name=tool_name, risk_level=risk_level, category="api"), args),
    )
    if decision.permission != Permission.ALLOW:
        raise HTTPException(status_code=403, detail=f"Permission denied for {tool_name}: {decision.permission.value}")


def _iters_from_command(command: str) -> int:
    """mlx-lm command에서 --iters 값을 파싱 (progress denominator 백업 경로)."""
    tokens = command.split()
    for i, tok in enumerate(tokens):
        if tok == "--iters" and i + 1 < len(tokens):
            try:
                return int(tokens[i + 1])
            except ValueError:
                return 0
    return 0


def _validate_start_request(request: TrainingJobStartRequest) -> None:
    """시작 요청 하이퍼파라미터 게이트 (TRN-01) — 잡 생성 전 400 거절.

    iterations가 지정된 경우 검증하고, 나머지 키는 finetune.hyperparameters의
    단일 규칙으로 검증한다 (백엔드는 요청 platform; auto면 mlx 가정).
    """
    from antigravity_k.finetune.hyperparameters import HyperparameterValidationError, validate_hyperparameters

    platform = str(request.get("platform", "auto"))
    backend = "mlx" if platform in ("", "auto", "mlx") else platform
    try:
        _ = validate_hyperparameters(dict(request.get("hyperparameters", {})), backend=backend)
    except HyperparameterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_job(job: _Job, request: TrainingJobStartRequest) -> None:
    """백그라운드 스레드 본체 — apply_recipe 후 run_training."""
    from antigravity_k.engine.lora_pipeline import LoRAPipeline

    output_dir = f"data/training_jobs/{job.view['job_id']}"
    hyper = {k: v for k, v in request.get("hyperparameters", {}).items() if k != "iterations"}
    iterations_raw = request.get("hyperparameters", {}).get("iterations", 600)
    try:
        job.iterations = int(iterations_raw) if isinstance(iterations_raw, (int, float, str)) else 600
    except (TypeError, ValueError):
        job.iterations = 600

    try:
        pipeline = LoRAPipeline()
        result = pipeline.apply_recipe(
            request.get("recipe", "chat-sft"),
            base_model=request.get("base_model", ""),
            output_dir=output_dir,
            source=request.get("source", ""),
            platform=request.get("platform", "auto"),
            pdf_pages=request.get("pdf_pages", ""),
            pdf_header_filter=request.get("pdf_header_filter", ""),
            pdf_question_template=request.get("pdf_question_template", ""),
            hyperparameter_overrides=hyper or None,
        )
    except Exception as exc:  # noqa: BLE001 — 잡 스레드에서 모든 실패를 상태로 전환
        logger.exception("apply_recipe failed for job %s", job.view["job_id"])
        job.finalize(success=False, error=str(exc))
        return

    # TRN-01: progress denominator와 digest는 apply_recipe 결과(검증된 오버라이드)에서
    # 읽는다 — 요청 → argv → progress가 하나의 dict에서 나온다.
    job.note(recipe_sha256=str(result.get("recipe_sha256", "")))
    config = result.get("config")
    config_iters = 0
    if isinstance(config, dict):
        hyper_cfg = config.get("hyperparameters")
        raw_iters = hyper_cfg.get("iterations") if isinstance(hyper_cfg, dict) else None
        try:
            config_iters = int(raw_iters) if raw_iters is not None else 0
        except (TypeError, ValueError):
            config_iters = 0
        if config_iters <= 0:
            config_iters = _iters_from_command(str(config.get("command", "")))
    if config_iters > 0:
        job.iterations = config_iters
    job.note(iterations=job.iterations)

    job.note(
        dataset_path=str(result.get("dataset_path", "")),
        config_path=str(result.get("config_path", "")),
        records=int(result.get("records", 0)),
        sufficient=bool(result.get("sufficient", False)),
        progress=5,  # config 생성 완료
    )

    config = result.get("config")
    if job.iterations <= 0 or not isinstance(config, dict):
        job.finalize(success=True, progress=100)
        return

    # 실제 학습 실행 (동기 — 잡 스레드 안이므로 이벤트 루프를 막지 않는다)
    # TRN-02: watchdog이 timeout/no-output/cancel을 감독하고, on_proc_start로
    # 실제 Popen을 잡에 노출해 취소가 프로세스 그룹에 도달하게 한다.
    def _capture_proc(proc: subprocess.Popen[str]) -> None:
        job.proc = proc

    run_result = pipeline.run_training(
        config,
        on_log=job.append_log,
        timeout_sec=request.get("timeout_sec"),
        no_output_timeout_sec=request.get("no_output_timeout_sec"),
        cancel_event=job.cancel_event,
        on_proc_start=_capture_proc,
    )
    job.finalize(
        success=run_result.success,
        termination=run_result.termination,
        error="" if run_result.success else (run_result.error or f"exit_code={run_result.exit_code}"),
        progress=100,
    )


@router.post("")
async def start_training_job(request: TrainingJobStartRequest) -> dict[str, object]:
    """레시피 적용 + 학습 실행을 백그라운드 잡으로 시작한다."""
    _validate_start_request(request)
    _require_allowed(
        "start_training", {"recipe": request.get("recipe", ""), "base_model": request.get("base_model", "")}, "critical"
    )

    job_id = f"train_{uuid.uuid4().hex[:12]}"
    job = _Job(job_id, request.get("recipe", ""), request.get("platform", "auto"))
    with _JOBS_LOCK:
        _JOBS[job_id] = job
        # 상한 초과 시 가장 오래된 완료 잡 정리
        if len(_JOBS) > _MAX_JOBS:
            finished = [k for k, v in _JOBS.items() if v.status != "running"]
            for key in sorted(finished, key=lambda k: _JOBS[k].view["started_at"])[: len(_JOBS) - _MAX_JOBS]:
                _ = _JOBS.pop(key, None)

    thread = threading.Thread(target=_run_job, args=(job, request), name=f"training-{job_id}", daemon=True)
    thread.start()
    return {"ok": True, "job_id": job_id}


@router.get("/{job_id}")
async def get_training_job(job_id: str) -> TrainingJobView:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown training job")
    # F-16 — 살아 있는 dict 를 돌려주지 않는다. 종결 필드는 한 세트로 읽혀야 한다.
    return job.snapshot()


@router.post("/{job_id}/cancel")
def cancel_training_job(job_id: str) -> dict[str, object]:
    """취소 — 종결 기록을 **먼저 소유**한 뒤 프로세스 그룹을 종료한다.

    - ``async def`` 가 아니라 ``def`` 다: 아래 ``terminate_process_group`` 은 ``proc.wait``
      로 최대 ``2 × grace`` 초를 블록하므로 이벤트 루프에서 돌리면 그 동안 서버 전체가
      멈춘다(F-17). FastAPI 는 동기 라우트를 스레드풀에서 실행한다.
    - 기록을 종료보다 **먼저** 쓴다: 사용자의 취소는 ``cancel_event`` 를 세우는 순간
      확정된 사실이고, 감독 watchdog 의 ``timeout`` 과 경합할 때 종료를 기다렸다가 쓰면
      늦게 도착한 timeout 이 기록을 가져간다(F-16).
    """
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown training job")
    if job.status != "running":
        # TRN-02 — 중복 cancel은 idempotent: 이미 종료된 잡이면 200 ok:false 반환
        return {"ok": False, "detail": "job is not running"}
    if not job.claim_cancel():
        return {"ok": False, "detail": "job already cancelled"}
    job.cancel_event.set()  # watchdog이 프로세스 그룹 전체를 종료한다
    owned = job.finalize(success=False, termination="cancelled", error="cancelled by user")
    proc = job.proc
    if proc is not None and hasattr(proc, "terminate"):
        # watchdog이 아직 시작 전인 극초기 레이스 보호 — 그룹 종료 재시도
        try:
            from antigravity_k.finetune.training_supervision import terminate_process_group

            terminate_process_group(proc, grace_sec=TERMINATION_GRACE_SEC)
        except Exception:  # noqa: BLE001 — 이미 종료된 프로세스는 무시
            pass
    if not owned:
        # 우리가 쓰기 전에 잡 스레드가 종결을 확정했다 — 종료는 했지만 기록의 주인은 아니다.
        return {"ok": False, "detail": "job already finished"}
    return {"ok": True}
