# Trusted Evidence Migration Guide

## Initial adoption policy

This foundation is adoption-neutral. Do not change existing prediction locks, Actual locks,
verification seals, or portable bundle schemas in the foundation PR.

## Existing field mapping

| Existing evidence | Foundation status | Reason |
|---|---|---|
| PR #63 `LOCAL_SYSTEM_UTC` | `LOCALLY_TIMESTAMPED` | Local clock only |
| PR #63 `actual_known=false` | unchanged lock fact | Not proof of external time |
| PR #53 verification seal time | `LOCALLY_TIMESTAMPED` when mapped | Local seal creation time |
| PR #64 source label | `OPERATOR_ASSERTED` | No source URL or source authentication |
| PR #64 publication time | `OPERATOR_ASSERTED` | Explicitly recorded as unverified |
| missing external evidence | `NOT_PROVIDED` | No inferred trust |

## Recommended future sequence

1. Resolve the PR #53 → #60 → #63 → #64 stack.
2. Add a sidecar evidence-bundle writer without changing the original lock bytes.
3. Include the sidecar and all verification materials in portable exports.
4. Extend portable verification to call `verify_evidence_bundle` offline.
5. Add one external verifier implementation per PR.
6. Run deterministic fixture tests before any live service test.
7. Keep every live result `UNVERIFIED` until an independent verifier passes retained material.
8. Add source-specific parsers separately from source authentication.
9. Preserve correction records append-only; never replace a prior evidence bundle.

## Compatibility gate

A migration PR must demonstrate:

- unchanged legacy artifact bytes;
- unchanged legacy verifier result when no sidecar exists;
- `NOT_PROVIDED` or legacy assertion mapping rather than invented verification;
- complete SHA-256 coverage of new material;
- portable verification after original source removal;
- no live request during ordinary offline verification;
- explicit rollback by removing only the additive sidecar path.
