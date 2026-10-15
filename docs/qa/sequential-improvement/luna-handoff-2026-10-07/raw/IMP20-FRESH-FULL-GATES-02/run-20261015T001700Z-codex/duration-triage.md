# Full Python duration observation

The single frozen run remained in its Python phase while owned pytest directory timestamps progressed through R19 A1, A2 and A3 at approximately129-second intervals. A bounded one-second native stack sample was collected. These observations are progress evidence, not test acceptance.

A read-only source investigation found that `tests/cognitive/test_live_pilot.py` runs36 real local fixture trials in each of those three cases: six FINAL tasks, three repetitions and two arms. They use ScriptedModelPort. The three cases therefore perform108 local trials; no live model inference belongs to this path.

The per-trial seed path calls `is_committed()` for corpus records; the store reparses its growing committed manifest. Context construction also reads and validates project records, including YAML bodies. Repeated parsing/object construction can explain CPU cost, but the native sample does not establish a precise Python hotspot. The recursive digest here is limited to the test-owned arm workspace. It does not traverse the checkout's node_modules, venv or raw evidence tree.

Relevant sources in candidate7360c785:

- `tests/cognitive/test_live_pilot.py:444`
- `src/antigravity_k/engine/cognitive/live_pilot.py:803`
- `src/antigravity_k/engine/cognitive/live_trial_execution.py:77`
- `src/antigravity_k/engine/cognitive/live_trial_adapter.py:119`
- `src/antigravity_k/engine/cognitive/store.py:356`
- `src/antigravity_k/engine/cognitive/context.py:193`

R19 A4 is a cheaper stub case; subsequent R18 train/validation cases can add time. No whole-suite completion estimate is derived from the three R19 cases. No implementation or test was changed, rerun or interrupted for this investigation. Performance optimization is a separate candidate after the frozen run, if warranted by its final evidence.
