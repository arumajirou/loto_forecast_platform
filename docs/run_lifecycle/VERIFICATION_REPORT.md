# Verification Report

## Current status

`PARTIALLY_VERIFIED`

## Provenance gates

- Design PR #140: open and Draft at requested head SHA — verified through GitHub connector.
- Design changed paths: docs-only under `docs/operational_resilience_expansion/**` — verified.
- Design manifest and SHA256SUMS values: mutually consistent — verified.
- Independent local rehash of connector-returned design bytes — not available through connector.
- Implementation base: latest `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0` — verified.
- Same-purpose branch/PR/Issue/package — not found before branch creation.

## Local validation

```text
Python=3.13.5
Pydantic=2.13.4
pytest=9.0.2
focused pytest=28 passed, 1 skipped
statement coverage=90%
compileall=PASS
AST parse=PASS
JSON parse=PASS
Python lines over 100=0
secret-pattern scan findings=0
static import=PASS
transition rules=140
```

The skipped tests are Hypothesis property tests because Hypothesis is not installed in the isolated
local runtime. The test source is included and the root repository development configuration already
declares Hypothesis.

## Pending

- Ruff: tool unavailable in isolated runtime.
- mypy: tool unavailable in isolated runtime.
- full repository pytest: no complete checkout in local runtime.
- GitHub Actions: to be inspected after publication.
- database/distributed durability: out of scope and not executed.

No pending or blocked gate is represented as passed.
