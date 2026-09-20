"""task 24 계약 시험 — 회귀 gate 가 **실제로 잡는가**를 시험한다.

gate 자체가 초록인 것은 아무것도 증명하지 않는다. 그래서 여기서는
① 고정 검색셋이 봉인되어 있는지(fixture·기준선·임계값),
② 정상 실행이 통과하는지,
③ **실패를 주입하면 겨눈 조건으로 실패하는지**,
④ 자동 완화 경로가 없는지(플래그·waiver·기준선) 를 잰다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "benchmark_ssak_search.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "ssak_search_eval"
ANCHOR = FIXTURE_DIR / "anchor.json"
SLICE = 10


def _script_module() -> object:
    """스크립트를 모듈로 불러온다(단위 검사용) — CLI 경로와 같은 코드를 잰다."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("benchmark_ssak_search", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass 가 문자열 annotation 을 해석하려면 모듈이 sys.modules 에 있어야 한다.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module() -> object:
    return _script_module()


def _run(*args: str, expect: int | None = None) -> tuple[int, dict[str, object]]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("AGK_SEARCH_", "SSAK_SEARCH_EVAL_")):
            env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=False,
    )
    if expect is not None:
        assert result.returncode == expect, f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    if "--output" not in args:  # 사용 오류 경로는 리포트를 쓰지 않는다
        return result.returncode, {}
    report_path = Path(args[args.index("--output") + 1])
    report = (
        cast(dict[str, object], json.loads(report_path.read_text(encoding="utf-8"))) if report_path.exists() else {}
    )
    return result.returncode, report


def _failed_checks(report: Mapping[str, object]) -> set[str]:
    gate = cast(Mapping[str, object], report["gate"])
    return {str(name) for name in cast(list[object], gate["failed"])}


def _contract_failures(report: Mapping[str, object]) -> list[str]:
    contract = cast(Mapping[str, object], report["contract"])
    return [str(name) for name in cast(list[object], contract["failures"])]


@pytest.fixture(scope="module")
def slice_anchor(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """시험용 기준선 — 커밋된 전체 기준선과 분리해 시험 시간을 줄인다(같은 코드 경로)."""
    workdir = tmp_path_factory.mktemp("ssak-search-gate")
    anchor = workdir / "anchor.json"
    _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--paired",
        "--refresh-anchor",
        "--reason",
        "계약 시험용 슬라이스 기준선",
        "--anchor",
        str(anchor),
        "--output",
        str(workdir / "refresh.json"),
        "--quiet",
        expect=0,
    )
    return anchor


# ── ① 고정 검색셋·기준선 ─────────────────────────────────────────────────────


def test_fixture_carries_the_declared_100_cases_and_30_extractions(module: object) -> None:
    loader = getattr(module, "load_fixture")
    fixture = loader()
    assert len(fixture.cases) == 100, "고정 검색셋은 100개다"
    assert len(fixture.extraction) == 30, "추출 fixture 는 30개다"
    categories = [case.category for case in fixture.cases]
    for name in ("official", "latest", "general", "dev", "multilingual"):
        assert categories.count(name) == 20, f"{name} 20건"
    assert len({case.case_id for case in fixture.cases}) == 100, "case_id 는 고유해야 한다"
    assert fixture.sha256, "고정 검색셋은 지문을 가진다"


def test_every_case_has_human_grades_and_a_usable_payload(module: object) -> None:
    fixture = getattr(module, "load_fixture")()
    for case in fixture.cases:
        grades = [hit.grade for hit in case.hits]
        assert max(grades) >= 1, f"{case.case_id}: 정답 등급이 없다"
        assert all(0 <= grade <= 3 for grade in grades), f"{case.case_id}: 등급 범위"
        assert case.query.strip(), f"{case.case_id}: 질의 없음"
        assert case.authority_expectation in {"satisfied", "absent", "n/a"}, case.authority_expectation
    satisfied = [case for case in fixture.cases if case.authority_expectation == "satisfied"]
    assert len(satisfied) >= 15, "권위 의도 케이스가 있어야 그 계약이 의미를 갖는다"
    for case in satisfied:
        assert case.authority_urls, f"{case.case_id}: satisfied 라면 payload 안에 권위 출처가 있어야 한다"


