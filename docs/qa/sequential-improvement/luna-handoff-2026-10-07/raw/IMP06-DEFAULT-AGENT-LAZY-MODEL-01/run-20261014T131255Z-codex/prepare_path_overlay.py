import hashlib,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
for label,repo in (("clean",Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")),("root",Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai"))):
    source=(repo/"tests/test_tool_loop.py").read_text()
    out=BASE/(label+"-fixture-overlay.py")
    target=str(BASE/("path-overlay-"+label)/"project_root")
    overlay=source.replace("/tmp/test",target)
    assert overlay.replace(target,"/tmp/test")==source
    out.write_text(overlay)
    (BASE/(label+"-overlay-binding.json")).write_text(json.dumps({"original_source_sha":hashlib.sha256(source.encode()).hexdigest(),"overlay_sha":hashlib.sha256(overlay.encode()).hexdigest(),"only_change":"/tmp/test substituted in fixture inputs and expected metadata with owned workspace","cases":["TestToolLoopEnginePostLoopChecks::test_quality_gate_revision_replaces_output_and_outcome","TestToolLoopEnginePostLoopChecks::test_event_bus_published"]},indent=2)+"\n")
print("Two owned fixture/expected-path overlays prepared")

