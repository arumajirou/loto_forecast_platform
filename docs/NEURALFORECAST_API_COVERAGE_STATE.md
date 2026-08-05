# NeuralForecast API coverage state bundle

## Purpose

The static argument catalog and API execution results are separate evidence sources.
A catalog row marked `PLANNED` must not be interpreted as verified merely because a
case with the same name exists. The coverage-state bundle joins the sources and records
an explicit verification state for every argument.

This workflow is CPU-safe. It does not claim GPU training, reload inference, PID, VRAM,
or CPU-fallback certification. When no target-host evidence is supplied, GPU status is
always written as `EXECUTION_PENDING`.

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

## Usage

Resolve an existing API coverage result:

```bash
uv run python -m loto.auto_campaign.coverage_state \
  --api-results artifacts/<run>/API_ARGUMENT_COVERAGE_RESULT.parquet \
  --output artifacts/<run>/coverage-state
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

```text
AUTO_CONSTRUCTOR_CONTRACT_MATRIX.csv
AUTO_CONSTRUCTOR_CONTRACT_MATRIX.parquet
API_ARGUMENT_COVERAGE_RESOLVED.csv
API_ARGUMENT_COVERAGE_RESOLVED.parquet
COVERAGE_SUMMARY.json
manifest.json
SHA256SUMS
```

`manifest.json` includes the argument-status counts, constructor-model count, API result
count, and the explicit GPU execution boundary.

## Fail-closed rules

The command fails or records `FAILED` when any of these occur:

- discovered AutoModel count differs from 36;
- a registered constructor lacks `h` or `config`;
- a supported backend default-config probe raises;
- an API result is malformed;
- duplicate `case_id` values are present;
- an API case has `FAILED` or an unknown status.

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