def test_committed_anchor_matches_the_frozen_fixture_and_the_code_thresholds(module: object) -> None:
    anchor = cast(Mapping[str, object], json.loads(ANCHOR.read_text(encoding="utf-8")))
    fixture = getattr(module, "load_fixture")()
    assert anchor["fixture_sha256"] == fixture.sha256, "고정 검색셋이 바뀌면 기준선을 사유와 함께 다시 떠야 한다"
    assert anchor["fixture_version"] == fixture.version
    assert anchor["thresholds"] == dict(getattr(module, "THRESHOLDS")), "기준선이 느슨한 임계값을 주장하면 안 된다"
    assert anchor["reason"].strip(), "기준선에는 갱신 사유가 기록된다"
    metrics = cast(Mapping[str, object], cast(Mapping[str, object], anchor["arms"])["integrated"])
    assert float(cast(float, cast(Mapping[str, object], metrics["metrics"])["case_count"])) == 100


def test_experiment_cannot_lower_thresholds_from_the_command_line(module: object) -> None:
    parser = getattr(module, "build_parser")()
    options = " ".join(option for action in parser._actions for option in action.option_strings)  # noqa: SLF001
    for forbidden in ("threshold", "tolerance", "ndcg", "p95", "cost", "allow-degradation"):
        assert forbidden not in options, f"임계값을 CLI 로 완화하는 플래그는 존재하면 안 된다: {forbidden}"
    assert "--waiver-approved-by" in options and "--refresh-anchor" in options, "완화는 기록되는 두 경로뿐이다"


# ── ② 정상 실행 ──────────────────────────────────────────────────────────────


def test_gate_passes_on_the_accepted_state(module: object, slice_anchor: Path, tmp_path: Path) -> None:
    _, report = _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--paired",
        "--anchor",
        str(slice_anchor),
        "--output",
        str(tmp_path / "clean.json"),
        "--quiet",
        expect=0,
    )
    gate = cast(Mapping[str, object], report["gate"])
    assert gate["verdict"] == "PASS"
    assert not _failed_checks(report)
    contract = cast(Mapping[str, object], report["contract"])
    assert contract["pass_rate"] == 1.0, _contract_failures(report)
    assert report["thresholds"] == dict(getattr(module, "THRESHOLDS"))
    assert report["comparison"], "--paired 이면 짝 비교가 리포트에 남는다"
    arms = cast(Mapping[str, object], report["arms"])
    for name in ("legacy", "integrated"):
        metrics = cast(Mapping[str, object], cast(Mapping[str, object], arms[name])["metrics"])
        assert float(cast(float, metrics["case_count"])) == SLICE
        assert float(cast(float, metrics["p95_cold_ms"])) > 0


def test_clean_report_carries_the_long_term_evidence(module: object, slice_anchor: Path, tmp_path: Path) -> None:
    _, report = _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--anchor",
        str(slice_anchor),
        "--output",
        str(tmp_path / "evidence.json"),
        "--quiet",
        expect=0,
    )
    for key in ("fixture", "machine", "thresholds", "arms", "contract", "extraction", "gate", "comparison"):
        assert key in report, key
    fixture = cast(Mapping[str, object], report["fixture"])
    assert fixture["sha256"] and fixture["case_count"] == SLICE
    extraction = cast(Mapping[str, object], report["extraction"])
    assert extraction["case_count"] == 30, "추출 fixture 는 슬라이스와 무관하게 항상 전부 잰다"
    assert report["latency_noise_floor_ms"] > 0


