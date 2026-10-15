from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final

RUN: Final = Path(__file__).resolve().parent
REPO: Final = Path("/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai")
PYTHON: Final = "/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai/.venv/bin/python"
EVIDENCE: Final = "docs/ssak-ai-core/evidence/"
OWNED: Final = [EVIDENCE + "digest_reverification.json", EVIDENCE + "digest_drift.json"]
PROTECTED: Final = [
    EVIDENCE + "T12_migration.md",
    "tests/cognitive/test_migration.py",
    "tests/cognitive/test_migration_snapshot_lineage.py",
    "src/antigravity_k/engine/cognitive/migration.py",
    "docs/ssak-ai-core/ARCHITECTURE_REVIEW.md",
]
PACKET: Final = REPO / (
    "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP19-BANDIT-GATE-CLOSURE-01/run-20261014T173200Z-codex"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(name: str, argv: list[str]) -> int:
    env = dict(os.environ, PYTHONPATH=str(REPO / "src") + ":" + str(REPO), PYTHONDONTWRITEBYTECODE="1")
    with (RUN / (name + ".stdout.txt")).open("xb") as out, (RUN / (name + ".stderr.txt")).open("xb") as err:
        result = subprocess.run(argv, cwd=REPO, env=env, stdout=out, stderr=err, timeout=600, check=False)
    (RUN / (name + ".receipt.json")).write_text(
        json.dumps({"argv": argv, "cwd": str(REPO), "exit_code": result.returncode}, indent=2) + "\n"
    )
    return result.returncode


if sys.argv[1] == "before":
    pre = RUN / "preimage"
    pre.mkdir()
    for name in OWNED:
        (pre / Path(name).name).write_bytes((REPO / name).read_bytes())
    (RUN / "protected-before.json").write_text(json.dumps({name: digest(REPO / name) for name in PROTECTED}, indent=2))
    manifest = json.loads((PACKET / "artifact-manifest.json").read_text())
    for row in manifest:
        data = (PACKET / row["path"]).read_bytes()
        assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"], row["path"]
    binding = json.loads((PACKET / "checks-attempt-1/source-binding.json").read_text())
    for row in binding:
        assert digest(REPO / row["path"]) == row["sha256"], row["path"]
    cases = ET.parse(PACKET / "checks-attempt-1/junit.xml").findall(".//testcase")
    migration_cases = [c for c in cases if c.get("classname", "").startswith("tests.cognitive.test_migration")]
    assert len(cases) == 141 and len(migration_cases) == 30
    assert not any(
        c.find("failure") is not None or c.find("error") is not None or c.find("skipped") is not None for c in cases
    )
    checks = json.loads((PACKET / "checks-attempt-1/checks.json").read_text())
    regression = next(c for c in checks if c["name"] == "regression")
    assert regression["exit_code"] == 0 and regression["source_binding"] == "source-binding.json"
    assert Path(regression["command"][-1]).name == "junit.xml"
    for name in PROTECTED[1:4]:
        committed = subprocess.check_output(["git", "show", "367863ce:" + name], cwd=REPO)
        assert committed == (REPO / name).read_bytes(), name
    (RUN / "prior-evidence-validation.json").write_text(
        json.dumps(
            {
                "manifest_rows_verified": len(manifest),
                "source_bindings_verified": len(binding),
                "junit_total": len(cases),
                "migration_cases": len(migration_cases),
                "junit_sha256": digest(PACKET / "checks-attempt-1/junit.xml"),
                "migration_sha256": digest(REPO / PROTECTED[3]),
                "test_and_migration_commit_367863ce_equal_current": True,
                "limit": "Prior source binding pins production files only; test execution bytes were not separately pinned. Existing JUnit is scoped regression evidence, not historical live renewal.",
            },
            indent=2,
        )
        + "\n"
    )
    assert command("before-drift", [PYTHON, "-B", "scripts/digest_drift.py", "--emit-json"]) != 0
elif sys.argv[1] == "after-retry":
    (RUN / "private-runtime").mkdir(exist_ok=True)
    assert (
        command(
            "cognitive-tests-attempt-2",
            [
                PYTHON,
                "-B",
                "-m",
                "pytest",
                "-q",
                "tests/cognitive/test_digest_drift.py",
                "tests/cognitive/test_architecture_review.py",
                "tests/cognitive/test_harness_canary.py",
                "--basetemp",
                str(RUN / "private-runtime/pytest"),
                "--junitxml",
                str(RUN / "junit-attempt-2.xml"),
            ],
        )
        == 0
    )
    before = json.loads((RUN / "protected-before.json").read_text())
    assert before == {name: digest(REPO / name) for name in PROTECTED}
    original = json.loads((RUN / "preimage/digest_reverification.json").read_text())
    current = json.loads((REPO / OWNED[0]).read_text())
    changed = [i for i, (a, b) in enumerate(zip(original["entries"], current["entries"], strict=True)) if a != b]
    assert len(changed) == 1
    assert current["entries"][changed[0]]["path"] == PROTECTED[3]
    assert original["command"] == current["command"]
    patch = subprocess.check_output(["git", "diff", "--binary", "--", *OWNED], cwd=REPO)
    (RUN / "task-only.patch").write_bytes(patch)
    replay = RUN / "private-runtime/reconstruction"
    replay.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(replay)], check=True)
    for name in OWNED:
        target = replay / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((RUN / "preimage" / Path(name).name).read_bytes())
    subprocess.run(["git", "apply", str(RUN / "task-only.patch")], cwd=replay, check=True)
    assert all((replay / name).read_bytes() == (REPO / name).read_bytes() for name in OWNED)
    (RUN / "final-binding.json").write_text(
        json.dumps({name: digest(REPO / name) for name in OWNED + PROTECTED}, indent=2) + "\n"
    )
    (RUN / "scope-verification.json").write_text(
        json.dumps(
            {
                "changed_registry_rows": changed,
                "historical_command_unchanged": True,
                "protected_files_unchanged": len(PROTECTED),
                "patch_reconstructed_byte_identical": len(OWNED),
            },
            indent=2,
        )
        + "\n"
    )
else:
    raise SystemExit("Expected before or after")
