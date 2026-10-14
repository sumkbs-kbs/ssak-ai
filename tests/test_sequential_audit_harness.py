"""IMP-00 계약. 독립 실행 시 --noconftest로 제품 전역 fixture를 읽지 않는다."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sequential_harness", ROOT / "scripts/run_sequential_audit.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke(harness: Any, tmp_path: Path, code: str, name: str = "command", timeout: float = 30) -> dict[str, Any]:
    return harness.run_command([sys.executable, "-c", code], tmp_path / name, timeout=timeout)


def output(tmp_path: Path, name: str = "command") -> str:
    return (tmp_path / name / "stdout.txt").read_text()


@pytest.mark.parametrize(
    "key",
    [
        "AGK_CONFIG_FILE",
        "AGK_ENV_FILE",
        "AGK_PATH_PROJECT_ROOT",
        "AGK_PATH_DATA_DIR",
        "AGK_PATH_MODELS_DIR",
        "AGK_PATH_DOCUMENTS_DIR",
        "AGK_PATH_VECTORS_DIR",
        "AGK_PATH_LOGS_DIR",
        "AGK_PATH_WIKI_DIR",
        "AGK_SEC_PIN_HASH_FILE",
        "AGK_SEC_TOKEN_SECRET_FILE",
    ],
)
def test_missing_setting_fails_before_import(harness: Any, tmp_path: Path, key: str) -> None:
    env = harness.isolated_environment(tmp_path, 12345)
    del env[key]
    with pytest.raises(ValueError, match=key):
        harness.preflight(tmp_path, env)


@pytest.mark.parametrize("change", ["missing-file", "incomplete-paths", "outside-root", "symlink"])
def test_invalid_config_is_fail_closed(harness: Any, tmp_path: Path, change: str) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    env = harness.isolated_environment(root, 12345)
    config = Path(env["AGK_CONFIG_FILE"])
    if change == "missing-file":
        config.unlink()
    else:
        values = json.loads(config.read_text())
        if change == "incomplete-paths":
            del values["paths"]["wiki_dir"]
        elif change == "outside-root":
            values["paths"]["data_dir"] = str(tmp_path / "peer")
        else:
            (root / "escape").symlink_to(tmp_path, target_is_directory=True)
            values["paths"]["data_dir"] = str(root / "escape/peer")
        config.write_text(json.dumps(values))
    with pytest.raises(ValueError):
        harness.preflight(root, env)


def test_parent_environment_and_credentials_are_unchanged(harness: Any, tmp_path: Path) -> None:
    before = dict(os.environ)
    result = invoke(
        harness,
        tmp_path,
        """import json, os, subprocess, sys
from pathlib import Path
from antigravity_k.config import config
root=Path(os.environ["SSAK_AUDIT_ROOT"])
assert config.config_path == root/"config.json"
assert config.paths.project_root == root/"project"
from antigravity_k.engine.model_registry import ModelRegistry
registry=ModelRegistry()
assert registry.list_models() == []
assert all(getattr(config.paths, name+"_dir").is_relative_to(root)
           for name in ("models", "data", "documents", "vectors", "logs", "wiki"))
child=subprocess.check_output([sys.executable,"-c", "from pathlib import Path; print(Path.home())"], text=True)
assert child.strip() == str(root/"home")
assert Path(os.path.expanduser("~")) == root/"home"
assert "OPENAI_API_KEY" not in os.environ
from antigravity_k.api.auth_routes import get_token_service
service=get_token_service()
secret=Path(os.environ["AGK_SEC_TOKEN_SECRET_FILE"])
assert secret.is_file() and secret.stat().st_mode & 0o777 == 0o600
print(json.dumps({"home":str(Path.home()),"child_home":child.strip(),"config":str(config.config_path)}))
""",
    )
    assert result["status"] == "PASS", (result, (tmp_path / "command/stderr.txt").read_text())
    assert dict(os.environ) == before
    assert result["cleanup"]["owned_root_removed"] is True
    assert result["owned_processes_remaining"] == []


def test_parallel_suites_do_not_purge_peer_data(harness: Any, tmp_path: Path) -> None:
    template = """import hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
