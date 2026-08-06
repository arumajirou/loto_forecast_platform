# TabPFN-TS Verification Report

Status: `PARTIALLY_VERIFIED`

## Implemented scope

This branch adds an isolated TabPFN-TS provider-contract v2 package without changing the
existing provider, shared worker, model catalog, root dependency manifest, root lockfile, or
GitHub Actions workflows.

The contract separates the fixed legacy V2 checkpoint lane from the current TS-3 lane. TS-3
remains fail-closed until its exact repository identity, revision, checkpoint SHA-256, and weight
license are verified.

## Executed verification

| Gate | Result |
|---|---|
| Python syntax / compileall | PASS |
| Focused contract and safety tests | PASS: 54 tests |
| Focused tests with only `src` on `PYTHONPATH` | PASS: 54 tests |
| Focused tests with repository root and `src` on `PYTHONPATH` | PASS: 54 tests |
| Changed Python line length (`<=100`) | PASS |
| Model-manifest JSON parse | PASS |
| Contract YAML parse | PASS |
| Patch whitespace check | PASS |
| Overlay and patch SHA-256 parity | PASS |
| Secret-pattern scan | PASS |
| Large-file and bytecode-cache scan | PASS |

## Test collection hardening

The focused tests originally imported fixtures through the absolute module path
`tests.adapters.tabpfn_ts.conftest`. Under pytest importlib mode, that path can depend on the
repository root being explicitly importable. The four affected test modules now use the
package-relative import `.conftest`.

No shared `tests/__init__.py` file was added and no path outside the TabPFN-TS-owned test package
was changed. The full 54-test set passes both with and without the repository root explicitly
included in `PYTHONPATH`.

## GitHub publication

| Item | Result |
|---|---|
| Base branch | `main` |
| Feature branch | `feat/tabpfn-ts-provider-contract-v2` |
| Draft pull request | `#97` |
| Existing provider modified | NO |
| Root `pyproject.toml` or `uv.lock` modified | NO |
| Merge or auto-merge | NOT PERFORMED |

The connected GitHub contents API creates one commit per changed file. This branch is therefore
intended for **squash merge only** after CI and review.

## GitHub Actions evidence

| Head / attempt | Workflow run | Job | Result | Steps | Log retrieval |
|---|---:|---:|---|---|---|
| initial | `31057547953` | `92478220826` | FAILURE | unavailable | `BlobNotFound` |
| failed-job rerun | `31057547953` | `92480636445` | FAILURE | empty | `BlobNotFound` |
| evidence head `24e25ff9` | `31058539700` | `92481258894` | FAILURE | empty | `BlobNotFound` |
| hardened head `b1aaadb5` | `31061022162` | `92488826881` | FAILURE | empty | `BlobNotFound` |
| report head `d48ac8ce` | `31061145234` | `92489197044` | FAILURE | empty | `BlobNotFound` |
| import-hardened head `e4fe66fc` | `31061603702` | `92490537927` | FAILURE | empty | `BlobNotFound` |

No checkout, setup-python, dependency-installation, Ruff, compileall, or pytest step is evidenced.
The CI condition remains classified as `CI_BLOCKED_RUNNER_START`; no TabPFN-TS code-test failure
has been proven by GitHub Actions.

## Pending gates

| Gate | Status | Reason |
|---|---|---|
| Repository CI | CI_BLOCKED_RUNNER_START | Workflow jobs stop before executable steps |
| Full pytest | EXECUTION_PENDING | Final integration gate |
| Ruff and mypy in repository environment | EXECUTION_PENDING | Must use repository toolchain |
| V2 real checkpoint load | EXECUTION_PENDING | Requires trusted checkpoint mount |
| V2 CPU and GPU inference | EXECUTION_PENDING | Runtime integration intentionally deferred |
| Separate-process reload certification | EXECUTION_PENDING | Requires actual provider environment |
| TS-3 inference | BLOCKED | Checkpoint hash and weight-license review incomplete |

## Formal interpretation

The contract, geometry, provenance gate, candidate-score semantics, quantile validation,
known-future covariate contract, strict CUDA evidence, local/batch parity rules, schema-v1
conversion, and test import boundary are implemented and locally verified. This is not yet
evidence that a real TabPFN checkpoint loaded, executed on GPU, or improved forecasting metrics.
