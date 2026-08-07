# Handoff

## Current state

Draft PR #47 contains the isolated Darts P1-P12 contract implementation. Local focused tests
verify schemas and fake-runtime certification paths. Real provider environments and the final
cross-library campaign remain pending.

## First actions for the next operator

1. Checkout the Draft PR head without rewriting history.
2. Confirm the base, head, changed-file scope, and that the PR remains Draft.
3. Resolve `darts[notorch]==0.46.1` and `darts[torch]==0.46.1` with reproducible `uv.lock`
   files in the isolated environment directories.
4. Pin immutable Chronos2 and TiRex revisions and generate local model SHA-256 manifests.
5. Run focused import, load, fit, predict, shape, finite, device, PID, VRAM, and persistence
   smoke tests before any large campaign.
6. Execute the eight-track P12 comparison using identical fairness contracts.
7. Preserve every failed provider and model in the result table.
8. Seal Prospective predictions before actual values are known.
9. Run full quality gates and regenerate the final package.

## Decisions that must not be changed silently

- Hit@±1 is the primary metric.
- Best-seed-only selection is forbidden.
- Train-only preprocessing and HPO are mandatory.
- Raw data is immutable.
- GPU availability alone is not a successful GPU run.
- Wrapper and standalone executions remain visible but duplicate algorithms count once.
- No merge, Ready transition, auto-merge, force push, rebase, or branch deletion without
  explicit user approval.
