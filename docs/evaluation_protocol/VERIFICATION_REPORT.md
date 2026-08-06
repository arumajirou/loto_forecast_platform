# Evaluation Protocol Completeness v1 Verification Report

## Status

```text
PARTIALLY_VERIFIED
FOCUSED_TESTS_PASS
COMPILEALL_PASS
AST_JSON_PASS
REMOTE_BLOB_PARITY_PASS
RUFF_BLOCKED_TOOL_UNAVAILABLE
MYPY_BLOCKED_TOOL_UNAVAILABLE
EVALUATION_REGRESSION_PENDING_COMPLETE_CHECKOUT
FULL_PYTEST_PENDING_GITHUB_ACTIONS
```

## Repository and branch

```text
repository=arumajirou/loto_forecast_platform
default_branch=main
base_sha=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
head_branch=fix/evaluation-protocol-completeness-v1
```

The branch was created from the re-fetched latest `main` SHA. No same-name branch or same-purpose
implementation PR or Issue existed before branch creation. PR #131 is the documentation-only design
source for this implementation. PR #121, #123, #124, #127, #128 and #129 retain their existing
ownership boundaries.

## Changed scope

```text
docs/evaluation_protocol/PROTOCOL_V2.md
docs/evaluation_protocol/VERIFICATION_REPORT.md
src/loto/evaluation/__init__.py
src/loto/evaluation/metric_registry.py
src/loto/evaluation/protocol_diff.py
src/loto/evaluation/protocol_v2.py
src/loto/evaluation/seed_summary.py
src/loto/evaluation/selection.py
tests/evaluation/test_protocol_v2_completeness.py
```

No root dependency, `uv.lock`, workflow, model provider, Runtime Certification, Data Access Ledger,
API health, UI, Holdout or Prospective path changed.

## Executed verification

Environment:

```text
Python=3.13.5
pytest=9.0.2
pydantic=2.13.4
uv=0.10.0
```

Final focused validation against local files with Git blob IDs equal to the published branch files:

```text
focused pytest=21 passed
compileall=PASS
AST parse=PASS
JSON parse=PASS
v2 artifact write/read/hash round trip=PASS
historical overwrite refusal=PASS
line length above 100 characters=0
remote Git blob parity for source and focused test files=PASS
```

The first standalone JSON round-trip smoke exposed that strict tuple fields rejected JSON arrays when
using `model_validate`. The reader was corrected to use strict JSON-mode validation through
`model_validate_json`; the regression test was added and the complete focused suite was rerun to PASS.
The failed pre-fix smoke is not hidden or represented as a final PASS.

Published blob parity:

```text
src/loto/evaluation/__init__.py=01a4296ad58042870f69a3e1a0df24169d8a568f
src/loto/evaluation/metric_registry.py=39078c1471d0ab7e5953e862f6bda207fcc6bbb9
src/loto/evaluation/selection.py=0f9564c102ff8ec48203c67095fe69c4eccec446
src/loto/evaluation/seed_summary.py=73fd48c4264a89c30cf47f923a5eadec4bbc311a
src/loto/evaluation/protocol_diff.py=202d7bac0a04fadb801611c7dd56655d6951f8d3
src/loto/evaluation/protocol_v2.py=586e835ab3335ad241e9111e6b15ecde0261d2fc
tests/evaluation/test_protocol_v2_completeness.py=5ca8933fe0d2f032682c49523fc9a357ac72718a
```

## Focused test coverage

The focused suite verifies:

- canonical Hit@±1 primary metric;
- complete point-metric inventory;
- better MAE cannot override worse Hit@±1;
- legacy aliases resolve to one canonical metric;
- alpha, multiplicity correction and conformal changes alter protocol hash;
- baseline and seed inventory changes alter protocol hash;
- resource budget changes alter comparison budget hash;
- all-seed count, mean, population variance, standard deviation and worst seed;
- best-seed-only rejection;
- minimize-metric worst direction;
- protocol v1 read compatibility and explicit v1/v2 comparison refusal;
- field path, values and severity in protocol diff;
- strict unknown-field, NaN and Infinity rejection;
- v2 artifact round trip;
- historical artifact overwrite refusal.

## Pending and blocked verification

```text
Ruff=BLOCKED_TOOL_UNAVAILABLE
mypy=BLOCKED_TOOL_UNAVAILABLE
evaluation-related repository regression=PENDING_COMPLETE_PRIVATE_CHECKOUT
full pytest=PENDING_GITHUB_ACTIONS
GitHub Actions=PENDING
```

The execution environment does not contain `ruff`, `mypy` or `gh`. Network-backed installation and a
complete private checkout are unavailable. These checks are not represented as PASS. GitHub Actions
shall be classified separately; a job that fails before creating steps is
`CI_BLOCKED_RUNNER_START`, not a demonstrated code failure.

## Explicit non-claims

```text
research_v3 migrated to protocol v2=false
historical artifacts backfilled=false
historical artifacts rewritten=false
Holdout accessed=false
Prospective accessed=false
model provider changed=false
Runtime Certification redefined=false
Data Access Ledger redefined=false
PR #127 health endpoint changed=false
custom UI implemented=false
accuracy improvement claimed=false
production deployment=false
```

## Rollback

Before merge, close the Draft PR and leave or delete the branch only under explicit operator action.
After merge, revert the PR normally. The implementation introduces no database, dependency, lockfile,
workflow, data or historical-artifact migration.

## Next PR

```text
feat/telemetry-contract-v1
```
