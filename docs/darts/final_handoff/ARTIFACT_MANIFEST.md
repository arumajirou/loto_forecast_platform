# Artifact manifest

The final handoff ZIP contains exactly the following files in this order:

1. `README.md` — status, provenance, verification boundary, and navigation.
2. `REQUIREMENTS.md` — metrics, comparison, isolation, runtime, and packaging requirements.
3. `SPECIFICATION.md` — P1-P12 phase and input/output specification.
4. `ARCHITECTURE.md` — layered design and execution flow.
5. `DATA_CONTRACT.md` — immutable data, splits, lags, covariates, and prediction records.
6. `TEST_PLAN.md` — completed focused gates and pending real-runtime tests.
7. `VERIFICATION_REPORT.md` — passed, blocked, and explicitly unclaimed results.
8. `CHANGELOG.md` — implementation history.
9. `HANDOFF.md` — next-operator actions and immutable decisions.
10. `RUNBOOK.md` — commands for environment setup, testing, execution, sealing, and packaging.
11. `ARTIFACT_MANIFEST.md` — this exact package inventory.
12. `SHA256SUMS` — SHA-256 values for the preceding 11 documents.

The ZIP builder rejects missing, additional, reordered, nested, absolute, or traversal paths.
It fixes every ZIP timestamp to `1980-01-01 00:00:00` and normalizes file mode to `0644` so
identical source documents produce byte-identical archives.