root=Path(os.environ["SSAK_AUDIT_ROOT"])
sentinel=root/"wiki/sentinel"
sentinel.write_text("peer marker")
sha=hashlib.sha256(sentinel.read_bytes()).hexdigest()
subprocess.run([sys.executable, "-c", "from pathlib import Path; (Path.home()/'child').write_text('owned')"], check=True)
suite=root/"test_owned.py"
suite.write_text("import os, shutil, time\\nfrom pathlib import Path\\ndef test_owned():\\n    root=Path(os.environ['SSAK_AUDIT_ROOT'])\\n    sentinel=root/'wiki/sentinel'\\n    ACTION\\n")
subprocess.run([sys.executable, "-m", "pytest", str(suite), "--noconftest", "-q", "-p", "no:cacheprovider"], check=True, stdout=subprocess.DEVNULL)
print(json.dumps({"root":str(root),"sha_before":sha,"sha_after":hashlib.sha256(sentinel.read_bytes()).hexdigest() if sentinel.exists() else None}))
"""
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(invoke, harness, tmp_path, template.replace("ACTION", "shutil.rmtree(root/'wiki')"), "A")
        b = pool.submit(
            invoke,
            harness,
            tmp_path,
            template.replace("ACTION", "time.sleep(2); assert sentinel.read_text()=='peer marker'"),
            "B",
        )
        ra, rb = a.result(), b.result()
    assert ra["status"] == rb["status"] == "PASS"
    oa, ob = json.loads(output(tmp_path, "A")), json.loads(output(tmp_path, "B"))
    assert oa["root"] != ob["root"]
    assert oa["sha_after"] is None
    assert ob["sha_before"] == ob["sha_after"]
    assert not Path(oa["root"]).exists() and not Path(ob["root"]).exists()


def test_python_personal_store_attempt_is_failure_even_if_caught(harness: Any, tmp_path: Path) -> None:
    # 보호 경로 문자열만 사용한다. 실제 개인 저장소 내용은 읽지 않는다.
    target = str(Path.home() / ".antigravity-k/never-read-audit-sentinel")
    result = invoke(
        harness,
        tmp_path,
        f"""from pathlib import Path
try:
    Path({target!r}).read_text()
except PermissionError:
    pass
""",
    )
    assert result["status"] == "FAIL" and result["reason"] == "ISOLATION_VIOLATION"
    assert result["access_violation_count"] == 1


def test_native_child_and_symlink_escape_are_os_blocked(harness: Any, tmp_path: Path) -> None:
    # native C open은 Python audit hook을 거치지 않으므로 OS 경계를 직접 검사한다.
    personal = str(ROOT / "config.yaml")
    result = invoke(
        harness,
        tmp_path,
        f"""import ctypes, errno, os, subprocess
from pathlib import Path
root=Path(os.environ["SSAK_AUDIT_ROOT"])
lib=ctypes.CDLL(None, use_errno=True)
fd=lib.open({personal.encode()!r}, os.O_RDONLY)
assert fd == -1 and ctypes.get_errno() == errno.EPERM
outside=root.parent/"ssak-should-not-create"
(root/"escape").symlink_to(root.parent, target_is_directory=True)
child=subprocess.run(["/bin/sh", "-c", "printf forbidden > "+str(root/"escape/ssak-should-not-create")], capture_output=True)
assert child.returncode != 0 and not outside.exists()
print("native and symlink denied")
""",
    )
    assert result["status"] == "PASS", (result, (tmp_path / "command/stderr.txt").read_text())


@pytest.mark.parametrize("mode", ["failure", "timeout"])
def test_failed_child_listener_and_grandchild_are_cleaned(harness: Any, tmp_path: Path, mode: str) -> None:
    code = """import json, subprocess, sys, time
child=subprocess.Popen([sys.executable,"-c", "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1], flush=True); time.sleep(60)"], stdout=subprocess.PIPE, text=True)
port=int(child.stdout.readline())
print(json.dumps({"child":child.pid,"port":port}), flush=True)
END
""".replace("END", "raise SystemExit(7)" if mode == "failure" else "time.sleep(60)")
    result = invoke(harness, tmp_path, code, timeout=2 if mode == "timeout" else 30)
    assert result["status"] == "FAIL"
    assert result["owned_processes_remaining"] == []
    value = json.loads(output(tmp_path))
    with socket.socket() as connection:
        connection.settimeout(0.2)
        assert connection.connect_ex(("127.0.0.1", value["port"])) != 0
    assert result["cleanup"]["owned_root_removed"] is True
    if mode == "failure":
        assert result["exit"] == 7
    else:
        assert result["reason"] == "TIMEOUT"


@pytest.mark.parametrize("failure_site", ["stop_group", "remaining_group_pids"])
def test_cleanup_error_retains_terminal_receipt_and_artifacts(
    harness: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_site: str
) -> None:
    original_stop = harness.stop_group

    def denied_cleanup(*args: Any) -> None:
        if failure_site == "stop_group":
            # 실제 소유 프로세스 정리는 수행하되, 검증 오류가 난 경로를 재현한다.
            original_stop(*args)
        raise PermissionError("synthetic cleanup verification denied")

    monkeypatch.setattr(harness, failure_site, denied_cleanup)
    before = dict(os.environ)
    result = invoke(
        harness,
        tmp_path,
        """import os