# ── ③ 실패 주입 → 겨눈 조건으로 검출 ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("injection", "expected"),
    [
        ("low-quality", "integrated_ndcg_at_k"),
        ("slow", "paired_p95_ratio"),
        ("expensive", "paired_token_ratio"),
        ("empty", "integrated_valid_source_ratio"),
    ],
)
def test_degraded_provider_trips_the_gate_on_the_matching_check(
    module: object, slice_anchor: Path, tmp_path: Path, injection: str, expected: str
) -> None:
    code, report = _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--paired",
        "--inject",
        injection,
        "--anchor",
        str(slice_anchor),
        "--output",
        str(tmp_path / f"inject-{injection}.json"),
        "--quiet",
    )
    assert code == 1, f"{injection} 주입은 gate 를 무너뜨려야 한다\n{report}"
    failed = _failed_checks(report)
    assert expected in failed, f"{injection}: 기대한 검사 {expected} 가 실패하지 않았다 — 실패: {sorted(failed)}"
    assert "canary_detected" not in failed, "주입은 자기가 겨눈 지표로 검출돼야 한다"
    canary = cast(Mapping[str, object], report["canary"])
    assert canary["injection"] == injection and canary["arm_measured"]


def test_nondeterministic_provider_trips_the_deterministic_contract(
    module: object, slice_anchor: Path, tmp_path: Path
) -> None:
    code, report = _run(
        "--limit",
        str(SLICE),
        "--runs",
        "2",
        "--paired",
        "--inject",
        "noisy",
        "--anchor",
        str(slice_anchor),
        "--output",
        str(tmp_path / "inject-noisy.json"),
        "--quiet",
    )
    assert code == 1
    failures = _contract_failures(report)
    assert any(name.endswith("warm_equals_cold") for name in failures), failures
    assert any(name.endswith("deterministic_across_runs") for name in failures), failures


def test_low_quality_injection_keeps_non_candidate_contracts_intact(
    module: object, slice_anchor: Path, tmp_path: Path
) -> None:
    """주입은 후보 arm 만 바꾼다 — legacy arm 에 계약 실패를 만들어 내면 그건 가짜 검출이다."""
    _, report = _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--paired",
        "--inject",
        "low-quality",
        "--anchor",
        str(slice_anchor),
        "--output",
        str(tmp_path / "inject-legacy-scope.json"),
        "--quiet",
    )
    failures = _contract_failures(report)
    assert not [name for name in failures if name.startswith("legacy:")], failures
    arms = cast(Mapping[str, object], report["arms"])
    legacy_metrics = cast(Mapping[str, object], cast(Mapping[str, object], arms["legacy"])["metrics"])
    assert float(cast(float, legacy_metrics["ndcg_at_k"])) > 0.5, "legacy arm 은 주입의 영향을 받지 않는다"


# ── ④ 자동 완화 금지 ────────────────────────────────────────────────────────


def test_waiver_requires_cause_value_and_approver(module: object, slice_anchor: Path, tmp_path: Path) -> None:
    common = (
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--inject",
        "low-quality",
        "--anchor",
        str(slice_anchor),
    )
    code, _ = _run(
        *common,
        "--waiver-cause",
        "원인만 적음",
        "--output",
        str(tmp_path / "waiver-partial.json"),
        "--quiet",
    )
    assert code == 2, "원인만 적은 예외는 거절된다"
    code, report = _run(
        *common,
        "--waiver-cause",
        "공급자 열화",
        "--waiver-user-value",
        "사용자 가치 문장",
        "--waiver-approved-by",
        "owner",
        "--output",
        str(tmp_path / "waiver-full.json"),
        "--quiet",
    )
    assert code == 0, "승인자까지 적은 예외만 통과시킨다"
    gate = cast(Mapping[str, object], report["gate"])
    assert gate["verdict"] == "PASS_WITH_WAIVER"
    waivers = cast(list[Mapping[str, object]], report["waivers"])
    assert waivers and waivers[0]["approved_by"] == "owner"
    assert _failed_checks(report), "예외를 적어도 실패한 검사 목록은 그대로 남는다"
    assert report["thresholds"] == dict(getattr(module, "THRESHOLDS"))


