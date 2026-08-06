# TabPFN-TS Verification Report

Status: `PARTIALLY_VERIFIED / CI_BLOCKED_RUNNER_START`

## Implemented scope

This branch adds an isolated TabPFN-TS provider-contract v2 package without changing the
existing provider, shared worker, model catalog, root dependency manifest, root lockfile, or
GitHub Actions workflows.

The contract separates the fixed legacy V2 checkpoint lane from the current TS-3 lane. TS-3
remains fail-closed until its exact repository identity, revision, checkpoint SHA-256, and weight
license are verified.

## Contract hardening

The post-publication static review closed the following fail-open boundaries:

- `status=OK` now requires an executable checkpoint lane;
- model repository, revision, filename, checkpoint SHA-256, artifact SHA-256, and license
  evidence must match the reviewed lane manifest;
- runtime and GPU PID/device evidence must agree;
- request histories must share identical timestamp identity;
- known-future covariate rows must be unique per series and horizon;
- point and quantile outputs must cover each series/horizon pair exactly once;
- the legacy candidate-score formulation is restricted to one-step forecasting and strictly
  increasing unique-selection games;
- calibrated candidate probabilities must cover every candidate exactly once.

## Executed verification

| Gate | Result |
|---|---|
| Python syntax / compileall | PASS |
| Focused contract and safety tests | PASS: 54 tests |
| Changed Python line-length scan (`<=100`) | PASS |
| Published Git blob parity for four hardened files | PASS |
| Model-manifest JSON parse | PASS |
| Contract YAML parse | PASS |
| Patch whitespace check | PASS |
| Overlay and patch SHA-256 parity | PASS |
| Secret-pattern scan | PASS |
| Large-file and bytecode-cache scan | PASS |

The four hardened GitHub blobs exactly matched the locally tested file contents.

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
intended for **squash merge only** after actionable CI and review.

## GitHub Actions evidence

| Head / attempt | Workflow run | Job | Result | Steps | Log retrieval |
|---|---:|---:|---|---|---|
| initial attempt | `31057547953` | `92478220826` | FAILURE | unavailable | `BlobNotFound` |
| failed-job rerun | `31057547953` | `92480636445` | FAILURE | empty | `BlobNotFound` |
| evidence-only head `24e25ff9` | `31058539700` | `92481258894` | FAILURE | empty | `BlobNotFound` |
| hardened head `b1aaadb5` | `31061022162` | `92488826881` | FAILURE | empty | `BlobNotFound` |

No checkout, Python setup, dependency installation, Ruff, compileall, or pytest step is evidenced
for these runs. Contemporaneous unrelated Draft PRs #95 and #96 showed the same pre-step failure
pattern. The current classification is therefore `CI_BLOCKED_RUNNER_START`; a TabPFN-TS code-test
failure is not proven.

GitHub's public status page reported Actions operational when the hardened-head run was checked.
That narrows the unresolved scope to a repository/account-specific Actions condition or an
unreported transient condition. Plausible categories include Actions policy, hosted-runner
allocation, billing/budget restrictions, or account restrictions. These categories are hypotheses;
the available connector cannot inspect repository billing or runner settings.

## Pending gates

| Gate | Status | Reason |
|---|---|---|
| Executable repository CI | BLOCKED | Job terminates before step creation |
| Full pytest | EXECUTION_PENDING | Final integration gate |
| Ruff and mypy in repository environment | EXECUTION_PENDING | Repository toolchain required |
| V2 real checkpoint load | EXECUTION_PENDING | Trusted checkpoint mount required |
| V2 CPU and GPU inference | EXECUTION_PENDING | Runtime integration intentionally deferred |
| Separate-process reload certification | EXECUTION_PENDING | Actual provider environment required |
| TS-3 inference | BLOCKED | Checkpoint hash and weight-license review incomplete |

## Formal interpretation

The contract, geometry, provenance gate, candidate-score semantics, quantile validation,
known-future covariate contract, strict device evidence, local/batch parity rules, and schema-v1
conversion are implemented and dependency-light verified. This is not evidence that a real
TabPFN checkpoint loaded, executed on GPU, improved Hit@±1, or exceeded any baseline.