from pathlib import Path
root=Path(os.environ["SSAK_AUDIT_ROOT"])
(root/"junit.xml").write_text('<testsuites><testsuite tests="1" failures="1" /></testsuites>')
(root/"pytest-outcomes.jsonl").write_text('{"nodeid":"synthetic::negative","outcome":"failed"}\\n')
print("raw negative control output", flush=True)
raise SystemExit(7)
""",
    )
    receipt = json.loads((tmp_path / "command/receipt.json").read_text())
    assert receipt == result
    assert receipt["status"] == "FAIL" and receipt["reason"].startswith("CLEANUP_ERROR:")
    assert "synthetic cleanup verification denied" in receipt["reason"]
    assert receipt["exit"] == 7 and receipt["end"]
    assert receipt["owned_processes_remaining"] is None  # 확인 불가를 빈 PID 목록으로 위장하지 않는다.
    assert receipt["cleanup"]["owned_root_removed"] is True
    assert receipt["cleanup"]["parent_environment_unchanged"] is True
    assert dict(os.environ) == before
    assert "raw negative control output" in output(tmp_path)
    assert (tmp_path / "command/junit.xml").is_file()
    assert json.loads((tmp_path / "command/pytest-outcomes.json").read_text()) == [
        {"nodeid": "synthetic::negative", "outcome": "failed"}
    ]
    assert (tmp_path / "command/manifest-after.json").is_file()


def test_source_movement_is_not_promoted_to_pass(harness: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = harness.source_manifest
    calls = 0

    def moved_manifest() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        value = original()
        if calls >= 2:
            value["sources"]["scripts/synthetic-movement.py"] = "changed"
        return value

    monkeypatch.setattr(harness, "source_manifest", moved_manifest)
    result = invoke(harness, tmp_path, "print(42)")
    assert result["status"] == "INCONCLUSIVE" and result["reason"] == "SOURCE_MOVED"
    assert result["changed_sources"] == ["scripts/synthetic-movement.py"]


def test_kg_validator_runs_only_on_owned_wiki(harness: Any, tmp_path: Path) -> None:
    result = invoke(
        harness,
        tmp_path,
        """import json, os
from pathlib import Path
from antigravity_k.knowledge.wiki import LLMWiki
from antigravity_k.knowledge.wiki_graph import KGBinaryValidator
root=Path(os.environ["SSAK_AUDIT_ROOT"])
wiki=LLMWiki(root/"wiki/test.db")
result=KGBinaryValidator(wiki.db_path).validate()
assert result["OK"] is True
print(json.dumps(result))
""",
    )
    assert result["status"] == "PASS", (result, (tmp_path / "command/stderr.txt").read_text())
    assert json.loads(output(tmp_path))["OK"] is True


def test_actual_cli_retains_failed_assertion_and_junit(tmp_path: Path) -> None:
    fixture = tmp_path / "test_negative.py"
    fixture.write_text("def test_false_completion():\n    assert 1 == 2\n")
    evidence = tmp_path / "negative"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_sequential_audit.py"),
            "pytest",
            "--evidence",
            str(evidence),
            "--timeout",
            "30",
            "--",
            str(fixture),
            "--noconftest",
            "-q",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert process.returncode == 1, process.stderr
    receipt = json.loads((evidence / "receipt.json").read_text())
    assert receipt["status"] == "FAIL" and receipt["exit"] == 1
    assert (evidence / "junit.xml").is_file()
    assert "assert 1 == 2" in (evidence / "stdout.txt").read_text()
    outcomes = json.loads((evidence / "pytest-outcomes.json").read_text())
    assert any(row["outcome"] == "failed" and "test_false_completion" in row["nodeid"] for row in outcomes)
    assert receipt["cleanup"]["owned_root_removed"] is True


def test_auth_and_server_respect_explicit_env_file(harness: Any, tmp_path: Path) -> None:
    result = invoke(
        harness,
        tmp_path,
        """import os
