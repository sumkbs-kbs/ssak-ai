---
title: Round6 historical log retention limits
tags: [qa, evidence]
date: 2026-10-03
---

The 987-test / 102-file exit0 result and successful TypeScript/production build were directly observed and independently reviewed on a1552cf1 before the next changes. The raw TESTS_CURRENT and BUILD_CURRENT bytes were not copied during the round6 freeze and have now been replaced by the final1001-test /103-file logs. Those old raw logs are not claimed to be immutable archived artifacts. TYPECHECK_ROUND6.log retains the original typecheck bytes. Historical review reports record the observed result; no round6 approval is reused for the changed final source. Current final logs and fresh final reviews provide release evidence.
