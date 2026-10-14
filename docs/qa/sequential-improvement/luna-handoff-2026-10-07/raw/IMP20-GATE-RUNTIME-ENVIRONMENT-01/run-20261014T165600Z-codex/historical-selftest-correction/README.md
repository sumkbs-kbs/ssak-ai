# Isolated historical artifact correction

The old diagnostic worktree's soak control selftest appended two 2026-10-14 cancellation receipts to its tracked historical `docs/qa/2026-09-16-followup/nx10/soak-exit.txt`. These refer to owned temporary selftest processes, not the historical soak. The complete modified file is retained separately before restoring only those appended lines to the committed preimage. The primary ROOT historical artifact is not edited.
