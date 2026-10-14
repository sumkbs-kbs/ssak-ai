"""`media` 오프로드 비용 모델과 그 **계측기**의 계약을 고정한다(D-F3-2 근거 · 배치 `FLUSH3` 설계).

계약(이 시험이 지키는 문장 — 전문은 `nx10/fsync4/MEDIA_OFFLOAD_COST_MODEL.md`):
  1. 이 기기에서 `F_FULLFSYNC` 는 **부피와 무관한 배리어 고정세**다 — 커밋당 상각은 `c_floor/k` 이고,
     `k` 가 커지면 단조 감소한다. 선형 적합(`a + b·k`)은 **데이터가 거부한다**(기울기가 음수가 나온다).
  2. 그래서 스케줄 산술은 **측정된 바닥값**으로 한다 — 관측되지 않은 부피 항을 지어내지 않는다.
  3. 창(주기 T)이 커지면 커밋당 상각도, 8시간 호출 수(동률이면)도 단조롭게 준다.
  4. **계측기 자체의 계약**: 배경 스레드가 파일을 못 열면 조용히 “0 호출”로 끝나지 않는다(그 결함을
     실제로 밟았다 — `O_CREAT` 없이 열어 스레드가 죽었고 리포트는 성공처럼 보였다).
  5. **교차 설계**: 팔(arm)은 라운드마다 돌리고, 델타는 **그 라운드의 기준선**과 짝지어 계산한다
     (순차 실행은 드리프트와 원인을 섞는다 — 첫 시도에서 기준선끼리 13 % 차이가 났다).
  6. **인과 귀속**: 밀린 구간은 평균이 아니라 **구간**으로 배경 호출과 겹치는지 본다.
  7. 위생: 남의 dirty 페이지를 남기지 않는다(첫 시도는 남긴 64 MB writeback 이 뒤 실측을 밀었다).

실행: .venv/bin/python -m pytest docs/qa/2026-09-16-followup/nx10/fsync4/test_media_offload_contract.py -q
"""

from __future__ import annotations

import importlib.util
import json
import os
import statistics
import tempfile
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent


def _load_probe() -> ModuleType:
    """프로브를 모듈로 불러온다 — 판정 함수를 **다시 쓰지 않고** 같은 바이트를 검사한다."""
    path = HERE / "probe_media_offload_cost.py"
    assert path.is_file(), f"프로브를 찾지 못했다: {path}"
    spec = importlib.util.spec_from_file_location("probe_media_offload_cost", path)
    assert spec and spec.loader, "프로브 로더를 만들지 못했다"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROBE = _load_probe()
# **두 번의 실측을 모두 보관한다** — 기울기 부호가 실행마다 뒤집힌다는 사실 자체가 근거다(1회 표본은
# 꼬리가 두꺼운 이 계열에서 주장을 못 받친다).
FIXTURES = (HERE / "probe-media-offload-run-a.json", HERE / "probe-media-offload-run-b.json")


def _fixture(name: int = 0) -> dict:
    path = FIXTURES[name]
    assert path.is_file(), f"실측 픽스처가 없다(조용히 건너뛰지 않는다): {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ── ① 호출 모델 — 배리어 고정세 ─────────────────────────────────────────────────────────────────
def _point(commits: int, media_min_us: float) -> dict:
    return {"commits": commits, "bytes": commits * 271, "media_min_us": media_min_us, "cache_min_us": 50.0}


def test_call_model_treats_the_call_as_a_flat_barrier():
    """k=8(2 KB)부터 k=32,768(8.9 MB)까지 같은 띠 — 바닥값은 **중앙값**, 부피 항은 관측 불가로 표시된다.

    띠의 폭(500 µs / 8.3 MB)은 16 GB/s 를 함의하므로 **물리가 아니다** — 그래서 지어내지 않는다.
    """
    points = [_point(1, 4700.0), _point(8, 3100.0), _point(512, 3260.0), _point(2048, 3300.0), _point(32_768, 3600.0)]
    model = PROBE._call_model(points)
    assert model["floor_us"] == statistics.median([3100.0, 3260.0, 3300.0, 3600.0]), model
    assert model["volume_term_observable"] is False, "부피 항을 지어냈다 — 9 MB 까지 관측되지 않는다"
    assert model["bandwidth_gb_per_s"] is None, model
    assert model["implied_bandwidth_if_volume_were_the_cause_gb_per_s"] > 3.0, model


