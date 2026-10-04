# Independent goal-completion review — 2026-09-27

Reviewer: final_goal (read-only source reviewer, independent of implementation). Reviewed repository `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`, full HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`. **Scoped verdict: FAIL** for completion of R05–R07/R11–R14/R17–R19 as integrated SSAK-AI behavior. This is not a statement that every producer implementation fails. No ops/live efficacy PASS is claimed.

Source was clean for reviewed tracked files at initial inspection; repository has pre-existing untracked artifacts and a dirty vault_data submodule. No source edits, whole-suite rerun, external provider call, or external effect performed. Graph discovery was used first; graph returned no store/runtime methods for some narrowed queries, so exact source inspection followed. Prior reports and current-remediation independent-review checklist distinguish self-review/fixture success from release GO; their narrow disclaimers are appropriate.

## Confirmed actionable findings

### G1 — P1: provider Context drops mandatory constraints and silently truncates required content (R05/R06/R14)

`src/antigravity_k/engine/cognitive/brain.py:542–551,596–633`: `_snippet_from_record` slices the first matching field to 400 chars, without signaling truncation; `render_context_for_brain` iterates only goal/L1/L3 and never L0 constraints or L2 history. A COMPLETE package containing required L0 content can become a provider-ready wire with that content absent. A material goal condition after character 400 is also silently dropped. Additionally the local `used` count covers entries only, excluding the final wire metadata, prompt/schema/repair budget, and uses floor character division; R06 serialized package accounting does not close this later renderer boundary.

Observed isolated real-renderer reproduction (`goal-repro.py`, `goal-repro.txt`, exit 0):
- L0 required record omitted: `ready=true`, `required_id_in_wire=false`, `omitted=[]`.
- Required goal tail omitted: `ready=true`, `tail_in_wire=false`, `omitted=[]`.

Fix acceptance: preserve every mandatory constraint and complete required content (or fail closed with explicit missing IDs); render L2 selected history when required; budget the actual complete request serialization, including overhead. Do not make Body decide which part of a required constraint is semantically expendable.

### G2 — P1: structured Brain output and request feedback do not traverse the runtime boundary (R07/R14)

`src/antigravity_k/engine/cognitive_surface.py:190–196`: `StructuredSurfaceBrainPort.think` maps a successful BrainJudgment to its ID/detail with `delta=None`, omitting its requests and updated plan. The class has no rethink method. This real adapter therefore cannot produce material runtime THINK or drive the documented request→feedback→targeted rethink loop; the runtime stops for no delta.

`src/antigravity_k/engine/cognitive/runtime.py:443–456,482–487`: runtime builds useful `RequestFeedback` fields (disposition, executed, detail, receipt_ref), but sends only the original request IDs to `RethinkPort`. It does not persist those feedback objects before invoking the port, and the port receives no resolver or context refresh. A consumer cannot learn whether identical request IDs were allowed, denied, successful, or returned new evidence from those arguments alone.

Evidence level: direct source/call-boundary inspection, not a live provider test. Reproduction recipe: return a valid BrainJudgment with material change and a bounded request through StructuredSurfaceBrainPort; inspect ThinkOutcome requests/delta. For feedback, record RethinkPort kwargs for same request ID under ALLOW and DENY: no disposition/receipt/detail arrives. Fix acceptance: real typed judgment/request/plan mapping plus typed feedback or committed, resolvable feedback IDs, with actual provider rethink consuming new evidence and denial reasons.

### G3 — P1: "correct" live trial fails and repeated trials contaminate one another (R18/R19)

`src/antigravity_k/engine/cognitive/live_trial_adapter.py:212–214,455–459`; `src/antigravity_k/engine/growth_fixture_tools.py:89–93`: trial target is just `<arm>/<task_id>.txt`, shared by all repetitions; fixture executor appends a newline, while success compares whole file to newline-free `task.append_content`.

Observed with real executor/storage and ScriptedModelPort(correct):
- Trial 0: `success=false`, written `PT-01 appended\n`, expected `PT-01 appended`, episode `COMPLETED`.
- Trial 1: `success=false`, written two appended lines, expected one newline-free string, episode `COMPLETED`.

This corrupts every registered score, even before LLM variability; a whitespace-only fix leaves repetition contamination intact. Fix acceptance: isolate each trial effect target/state or score a precisely registered per-trial delta; score actual receipt/output under the tool's documented format. Prove a correct choice succeeds in two independent repetitions and an incorrect choice remains failure.

### G4 — P1: live TRAIN→policy→future-choice path is marker-only and lacks durable experience (R11/R13/R18)

`live_trial_adapter.py:341–461` builds context with **Fresh limits for both arms**, does not pass built content to ModelPort (passes raw GrowthTask, which also contains expected append answer), ignores `choice.expand_missing`, and installs no experience ledger or record sink in the runtime. `_policy_for` changes a version string; the only durable promoted-policy effect is a JSON marker file. `run_train_validation:299–336` counts success/failure and promotes a predetermined candidate version, without deriving a candidate from selected TRAIN experience or validating an actual changed selector. R13's separate growth demo selector trace does not fix this live path.

Observed after two real trial executions: canonical store entity types are only `Evidence`, `Goal`, `Project`; no committed ContextPackage, judgment, action outcome, operational record, selection, Experience, validation or policy trace is present. This is a real-storage observation, not a claim based on absent graph edges.

Fix acceptance: model input is the actual Context plus allowed task instructions (hold evaluator answer outside the provider payload); persist authentic operational/selected experience; derive and validate allowed operating knobs from TRAIN records; apply validated knobs in the real FINAL selector; record independently observed shadow/actual IDs and pin/version lineage. Do not fix by concatenating expected refs or creating marker-only "learning".

### G5 — P2: auto-formed Experience core omits required outcome/governance lineage (R11/R12)

`runtime.py:789–808` auto-forms selected Experience with only context_ref, judgment_ref and action_ref. Although `form_experience_core` supports decision_ref/observation_refs/evidence_refs, this caller never supplies them, including for observed episodes. Noncanonical shorthand refs are discarded. This can produce an apparently reusable core without traceable Governance/Outcome/Reality Feedback required by C06. Core creation alone is not a durable full episode story.

Evidence level: source only. Fix acceptance: build core only from committed canonical episode records with explicit nonexecution/pending distinctions, populate the actual governance/observation/evidence links, and assert those links resolve after restart. Preserve UNKNOWN decision quality when no Primary/Human assessment exists; do not add a Body semantic evaluator.

### G6 — completion limit: public registered-live entry has no real provider path (R19)

`scripts/benchmark_cognitive_growth.py:146–202`: without SSAK_LIVE_SCRIPTED=1 returns NOT_RUN; with it constructs only ScriptedModelPort. No real-provider result was produced by this audit. This is honestly documented in prior reports but means R18/R19 cannot be called a completed live efficacy experiment. A provider-independent fixture contract is useful and distinct from real model validation.

## Scope matrix

| Cards | Verdict for reviewed scope |
|---|---|
| R05/R06 | FAIL integrated provider-boundary mandatory content/budget, G1; not a blanket rejection of ContextBuilder unit behavior |
| R07 | FAIL real feedback consumer contract, G2 |
| R11 | FAIL live durability/full core lineage, G4/G5 |
| R12 | Source design preserves explicit decision assessment/UNKNOWN; no independent full PASS claimed |
| R13 | Fixture selector observation is narrower than live validated policy consumption; FAIL live integration, G4 |
| R14 | FAIL required Context and real structured runtime integration, G1/G2 |
| R17 | Ledger/schema producer not fully re-audited; no newly reproduced schema defect; downstream scores invalidated by G3 |
| R18/R19 | FAIL real trial semantics and learning consumption, G3/G4; real-provider efficacy NOT_RUN, G6 |

## Reproduction and provenance

Exact successful command from repository root:

```sh
PYTHONPATH=.:src .venv/bin/python /Users/mr.k/Documents/Codex/2026-09-22/referenced-chatgpt-conversation-this-is-an/work/finalize-2026-09-27/goal-repro.py
```

First attempt without PYTHONPATH failed importing tests fixture helpers; it was an environment import issue, not product behavior. Successful rerun exit 0 exercised actual renderer, CanonicalStore and ToolExecutor with only a scripted model. Isolated TemporaryDirectory removed its files. Raw output is in `goal-repro.txt`; journal is `goal-debug-journal.md`. No whole suite was run (QA owner handles it).

SHA-256 at reviewed bytes:

```text
e6af5eb9b97e189b0d046fa19e48ec047187bc47124acee7ecd0abea0dc993cb  cognitive/brain.py
4d9bcd242cefa644d0aa50efc1a9ea5f6a3f5fbfc7d8fa520e04f8c690890f83  cognitive/runtime.py
31c6373ea64a9eb029b51bc426734a8432254bcdb382ef06df03b948bed1c022  cognitive/live_trial_adapter.py
08ec7fb4e9a091e0da4ef1a834d2a4aa1f2a11999f9c5b4cd5ad4df0992f1f44  cognitive/live_pilot.py
28e234993067f8f8a64d0ee63a5a2b928b55ae1e75390eb1d2e755c7562fbb50  cognitive/context.py
7190d690d3a336653aedc82b9463c632137422c99078c80301dd874acd94c55d  cognitive/learning.py
4a502bf478f5a0e024a76a2fca785b884212efd71b7c0200918765afc5299f3e  cognitive/growth.py
b63cfb53c2e074ac51b688996a85567ab291b98fb30e591733c7c7d828691e4b  cognitive_surface.py
911b95cf4b2eddf02363caaf791bfab37a450a5a8e5f0578d292a0b362e97de6  AGENT_HANDOFF.md
8055dcebb2de2e940a5ebe622daf7e9c94209b0a4f0bf0672871b58bd40e7c07  IMPLEMENTATION_CONTRACTS.md
```

Source paths above are relative to `src/antigravity_k/engine/`; specification hashes refer to `outputs/SSAK_AI_REVIEW_2026-09-26/` in the review workspace. Any later parent fixes require a new scoped rerun; this verdict applies only to the pinned bytes.
