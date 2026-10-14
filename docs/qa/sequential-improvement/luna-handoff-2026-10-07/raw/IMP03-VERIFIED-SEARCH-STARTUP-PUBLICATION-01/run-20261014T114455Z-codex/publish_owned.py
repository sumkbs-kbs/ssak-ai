from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
WORKTREE = Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
RUN = Path(__file__).resolve().parent
run_paths = [
    "/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP07-RAG-REAL-RETRIEVAL-01/run-20261014T075920Z-6443cb2d",
    "/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e",
    "/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-GBRAIN-STORAGE-ROOT-01/run-20261014T092714Z-d506f8f5",
    "/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-STARTUP-STORAGE-ROOT-CLOSURE-01/run-20261014T093201Z-cd1a16ca",
    "/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-STARTUP-STORAGE-ROOT-CURRENT-TREE-01/run-20261014T093806Z-a22b8954",
    "/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-LIFESPAN-AGENCY-ROOT-01/run-20261014T094816Z-aea9f054",
    "/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-LIFESPAN-AGENCY-ROOT-CURRENT-TREE-01/run-20261014T095316Z-24e16a5c"
]
RUNS = [Path(value) for value in run_paths] + [RUN]
DOCS = Path("docs/qa/sequential-improvement/luna-handoff-2026-10-07")
MANIFEST = RUN / "publication-manifest.json"
LIST = RUN / "publication-commit-paths.txt"
SKIP_PARTS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv",
    "state", "pytest-temp", "isolated", "reconstruction",
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    assert not MANIFEST.exists()
    credentials: list[bytes] = []
    for private in Path(run_paths[1]).rglob("auth-private"):
        secret = private / "token-secret"
        if secret.is_file():
            credentials.append(secret.read_bytes().strip())
        login = private / "login.response.bin"
        if login.is_file():
            token = json.loads(login.read_bytes()).get("token")
            if isinstance(token, str):
                credentials.append(token.encode())
    assert subprocess.check_output(["git", "-C", str(WORKTREE), "rev-parse", "HEAD"]).decode().strip() == "e3ef83547b70a4856ce196ef6c69fd4f4bc715f1"
    before_tasks = json.loads((WORKTREE / DOCS / "tasks.json").read_text())
    after_tasks = json.loads((ROOT / DOCS / "tasks.json").read_text())
    assert {k: v for k, v in before_tasks.items() if k != "current_snapshot"} == {k: v for k, v in after_tasks.items() if k != "current_snapshot"}
    assert (WORKTREE / DOCS / "STATUS.md").read_text().split("## 역사 스냅샷", 1)[1] == (ROOT / DOCS / "STATUS.md").read_text().split("## 역사 스냅샷", 1)[1]
    staged = subprocess.check_output(["git", "-C", str(ROOT), "diff", "--cached", "--binary"])
    assert digest(staged) == "84297d5d47940af4560187d6b9f531b3b1eed5a7fa6cd1dca20c4da48fddab6f"
    for row in after_tasks["current_snapshot"]["scoped_results"]:
        for key in ("review", "result"):
            ref = row.get(key)
            if isinstance(ref, str) and ref.startswith("docs/"):
                assert (ROOT / ref).is_file(), ref
    assert after_tasks["current_snapshot"]["next_task"] == "IMP-07-PROJECT-MEMORY-API-PURGE-01"
    items: list[dict[str, object]] = []
    omitted: list[dict[str, str]] = []
    for run in RUNS:
        for path in sorted(run.rglob("*")):
            if not path.is_file() or path in {MANIFEST, LIST}:
                continue
            local = path.relative_to(run)
            reason = None
            if path.is_symlink():
                reason = "local_symlink"
            elif SKIP_PARTS.intersection(local.parts) or any("tmp" in part or "cache" in part or part.startswith("persist-") for part in local.parts):
                reason = "runtime_cache_or_reconstruction_preserved_locally"
            elif "auth-private" in local.parts or ( "live-once" in local.parts and len(local.parts) > local.parts.index("live-once") + 2) or "parent-preservation-before" in path.name or "token_secret" in path.name or "auth_hash" in path.name or path.suffix in {".db", ".sqlite", ".sqlite3"}:
                reason = "private_auth_or_runtime_database"
            name = path.relative_to(ROOT).as_posix()
            if reason is None and any(part.startswith(".") for part in local.parts):
                reason = "hidden_local_runtime_cache"
            if reason is None and subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", name], check=False).returncode == 0:
                reason = "gitignored"
            if reason:
                omitted.append({"path": name, "reason": reason})
                continue
            assert not (WORKTREE / name).exists(), name
            raw = path.read_bytes()
            assert b"-----BEGIN " + b"PRIVATE KEY-----" not in raw, name
            assert not any(value and value in raw for value in credentials), name
            items.append({"path": name, "bytes": len(raw), "sha256": digest(raw)})
    for name in (DOCS / "STATUS.md", DOCS / "tasks.json"):
        raw = (ROOT / name).read_bytes()
        items.append({"path": name.as_posix(), "bytes": len(raw), "sha256": digest(raw)})
    document = {
        "scope": "Verified scoped real RAG, startup/auth observations, storage and agency fixes; original failures and old ledgers preserved",
        "feature_commit": "e3ef83547b70a4856ce196ef6c69fd4f4bc715f1",
        "files": items,
        "omitted_local_files": omitted,
        "omitted_files_preserved_locally": True,
        "historical_tasks_and_status_equal": True,
        "preserved_staged_sha256": digest(staged),
    }
    with MANIFEST.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    names = [str(item["path"]) for item in items] + [MANIFEST.relative_to(ROOT).as_posix()]
    for name in names:
        destination = WORKTREE / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    with LIST.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(names) + "\n")
    print(json.dumps({"published_files": len(names), "omitted": len(omitted), "legacy_preserved": True}))


if __name__ == "__main__":
    main()