def test_call_model_accepts_a_volume_term_when_it_is_physically_plausible():
    """**반대 방향 대조군**: 부피가 정말 비용을 만들면(느린 기기) 모델이 그 항을 받아들여야 한다.

    8.3 MB 에 100 ms 추가 = 0.083 GB/s → 기기 대역폭 안이다. 이때만 `bandwidth_gb_per_s` 가 채워진다.
    """
    points = [_point(8, 3100.0), _point(2048, 3200.0), _point(32_768, 103_200.0)]
    model = PROBE._call_model(points)
    assert model["volume_term_observable"] is True, model
    assert model["bandwidth_gb_per_s"] is not None and model["bandwidth_gb_per_s"] < 0.2, model


def test_call_model_amortisation_falls_with_k():
    """커밋당 상각 = 바닥값/k — 단조 감소(이것이 배치가 값을 갖는 유일한 이유다)."""
    model = PROBE._call_model([_point(8, 3000.0), _point(2048, 3300.0), _point(32_768, 4400.0)])
    rows = PROBE._schedule_arithmetic(model, (1.0, 10.0, 60.0))
    amortised = [row["amortized_us_per_commit"] for row in rows]
    assert amortised == sorted(amortised, reverse=True), f"T 가 커지는데 상각이 안 준다: {amortised}"
    assert amortised[-1] < amortised[0] / 10, amortised


def test_the_floor_dominates_even_the_largest_call():
    """**핵심 부정 대조군**: 8.9 MB 한 번조차 비용의 절반 이상은 **부피와 무관한 배리어**다(두 실행 모두).

    서사가 “부피가 비용을 만든다”로 되돌아가면 이 시험이 문다 — 그러면 처방도 (정책·배치에서
    ”무엇을 더 적게 쓰는가“로) 바뀌여야 하는데, 실측은 그걸 지지하지 않는다.
    """
    for index in (0, 1):
        points = _fixture(index)["accumulation_curve"]["points"]
        model = PROBE._call_model(points)
        assert model["floor_share_of_largest_call"] >= 0.5, f"run {index}: {model}"
        bound = model["volume_slope_upper_bound_us_per_kb"]
        assert 0 < bound < 3.0, f"run {index}: 줄당 상한이 물리가 아니다({bound} µs/KB)"
        assert "식별되지 않는다" in model["linear_fit_verdict"]


def test_worst_measured_call_keeps_amortisation_far_below_budget():
    """** 견고한 결론**(두 실행 모두): 가장 큰 창(8.9 MB)조차 커밋당 상각이 1 µs 미만이다.

    서사의 무게가 여기 실려 있다: 어느 모델을 골라도 주기 T 의 처리량 비용은 무시할 수 있다 —
    D-F3-2 의 결정을 가르는 것은 비용이 아니라 **창의 크기와 간섭**이다.
    """
    for index in (0, 1):
        points = _fixture(index)["accumulation_curve"]["points"]
        largest = max(points, key=lambda p: p["commits"])
        assert largest["media_us_per_commit_min"] < 1.0, f"run {index}: {largest}"
        rows = PROBE._schedule_arithmetic(_fixture(index)["call_model"], (600.0,))
        assert rows[0]["amortized_us_per_commit"] < 0.3, rows[0]
        # 0.5 GB/s 는 이 기기에서 관측된 가장 느린 8.9 MB 호출이 함의하는 값 — 그 가정에서도 1 µs 미만이다.
        assert rows[0]["amortized_us_per_commit_at_bandwidth"]["0.5"] < 1.0, rows[0]
        assert rows[0]["share_of_budget_percent"] < 0.02, rows[0]


