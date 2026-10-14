"""`media` 등급을 **핫패스 밖**에서만 돌릴 수 있는가 — 비용 모델과 간섭을 잰다.

D-F3-2(“`media` 를 제공한다면 단위”)에 답하려면 숫자 셋이 필요하다:

  A. **누적량 → 호출 1회 비용 곡선**: 커밋 k개를 sync 없이 쌓은 뒤 sync 1회. 이것이 주기·체크포인트가
     지불하는 값이다(= `c(k) = a + b·k`). 단발 값(1줄 = 4,163 µs)만 보면 “커밋당 242 %” 라는 결론이 나오지만,
     배치 flush 8 MB 는 7,029 µs 였다 — 고정세(a)와 줄당 비용(b)을 나눠야 배치의 값이 보인다.
  B. **유휴 호출**: 아무것도 안 쓴 창에서 타이머가 sync 를 부르면 얼마인가. 또 **다른 파일이 페이지 캐시를
     더럽힌 상태**에서 이 파일의 호출은 얼마인가(macOS `F_FULLFSYNC` 는 “드라이브의 버퍼를 비우라”는
     요청이라 **남의 dirty 까지 지불**할 수 있다 — 그러면 “전역 주기” 대안의 값이 달라진다).
  C. **간섭**: 커밋당 예산 1,653 µs(4차 soak 실측 605 ops/s)를 지키는 페이스로 도는 쓰기 위에
     배경 media sync 를 걸었을 때 **핫패스가 예산을 지키는가**. 같은 파일(자기 대화) / 다른 파일(남의 대화)을
     나눠 잰다 — “핫패스 밖”은 가정이 아니라 재야 할 주장이다.

한계(먼저 적는다): **크래시 유실은 실측할 수 없다**(전원 손실 필요). 이 프로브는 “무엇이 얼마인가”와
“누가 멈추는가”만 잰다. 그리고 지금 **4차 soak 이 같은 디스크에 쓰고 있다** — 절대값은 그 조건의 값이고,
읽어야 할 것은 **비율·계단·예산 유지 여부**다.

사용: `.venv/bin/python nx10/fsync4/probe_media_offload_cost.py [--json <out>]`
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

SOAK_OPS_PER_SECOND = 605.0  # 4차 soak 실측(감시 표본) — 배치 산술의 기준
PER_OP_BUDGET_US = 1_000_000 / SOAK_OPS_PER_SECOND  # 1,652.9 µs
LINE_BYTES = 271  # 저널 1줄 실측
HAS_FULLFSYNC = hasattr(fcntl, "F_FULLFSYNC")


def _media_sync(fd: int) -> None:
    """`media` 등급의 실제 syscall (없으면 `os.fsync` 로 강등 — 능력은 리포트가 밝힌다)."""
    if HAS_FULLFSYNC:
        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)


def _us(start: float) -> float:
    return (time.perf_counter() - start) * 1_000_000


def _overlap_us(first: tuple[float, float], second: tuple[float, float]) -> float:
    """두 시간 구간의 겹침(µs). 0 이하면 안 겹친다.

    인과 귀속의 전부다: 앞이 밀린 구간과 배경 media 호출이 **동시에** 있었는가. 순서·평균이 아니라
    구간으로 물어야 한다 — 밀림은 평균을 거의 안 올리면서 꼬리만 키우기 때문이다.
    """
    return min(first[1], second[1]) - max(first[0], second[0])


# ── A. 누적량 → 호출 1회 비용 곡선 ────────────────────────────────────────────────────────────────
def _one_call(tmp: Path, count: int, level: str, tag: str) -> float:
    """커밋 `count`개를 sync 없이 쌓고 sync 1회 — 그 한 번의 µs."""
    payload = b"z" * (LINE_BYTES - 1) + b"\n"
    path = tmp / f"acc-{level}-{count}-{tag}.jsonl"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        for _ in range(count):
            os.write(fd, payload)
        start = time.perf_counter()
        if level == "media":
            _media_sync(fd)
        else:
            os.fsync(fd)
        return _us(start)
    finally:
        os.close(fd)


def _accumulation_curve(tmp: Path, counts: tuple[int, ...], reps: int) -> list[dict[str, Any]]:
    """**교차 반복**(rep → count 순)으로 곡선을 그린다.

    첫 시도의 순차 실행은 곡선이 **단조가 아니게** 나왔다(k=8 이 k=512 보다 8배 비쌌다) — 드라이브 큐에
    남은 일감이 다음 호출의 값이 되므로, 순서 효과를 평균하기 위해 k 를 돌려 가며 반복한다.
    **최소값을 그 k 의 고유 비용**으로 읽는다(최소값이 오염이 가장 적은 추정이다).
    """
    samples: dict[tuple[int, str], list[float]] = {}
    for rep in range(reps):
        for count in counts:
            for level in ("media", "cache"):
                samples.setdefault((count, level), []).append(_one_call(tmp, count, level, f"r{rep}"))

    points: list[dict[str, Any]] = []
    for count in counts:
        entry: dict[str, Any] = {"commits": count, "bytes": count * LINE_BYTES, "reps": reps}
        for level in ("media", "cache"):
            values = sorted(samples[(count, level)])
            entry[f"{level}_min_us"] = round(values[0], 1)
            entry[f"{level}_median_us"] = round(statistics.median(values), 1)
            entry[f"{level}_max_us"] = round(values[-1], 1)
            entry[f"{level}_us_per_commit_min"] = round(values[0] / count, 3)
        entry["media_over_cache_min"] = round(entry["media_min_us"] / entry["cache_min_us"], 2)
        entry["media_min_share_of_budget_percent"] = round(100 * entry["media_us_per_commit_min"] / PER_OP_BUDGET_US, 3)
        points.append(entry)
    return points


PLAUSIBLE_MEDIA_GB_PER_S = 3.0  # 이 기기에서 믿을 수 있는 쓰기 대역폭 상한(내부 NVMe). 넘으면 그건 잡음이다.


def _linear_fit(points: list[dict[str, Any]], key: str) -> dict[str, float | None]:
    """`a + b·k` 최소제곱 + **함의 대역폭** — 계열이 선형으로 식별되는지 보려고만 쓴다(모델로는 안 쓴다)."""
    xs = [float(p["commits"]) for p in points]
    ys = [float(p[key]) for p in points]
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = 0.0 if denom == 0 else sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    per_byte_us = slope / LINE_BYTES  # µs/byte
    # GB/s = 1e-9 / (초/byte) ─ 초/byte = per_byte_us × 1e-6
    bandwidth = None if per_byte_us <= 0 else round(1 / (per_byte_us * 1e3), 2)
    return {
        "fixed_us": round(mean_y - slope * mean_x, 1),
        "per_commit_us": round(slope, 5),
        "implied_bandwidth_gb_per_s": bandwidth,
    }


def _call_model(points: list[dict[str, Any]]) -> dict[str, Any]:
    """호출 비용 모델 — `c(k) ≈ c_floor`(**부피 무관 배리어**), 커밋당 상각 = `c_floor/k`.

    실측: `k=8`(2.2 KB)부터 `k=32,768`(8.9 MB)까지 호출이 **같은 띠 안**에 있다. 부피 항을 쓰려면
    그 띠의 폭이 **믿을 수 있는 쓰기 대역폭**으로 설명돼야 한다(> `PLAUSIBLE_MEDIA_GB_PER_S` 면 잡음이다).
    큰 두 점의 차이로 추정해 보고, 그 함의 대역폭이 물리가 안 되는 값이면 **관측 불가**로 적고 바닥값만 쓴다.
    """
    big = [p for p in points if p["commits"] >= 8]
    floor_samples = sorted(p["media_min_us"] for p in big)
    floor = statistics.median(floor_samples)
    ordered = sorted(points, key=lambda p: p["commits"])
    low, high = ordered[-2], ordered[-1]
    delta_us = high["media_min_us"] - low["media_min_us"]
    delta_bytes = high["bytes"] - low["bytes"]
    implied = None if delta_us <= 0 else round(delta_bytes / (delta_us * 1e-6) / 1e9, 2)
    observable = bool(delta_us > 0.25 * floor and implied is not None and implied <= PLAUSIBLE_MEDIA_GB_PER_S)
    delta_kb = max(1.0, delta_bytes / 1024)
    return {
        "floor_us": round(floor, 1),
        "floor_spread_us": [round(floor_samples[0], 1), round(floor_samples[-1], 1)],
        "floor_basis": f"k>={big[0]['commits']} 의 최소값 중앙값",
        "floor_share_of_largest_call": round(floor / max(high["media_min_us"], 1e-9), 3),
        "volume_slope_upper_bound_us_per_kb": round(max(0.0, delta_us) / delta_kb, 4),
        "bandwidth_gb_per_s": implied if observable else None,
        "implied_bandwidth_if_volume_were_the_cause_gb_per_s": implied,
        "volume_term_observable": observable,
        "plausible_write_bandwidth_gb_per_s": PLAUSIBLE_MEDIA_GB_PER_S,
        "model": "c(k) ≈ c_floor (부피 무관 배리어) — 커밋당 상각 = c_floor / k",
        "linear_fit": _linear_fit(points, "media_min_us"),
        "linear_fit_verdict": (
            "**식별되지 않는다**: 이 판정(`volume_term_observable`)은 실행마다 뒤집혔다(A 미관측 / B 관측) "
            "— 큰 두 점의 차이가 잡음 띠와 같은 크기이기 때문이다. 그래서 모델로 쓰지 않고, 바닥값 + "
            "**상한**(`volume_slope_upper_bound_us_per_kb`) 으로 적는다."
        ),
    }


# ── B. 유휴 호출 · 남의 dirty ─────────────────────────────────────────────────────────────────────
def _idle_calls(tmp: Path, rounds: int = 20) -> dict[str, Any]:
    """창이 빈 상태(sync 직후 아무것도 안 씀)에서의 호출 비용 — 타이머가 조용한 구간에 지불하는 값."""
    path = tmp / "idle.jsonl"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, b"x" * (LINE_BYTES - 1) + b"\n")
        os.fsync(fd)
        clean: list[float] = []
        for _ in range(rounds):
            start = time.perf_counter()
            _media_sync(fd)
            clean.append(_us(start))
        # 이 파일은 그대로 두고 **남의 파일**로 페이지 캐시를 더럽힌다(64 MB, sync 없음).
        other = tmp / "other-dirty.bin"
        chunk = b"o" * (1024 * 1024)
        with open(other, "wb", buffering=0) as handle:
            for _ in range(64):
                handle.write(chunk)
        neighbor_dirty: list[float] = []
        for _ in range(rounds):
            start = time.perf_counter()
            _media_sync(fd)
            neighbor_dirty.append(_us(start))
    finally:
        os.close(fd)
        # **첫 시도의 교훈**: 이 64 MB 를 sync 없이 두었더니 이후 간섭 실측 도중에 OS 의 주기 writeback 이
        # 터져 기준선이 13 % 밀렸다(그래서 "밀린 구간"이 어디서 왔는지 알 수 없게 됐다). 남기지 않는다.
        cleanup_start = time.perf_counter()
        with open(other, "r+b", buffering=0) as handle:
            os.fsync(handle.fileno())
        other.unlink(missing_ok=True)
        cleanup_us = _us(cleanup_start)
    return {
        "note": "이 파일은 두 경우 모두 깨끗하다 — 차이는 **다른 파일의 dirty 64 MB** 뿐이다.",
        "clean_median_us": round(statistics.median(clean), 1),
        "clean_p95_us": round(sorted(clean)[int(rounds * 0.95)], 1),
        "neighbor_dirty_median_us": round(statistics.median(neighbor_dirty), 1),
        "neighbor_dirty_p95_us": round(sorted(neighbor_dirty)[int(rounds * 0.95)], 1),
        "neighbor_dirty_over_clean": round(statistics.median(neighbor_dirty) / max(statistics.median(clean), 1e-9), 2),
        "neighbor_cleanup_us": round(cleanup_us, 1),
        "neighbor_cleanup_note": "남의 dirty 를 남기지 않는다 — 첫 시도에서는 이 64 MB 가 뒤의 간섭 실측을 밀었다.",
    }


# ── C. 간섭 — 예산을 지키는가 ────────────────────────────────────────────────────────────────────
def _paced_write(
    path: Path,
    commits: int,
    *,
    pace_us: float,
    sync_every: int,
    background_media: threading.Event | None = None,
    background_interval_s: float = 0.0,
) -> dict[str, Any]:
    """커밋당 예산(`pace_us`)에 맞춰 쓰는 핫패스. 배경 스레드는 **media sync 만** 한다.

    재는 것: ① 배경이 켜져도 처리량(ops/s)이 유지되는가 ② 개별 커밋이 예산을 얼마나 넘겼는가(max/p99)
    ③ 배경이 몇 번·얼마를 지불했는가.
    """
    payload = b"y" * (LINE_BYTES - 1) + b"\n"
    origin = time.perf_counter()  # 두 스레드의 시간축을 맞춘다(인과 귀속용)
    stops = threading.Event()
    background: dict[str, Any] = {
        "calls": 0,
        "total_us": 0.0,
        "max_us": 0.0,
        "lost_to_error": 0,
        "errors": [],  # 워커 안에서 sync 가 던진 예외 — **조용한 죽음을 금지**한다(첫 시도가 그랬다)
        "intervals_us": [],  # [(start,end)] — 앞이 밀린 구간과 **겹치는가**를 본다
    }
    in_flight: dict[str, float] = {"started_at": 0.0, "unfinished_us": 0.0}
    thread: threading.Thread | None = None

    if background_media is not None:

        def worker() -> None:
            # 첫 시도는 `O_CREAT` 없이 열어 **스레드가 조용히 죽었다** — 그 결함을 시험으로 고정했다(㊽).
            try:
                bg_fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            except OSError:
                background["lost_to_error"] += 1
                return
            try:
                while not stops.is_set():
                    started = time.perf_counter()
                    in_flight["started_at"] = started
                    try:
                        _media_sync(bg_fd)
                    except Exception as exc:  # noqa: BLE001 — 어떤 예외든 기록한다(조용한 죽음 금지)
                        in_flight["started_at"] = 0.0
                        background["errors"].append(f"{type(exc).__name__}: {exc}"[:120])
                        if len(background["errors"]) >= 3:
                            return
                        stops.wait(background_interval_s)
                        continue
                    finished = time.perf_counter()
                    elapsed = _us(started)
                    in_flight["started_at"] = 0.0
                    background["calls"] += 1
                    background["total_us"] += elapsed
                    background["max_us"] = max(background["max_us"], elapsed)
                    if elapsed > 100_000:  # 100 ms 넘은 호출만 기억한다(밀린 구간과 짝지을 후보)
                        background["intervals_us"].append(
                            [round(_us(origin) - _us(started), 1), round(_us(origin) - _us(finished), 1)]
                        )
                    stops.wait(background_interval_s)
            finally:
                os.close(bg_fd)

        thread = threading.Thread(target=worker, name="bg-media", daemon=True)
        thread.start()

    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_APPEND, 0o600)
    gaps: list[float] = []
    slow_gaps: list[list[float]] = []  # [(start,end)] 100 ms 넘은 밀림만
    try:
        run_start = time.perf_counter()
        next_at = run_start
        previous = run_start
        previous_rel = 0.0
        for index in range(commits):
            os.write(fd, payload)
            if index % sync_every == sync_every - 1:
                os.fsync(fd)  # `cache` 등급은 그대로 — 배경이 바꾸는 것은 media 뿐이다
            next_at += pace_us / 1_000_000
            now = time.perf_counter()
            if next_at > now:
                time.sleep(next_at - now)
            elif now > next_at:
                next_at = now  # 밀렸으면 페이스를 리셋하지 않고 따라잡는다(밀림을 gap 으로 센다)
            stamp = time.perf_counter()
            gap_us = (stamp - previous) * 1_000_000
            gaps.append(gap_us)
            if gap_us > 100_000:
                slow_gaps.append([previous_rel, round(_us(origin), 1)])
            previous = stamp
            previous_rel = round(_us(origin), 1)
        elapsed = time.perf_counter() - run_start
    finally:
        os.close(fd)
        stops.set()
        if thread is not None:
            thread.join(timeout=5)

    ordered = sorted(gaps)
    overshoot = [g - pace_us for g in gaps if g > pace_us]
    if in_flight["started_at"]:
        in_flight["unfinished_us"] = round(_us(in_flight["started_at"]), 1)
    return {
        "commits": commits,
        "pace_us": round(pace_us, 1),
        "elapsed_s": round(elapsed, 3),
        "ops_per_second": round(commits / elapsed, 1),
        "throughput_vs_pace_percent": round(100 * (commits / elapsed) * pace_us / 1_000_000, 2),
        "gap_median_us": round(statistics.median(gaps), 1),
        "gap_p99_us": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))], 1),
        "gap_max_us": round(ordered[-1], 1),
        "overshoot_count": len(overshoot),
        "overshoot_over_budget_count": sum(1 for g in gaps if g > 2 * pace_us),
        "overshoot_max_us": round(max(overshoot), 1) if overshoot else 0.0,
        "slow_gaps_us": slow_gaps,
        "background": {
            "calls": background["calls"],
            "total_us": round(background["total_us"], 1),
            "max_us": round(background["max_us"], 1),
            "unfinished_us": in_flight["unfinished_us"],
            "thread_error": background["lost_to_error"],
            "errors": background["errors"],
            "slow_intervals_us": background["intervals_us"],
        },
    }


def _interference(tmp: Path, commits_per_block: int, rounds: int, *, os_sync: bool = True) -> dict[str, Any]:
    """**교차 설계(arm × round)**로 “핫패스 밖”을 재다.

    첫 시도는 순차 실행이었고, 그 사이 디스크 조건이 변해(남은 64 MB writeback + 도는 soak) 어느 팔이
    원인인지 말할 수 없게 됐다(기준선끼리 13 % 차이). 그래서 매 라운드마다 `기준선 → 같은 파일 → 다른 파일`
    을 돌려 **그 라운드의 기준선과 짝지어** 비교한다 — 드리프트가 상쇄되고, 배경 sync 의 몫만 남는다.
    """
    # 200 ms 는 “세밀한 주기”, 1000 ms 는 “드물게” — 간섭이 **호출 수에 비례**하는지(줄일 수 있는지) 본다.
    arms: list[tuple[str, Any, float]] = [
        ("baseline", None, 0.0),
        ("media_self_200ms", "self", 0.2),
        ("media_self_1000ms", "self", 1.0),
        ("media_other_200ms", "other", 0.2),
    ]
    if os_sync and hasattr(os, "sync"):
        os.sync()  # 디스크 큐를 비우고 시작한다 — 이전 단계의 dirty 가 첫 라운드를 밀지 않도록
    per_arm: dict[str, list[dict[str, Any]]] = {name: [] for name, _, _ in arms}
    for round_index in range(rounds):
        for name, mode, interval in arms:
            target = tmp / ("self.jsonl" if mode == "self" else "other.jsonl")
            entry = {
                "case": name,
                "round": round_index,
                "interval_s": interval,
                "mode": mode or "none",
                **_paced_write(
                    target,
                    commits_per_block,
                    pace_us=PER_OP_BUDGET_US,
                    sync_every=8,
                    background_media=threading.Event() if mode else None,
                    background_interval_s=interval,
                ),
            }
            per_arm[name].append(entry)

    summary: list[dict[str, Any]] = []
    for name, _, interval in arms:
        entries = per_arm[name]
        paired = []
        for entry in entries:
            base = per_arm["baseline"][entry["round"]]
            paired.append(100 * (entry["ops_per_second"] / base["ops_per_second"] - 1))
        # 인과 귀속: 밀린 구간이 배경 호출 구간과 **겹치는가**(시각으로).
        overlaps: list[float] = []
        for entry in entries:
            for gap in entry["slow_gaps_us"]:
                for call in entry["background"]["slow_intervals_us"]:
                    overlap = _overlap_us((gap[0], gap[1]), (call[0], call[1]))
                    if overlap > 0:
                        overlaps.append(overlap)
        summary.append(
            {
                "case": name,
                "interval_s": interval,
                "rounds": len(entries),
                "median_ops_per_second": round(statistics.median(e["ops_per_second"] for e in entries), 1),
                "paired_delta_percent_median": round(statistics.median(paired), 2),
                "paired_delta_percent_worst": round(min(paired), 2),
                "gap_p99_us_max": round(max(e["gap_p99_us"] for e in entries), 1),
                "gap_max_us": round(max(e["gap_max_us"] for e in entries), 1),
                "stalls_over_100ms": sum(1 for e in entries if e["gap_max_us"] > 100_000),
                "over_2x_budget_total": sum(e["overshoot_over_budget_count"] for e in entries),
                "background_calls_total": sum(e["background"]["calls"] for e in entries),
                "background_max_us": round(max(e["background"]["max_us"] for e in entries), 1),
                "background_unfinished_us": round(max(e["background"]["unfinished_us"] for e in entries), 1),
                "background_thread_errors": sum(e["background"]["thread_error"] for e in entries),
                "background_sync_errors": sum(len(e["background"].get("errors") or []) for e in entries),
                "slow_gaps_total": sum(len(e["slow_gaps_us"]) for e in entries),
                "slow_gaps_overlapping_a_media_call": len(overlaps),
                "max_overlap_us": round(max(overlaps), 1) if overlaps else 0.0,
            }
        )
    return {
        "note": "매 라운드 `기준선 → 같은 파일 200 ms → 다른 파일 200 ms`. 델타는 **그 라운드의 기준선과 짝지은** 값이다.",
        "commits_per_block": commits_per_block,
        "rounds": rounds,
        "summary": summary,
        "blocks": [entry for name, _, _ in arms for entry in per_arm[name]],
    }


# ── D. 산술 — 정책을 커밋당 상각으로 ─────────────────────────────────────────────────────────────
def _schedule_arithmetic(
    model: dict[str, Any],
    windows_s: tuple[float, ...],
    sensitivity_bandwidths: tuple[float, ...] = (0.5, 2.0, 10.0),
) -> list[dict[str, Any]]:
    """주기 T초마다 media sync 1회: `c(k)/k` 가 커밋당 상각이고(k = T초에 쌓이는 커밋), 창은 그 k 다.

    본선: `c(k) = c_floor`(관측된 바닥값). 부피 항은 관측되지 않았으므로 **민감도**로만 겉어 본다:
    “만약 대역폭이 S 라면 상각이 얼마인가”를 `amortized_us_per_commit_at_bandwidth` 에 적는다.
    (0.5 GB/s 는 이 기기에서 관측된 가장 느린 8.9 MB 호출이 함의하는 값이다 — 사실상 하한.)
    **체크포인트(검지 회전)와 셧다운**은 같은 산술의 두 극단이다: 창이 각각 “회전 간격”과 “프로세스 수명”이다.
    """
    floor_us = model["floor_us"]
    bandwidth = model.get("bandwidth_gb_per_s")
    rows: list[dict[str, Any]] = []
    for window_s in windows_s:
        commits = SOAK_OPS_PER_SECOND * window_s
        volume_us = 0.0 if not bandwidth else commits * LINE_BYTES / (bandwidth * 1e9) * 1e6
        call_us = floor_us + volume_us
        amortized = call_us / commits
        sensitivity = {
            str(band): round(
                (floor_us + commits * LINE_BYTES / (band * 1e9) * 1e6) / commits,
                4,
            )
            for band in sensitivity_bandwidths
        }
        rows.append(
            {
                "window_s": window_s,
                "window_commits_at_605ops": int(commits),
                "window_bytes": int(commits * LINE_BYTES),
                "media_call_us": round(call_us, 1),
                "amortized_us_per_commit": round(amortized, 4),
                "amortized_us_per_commit_at_bandwidth": sensitivity,
                "share_of_budget_percent": round(100 * amortized / PER_OP_BUDGET_US, 4),
                "calls_per_8h": int(8 * 3600 / window_s),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="")
    parser.add_argument("--commits", type=int, default=600, help="간섭 실측의 블록당 커밋 수(≈1초)")
    parser.add_argument("--rounds-ab", type=int, default=6, help="교차 설계의 라운드 수(팔 3개 × 라운드)")
    parser.add_argument("--reps", type=int, default=3, help="누적 곡선의 교차 반복 수")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="nx10-media-offload-") as tmpdir:
        tmp = Path(tmpdir)
        curve = _accumulation_curve(tmp, (1, 8, 32, 128, 512, 2_048, 8_192, 32_768), args.reps)
        model = _call_model(curve)
        idle = _idle_calls(tmp)
        interference = _interference(tmp, args.commits, args.rounds_ab)
        arithmetic = _schedule_arithmetic(model, (1.0, 10.0, 60.0, 600.0, 3_600.0))

    payload: dict[str, Any] = {
        "capabilities": {
            "platform": sys.platform,
            "F_FULLFSYNC": HAS_FULLFSYNC,
            "os.fdatasync": hasattr(os, "fdatasync"),
        },
        "reference": {
            "soak_ops_per_second": SOAK_OPS_PER_SECOND,
            "per_op_budget_us": round(PER_OP_BUDGET_US, 1),
            "line_bytes": LINE_BYTES,
            "note": "측정 시각에 4차 soak 이 같은 디스크에 쓰고 있었다 — 절대값이 아니라 비율·계단을 읽는다.",
        },
        "accumulation_curve": {
            "note": "커밋 k개를 sync 없이 쌓고 sync 1회(교차 반복 → 최소값). 주기·체크포인트가 지불하는 값이다.",
            "points": curve,
        },
        "call_model": model,
        "idle_and_neighbor": idle,
        "interference": interference,
        "schedule_arithmetic": {
            "note": "call_model 로 주기 T초 정책의 커밋당 상각을 계산. 창 = T초의 이력(커밋 수·바이트).",
            "rows": arithmetic,
        },
        "limits": [
            "크래시 유실은 실측할 수 없다(전원 손실 필요) — 창은 규칙으로 정의하고 시험으로 간접 검증한다.",
            "4차 soak 이 같은 디스크에 쓰는 중 — 절대 지연은 그 조건의 값이다.",
            "F_FULLFSYNC 의 ‘미디어 보장’ 자체는 플랫폼 문서 근거이고, 실측된 것은 비용 차이다.",
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