def test_waiver_alone_cannot_turn_a_failure_into_a_pass(module: object, slice_anchor: Path, tmp_path: Path) -> None:
    code, _ = _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--inject",
        "low-quality",
        "--anchor",
        str(slice_anchor),
        "--output",
        str(tmp_path / "no-waiver.json"),
        "--quiet",
    )
    assert code == 1, "예외 기록이 없으면 그대로 실패한다"


def test_anchor_can_only_be_refreshed_with_a_recorded_reason(module: object, tmp_path: Path) -> None:
    anchor = tmp_path / "anchor.json"
    _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--refresh-anchor",
        "--anchor",
        str(anchor),
        "--output",
        str(tmp_path / "no-reason.json"),
        "--quiet",
        expect=2,
    )
    assert not anchor.exists(), "사유 없는 갱신은 기준선을 만들지 않는다"
    _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--refresh-anchor",
        "--reason",
        "사유 있음",
        "--anchor",
        str(anchor),
        "--output",
        str(tmp_path / "with-reason.json"),
        "--quiet",
        expect=0,
    )
    written = cast(Mapping[str, object], json.loads(anchor.read_text(encoding="utf-8")))
    assert written["reason"] == "사유 있음" and written["actor"]


def test_anchor_drift_and_fixture_change_are_both_detected(module: object, slice_anchor: Path, tmp_path: Path) -> None:
    tighter = cast(dict[str, object], json.loads(slice_anchor.read_text(encoding="utf-8")))
    arms = cast(dict[str, object], tighter["arms"])
    integrated = cast(dict[str, object], arms["integrated"])
    metrics = cast(dict[str, object], integrated["metrics"])
    metrics["ndcg_at_k"] = float(cast(float, metrics["ndcg_at_k"])) + 0.2
    drifted = tmp_path / "anchor-tightened.json"
    drifted.write_text(json.dumps(tighter, ensure_ascii=False), encoding="utf-8")
    code, report = _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--anchor",
        str(drifted),
        "--output",
        str(tmp_path / "drift.json"),
        "--quiet",
    )
    assert code == 1 and "integrated_ndcg_at_k" in _failed_checks(report)

    broken = cast(dict[str, object], json.loads(slice_anchor.read_text(encoding="utf-8")))
    broken["fixture_sha256"] = "deadbeef"
    broken_path = tmp_path / "anchor-other-fixture.json"
    broken_path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    code, report = _run(
        "--limit",
        str(SLICE),
        "--runs",
        "1",
        "--anchor",
        str(broken_path),
        "--output",
        str(tmp_path / "fixture-drift.json"),
        "--quiet",
    )
    assert code == 1 and "anchor_fixture_unchanged" in _failed_checks(report)


def test_paired_requires_both_arms(module: object, tmp_path: Path) -> None:
    code, _ = _run(
        "--paired",
        "--provider",
        "legacy",
        "--limit",
        str(SLICE),
        "--output",
        str(tmp_path / "paired-legacy.json"),
        "--quiet",
    )
    assert code == 2


# ── 단위: 지표·주입 헬퍼 ─────────────────────────────────────────────────────


def test_percentile_and_ratio_helpers(module: object) -> None:
    percentile = getattr(module, "_percentile")
    ratio = getattr(module, "_ratio")
    assert percentile([], 0.95) == 0.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95) == 5.0
    assert percentile([1.0], 0.95) == 1.0
    assert ratio(2.0, 1.0) == 2.0
    assert ratio(0.0, 0.0) == 0.0
    assert ratio(1.0, 0.0) == float("inf")