def test_schedule_arithmetic_uses_only_the_measured_floor():
    """부피 항이 관측되지 않으면 호출값 == 바닥값(지어낸 대역폭 0건) — 부피 항은 민감도 표로만 나온다."""
    model = {"floor_us": 4000.0, "bandwidth_gb_per_s": None}
    rows = PROBE._schedule_arithmetic(model, (1.0, 600.0))
    assert all(row["media_call_us"] == 4000.0 for row in rows), rows
    assert rows[0]["calls_per_8h"] == 28_800 and rows[1]["calls_per_8h"] == 48, rows
    slow = rows[1]["amortized_us_per_commit_at_bandwidth"]["0.5"]
    assert slow > rows[1]["amortized_us_per_commit"], "민감도가 본선보다 커야 한다"


def test_recorded_floor_is_a_barrier_in_a_plausible_band():
    """실측 바닥값은 두 실행 모두 “수 밀리초 배리어” 띠 — 0 에 가깝거나 1초를 넘으면 계기가 고장 난 것이다."""
    for index in (0, 1):
        model = _fixture(index)["call_model"]
        assert 500 < model["floor_us"] < 50_000, model


# ── ② 인과 귀속 — 구간 겹침 ─────────────────────────────────────────────────────────────────────
def test_overlap_detects_a_stall_inside_an_in_flight_call():
    """겹침 판정: 완전 포함·부분 겹침은 >0, 떨어진 구간은 ≤0."""
    assert PROBE._overlap_us((100.0, 500.0), (200.0, 900.0)) == 300.0
    assert PROBE._overlap_us((200.0, 900.0), (100.0, 500.0)) == 300.0
    assert PROBE._overlap_us((100.0, 200.0), (300.0, 400.0)) <= 0
    assert PROBE._overlap_us((100.0, 200.0), (200.0, 300.0)) == 0.0


def test_recorded_runs_attribute_stalls_to_media_calls():
    """실측 귀속(두 실행): 기준선에는 밀림이 0건이고, media 팔의 밀림은 배경 호출과 겹친다."""
    for index in (0, 1):
        summary = _fixture(index)["interference"]["summary"]
        baseline = [row for row in summary if row["case"] == "baseline"]
        assert baseline and baseline[0]["slow_gaps_total"] == 0, baseline
        assert baseline[0]["background_calls_total"] == 0, baseline
        for row in summary:
            if row["case"] == "baseline":
                continue
            assert row["background_calls_total"] > 0, row
            assert row["background_sync_errors"] == 0, row
            assert row["slow_gaps_overlapping_a_media_call"] <= row["slow_gaps_total"], row
            assert row["max_overlap_us"] <= row["gap_max_us"] + 1, row
        assert any(row["slow_gaps_total"] > 0 for row in summary), "media 팔에서 밀림이 한 건도 안 잡혔다"


# ── ③ 계측기 계약 — 조용한 0 호출 금지 ────────────────────────────────────────────────────────────
def test_background_thread_that_cannot_open_is_reported_not_silent(monkeypatch):
    """**핵심 계기 계약**: 배경 스레드의 열기가 실패하면 `thread_error` 가 서고, 성공처럼 보이지 않는다.

    열기를 **스레드에서만** 실패시킨다(첫 시도의 결함은 “배경이 못 여는데 리포트는 정상”이었다).
    """
    import errno
    import threading

    real_open = os.open

    def flaky_open(path, flags, *args, **kwargs):
        if threading.current_thread() is not threading.main_thread():
            raise OSError(errno.ENOENT, "simulated worker-side failure")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", flaky_open)
    with tempfile.TemporaryDirectory(prefix="nx10-media-contract-") as tmp:
        result = PROBE._paced_write(
            Path(tmp) / "journal.jsonl",
            40,
            pace_us=200.0,
            sync_every=8,
            background_media=threading.Event(),
            background_interval_s=0.05,
        )
    assert result["background"]["thread_error"] == 1, result["background"]
    assert result["background"]["calls"] == 0, "실패한 스레드가 호출을 성공으로 세면 안 된다"
    assert result["commits"] == 40, "배경이 죽어도 포그라운드는 돌아야 한다"


