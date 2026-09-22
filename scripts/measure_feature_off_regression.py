#!/usr/bin/env python
"""P11 feature-off 회귀 실측 — 설정이 OFF일 때 기존 경로가 그대로인지 관찰한다.

세 가지 설정으로 같은 legacy 인지 루프 hook을 실제로 돌리고 결과를 비교한다.

1. ``absent``: `cognitive_core` 섹션이 없는 현재 기본값
2. ``disabled_explicit``: ``enabled=false`` + ``mode=active`` (켜려는 시도를 명시적으로 거부)
3. ``shadow_enabled``: ``enabled=true`` + ``mode=shadow`` (adapter를 실제로 만들어 shadow episode 실행)

판정:

- legacy transcript(verify/reflect/adapt 결과)는 세 설정에서 **동일**해야 한다.
- shadow는 workspace에 **아무 파일도 만들지 않아야** 한다(dispatch 0).

```sh
.venv/bin/python scripts/measure_feature_off_regression.py --output /tmp/feature-off.json
```
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from antigravity_k.engine.cognitive.actions import PolicyClearance
from antigravity_k.engine.cognitive.authority import AuthorityDecision, AuthorityVerdict
from antigravity_k.engine.cognitive.models import AuthorityDimension, RiskProfile
from antigravity_k.engine.cognitive.readiness import (
    ActionScope,
    EvidenceRef,
    HardConstraint,
    ReadinessInputs,
    check_readiness,
)
from antigravity_k.engine.cognitive.runtime import ThinkOutcome
from antigravity_k.engine.cognitive_loop import CognitiveLoop
from antigravity_k.engine.cognitive_surface import (
    CONFIG_SECTION,
    CognitiveCoreSettings,
    CognitiveSurfaceAdapter,
    SurfaceEpisodeRequest,
    SurfaceIntentRequest,
    SurfaceMode,
)

EXIT_OK: Final[int] = 0
EXIT_REGRESSION: Final[int] = 1
CONFIGS: Final[tuple[str, ...]] = ("absent", "disabled_explicit", "shadow_enabled")
AUTHORITY_REVISION: Final[int] = 1
DECISION_REVISION: Final[int] = 1
STATE_REVISION: Final[int] = 1
POLICY_VERSION: Final[str] = "feature-off-v1"
WOULD_BE_TARGET: Final[str] = "would-be-write.txt"


def source_head() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def settings_for(config: str) -> CognitiveCoreSettings:
    if config == "absent":
        return CognitiveCoreSettings.from_config({})
    if config == "disabled_explicit":
        return CognitiveCoreSettings.from_config({CONFIG_SECTION: {"enabled": False, "mode": "active"}})
    return CognitiveCoreSettings.from_config({CONFIG_SECTION: {"enabled": True, "mode": "shadow"}})


class _StubBrain:
    """shadow 판단 주체. 모델 호출이 아니라 계측 경로 확인용 stub이다."""

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        _ = (context_ref, request_signature, attempt)
        return ThinkOutcome(judgment_ref="judgment:feature-off")


def _write_intent(target: Path) -> SurfaceIntentRequest:
    """dispatch된다면 target에 파일을 만드는 의도. shadow에서는 만들어지면 안 된다."""

    request = SurfaceIntentRequest(
        action_key="feature-off:write",
        tool="fixture_write",
        arguments={"file_path": str(target), "content": "would be written"},
        scope=WOULD_BE_TARGET,
        dimension=AuthorityDimension.TOOL_WRITE,
        policy_version=POLICY_VERSION,
        decision_revision=DECISION_REVISION,
        state_revision=STATE_REVISION,
        authority_revision=AUTHORITY_REVISION,
    )
    digest = request.to_intent().args_digest()
    decision = AuthorityDecision(
        allowed=True,
        verdict=AuthorityVerdict.ALLOWED,
        reason="feature-off regression clearance",
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope=WOULD_BE_TARGET,
        profile_revision=AUTHORITY_REVISION,
    )
    readiness = check_readiness(
        ReadinessInputs(
            action=ActionScope(
                tool="fixture_write",
                scope=WOULD_BE_TARGET,
                expected_outcome="would be written",
                action_digest=digest,
            ),
            authorized_action_digest=digest,
            decision_revision=DECISION_REVISION,
            state_revision=STATE_REVISION,
            authority_revision=AUTHORITY_REVISION,
            policy_version=POLICY_VERSION,
            grounds=("evidence:feature-off",),
            evidence_refs=(
                EvidenceRef(
                    evidence_id="evidence:feature-off",
                    provenance_uri="fixtures/feature-off/evidence.json",
                    provenance_digest="sha256:" + hashlib.sha256(b"feature-off").hexdigest(),
                    observed_at=datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
                ),
            ),
            constraints=(HardConstraint(name="no_network", satisfied=True),),
            risk=RiskProfile(),
            authority_decision=decision,
        )
    )
    return replace(
        request,
        readiness=readiness,
        clearance=PolicyClearance(authority=decision, revision=AUTHORITY_REVISION),
    )


def legacy_transcript(project_root: Path) -> dict[str, object]:
    """기존 경로(legacy CognitiveLoop)를 실제로 돌려 관찰 가능한 결과를 남긴다."""

    loop = CognitiveLoop(project_root=str(project_root), max_retries=1, dialectic_enabled=False)
    missing = loop.verify_tool_result("fixture_write", {"file_path": "missing.txt"}, "Error: missing evidence file")
    ok = loop.verify_tool_result("fixture_write", {"file_path": "ok.txt"}, "appended ok.txt")
    reflection = loop.reflect("task: append evidence", "output")
    return {
        "verify_missing": dict(missing),
        "verify_ok": dict(ok),
        "reflect": asdict(reflection),
        "anti_patterns": list(loop.get_anti_patterns()),
        "adapt_after_failure": bool(loop.adapt_for_retry()),
        "max_retries": loop.max_retries,
        "dialectic_enabled": loop.dialectic_enabled,
    }


def _digest(payload: object) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
    )


def _tree_digest(root: Path) -> str:
    entries = sorted((str(path.relative_to(root)), path.stat().st_size) for path in root.rglob("*") if path.is_file())
    return _digest(entries)


@dataclass(frozen=True, slots=True)
class ConfigRun:
    """한 설정에서 관찰한 결과."""

    settings: Mapping[str, object]
    surface_status: Mapping[str, object]
    shadow: Mapping[str, object] | None
    legacy_transcript: Mapping[str, object]
    legacy_digest: str
    workspace_digest: str
    would_be_target_created: bool

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "settings": dict(self.settings),
            "surface_status": dict(self.surface_status),
            "shadow": dict(self.shadow) if self.shadow is not None else None,
            "legacy_transcript": dict(self.legacy_transcript),
            "legacy_digest": self.legacy_digest,
            "workspace_digest": self.workspace_digest,
            "would_be_target_created": self.would_be_target_created,
        }


@dataclass(frozen=True, slots=True)
class FeatureOffMeasurement:
    """feature-off 회귀 측정 결과."""

    source_head: str
    configs: tuple[str, ...]
    runs: Mapping[str, ConfigRun]
    legacy_digests: Mapping[str, str]
    legacy_transcript_identical: bool
    workspace_unchanged: bool
    would_be_target_absent: bool
    shadow_dispatched_actions: int
    passed: bool
    reasons: tuple[str, ...]

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "source_head": self.source_head,
            "configs": list(self.configs),
            "runs": {config: run.as_mapping() for config, run in self.runs.items()},
            "invariants": {
                "legacy_transcript_identical": self.legacy_transcript_identical,
                "legacy_digests": dict(self.legacy_digests),
                "workspace_unchanged": self.workspace_unchanged,
                "would_be_target_absent": self.would_be_target_absent,
                "shadow_dispatched_actions": self.shadow_dispatched_actions,
            },
            "verdict": {"passed": self.passed, "reasons": list(self.reasons)},
        }


def measure() -> FeatureOffMeasurement:
    runs: dict[str, ConfigRun] = {}
    for config in CONFIGS:
        project_root = Path(tempfile.mkdtemp(prefix=f"feature-off-{config}-"))
        workspace = project_root / "workspace"
        workspace.mkdir()
        target = workspace / WOULD_BE_TARGET
        settings = settings_for(config)
        adapter = CognitiveSurfaceAdapter(settings, think=_StubBrain())
        shadow: Mapping[str, object] | None = None
        if settings.effective_mode is SurfaceMode.SHADOW:
            run = adapter.run_shadow(
                SurfaceEpisodeRequest(
                    episode_id=f"episode:feature-off:{config}",
                    context_ref="context:feature-off",
                    goal_ref="goal:feature-off",
                    intent=_write_intent(target),
                    expected_outcome="would be written",
                    policy_version=POLICY_VERSION,
                )
            )
            shadow = dict(run.as_mapping())
        transcript = legacy_transcript(project_root)
        runs[config] = ConfigRun(
            settings=dict(settings.as_mapping()),
            surface_status=dict(adapter.status().as_mapping()),
            shadow=shadow,
            legacy_transcript=transcript,
            legacy_digest=_digest(transcript),
            workspace_digest=_tree_digest(workspace),
            would_be_target_created=target.exists(),
        )
    digests = {config: run.legacy_digest for config, run in runs.items()}
    baseline = digests["absent"]
    identical = all(digest == baseline for digest in digests.values())
    workspace_untouched = all(run.workspace_digest == runs["absent"].workspace_digest for run in runs.values())
    no_target_created = not any(run.would_be_target_created for run in runs.values())
    shadow_run = runs["shadow_enabled"].shadow
    raw_dispatched = shadow_run["dispatched_actions"] if shadow_run is not None else 0
    dispatched = raw_dispatched if isinstance(raw_dispatched, int) else -1
    passed = bool(identical and workspace_untouched and no_target_created and dispatched == 0)
    return FeatureOffMeasurement(
        source_head=source_head(),
        configs=CONFIGS,
        runs=runs,
        legacy_digests=digests,
        legacy_transcript_identical=identical,
        workspace_unchanged=workspace_untouched,
        would_be_target_absent=no_target_created,
        shadow_dispatched_actions=dispatched,
        passed=passed,
        reasons=() if passed else ("legacy 동작 또는 shadow action 0 계약 위반",),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measure_feature_off_regression",
        description="SSAK-AI feature-off regression measurement (legacy path unchanged)",
    )
    parser.add_argument("--output", type=Path, default=None, help="결과 JSON artifact 경로")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    measurement = measure()
    print(f"legacy transcript identical: {measurement.legacy_transcript_identical}")
    for config, digest in measurement.legacy_digests.items():
        run = measurement.runs[config]
        extra = ""
        if run.shadow is not None:
            extra = f" · shadow dispatched={run.shadow['dispatched_actions']} refusal={run.shadow['refusal']}"
        print(f"  {config:18s} {digest}{extra}")
    print(
        f"workspace unchanged: {measurement.workspace_unchanged} · target absent: {measurement.would_be_target_absent}"
    )
    print(f"verdict: passed={measurement.passed}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(measurement.as_mapping(), ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.output}")
    return EXIT_OK if measurement.passed else EXIT_REGRESSION


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