def test_valid_source_and_authority_rules_match_the_product(module: object) -> None:
    valid = getattr(module, "_valid_source")
    authoritative = getattr(module, "_is_authoritative")
    assert valid("https://docs.python.org/3/library/asyncio-task.html")
    assert not valid("http://localhost:8080/search")
    assert not valid("http://127.0.0.1/search")
    assert not valid("https://unknown-tld-page.zzz/x")
    assert authoritative("https://www.law.go.kr/LSW/lsInfoP.do")
    assert not authoritative("https://github.com/opencontainers/image-spec/blob/main/spec.md"), (
        "github 은 제품 규칙에서 제외"
    )


def test_injections_only_touch_the_intended_dimension(module: object) -> None:
    fixture = getattr(module, "load_fixture")(limit=20)
    injected = getattr(module, "_injected_hits")
    case = next(case for case in fixture.cases if any(hit.grade == 0 for hit in case.hits))
    untouched = injected(case, None)
    assert untouched == case.hits
    degraded = injected(case, "low-quality")
    assert degraded and all(hit.grade == 0 for hit in degraded)
    assert len(degraded) < len(case.hits)
    expensive = injected(case, "expensive")
    assert len(expensive) == len(case.hits)
    assert sum(len(hit.snippet) for hit in expensive) > sum(len(hit.snippet) for hit in case.hits) * 2
    assert injected(case, "empty") == ()
    assert injected(case, "slow") == case.hits, "지연 주입은 payload 모양을 바꾸지 않는다"


def test_extraction_fixtures_are_grounded_and_never_invent_evidence(module: object) -> None:
    fixture = getattr(module, "load_fixture")()
    block = cast(Mapping[str, object], getattr(module, "extraction_block")(fixture))
    assert block["case_count"] == 30
    assert block["label_rate"] == 1.0, f"근거 유무 판정이 fixture 기대와 갈렸다: {block['failures']}"
    assert block["junk_rate"] == 1.0, f"군더더기가 남았다: {block['failures']}"
    negatives = [case for case in fixture.extraction if not case.expect_supported]
    assert len(negatives) >= 5, "없는 근거를 만들지 않는지 재려면 음성 fixture 가 필요하다"
    for case in negatives:
        assert case.required_facts, f"{case.case_id}: 음성 fixture 도 사실 목록이 있어야 검출된다"


def test_html_to_text_seam_strips_scripts_and_navigation() -> None:
    from antigravity_k.tools.web_search_engine import PageScraper, html_to_text

    html = (
        "<html><body><nav>메뉴</nav><script>var secret=1;</script>"
        "<main><h1>제목</h1><p>본문 사실</p></main><footer>바닥글</footer></body></html>"
    )
    text = html_to_text(html)
    assert "본문 사실" in text and "제목" in text
    for junk in ("메뉴", "var secret", "바닥글"):
        assert junk not in text, junk
    assert html_to_text("<p>" + "가" * 50 + "</p>", max_chars=10) == "가" * 10
    assert hasattr(PageScraper, "extract_text"), "추출 seam 은 PageScraper 가 쓰는 그 함수다"


def _observation(module: object, case: object, urls: tuple[str, ...], **overrides: object) -> object:
    kwargs: dict[str, object] = {
        "case_id": getattr(case, "case_id"),
        "cold_ms": 1.0,
        "warm_ms": 1.0,
        "results": tuple((f"t{i}", url, "snippet") for i, url in enumerate(urls)),
        "cold_results": urls,
        "warm_results": urls,
        "tokens": 10,
    }
    kwargs.update(overrides)
    return getattr(module, "Observation")(**kwargs)  # type: ignore[arg-type]


def _contracts_for(module: object, observations: list[object], cases: list[object]) -> dict[str, object]:
    fixture = getattr(module, "load_fixture")(limit=len(cases))
    arm = getattr(module, "ArmResult")(name="legacy", observations=observations)
    hits = {getattr(case, "case_id"): tuple(hit.url for hit in getattr(case, "hits")) for case in cases}
    return cast(
        dict[str, object],
        getattr(module, "contract_checks")(
            fixture,
            [case for case in fixture.cases],
            {"legacy": arm},
            1,
            getattr(module, "extraction_block")(fixture),
            hits,
            hits,
        ),
    )