def test_negative_control_without_ocreat_the_thread_dies_silently():
    """**음성 대조군**: 옛 코드(`O_CREAT` 없이 열기)는 예외로 **스레드만 죽고** 리포트는 0 호출로 남는다.

    이 시험이 없으면 “조용히 0 호출”이 다시 들어와도 아무도 모른다 — 첫 시도가 정확히 그랬다.
    (같은 시나리오를 `_paced_write` 로는 만들 수 없다: 새 코드는 `O_CREAT` 로 열어 살아남기 때문이다.
    그래서 옛 규칙을 **여기서 그대로 재현**한다.)
    """
    import threading

    with tempfile.TemporaryDirectory(prefix="nx10-media-contract-") as tmp:
        missing = Path(tmp) / "no-such-dir" / "journal.jsonl"
        outcome: dict[str, object] = {}

        def old_worker() -> None:
            try:
                os.open(str(missing), os.O_WRONLY | os.O_APPEND)  # O_CREAT 없음 → 옛 코드의 결함
            except OSError as exc:
                outcome["error"] = type(exc).__name__
                return
            outcome["opened"] = True

        thread = threading.Thread(target=old_worker)
        thread.start()
        thread.join(timeout=5)
    assert outcome.get("error") == "FileNotFoundError", outcome
    assert "opened" not in outcome, "옛 코드가 열렸다면 이 대조군은 뜻을 잃는다"


def test_worker_source_keeps_the_ocreat_that_makes_it_alive():
    """소스 이빨: 워커의 여는 호출에 `O_CREAT` 가 있어야 한다(계기가 살아 있어야 값을 낸다)."""
    source = (HERE / "probe_media_offload_cost.py").read_text(encoding="utf-8")
    worker = source.split("def worker()", 1)[1].split("thread = threading.Thread", 1)[0]
    assert "os.O_CREAT" in worker, "워커가 O_CREAT 없이 연다 — 없는 파일이면 스레드가 조용히 죽는다"


def test_sync_exception_inside_the_worker_is_recorded_not_swallowed(monkeypatch):
    """두 번째 조용한 죽음 경로: 워커의 sync 가 던지면 **기록**되고 0 호출로 포장되지 않는다.

    첫 시도에서 배운 것을 부류로 막는다: “배경이 죽었는데 리포트는 정상”은 한 곳(열기)만이 아니라
    sync 호출 자체에서도 생길 수 있다.
    """
    import threading

    def exploding_media_sync(fd: int) -> None:
        if threading.current_thread() is not threading.main_thread():
            raise OSError("simulated media sync failure")

    monkeypatch.setattr(PROBE, "_media_sync", exploding_media_sync)
    with tempfile.TemporaryDirectory(prefix="nx10-media-contract-") as tmp:
        result = PROBE._paced_write(
            Path(tmp) / "journal.jsonl",
            40,
            pace_us=200.0,
            sync_every=8,
            background_media=threading.Event(),
            background_interval_s=0.01,
        )
    assert result["background"]["calls"] == 0, result["background"]
    assert result["background"]["errors"], "워커의 예외가 사라졌다 — 조용한 죽음이 돌아왔다"
    assert "OSError" in result["background"]["errors"][0], result["background"]