from antigravity_k.api.auth_routes import _limiter
from antigravity_k.api.server import limiter
assert _limiter.app_config.file_values == {}
assert limiter.app_config.file_values == {}
assert os.environ["AGK_ENV_FILE"].endswith("empty.env")
print("explicit env respected")
""",
    )
    assert result["status"] == "PASS", (result, (tmp_path / "command/stderr.txt").read_text())


def test_owned_checkout_does_not_read_or_copy_runtime_stores(harness: Any, tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    (origin / "scripts").mkdir()
    (origin / "scripts/current.py").write_text("print(42)\n")
    (origin / "src/antigravity_k").mkdir(parents=True)
    (origin / "src/antigravity_k/config.yaml").write_text("model: {}\n")
    (origin / "data/wiki").mkdir(parents=True)
    (origin / "data/wiki/private.txt").write_text("must not copy")
    (origin / ".env").write_text("API_KEY=must-not-copy\n")
    (origin / "config.yaml").write_text("private config\n")
    (origin / "scripts/escape").symlink_to(origin / "data/wiki/private.txt")
    safe_evidence = (
        ".omo/evidence/web-search-answer/final-two-run-manifest.json",
        ".omo/evidence/web-search-answer/final-two-run-verification.txt",
        ".omo/evidence/web-search-answer/web-search-answer-fix.md",
        "docs/qa/2026-10-04-sequential-audit/dashboard-responsive-build.log",
        "docs/qa/2026-10-04-sequential-audit/dashboard-responsive-lint.log",
        "docs/qa/2026-10-04-sequential-audit/dashboard-responsive-tests.log",
        "docs/qa/2026-09-16-followup/tests.log",
    )
    for name in safe_evidence:
        target = origin / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("synthetic historical receipt\n")
    (origin / ".gitignore").write_text(".omo/\n*.log\n")
    (origin / "docs/qa/private.log").write_text("do not copy arbitrary ignored data")
    subprocess.run(["git", "init", "-q", str(origin)], check=True)
    subprocess.run(["git", "-C", str(origin), "add", "scripts", "src"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(origin),
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    # 현재 dirty 코드가 HEAD export로 바뀌면 이 검사가 실패한다.
    (origin / "scripts/current.py").write_text("print(47)\n")
    result = harness.owned_checkout(tmp_path / "owned", origin)
    project = tmp_path / "owned/project"
    assert (project / "scripts/current.py").read_text() == "print(47)\n"
    assert not (project / "data").exists()
    assert not (project / "scripts/escape").exists()
    assert (project / ".env").read_text() == ""
    assert (project / "config.yaml").read_text() == "model: {}\n"
    assert result["runtime_stores_copied"] is False
    assert result["release_candidate_certified"] is False
    for name in safe_evidence:
        assert (project / name).read_bytes() == (origin / name).read_bytes()
        assert name in result["copied_sources"]
    assert not (project / "docs/qa/private.log").exists()
    assert "scripts/escape" in result["omitted_paths"]
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project) == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=origin
    )


def test_owned_checkout_import_and_git_mutation_are_isolated(harness: Any, tmp_path: Path) -> None:
    code = """import json, os, subprocess
from pathlib import Path
import antigravity_k
from antigravity_k.knowledge.wiki import LLMWiki
from antigravity_k.knowledge.wiki_graph import KGBinaryValidator
root=Path(os.environ["SSAK_AUDIT_ROOT"])
project=root/"project"
assert Path(antigravity_k.__file__).is_relative_to(project)
assert Path.cwd() == project
assert not (project/"data/wiki_entries").exists()
assert (project/".env").read_text()==""
assert (project/"config.yaml").read_bytes()==(project/"src/antigravity_k/config.yaml").read_bytes()
subprocess.run(["git", "status", "--porcelain=v1", "-uno"], check=True, stdout=subprocess.DEVNULL)
(project/"owned-note.txt").write_text("owned")
subprocess.run(["git","add","owned-note.txt"],check=True)
wiki=LLMWiki(root/"wiki/owned.db")
validation=KGBinaryValidator(wiki.db_path).validate()
assert validation["OK"] is True
print(json.dumps({"package":antigravity_k.__file__,"kg":validation}))
"""
    before = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT)
    result = harness.run_command([sys.executable, "-c", code], tmp_path / "checkout", timeout=60, checkout=True)
    assert result["status"] == "PASS", (result, (tmp_path / "checkout/stderr.txt").read_text())
    assert subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT) == before
    manifest = json.loads((tmp_path / "checkout/checkout-manifest.json").read_text())
    assert manifest["copied_source_count"] > 1000
    assert result["owned_processes_remaining"] == []
    assert result["cleanup"]["owned_root_removed"] is True


def test_owned_checkout_blocks_original_source_access(harness: Any, tmp_path: Path) -> None:
    result = harness.run_command(
        [sys.executable, "-c", f"from pathlib import Path; Path({str(ROOT / 'README.md')!r}).read_text()"],
        tmp_path / "origin-denied",
        timeout=60,
        checkout=True,
    )
    assert result["status"] == "FAIL" and result["reason"] == "ISOLATION_VIOLATION"


def test_owned_boundary_survives_nested_fixture_clearing_environment(harness: Any, tmp_path: Path) -> None:
    code = """import os
