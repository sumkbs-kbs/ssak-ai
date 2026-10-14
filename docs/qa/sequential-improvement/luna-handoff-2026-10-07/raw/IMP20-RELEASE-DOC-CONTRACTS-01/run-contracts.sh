#!/bin/sh
set -u
candidate=/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai
task_evidence=/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-RELEASE-DOC-CONTRACTS-01
task_run="$task_evidence/$1"
mkdir "$task_run" || exit 2
cd "$candidate" || exit 2
task_runtime="$candidate/.omo/evidence/raw/IMP20-RELEASE-DOC-CONTRACTS-01/runtime/$1"
mkdir -p "$task_runtime"
export AGK_PATH_DATA_DIR="$task_runtime/data"
export AGK_PATH_DOCUMENTS_DIR="$task_runtime/documents"
export AGK_PATH_VECTORS_DIR="$task_runtime/vectors"
export AGK_PATH_LOGS_DIR="$task_runtime/logs"
export AGK_PATH_WIKI_DIR="$task_runtime/wiki"
export AGK_PATH_MODELS_DIR="$task_runtime/models"
export AGK_HOOK_VAULT_DIR="$task_runtime/vault"
export PYTHONPATH=src:.
git rev-parse HEAD > "$task_run/head-before.txt"
while IFS= read -r task_source; do
    shasum -a 256 "$task_source"
done < "$task_evidence/bound-paths.txt" > "$task_run/source-before.sha256"
.venv/bin/python -m pytest -q -rs tests/test_nx07_doc_consistency.py tests/test_cr14_fence_movement_detection.py tests/test_cr14_fingerprint_scope_contract.py tests/test_docs_toolchain_contract.py tests/test_qwen_repo_prompt_budget.py tests/test_cr12_docs_alignment.py --junitxml="$task_run/junit.xml" > "$task_run/pytest.log" 2>&1
task_rc=$?
echo "$task_rc" > "$task_run/exit-code.txt"
while IFS= read -r task_source; do
    shasum -a 256 "$task_source"
done < "$task_evidence/bound-paths.txt" > "$task_run/source-after.sha256"
git rev-parse HEAD > "$task_run/head-after.txt"
if cmp -s "$task_run/source-before.sha256" "$task_run/source-after.sha256"; then
    echo SOURCE_STABLE > "$task_run/source-stability.txt"
else
    echo SOURCE_MOVED > "$task_run/source-stability.txt"
    task_rc=3
fi
tail -15 "$task_run/pytest.log"
exit "$task_rc"
