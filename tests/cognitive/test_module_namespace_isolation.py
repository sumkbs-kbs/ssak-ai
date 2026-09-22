"""T14 회귀가 찾은 오염원의 회귀 시험 — **import 시점에 namespace 를 비우지 않는다**.

전량 회귀에서 `authority.AuthorityProfile` 이 두 객체가 되자 유효한 grant 가 DEFER 로 떨어졌다. 원인은
`tests/test_flush_budget_contract.py` 가 import 시점에 `sys.modules` 의 `antigravity_k.*` 를 전부 지운 것이었다
(미러 리허설에서 다른 트리의 바이트를 검사하려던 의도). 이 시험은 세 가지를 고정한다.

1. 그 purge 가 **미러 override(`NX10_FLUSH_TREE`)에서만** 일어난다 — 승격된 위치에서는 namespace 를 건드리지 않는다.
2. override 경로는 그대로 살아 있다(리허설의 이빨을 죽이지 않았다).
3. 수집 대상 시험 파일 어디에도 **감싸이지 않은** import 시점 purge 가 없다(`scripts/audit_test_namespace_purge.py`).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "audit_test_namespace_purge.py"
CONTRACT_TEST = REPO_ROOT / "tests" / "test_flush_budget_contract.py"

_PROBE = """
import importlib.util
import sys
import types

import antigravity_k.engine.cognitive.authority as authority

sentinel = types.ModuleType("antigravity_k.namespace_probe")
sys.modules["antigravity_k.namespace_probe"] = sentinel

spec = importlib.util.spec_from_file_location("nx10_flush_contract_probe", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

print(
    int(sys.modules.get("antigravity_k.engine.cognitive.authority") is authority),
    int(sys.modules.get("antigravity_k.namespace_probe") is sentinel),
)
"""


def load_audit() -> ModuleType:
    spec = importlib.util.spec_from_file_location("audit_test_namespace_purge", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_test_namespace_purge"] = module
    spec.loader.exec_module(module)
    return module


def probe_import(*, override: Path | None) -> tuple[bool, bool]:
    """별도 인터프리터에서 승격된 계약 시험을 import 하며 namespace 가 유지되는지 본다."""

    env = dict(os.environ)
    env.pop("NX10_FLUSH_TREE", None)
    if override is not None:
        env["NX10_FLUSH_TREE"] = str(override)
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, str(CONTRACT_TEST)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )
    module_kept, sentinel_kept = result.stdout.split()
    return module_kept == "1", sentinel_kept == "1"


def test_promoted_contract_test_keeps_the_namespace_without_override() -> None:
    """승격된 위치(`tests/`)에서는 이미 import 된 module 을 그대로 써야 한다 — 새 객체를 만들지 않는다."""

    assert CONTRACT_TEST.is_file(), "승격된 계약 시험이 본 트리에 있어야 한다"
    module_kept, sentinel_kept = probe_import(override=None)
    assert module_kept is True, "import 시점에 `antigravity_k.*` 가 지워졌다(판정이 순서에 따라 흔들린다)"
    assert sentinel_kept is True, "namespace 의 다른 module 까지 사라졌다"


def test_mirror_override_still_purges_the_namespace(tmp_path: Path) -> None:
    """미러 리허설의 이빨은 살아 있어야 한다 — override 를 주면 옛 바이트를 버리고 새 트리를 읽는다."""

    module_kept, sentinel_kept = probe_import(override=tmp_path)
    assert module_kept is False, "override 를 줬는데 이전 임포트가 남아 있다(옛 바이트를 검사할 위험)"
    assert sentinel_kept is False, "override 경로의 purge 가 사라졌다"


def test_no_collected_test_purges_the_namespace_at_import_time() -> None:
    audit = load_audit()
    violations = audit.scan_paths()
    details = [f"{v.file}:{v.line} {v.expression}" for v in violations]
    assert violations == (), f"감싸이지 않은 import 시점 namespace purge 가 있다: {details}"


def test_audit_detects_an_unguarded_purge_and_passes_a_guarded_one() -> None:
    """감사가 실제로 무는지 — 가짜 source 로 확인한다(조용히 무력해질 수 없다)."""

    audit = load_audit()
    unguarded = (
        "import os\n"
        "import sys\n"
        "for name in [key for key in list(sys.modules) if key.startswith('antigravity_k')]:\n"
        "    del sys.modules[name]\n"
    )
    violations = audit.scan_source(unguarded, file="sample.py")
    assert [v.kind for v in violations] == ["unguarded_purge"]
    assert [v.line for v in violations] == [4]  # 삭제가 실제로 일어나는 줄을 가리킨다

    # 문장 자체가 purge 인 형태도 문다(`del`/`pop`/`clear`).
    assert [v.line for v in audit.scan_source("del sys.modules['x']\n", file="sample.py")] == [1]
    assert [v.line for v in audit.scan_source("sys.modules.pop('x', None)\n", file="sample.py")] == [1]
    assert [v.line for v in audit.scan_source("sys.modules.clear()\n", file="sample.py")] == [1]

    guarded = (
        "import os\n"
        "import sys\n"
        "if os.environ.get('NX10_SAMPLE_TREE'):\n"
        "    for name in [key for key in list(sys.modules) if key.startswith('antigravity_k')]:\n"
        "        del sys.modules[name]\n"
    )
    assert audit.scan_source(guarded, file="sample.py") == ()

    # 경계: 함수 본문 purge 는 수집 단계가 아니므로 위반이 아니다(범위를 문서와 일치시킨다).
    in_function = "import sys\n\ndef reset():\n    sys.modules.pop('antigravity_k', None)\n"
    assert audit.scan_source(in_function, file="sample.py") == ()

    # namespace 는 가리지 않는다 — comprehension 조건을 평가하지 않으므로 보수적으로 위반으로 본다.
    # (수집 단계에서 어느 namespace 든 지우면 뒤따르는 시험 파일의 import 결과가 달라진다.)
    other = (
        "import sys\n"
        "for name in [key for key in list(sys.modules) if key.startswith('other')]:\n"
        "    del sys.modules[name]\n"
    )
    assert [v.line for v in audit.scan_source(other, file="sample.py")] == [3]


def test_audit_reports_clean_tree_via_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    audit = load_audit()
    output = tmp_path / "namespace-audit.json"
    exit_code = audit.main(["--json", str(output)])
    captured = capsys.readouterr()
    assert exit_code == 0, captured.out
    assert "namespace purge 없음" in captured.out
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["count"] == 0
    assert payload["violations"] == []