def test_contract_checks_catch_a_provider_that_invents_sources(module: object) -> None:
    fixture = getattr(module, "load_fixture")(limit=1)
    case = fixture.cases[0]
    report = _contracts_for(module, [_observation(module, case, ("https://evil.example/invented",))], [case])
    assert "legacy:no_fabricated_sources" in cast(list[str], report["failures"])


def test_contract_checks_catch_over_limit_and_duplicate_results(module: object) -> None:
    fixture = getattr(module, "load_fixture")(limit=1)
    case = fixture.cases[0]
    urls = tuple(hit.url for hit in case.hits)
    padded = urls + tuple(f"https://extra.example/{index}" for index in range(9))
    report = _contracts_for(module, [_observation(module, case, padded)], [case])
    assert "legacy:result_limit" in cast(list[str], report["failures"])
    duplicated = (urls[0], urls[0], *urls[1:])
    report = _contracts_for(module, [_observation(module, case, duplicated)], [case])
    assert "legacy:unique_urls" in cast(list[str], report["failures"])


def test_contract_checks_catch_an_empty_answer_when_the_provider_had_results(module: object) -> None:
    fixture = getattr(module, "load_fixture")(limit=1)
    case = fixture.cases[0]
    report = _contracts_for(module, [_observation(module, case, ())], [case])
    assert "legacy:non_empty_results" in cast(list[str], report["failures"])


def test_contract_checks_demand_authority_for_authoritative_intent(module: object) -> None:
    fixture = getattr(module, "load_fixture")()
    case = next(case for case in fixture.cases if case.authority_expectation == "satisfied")
    without_authority = tuple(hit.url for hit in case.hits if hit.url not in case.authority_urls)
    report = _contracts_for(module, [_observation(module, case, without_authority)], [case])
    assert "legacy:authority_required" in cast(list[str], report["failures"])


def test_contract_checks_catch_a_warm_call_that_goes_back_to_the_provider(module: object) -> None:
    fixture = getattr(module, "load_fixture")(limit=1)
    case = fixture.cases[0]
    urls = tuple(hit.url for hit in case.hits)
    observation = _observation(module, case, urls, cache_supported=True, warm_provider_requests=3)
    report = _contracts_for(module, [observation], [case])
    assert "legacy:warm_adds_no_provider_requests" in cast(list[str], report["failures"])


def test_legacy_arm_really_observes_the_cache(module: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """캐시 계약의 **관측 자체**를 잰다 — 카운터가 0 을 하드코딩해도 초록이면 계약이 아니다."""
    import asyncio

    from antigravity_k.tools import web_search_cache as cache_module
    from antigravity_k.tools.web_search_cache import SearchCache

    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    fixture = getattr(module, "load_fixture")(limit=2)
    arm = getattr(module, "LegacyArm")(fixture.cases, 5)
    warm = asyncio.run(arm.run_case(fixture.cases[0]))
    assert warm.cache_supported is True, "정상 케이스는 캐시가 실제로 저장되어야 한다"
    assert warm.warm_provider_requests == 0, "캐시가 일했으면 provider 요청은 늘지 않는다"
    assert warm.cold_results == warm.warm_results

    monkeypatch.setattr(SearchCache, "set", lambda self, query, response: None)
    cold_only = asyncio.run(arm.run_case(fixture.cases[1]))
    assert cold_only.cache_supported is False
    assert cold_only.warm_provider_requests > 0, (
        "캐시가 없으면 웜 호출이 provider 로 다시 나간다 — 카운터가 실제로 센다"
    )
    asyncio.run(arm.close())


def test_canary_targets_cover_every_injection(module: object) -> None:
    targets = cast(Mapping[str, tuple[str, ...]], getattr(module, "CANARY_TARGETS"))
    injections = getattr(module, "INJECTIONS")
    assert set(targets) == set(injections), "모든 주입은 겨눌 검사를 가진다"
    assert all(values for values in targets.values())
