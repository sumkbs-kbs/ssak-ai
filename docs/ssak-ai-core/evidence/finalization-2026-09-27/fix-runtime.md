# Runtime feedback and active-plan lineage

Baseline HEAD: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382; source changes are uncommitted and require final manifest binding.

The prior runtime forwarded request IDs without their dispositions, reasons, or receipt references. It could then execute the original final action even when no rethink port existed or the expansion budget prevented Primary from integrating those results. The regression run produced three failures: missing typed feedback, and actual final dispatch under each missing-rethink/budget-zero condition.

Runtime now forwards typed RequestFeedback through RethinkPort. When integration cannot happen it returns DEFERRED or STOPPED_BUDGET without final dispatch. The current plan is copied into EpisodeRequest after initial think and each changed rethought plan, ensuring Experience uses the actual executed plan rather than the original request. EpisodePlan carries optional decision, governance, outcome, observation and evidence lineage; form_experience_core preserves these fields.

When an actual synchronous observation has no existing canonical observation reference, runtime publishes an Observation before reconciling the receipt. Canonical storage failure propagates before projection settlement. Caller-supplied canonical observation references are preserved. This does not invent an observation for dispatch or a missing readback.

Immediate regression: tests/cognitive/test_episode.py: 37 passed. Subsequent phase-aware Experience integrity and full current verification belong to the final evidence report. No global rollout or real-user effect was performed by these tests.