from pathlib import Path
from unittest.mock import patch
root=Path(os.environ["SSAK_AUDIT_ROOT"])
with patch.dict(os.environ, {}, clear=True):
    import dotenv
    assert dotenv is not None
    try:
        Path(ORIGINAL).read_text()
    except PermissionError:
        pass
""".replace("ORIGINAL", repr(str(ROOT / "README.md")))
    result = harness.run_command([sys.executable, "-c", code], tmp_path / "nested-env", timeout=60, checkout=True)
    assert result["status"] == "FAIL" and result["reason"] == "ISOLATION_VIOLATION"
    rows = json.loads((tmp_path / "nested-env/access-violations.json").read_text())
    assert [row["path"] for row in rows] == [str(ROOT / "README.md")]


def test_cli_help_is_usable() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_sequential_audit.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "--evidence" in result.stdout and "--timeout" in result.stdout


@pytest.mark.parametrize("layout", ["file", "directory"])
def test_owned_os_boundary_denies_native_origin_git_reads(
    harness: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    home = tmp_path / "personal-home"
    origin = home / "origin"
    owned = tmp_path / "owned"
    origin.mkdir(parents=True)
    owned.mkdir()
    git_path = origin / ".git"
    if layout == "directory":
        git_path.mkdir()
        target = git_path / "config"
    else:
        target = git_path
    target.write_text("synthetic-origin-git-marker\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(harness, "ROOT", origin)
    environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "--quiet", str(owned)], env=environment, check=True, timeout=10)
    profile = harness.sandbox_profile(owned, checkout=True)
    denied = subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", profile, "/bin/cat", str(target)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert denied.returncode != 0
    assert "synthetic-origin-git-marker" not in denied.stdout
    local = subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", profile, "git", "-C", str(owned), "rev-parse", "--git-dir"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert local.returncode == 0, local.stderr
    assert local.stdout.strip() == ".git"


def test_owned_checkout_omits_untracked_private_evidence(
    harness: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    packaged = origin / "src/antigravity_k/config.yaml"
    packaged.parent.mkdir(parents=True)
    packaged.write_text("paths: {}\n")
    (origin / "README.md").write_text("Owned fixture source\n")
    environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "--quiet", str(origin)], env=environment, check=True, timeout=10)
    subprocess.run(["git", "add", "README.md", "src"], cwd=origin, env=environment, check=True, timeout=10)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=HarnessFixture",
            "-c",
            "user.email=harness@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=origin,
        env=environment,
        check=True,
        timeout=10,
    )
    late = origin / "src/antigravity_k/late_module.py"
    late.write_text("VALUE = 42\n")
    private = origin / "docs/qa/private-runtime/auth-private/pin.txt"
    private.parent.mkdir(parents=True)
    private.write_text("synthetic-private-marker\n")
    public = origin / "docs/qa/public-result.json"
    public.write_text('{"fixture": true}\n')
    monkeypatch.setattr(harness, "QA_RECEIPTS", ("docs/qa/public-result.json",))
    owned = tmp_path / "owned"
    owned.mkdir()
    result = harness.owned_checkout(owned, origin)
    assert not (owned / "project/docs/qa/private-runtime").exists()
    assert (owned / "project/src/antigravity_k/late_module.py").read_bytes() == late.read_bytes()
    assert (owned / "project/docs/qa/public-result.json").read_bytes() == public.read_bytes()
    assert "docs/qa/private-runtime/auth-private/pin.txt" not in result["copied_sources"]
