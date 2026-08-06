# Timer-S1 changelog

## PR-A

- Added canonical provenance and license policy.
- Added strict request, success, and failure contracts.
- Added structural game geometry and chronology compilation.
- Added quantile normalization and q0.5 point identity checks.
- Added fail-closed remote-code and snapshot policies.
- Added an isolated Python 3.11 declaration and provider skeleton.
- Added focused tests, handoff material, manifests, and checksums.

## PR-A review hardening

- Restricted success responses to verified CPU/GPU statuses.
- Bound response matrices and chronology to exact game/context/horizon geometry.
- Enforced finite values, per-cell quantile monotonicity, and q0.5 point identity in the contract.
- Bound request config, weight-index, and canonical weight-set hashes to manifest records.
- Required safe manifest paths and exact snapshot file, size, and SHA-256 accounting.
- Required pinned, timezone-aware remote-code review evidence.
- Sanitized unsafe invalid-request run IDs before structured CLI failure output.
- Added regression tests for every hardening item.
