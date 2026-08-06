# TiRex-2 focused test plan

1. Exact package and model provenance constants.
2. Request unknown-key rejection.
3. Geometry and arbitrary target counts 1/3/4/5/6/7.
4. Horizons 1/2/5 without first-step truncation.
5. Full quantile schema, finite values, monotonicity, and q0.5 identity.
6. Covariate shape and chronology; fail-closed future-known rules.
7. Local/batch/joint layout constraints.
8. Future-mutation invariance comparison helper.
9. CUDA fallback rejection in successful response schema.
10. Legacy schema-v1 conversion isolated to seven-position compatibility.
11. Two-process comparison: distinct PIDs, exact point/all-quantile identity, and drift rejection.
12. Provider failures preserve structured JSON and return a non-zero process exit code.

13. Bounded direct requirement satisfaction against resolved versions.
14. Registry-only package sources and complete artifact SHA-256 inventory.
15. Official TiRex-2 0.1.1 wheel/sdist hash presence.
16. Dry-run immutability and explicit apply-token enforcement.
17. Installed project/lock/report/approval cross-hash validation.
18. Tampered installed lock rejection before provider import.

Actual package, CPU, GPU, and subprocess reload tests require the dedicated environment and
trusted model snapshot and are not claimed by the hermetic focused suite.