# ── ④ 교차 설계 · 위생 ────────────────────────────────────────────────────────────────────────────
def test_paired_design_compares_each_arm_with_its_own_round():
    """소스 이빨: 델타는 `per_arm["baseline"][그 라운드]` 와 짝지어 계산한다(전역 평균이 아니다)."""
    source = (HERE / "probe_media_offload_cost.py").read_text(encoding="utf-8")
    assert 'paired.append(100 * (entry["ops_per_second"] / base["ops_per_second"] - 1))' in source
    assert 'base = per_arm["baseline"][entry["round"]]' in source, "라운드 짝짓기가 사라졌다"
    fixture = _fixture()["interference"]
    arms = {row["case"] for row in fixture["summary"]}
    assert fixture["rounds"] >= 2 and len(fixture["blocks"]) == fixture["rounds"] * len(arms), fixture.keys()


def test_probe_leaves_no_neighbour_dirty_pages_behind():
    """위생: 이웃 파일(64 MB)은 측정 뒤 sync + unlink 된다 — 첫 시도는 이걸 남겨 뒤 실측을 밀었다."""
    with tempfile.TemporaryDirectory(prefix="nx10-media-contract-") as tmp:
        tmp_path = Path(tmp)
        result = PROBE._idle_calls(tmp_path, rounds=2)
        leftovers = sorted(p.name for p in tmp_path.iterdir())
    assert "other-dirty.bin" not in leftovers, f"이웃 dirty 를 남겼다: {leftovers}"
    assert result["neighbor_cleanup_us"] > 0, result
    assert "남기지 않는다" in result["neighbor_cleanup_note"]


def test_documented_numbers_match_the_recorded_runs():
    """**문서↔픽스처 대조**: 설계 문서에 인용한 수치가 기록된 두 실행과 **문자 단위로** 같은가.

    이 시험이 없으면 그 부류의 오류가 그대로 남는다 — 실제로 이 문서를 쓰면서 밟았다: 프로브를 한 번 더 돌려
    (`1,000 ms` 팔 추가) 픽스처가 바뀜 뒤에도 표는 **옛 세대의 수치**를 들고 있었다. 서사가 맞아도 수치가
    낡으면 다음 사람이 그것을 인용한다. 문서를 고칠 때 같이 고장 나는 것이 이 시험의 임무다.
    """
    doc = (HERE / "MEDIA_OFFLOAD_COST_MODEL.md").read_text(encoding="utf-8").replace("\u2212", "-")
    missing: list[str] = []

    def need(text: str) -> None:
        if text not in doc:
            missing.append(text)

    for index in (0, 1):
        fixture = _fixture(index)
        model = fixture["call_model"]
        need(f"{model['floor_us']:,.1f}")
        need(f"{fixture['idle_and_neighbor']['clean_median_us']:,.1f}")
        for point in fixture["accumulation_curve"]["points"]:
            need(f"{point['media_min_us']:,.0f}")
            if point["commits"] >= 128:
                need(f"{point['media_us_per_commit_min']:.3f}")
        for row in fixture["interference"]["summary"]:
            if row["case"] == "baseline":
                continue
            need(f"{row['paired_delta_percent_median']:.2f}")
            need(f"{row['paired_delta_percent_worst']:.2f}")
            if row["background_max_us"]:
                need(f"{row['background_max_us'] / 1e6:.2f} s")
        if index == 0:
            for row in PROBE._schedule_arithmetic(model, (1.0, 10.0, 60.0, 600.0, 3600.0)):
                need(f"{row['amortized_us_per_commit']:.4f}".rstrip("0").rstrip("."))

    assert not missing, (
        f"설계 문서가 낡은 수치를 들고 있다(픽스처에서 찾은 값 {len(missing)}개가 문서에 없다): {missing[:12]}"
    )


def test_idle_call_is_measured_with_nothing_pending_on_either_side():
    """유휴 호출도 값이 있다(0 이 아니다) — “쓸 게 없으면 공짜”가 아니라 **호출당 배리어 값**이다."""
    with tempfile.TemporaryDirectory(prefix="nx10-media-contract-") as tmp:
        result = PROBE._idle_calls(Path(tmp), rounds=2)
    assert result["clean_median_us"] > 0, result
    assert result["neighbor_dirty_over_clean"] > 0, result
