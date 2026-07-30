# Loto Forecast Platform Constitution

## Core Principles

### I. Primary-Source Truth (NON-NEGOTIABLE)

Every model, class name, and capability claim MUST be traceable to a primary source
(upstream `__all__`, upstream class definition, or a Hugging Face repo id + commit SHA).
Counts asserted in documentation MUST be computed from the machine-readable catalog,
never hand-typed. A hand-typed count is a defect even when it happens to be correct.

### II. No Silent Substitution, No Silent Failure

An unavailable model is reported as `UNAVAILABLE` with the exact import error. It is never
replaced by a different model. `except Exception: pass` and bare fallbacks that change
observable behaviour are prohibited. Every degraded path MUST emit a typed status record.

### III. Test Hermeticity (NON-NEGOTIABLE)

A test MUST produce the same verdict under `--extra dev` alone as under `--extra full`.
Any test whose outcome depends on an optional package MUST either declare that package in
`dev`, or `skipif` on it explicitly. A test that silently changes verdict with the
environment is a defect of the same severity as a failing test.

### IV. Game-Agnostic Core

No module outside `loto.game` may hard-code a universe size, a draw size, or a digit count.
All such values flow from `GameGeometry`. Loto7 is a *configuration*, not an assumption.

### V. Statistical Honesty

Any leaderboard comparing more than one model MUST report, alongside every point estimate:
the sample size, a dispersion measure, a multiplicity-corrected p-value, and the
`protocol_hash` under which the number was produced. Ranking without multiplicity
correction is prohibited. Comparing metrics across differing `protocol_hash` values is a
hard error, not a warning.

### VI. Leakage is Falsifiable

Every research run MUST execute a negative control (label-permuted sentinel). If the
sentinel scores within the acceptance band of the champion, the run is marked
`SENTINEL_TRIPPED` and no promotion may occur.

### VII. Integrity is Self-Verifying

The shipped artifact MUST contain exactly one authoritative checksum manifest, and the
tool MUST be able to verify itself against that manifest. Two manifests that disagree is a
release-blocking defect.

## Additional Constraints

- Python >= 3.11. Core dependencies limited to numpy / pandas / pydantic / scikit-learn /
  scipy / PyYAML / prometheus-client. Everything else is optional and gated.
- Network fetches respect `robots.txt` and never bypass authentication, CAPTCHA, or rate
  limits.
- Holdout data is inaccessible through the research API surface. Access requires an
  explicit, audited unseal call.

## Quality Gates

1. `pytest -q` green under `dev` extra alone.
2. `python -m loto.verify.integrity check` green against the shipped manifest.
3. Catalog counts in every document regenerated from the catalog, not edited by hand.
4. No module outside `loto.game` matches the regex `\b(37|43|31|40)\b` in a
   universe-size position (enforced by `test_no_hardcoded_geometry`).

## Governance

This constitution supersedes convention. Any exception MUST be recorded as an ADR under
`docs/ADR/` with an explicit expiry condition.

**Version**: 3.0.0 | **Ratified**: 2026-07-30 | **Last Amended**: 2026-07-30
