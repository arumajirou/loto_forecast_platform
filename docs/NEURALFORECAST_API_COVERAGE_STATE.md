# NeuralForecast API coverage state bundle

## Purpose

The static argument catalog and API execution results are separate evidence sources.
A catalog row marked `PLANNED` must not be interpreted as verified merely because a
case with the same name exists. The coverage-state bundle joins the sources and records
an explicit verification state for every argument.

This workflow is CPU-safe. It does not claim GPU training, reload inference, PID, VRAM,
or CPU-fallback certification. When no target-host evidence is supplied, GPU status is
always written as `EXECUTION_PENDING`.

## Integrated execution

The standard API coverage stage executes the state resolver automatically:

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign.yaml \
  run \
  --stage api-coverage \
  --output artifacts/<run>
```

The integrated pipeline performs these steps in order:

1. execute the existing API coverage cases;
2. retain the original plan, result, per-case, failure, and manifest artifacts;
3. load `API_ARGUMENT_COVERAGE_RESULT.parquet`;
4. build the all-36-AutoModel constructor/default-config matrix;
5. resolve every static catalog row to an explicit verification state;
6. write the nested `coverage-state` bundle;
7. update the root manifest and regenerate the portable root `SHA256SUMS`.

The original API coverage top-level `status` remains compatible. The integrated root
manifest adds:

```text
coverage_state_schema_version
coverage_state_status
verification_status
coverage_state_path
gpu_runtime_status
coverage_state
```

A resolver failure does not delete completed API case results. It removes any partial
`coverage-state` directory, writes `coverage_state_failure.json`, changes the root status
to `PARTIAL`, records `verification_status=FAILED`, regenerates `SHA256SUMS`, and causes
the existing CLI non-PASS exit contract to return exit code 2.

A successful `--resume` execution replaces the prior `coverage-state` directory and
removes stale `coverage_state_failure.json` evidence.

## Integrated verification

The existing verify command now applies the legacy campaign checks first and then the
coverage-state contract:

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign.yaml \
  verify \
  --run artifacts/<run>
```

For non-API campaign runs, coverage verification returns `NOT_APPLICABLE` and preserves
the previous verification behavior. For an integrated API coverage run, verification is
fail-closed and checks:

- required root API coverage artifacts;
- root `SHA256SUMS` through the legacy verifier;
- safe, run-relative `coverage_state_path` without `..` or absolute paths;
- root, embedded, and nested manifest state/schema equality;
- nested `coverage-state/SHA256SUMS` completeness and file digests;
- exactly 36 unique constructor matrix model names;
- constructor status-count totals;
- non-empty resolved argument evidence;
- resolved argument counts and verification-state totals;
- API result Parquet readability and row-count agreement;
- absence of stale failure evidence after success;
- absence of partial `coverage-state` output after failure;
- structured resolver failure phase, exception, traceback, and GPU boundary;
- `gpu_runtime_status=EXECUTION_PENDING` while target-host runtime evidence is absent.

The result is embedded in `VERIFICATION_REPORT.json` as
`coverage_state_verification`. The root `SHA256SUMS` is regenerated after the final
report is written.

An internally consistent resolver failure can pass the artifact-consistency sub-check,
but the complete run remains `FAIL` because its root manifest status is `PARTIAL` and
its coverage state is `FAILED`.

## State model

| State | Meaning |
|---|---|
| `EXECUTION_PENDING` | No sufficient execution or constructor evidence exists. |
| `PARTIALLY_VERIFIED` | Some evidence passed, but a required probe remains pending. |
| `VERIFIED` | All applicable evidence for the row passed. |
| `FAILED` | A case failed, an unknown status appeared, inventory changed, or a constructor/default-config probe failed. |

The original catalog `status` remains available as `declared_status`. Runtime evidence
is stored separately in `observed_statuses` and `verification_status`, so historical
catalog meaning is not overwritten.

## All-36-model constructor matrix

The command dynamically discovers every `BaseAuto` subclass exported by
`neuralforecast.auto` and requires exactly 36 models for the pinned NeuralForecast
3.2.0 environment. For every model it records:

- module, class and constructor signature;
- `h` and `config` constructor availability;
- `n_series` requirement;
- track and exogenous-variable capabilities;
- supported Ray/Optuna backends;
- `get_default_config` result for each supported backend;
- explicit `NOT_APPLICABLE` for unsupported backends such as AutoHINT with Optuna.

The matrix does not call `fit`, `predict`, `save`, or `load`. It proves constructor and
default-config contracts only.

## Standalone usage

Resolve an existing API coverage result without rerunning the cases:

```bash
uv run python -m loto.auto_campaign.coverage_state \
  --api-results artifacts/<run>/API_ARGUMENT_COVERAGE_RESULT.parquet \
  --output artifacts/<run>/coverage-state-manual
```

Build the signature matrix when optional default-config dependencies are unavailable:

```bash
uv run python -m loto.auto_campaign.coverage_state \
  --output artifacts/<run>/coverage-state-signatures \
  --skip-default-config-probes
```

The second command intentionally produces `PARTIALLY_VERIFIED` constructor rows because
default-config probes were skipped.

## Artifacts

Integrated root:

```text
API_ARGUMENT_COVERAGE_PLAN.parquet
API_ARGUMENT_COVERAGE_RESULT.csv
API_ARGUMENT_COVERAGE_RESULT.parquet
failures.json
manifest.json
VERIFICATION_REPORT.json  # after verify
SHA256SUMS
coverage_state_failure.json  # only on resolver failure
```

Nested `coverage-state` bundle:

```text
AUTO_CONSTRUCTOR_CONTRACT_MATRIX.json
AUTO_CONSTRUCTOR_CONTRACT_MATRIX.csv
AUTO_CONSTRUCTOR_CONTRACT_MATRIX.parquet
API_ARGUMENT_COVERAGE_RESOLVED.json
API_ARGUMENT_COVERAGE_RESOLVED.csv
API_ARGUMENT_COVERAGE_RESOLVED.parquet
COVERAGE_SUMMARY.json
manifest.json
SHA256SUMS
```

JSON is the evidence source of record. Nested values are converted to deterministic JSON
strings before CSV and Parquet output to avoid ambiguous or backend-dependent tabular
types.

## Fail-closed rules

The command fails or records `FAILED` when any of these occur:

- the API result Parquet is missing, unreadable, or empty;
- discovered AutoModel count differs from 36;
- constructor model names are empty or duplicated;
- a registered constructor lacks `h` or `config`;
- a supported backend default-config probe raises;
- an API result is malformed;
- duplicate `case_id` values are present;
- an API case has `FAILED` or an unknown status;
- a required root or nested artifact is missing;
- a root or nested manifest disagrees with embedded evidence;
- a nested SHA-256 digest is invalid or incomplete;
- an evidence JSON object or list is empty;
- an artifact path escapes the run directory;
- GPU status is promoted without target-host runtime evidence.

## Certification boundary

This bundle may be generated while the local RTX environment is unavailable. It must not
be used to change the following states to `VERIFIED`:

```text
GPU fit execution
GPU reload inference
GPU PID
VRAM evidence
CPU fallback rejection on the target GPU host
all-36-model GPU runtime campaign
```

Those remain `EXECUTION_PENDING` until a local or self-hosted GPU runner produces the
required runtime evidence.
