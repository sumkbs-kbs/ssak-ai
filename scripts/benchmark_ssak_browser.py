#!/usr/bin/env python3
"""task 22 — 브라우저 업무 benchmark · false-completion 평가.

계획 QA:
    uv run --frozen python scripts/benchmark_ssak_browser.py \
        --suite tests/fixtures/browser_workflows --runs 3 --output <E/task-22/results.json>

무엇을 재는가
------------
50개 워크플로(30 읽기 + 20 다단계)를 fixture 서버 **위에서** 실제 Chromium 으로 수행하고,
루프의 결말(`TaskOutcome`)과 **독립 그레이더**의 판정을 교차한다.

- ground truth 는 fixture DOM(서버가 주는 HTML)과 **서버 상태**(경로별 GET 카운터 · POST 뮤테이션
  카운터)다 — 루프가 스스로 보고한 사후조건과 별개다.
- **false completion** = 루프가 `succeeded` 라고 보고했는데 그레이더가 달성 아니라고 판정한 실행.
  반대(실패 보고 + 실제 달성)는 `underclaim` 으로 따로 센다.
- **사람 개입** = 승인이 필요한 효과에서 루프가 `blocked` 로 멈춘 실행(의도된 정답 경로).
- **접속 불가** 워크플로는 실패로 집계되고 **분모에서 빠지지 않는다**(`denominator.excluded` 는
  비어 있는 것이 정상이다).
- scripted planner(결정적)와 실제 모델 planner 는 **별도 표기**된다 — 모델이 없으면 그 칸은
  `NOT_RUN` 과 이유로 남는다(조용히 비우지 않는다).

나가는 코드: 0 정상 · 1 `--fail-on-false-completion` 에서 false completion 발견 · 2 하네스 오류.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import statistics
import sys
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from antigravity_k.agents.browser_surfing_agent import BrowserSurfingAgent, _ObserverLoopHost, _SurfSession
from antigravity_k.agents.browser_task_loop import (
    GOAL_VERIFIED,
    BrowserTaskLoop,
    PlannedAction,
    Postcondition,
    TaskBudget,
    TaskGoal,
    TaskOutcome,
    host_token_budget,
)
from antigravity_k.tools.browser_approval import reset_browser_approval
from antigravity_k.tools.browser_observation import BrowserObserver, Observation, ObservationPolicy
from antigravity_k.tools.browser_session_owner import BrowserOwner

RESULTS_SCHEMA = "ssak.browser.benchmark.v1"
NAVIGATION_FAILED = "NAVIGATION_FAILED"


# ── fixture 서버: DOM + 서버 상태(ground truth) ─────────────────────────────


@dataclass
class ServerState:
    """그레이더가 읽는 유일한 서버 진실. 실행마다 해당 워크플로 칸만 리셋된다."""

    reads: dict[tuple[str, str], int] = field(default_factory=dict)
    mutations: dict[str, int] = field(default_factory=dict)

    def reset(self, wid: str) -> None:
        self.mutations[wid] = 0
        for key in [key for key in self.reads if key[0] == wid]:
            del self.reads[key]

    def snapshot(self, wid: str) -> dict[str, int]:
        return {route: count for (owner, route), count in self.reads.items() if owner == wid}


def make_server(pages: dict[tuple[str, str], str], state: ServerState) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _serve(self, *, mutation: bool) -> None:
            route = self.path.split("?", 1)[0]
            key = _route_key(route)
            if mutation:
                state.mutations[key[0]] = state.mutations.get(key[0], 0) + 1
                payload = b'{"ok":true}'
                status = 200
            else:
                body = pages.get(key)
                if body is None:
                    payload = b"<html><body>not found</body></html>"
                    status = 404
                else:
                    state.reads[key] = state.reads.get(key, 0) + 1
                    # `@/...` 링크는 이 워크플로의 네임스페이스로 재작성한다 — fixture 페이지가
                    # 서로 다른 워크플로의 경로를 건드리지 못하게 하는 유일한 통로다.
                    payload = body.replace("@/", f"/{key[0]}/").encode("utf-8")
                    status = 200
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            self._serve(mutation=False)

        def do_POST(self) -> None:  # noqa: N802
            _ = int(self.headers.get("Content-Length") or 0)
            if self.rfile and _:
                _ = self.rfile.read(_)
            self._serve(mutation=True)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - 부모 규약
            return  # 시험 로그를 조용히

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _route_key(route: str) -> tuple[str, str]:
    parts = route.lstrip("/").split("/", 1)
    if len(parts) == 2:
        return (parts[0], "/" + parts[1])
    return (parts[0] if parts else "", "/")


# ── scripted planner(결정적) ────────────────────────────────────────────────


class ScriptedWorkflowPlanner:
    """JSON 대본을 따라가는 planner. 관찰에 없는 대상은 **지어내지 않고** 멈춘다(기록용 표식)."""

    def __init__(self, script: list[dict[str, Any]], url_for: Any) -> None:
        self.queue: deque[dict[str, Any]] = deque(script)
        self.url_for = url_for
        self.calls = 0
        self.last_tokens = 0
        self.stalled: list[str] = []

    async def plan(
        self,
        *,
        goal: TaskGoal,
        observation: Observation,
        history: Any,
        remaining_actions: int,
    ) -> PlannedAction:
        self.calls += 1
        # 직전 행동이 계약 거절로 끝났다면 **같은 항목을 다시 제안**한다(재관찰 후 재시도) —
        # 무조건 다음 항목으로 넘어가면 대본이 실제 페이지와 어긋난다.
        retried = bool(history) and bool(getattr(history[-1], "rejected", ""))
        if not self.queue:
            return PlannedAction(action="done", reason="대본을 모두 수행했다")
        item = self.queue[0] if retried else self.queue.popleft()
        action = str(item.get("action") or "")
        if action == "done":
            return PlannedAction(action="done", reason=str(item.get("reason") or ""))
        if action == "goto":
            return PlannedAction(
                action="goto", url=self.url_for(str(item.get("target") or "/")), reason=str(item.get("reason") or "")
            )
        name = str(item.get("target") or "")
        ref = observation.ref_for(name)
        if ref is None:
            self.stalled.append(name)
            return PlannedAction(action="done", reason=f"관찰에 {name!r} 이(가) 없어 대본을 멈춘다")
        filled = str(item.get("value") or "")
        return PlannedAction(
            action="click" if action == "click" else "fill",
            ref=ref,
            target_name=name,
            text=filled if action != "click" else None,
            value=filled,
            reason=str(item.get("reason") or ""),
        )


# ── 그레이더(루프와 독립) ───────────────────────────────────────────────────


def grade(workflow: dict[str, Any], state: ServerState, base: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    wid = workflow["id"]
    spec = workflow["grader"]
    mutations = state.mutations.get(wid, 0)
    expected = int(spec.get("mutations_equals", 0))
    if mutations != expected:
        reasons.append(f"mutations={mutations} (기대 {expected})")
    for route, minimum in (spec.get("reads_min") or {}).items():
        seen = state.reads.get((wid, str(route)), 0)
        if seen < int(minimum):
            reasons.append(f"reads[{route}]={seen} < {minimum}")
    for item in spec.get("content") or []:
        route = str(item.get("route") or "/")
        try:
            with urllib.request.urlopen(f"{base}/{wid}{route}", timeout=10) as response:
                body = response.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - 그레이더는 실패 사실을 문장으로 남긴다
            reasons.append(f"content[{route}] 조회 실패: {exc}")
            continue
        for needle in item.get("contains") or []:
            if needle not in body:
                reasons.append(f"content[{route}] 에 {needle!r} 없음")
    return (not reasons), reasons


# ── 지표 ────────────────────────────────────────────────────────────────────


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(ratio * (len(ordered) - 1))))
    return float(ordered[index])


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_design: dict[str, int] = {}
    for run in runs:
        by_status[run["status"]] = by_status.get(run["status"], 0) + 1
        by_design[run["by_design"]] = by_design.get(run["by_design"], 0) + 1
    elapsed = [float(run["elapsed_seconds"]) for run in runs]
    steps = [int(run["actions"]) for run in runs]
    tokens = [int(run["tokens"]) for run in runs]
    return {
        "runs": len(runs),
        "by_status": by_status,
        "by_design": by_design,
        "false_completion": sum(1 for run in runs if run["false_completion"]),
        "underclaim": sum(1 for run in runs if run["underclaim"]),
        "human_intervention": by_status.get("blocked", 0),
        "elapsed_seconds": {
            "p50": percentile(elapsed, 0.50),
            "p95": percentile(elapsed, 0.95),
            "mean": round(statistics.fmean(elapsed), 3) if elapsed else 0.0,
        },
        "steps": {
            "p50": percentile([float(v) for v in steps], 0.50),
            "p95": percentile([float(v) for v in steps], 0.95),
        },
        "tokens": {
            "p50": percentile([float(v) for v in tokens], 0.50),
            "p95": percentile([float(v) for v in tokens], 0.95),
        },
    }


def trace_of(
    workflow: dict[str, Any],
    run_index: int,
    planner_name: str,
    outcome: TaskOutcome | None,
    synthetic: dict[str, Any] | None,
    achieved: bool,
    grader_reasons: list[str],
    *,
    injected: bool,
) -> dict[str, Any]:
    wid = workflow["id"]
    tags = [tag for tag in workflow.get("tags", []) if str(tag).startswith("by_design:")]
    by_design = tags[0].split(":", 1)[1] if tags else "ok"
    if synthetic is not None:
        payload = synthetic
    else:
        assert outcome is not None
        payload = {
            "status": outcome.status.value,
            "code": outcome.code,
            "reason": outcome.reason,
            "verified": f"{outcome.verified_count}/{outcome.total_count}",
            "postconditions": [
                {"description": item.description, "verified": item.verified} for item in outcome.postconditions
            ],
            "steps": [
                {
                    "action": step.action,
                    "target": step.target,
                    "performed": step.performed,
                    "effect_verified": step.effect_verified,
                    "rejected": step.rejected,
                    "detail": step.detail,
                }
                for step in outcome.steps
            ],
            "actions": outcome.actions_performed,
            "tokens": outcome.tokens_used,
            "elapsed_seconds": round(outcome.elapsed_seconds, 3),
            "final_url": outcome.final_url,
            "claimed": outcome.claimed,
            "blocked_kind": outcome.blocked_kind,
        }
    status = payload["status"]
    return {
        "workflow": wid,
        "kind": workflow["kind"],
        "run": run_index,
        "planner": planner_name,
        "by_design": by_design,
        "injected": injected,
        **payload,
        "grader_achieved": achieved,
        "grader_reasons": grader_reasons,
        "false_completion": status == "succeeded" and not achieved,
        "underclaim": status != "succeeded" and achieved,
    }


# ── 실행 ────────────────────────────────────────────────────────────────────


def load_suite(suite_dir: Path, only: set[str]) -> list[dict[str, Any]]:
    manifest = json.loads((suite_dir / "suite.json").read_text(encoding="utf-8"))
    workflows: list[dict[str, Any]] = []
    for name in manifest["workflows"]:
        workflow = json.loads((suite_dir / name).read_text(encoding="utf-8"))
        if only and workflow["id"] not in only:
            continue
        workflows.append(workflow)
    if not workflows:
        raise SystemExit("선택된 워크플로가 없다 (--only)")
    return workflows


def closed_port() -> int:
    """아무도 듣지 않는 포트를 찾는다(접속 불가 워크플로의 목적지)."""
    for _ in range(16):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        with socket.socket() as checker:
            checker.settimeout(0.2)
            if checker.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("닫힌 포트를 찾지 못했다")


def _goal_of(workflow: dict[str, Any]) -> TaskGoal:
    return TaskGoal(
        goal=str(workflow["goal"]),
        postconditions=tuple(
            Postcondition(
                str(p["kind"]),
                str(p.get("value") or ""),
                description=str(p.get("description") or ""),
                key=str(p.get("key") or ""),
            )
            for p in workflow["postconditions"]
        ),
    )


async def run_benchmark(args: argparse.Namespace) -> int:
    from playwright.async_api import async_playwright

    suite_dir = Path(args.suite)
    only = {item.strip() for item in (args.only or "").split(",") if item.strip()}
    workflows = load_suite(suite_dir, only)
    state = ServerState()
    pages = {(workflow["id"], route): body for workflow in workflows for route, body in workflow["pages"].items()}
    server = make_server(pages, state)
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    dead_port = closed_port()

    def url_for(workflow: dict[str, Any], route: str) -> str:
        if any(tag == "by_design:unreachable" for tag in workflow.get("tags", [])):
            return f"http://127.0.0.1:{dead_port}{route}"
        return f"{base}/{workflow['id']}{route}"

    token_budget = args.budget_tokens if args.budget_tokens is not None else host_token_budget()
    budget = TaskBudget(
        action_budget=args.budget_actions, deadline_seconds=args.budget_deadline, token_budget=token_budget
    )
    runs: list[dict[str, Any]] = []
    scripted: dict[str, Any] = {"planner": "scripted", "deterministic": True, "seed": args.seed}
    started = time.monotonic()

    async with async_playwright() as controller:
        browser = await controller.chromium.launch(headless=not args.headed)
        try:
            for workflow in workflows:
                wid = workflow["id"]
                for run_index in range(1, args.runs + 1):
                    state.reset(wid)
                    reset_browser_approval()
                    injected = bool(args.inject_false_success) and wid == args.inject_false_success and run_index == 1
                    if injected:
                        # 주입: 브라우저를 돌리지 않고 성공을 **지어낸다** — 그레이더가 잡아야 한다.
                        achieved, reasons = grade(workflow, state, base)
                        runs.append(
                            trace_of(
                                workflow,
                                run_index,
                                "scripted",
                                None,
                                {
                                    "status": "succeeded",
                                    "code": GOAL_VERIFIED,
                                    "reason": "주입된 거짓 성공 — 실제로는 실행하지 않았다",
                                    "verified": "0/0",
                                    "postconditions": [],
                                    "steps": [],
                                    "actions": 0,
                                    "tokens": 0,
                                    "elapsed_seconds": 0.0,
                                    "final_url": "",
                                    "claimed": "주입(--inject-false-success)",
                                    "blocked_kind": "",
                                },
                                achieved,
                                reasons,
                                injected=True,
                            )
                        )
                        continue
                    planner = ScriptedWorkflowPlanner(
                        list(workflow["script"]), lambda route, w=workflow: url_for(w, route)
                    )
                    context = await browser.new_context()
                    page = await context.new_page()
                    began = time.monotonic()
                    outcome: TaskOutcome | None = None
                    synthetic: dict[str, Any] | None = None
                    try:
                        try:
                            await page.goto(url_for(workflow, str(workflow["entry"])), wait_until="load", timeout=15000)
                        except Exception as exc:  # noqa: BLE001 - 접속 불가는 기록되는 실패다
                            synthetic = {
                                "status": "failed",
                                "code": NAVIGATION_FAILED,
                                "reason": f"진입 주소에 닿을 수 없다: {str(exc).splitlines()[0][:160]}",
                                "verified": "0/0",
                                "postconditions": [],
                                "steps": [],
                                "actions": 0,
                                "tokens": 0,
                                "elapsed_seconds": round(time.monotonic() - began, 3),
                                "final_url": page.url,
                                "claimed": "",
                                "blocked_kind": "",
                            }
                        if synthetic is None:
                            owner = BrowserOwner(
                                subject="benchmark", scope="browser-benchmark", task_id=f"{wid}#{run_index}"
                            )
                            observer = BrowserObserver(
                                owner,
                                policy=ObservationPolicy(
                                    allow_local=True, download_dir=Path(args.downloads) / f"{wid}-{run_index}"
                                ),
                            )
                            observer.register_page(page, "main")
                            page_like: Any = page  # _SurfSession 의 페이지 프로토콜은 사적 타입이다
                            session = _SurfSession(owner=observer.owner, reused=True, page=page_like, observer=observer)
                            host_loop = _ObserverLoopHost(BrowserSurfingAgent(model_manager=None), session)
                            outcome = await BrowserTaskLoop(planner, budget=budget).run(_goal_of(workflow), host_loop)
                    finally:
                        await context.close()
                    achieved, reasons = grade(workflow, state, base)
                    trace = trace_of(
                        workflow, run_index, "scripted", outcome, synthetic, achieved, reasons, injected=False
                    )
                    if planner.stalled:
                        trace["script_stalled_on"] = planner.stalled
                    runs.append(trace)
                    print(
                        f"  {wid}#{run_index} {trace['status']}({trace['code']}) grader={'달성' if achieved else '미달'}"
                        + (" ← FALSE COMPLETION" if trace["false_completion"] else ""),
                        flush=True,
                    )
        finally:
            await browser.close()
    server.shutdown()
    server.server_close()

    scripted["summary"] = summarize(runs)
    scripted["runs"] = runs
    model_section: dict[str, Any]
    if args.planner in ("model", "both"):
        model_section = await model_planner_section(args, workflows)
    else:
        model_section = {"status": "NOT_RUN", "reason": f"--planner={args.planner} (scripted 기준선만 실행)"}

    summary = scripted["summary"]
    results: dict[str, Any] = {
        "schema": RESULTS_SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "suite": {"path": str(suite_dir), "workflows": len(workflows), "runs_per_workflow": args.runs},
        "config": {
            "planner": args.planner,
            "seed": args.seed,
            "budget": {
                "actions": args.budget_actions,
                "deadline_seconds": args.budget_deadline,
                "tokens": token_budget,
            },
            "browser": f"chromium {'headed' if args.headed else 'headless'}",
            "wall_seconds": round(time.monotonic() - started, 1),
            "injected_false_success": args.inject_false_success or None,
        },
        "denominator": {"scheduled": len(workflows) * args.runs, "executed": len(runs), "excluded": []},
        "summary": summary,
        "planners": {"scripted": scripted, "model": model_section},
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n== {len(runs)} 실행 ({results['config']['wall_seconds']}s) ==")
    for key, count in sorted(summary["by_status"].items()):
        print(f"  {key:12s} {count}")
    print(
        f"  false completion {summary['false_completion']} · underclaim {summary['underclaim']} · 사람개입 {summary['human_intervention']}"
    )
    print(
        f"  elapsed p50={summary['elapsed_seconds']['p50']:.2f}s p95={summary['elapsed_seconds']['p95']:.2f}s · steps p50={summary['steps']['p50']} p95={summary['steps']['p95']}"
    )
    print(f"  결과: {output}")
    if summary["false_completion"] and args.fail_on_false_completion:
        print("게이트: false completion 이 잡혔다 — 실패로 종료한다", file=sys.stderr)
        return 1
    return 0


async def model_planner_section(
    args: argparse.Namespace, workflows: list[dict[str, Any]]
) -> dict[str, Any]:  # pragma: no cover - 모델 환경에서만
    """실제 모델 planner 칸. 모델이 구성되지 않은 환경은 NOT_RUN 로 남긴다(조용히 비우지 않는다)."""
    try:
        from antigravity_k.agents.browser_task_loop import ModelPlanner
        from antigravity_k.engine.model_manager import ModelManager
        from antigravity_k.engine.model_registry import ModelRegistry

        manager = ModelManager(ModelRegistry())
        planner = ModelPlanner(manager)
        target = planner._target()  # noqa: SLF001 - 구성 확인용
        return {"status": "AVAILABLE_NOT_EXECUTED_HERE", "model": target, "workflows": [w["id"] for w in workflows]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "NOT_RUN", "reason": f"모델 planner 구성 실패: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ssak-Ai 브라우저 업무 benchmark (task 22)")
    parser.add_argument("--suite", default="tests/fixtures/browser_workflows")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", default="data/benchmarks/ssak-browser.json")
    parser.add_argument("--only", default="", help="워크플로 id 쉼표 목록(스모크·시험용)")
    parser.add_argument("--planner", choices=("scripted", "model", "both"), default="scripted")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--budget-actions", type=int, default=30)
    parser.add_argument("--budget-deadline", type=float, default=600.0)
    parser.add_argument("--budget-tokens", type=int, default=None)
    parser.add_argument("--downloads", default="/tmp/ssak-browser-benchmark-downloads")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--inject-false-success", default="", help="이 워크플로의 첫 실행에 거짓 성공을 주입한다(그레이더 검증용)"
    )
    parser.add_argument(
        "--fail-on-false-completion", action="store_true", help="false completion 이 하나라도 잡히면 종료코드 1"
    )
    args = parser.parse_args()
    try:
        return asyncio.run(run_benchmark(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
