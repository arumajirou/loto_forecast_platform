# Verification Report

This report is regenerated from executed checks before publication. See the final section for the
exact status of each requested gate.

## Scope

- base branch: `main`;
- frozen base SHA: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- implementation branch: `feat/research-source-registry-v1`;
- allowed paths only: `src/loto/research_sources/**`, `tests/research_sources/**`,
  `docs/research_sources/**`, and `configs/research_sources/**`.

## Source recheck summary

Official paper, source, and model pages were re-fetched on 2026-08-06. Values that were not
independently pinned or byte-verified remain `UNPINNED`, `UNVERIFIED`, or `UNKNOWN`. In particular,
an official repository listing was not treated as proof of checkpoint bytes or runtime success.

## Explicit non-claims

- model implementation not started;
- dependency resolution not executed;
- checkpoint download not executed;
- CPU/GPU runtime not executed;
- OOF not executed;
- Holdout not opened;
- Prospective not opened;
- production registration not performed.

## Gate results

The final executed values are appended before publication. No unavailable gate is represented as
passing.

| Gate | Result | Evidence boundary |
|---|---|---|
| focused pytest | PASS: 42 passed | isolated exact proposed source/config/tests |
| compileall | PASS | `src/loto/research_sources` and `tests/research_sources` |
| Python AST parse | PASS | every changed Python file |
| JSON parse | PASS | registry index and 11 record JSON files |
| YAML parse | NOT_APPLICABLE | no YAML artifact is introduced |
| line-length scan | PASS: 0 over 100 | changed Python source and tests |
| secret-pattern scan | PASS: 0 findings | all proposed text artifacts |
| changed-path ownership | PASS | 30 pre-manifest files, all in allowed paths |
| artifact manifest | PASS | regenerated after this report and verified |
| SHA256SUMS | PASS | regenerated after this report and verified |
| Ruff | BLOCKED_TOOL_UNAVAILABLE | `python -m ruff`: module not installed |
| mypy | BLOCKED_TOOL_UNAVAILABLE | `python -m mypy`: module not installed |
| related catalog regression | PASS | active catalogs were not imported or modified |
| local artifact full pytest | PASS: 42 passed | all tests present in isolated artifact mirror |
| full repository pytest | BLOCKED_NO_FULL_CHECKOUT | private full checkout unavailable here |
| GitHub Actions | BLOCKED_NO_ACTIONABLE_LOG | run #2800 had no steps; logs returned BlobNotFound |

## Verification classification

```text
PARTIALLY_VERIFIED
FOCUSED_TESTS_PASS
STATIC_CONTRACT_AND_RECORDS_VERIFIED
SUBSTANTIVE_REVIEW_HARDENING_PASS
REPOSITORY_WIDE_VALIDATION_BLOCKED
RUNTIME_NOT_EXECUTED
```

## Substantive self-review hardening

The post-publication review identified and closed fail-open boundaries where a record could claim
`VERIFIED_FOR_INTAKE` while paper identity, canonical repository identity, release state, required
artifact sizes/hashes, license sources, or commercial eligibility remained unresolved. It also
corrected the remote-code state machine so a completed review can reach intake only with a safe
non-empty allowlist whose files are present and pinned in the artifact inventory. Fifteen regression
tests were added; the final focused result is `42 passed`.
