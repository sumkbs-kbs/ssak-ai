---
title: QA06 Ollama continuation HTTP 500 diagnosis
tags: [qa, core, ollama, required-tools]
date: 2026-10-04
---

Result: the same QA06 now passes in the root's actual production browser and in separate actual-runtime replays. The previously observed upstream Qwen tool-parser failure is retained as a known intermittent failure. No additional product patch was made, and this result does not establish a permanent fix or a complete upstream root cause.

The failed root request was: `QA-06. 이 프로젝트의 qa-source.txt를 read_file 도구로 한 번만 실제로 읽으세요. QA_MARKER와 QA_VALUE를 {"marker":"값","value":정수} JSON 하나로 답하세요. 파일 변경과 저장은 하지 마세요.` The actual file read executed once, followed by `[API Error for qwen3.8] HTTP Error 500`. Root preserved `read-file-contract-final-failed.ax.txt` and the failed screenshot; `live-contract-final.log` retains the provider traceback and two egress retries.

The existing Ollama server log at **13:02:45, 13:02:46 and 13:02:49 KST** records `qwen3coder.go` / `qwen35.go` tool parsing failures with `error=EOF`, each paired with HTTP 500 from `/api/chat`. Nine relevant parser/status lines are preserved in `required-tool-ollama-upstream-failure.txt`. No model crash or OOM appears in that inspected excerpt. The provider's failing HTTP body and generated tokens were not preserved by the original request, so the exact malformed generation cannot be recovered or attributed to a particular prompt segment.

The actual call path was checked: ToolLoop sends the combined `prompt_str` to ModelManager; it does **not** supply `raw_messages` on this path. Ollama receives a system thinking directive plus a single user message containing that prompt. Consequently, the fact that `shaped_messages` does not include the final contract directive is not evidence for this failure on the current production path. The final combined prompt includes `[REQUIRED TOOL CONTRACT SATISFIED]` and the instruction to provide the answer without more calls.

`required_tool_ollama_replay.py` uses actual OrchestratorAgent, ToolLoopEngine, ModelManager, Ollama provider/network, ToolExecutor/ReadFileTool and SQLite with a disposable synthetic project. A process-local wrapper observes request bodies/statuses while calling the real provider HTTP function; it supplies no model response. No bearer header is saved. Both worker executions used the same exact Korean request and the existing live QA configuration. The first replay is retained in `required-tool-ollama-before.json` / `.txt`, and the final checked driver replay in `required-tool-ollama-replay.json` / `.txt`.

Both executions issued **HTTP 200 for the required-read generation and HTTP 200 for its answer continuation**, invoked `read_file` exactly once, returned exactly `{"marker":"blue","value":47}`, recorded task `done`, preserved the source bytes, and removed the temporary root. The observed first request carries only the `read_file` schema; the continuation removes tool schemas and contains the contract-satisfied directive. This supports compatibility of the current schema/continuation contract but does not prove that probabilistic Qwen generation can never hit the upstream parser failure.

Root also reran the exact question through the new production UI and observed one actual read and the same JSON. Its task `direct_7596151de58f`, two checkpoints and seven events were immediately preserved through a read-only SQLite connection in `required-tool-ollama-root-replay.json`. Root's final UI/raw receipts are `read-file-contract-final.*`.

The replay driver passes scoped Ruff/formatting, the repository's basedpyright error gate, and the new-file strict-rule check. No shared server/model restart, model setting change, dependency installation, private data mutation, persistent listener, temporary source instrumentation, commit or push was performed by this lane. Earlier mandatory-tool and negative-tool guards remain unchanged by this follow-up. Root owns the existing production server lifecycle and the remaining citation work.
