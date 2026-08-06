# TabPFN-TS Verification Report

Status: `PARTIALLY_VERIFIED`

## Implemented scope

This branch adds an isolated TabPFN-TS provider-contract v2 package without changing the
existing provider, shared worker, model catalog, root dependency manifest, root lockfile, or
GitHub Actions workflows.

The contract separates the fixed legacy V2 checkpoint lane from the current TS-3 lane. TS-3
remains fail-closed until its exact repository identity, revision, checkpoint SHA-256, and weight
license are verified.

## Executed before GitHub publication

| Gate | Result |
|---|---|
| Python syntax / compileall | PASS |
| Focused contract and safety tests | PASS: 42 tests |
| Model-manifest JSON parse | PASS |
| Contract YAML parse | PASS |
| Patch whitespace check | PASS |
| Overlay and patch SHA-256 parity | PASS |
| Secret-pattern scan | PASS |
| Large-file and bytecode-cache scan | PASS |

## GitHub publication

| Item | Result |
|---|---|
| Base branch | `main` |
| Feature branch | `feat/tabpfn-ts-provider-contract-v2` |
| Draft pull request | `#97` |
| Existing provider modified | NO |
| Root `pyproject.toml` or `uv.lock` modified | NO |
| Merge or auto-merge | NOT PERFORMED |

The connected GitHub contents API creates one commit per added file. This branch is therefore
intended for **squash merge only** after CI and review.

## GitHub Actions evidence

| Attempt | Workflow run | Job | Result | Step metadata | Log retrieval |
|---:|---:|---:|---|---|---|
| 1 | `31057547953` | `92478220826` | FAILURE | unavailable | `BlobNotFound` |
| 2 | `31057547953` | `92480636445` | FAILURE | empty | `BlobNotFound` |

The failed-job rerun request was accepted. Both attempts completed without retrievable step
metadata or logs. Therefore the root cause remains `UNVERIFIED`; these results must not be
reported as a confirmed Ruff, pytest, dependency-installation, or source-code failure.

A fresh workflow run is triggered by this evidence-only documentation update to distinguish a
run-storage or runner-startup failure from a branch-content failure.

## Pending gates

| Gate | Status | Reason |
|---|---|---|
| Repository CI | FAILED_ROOT_CAUSE_UNVERIFIED | Two attempts lack steps and logs |
| Full pytest | EXECUTION_PENDING | Final integration gate |
| Ruff and mypy in repository environment | EXECUTION_PENDING | Must use repository toolchain |
| V2 real checkpoint load | EXECUTION_PENDING | Requires trusted checkpoint mount |
| V2 CPU and GPU inference | EXECUTION_PENDING | Runtime integration intentionally deferred |
| Separate-process reload certification | EXECUTION_PENDING | Requires actual provider environment |
| TS-3 inference | BLOCKED | Checkpoint hash and weight-license review incomplete |

## Formal interpretation

The contract, geometry, provenance gate, candidate-score semantics, quantile validation,
known-future covariate contract, strict CUDA evidence, local/batch parity rules, and schema-v1
conversion are implemented and locally verified. This is not yet evidence that a real TabPFN
checkpoint loaded, executed on GPU, or improved forecasting metrics.
