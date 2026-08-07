# AutoTimeLLM contract foundation

## Status

`PARTIALLY_VERIFIED / CONTRACT_AND_FACTORY_TESTS_PASS / REAL_RUNTIME_NOT_EXECUTED`

## Purpose

This add-only module introduces a local NeuralForecast `AutoTimeLLM` factory without changing
`neuralforecast.auto`, the shared Auto Campaign registry, common workers, root dependencies, or
existing Draft PR stacks. The logical model ID is `nf-local-auto-timellm`.

## Provenance

- target project runtime: `neuralforecast==3.2.0`;
- upstream class: `neuralforecast.models.timellm.TimeLLM`;
- upstream license: Apache-2.0;
- supported search backends: Ray and Optuna;
- upstream reference default LLM: `openai-community/gpt2`;
- observed reference LLM license: MIT.

No LLM repository or revision is an executable default. Every run must supply an immutable local
Hugging Face snapshot with an exact repository commit and byte inventory.

## Requirements

- expose dependency-lazy `AutoTimeLLM` and `PinnedTimeLLM` classes;
- use NeuralForecast `BaseAuto` with Ray and Optuna contracts;
- preserve the upstream `TimeLLM` window and training interface;
- derive hidden size and layer count from reviewed `config.json`;
- reject upstream fallback to another LLM identity;
- restrict the initial lane to point losses and position-univariate forecasting;
- keep the model inactive until a separate integration PR is approved;
- add no root dependency, lockfile, worker, catalog, CLI, API, Holdout, or Prospective change.

## Architecture

```text
PinnedLLMIdentity
        |
        v
verify_snapshot ------------------ complete byte inventory / no custom code
        |
        v
load_snapshot_model_metadata ----- hidden size / layer count
        |
        v
AutoTimeLLM (BaseAuto)
        |
        +-- Ray dictionary config
        +-- Optuna define-by-run config
        |
        v
PinnedTimeLLM (TimeLLM)
        |
        +-- offline environment
        +-- bounded architecture profile
        +-- point-loss gate
        +-- enc_in=1 / dec_in=1
        +-- post-load snapshot identity gate
```

Runtime classes are registered under stable module-level names after lazy construction so process
serialization can resolve them without importing heavy optional dependencies during normal package
import.

## Data and snapshot contract

`PinnedLLMIdentity` freezes repository ID, immutable 40-character revision, absolute materialized
snapshot path, license identifier, exact file inventory, file sizes, and SHA-256 values.

The runtime requires:

- snapshot directory name equal to the exact revision;
- no symlink at the root or any retained path component;
- exact equality between listed and actual files;
- `config.json`, tokenizer evidence, and at least one weight file;
- no Hugging Face `auto_map` custom-code declaration;
- positive hidden-size and layer-count metadata;
- loaded config, model, and tokenizer paths equal to the local snapshot;
- `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and telemetry disabled during load.

`PinnedTimeLLM` fixes `enc_in=1` and `dec_in=1`. Future, historic, and static exogenous variables
remain unsupported in this initial lane. Only point training and validation losses are accepted.

## Search-space contract

The bounded default uses architecture profile IDs rather than independent geometry fields. This
prevents invalid combinations such as `patch_len > input_size`, `stride > patch_len`, or
`d_model % n_heads != 0`.

Tuned fields:

- architecture profile: compact, balanced, or wide;
- learning rate: log-uniform `1e-5` to `1e-3`;
- maximum steps: 100, 300, or 500;
- validation check steps: 20, 50, or 100;
- batch size: 8, 16, or 32;
- windows batch size: 32, 64, or 128;
- dropout: 0.0, 0.1, or 0.2;
- scaler: identity or robust;
- random seed: integer 1 through 19.

LLM repository, revision, files, hidden size, layer count, and license are fixed study inputs rather
than search dimensions. One study must bind one model snapshot and one seed set. Nested Ray remains
prohibited by the surrounding campaign design.

## Verification executed

```text
Python=3.13.5
Pydantic=2.13.4
pytest=9.0.2
focused pytest=10 passed in 0.10s
package import without heavy runtime dependencies=PASS
Python compileall=PASS
Python AST parse=PASS
Python lines over 100 characters=0
SHA256SUMS verification=PASS
```

The package import reported the expected unavailable runtime dependencies:

```text
neuralforecast=false
ray=false
transformers=false
```

Focused tests verify immutable revision validation, safe paths, complete inventory, byte tamper
rejection, unexpected-file rejection, custom-code rejection, metadata parsing, architecture
constraints, validation-step bounds, stable runtime class identity, Ray identity injection, hidden
geometry derivation, forced univariate dimensions, and rejection of upstream LLM fallback.

Runtime-factory tests use module doubles. They validate project-side contracts only and are not real
NeuralForecast, Ray, Transformers, CPU, or GPU evidence.

## Not executed and explicit non-claims

- Ruff and mypy: tools unavailable;
- complete private repository checkout tests and full pytest: not executed;
- exact NeuralForecast 3.2.0, Ray, and Transformers runtime: not executed;
- real immutable LLM snapshot load: not executed;
- fit, prediction, save, reload, and replay with a real model: not executed;
- CPU or GPU runtime certification: not established;
- Hit@±1, MAE, MSE, RMSE, position metrics, or baseline comparison: not measured;
- Holdout and Prospective: not opened;
- shared Auto Campaign registration: not implemented;
- production availability and merge readiness: not established.

## Test and runtime handoff

A later runtime PR must start from the then-current main after this Draft PR is reviewed and merged.
It must provide a reviewed immutable snapshot and verify package identity, load, input, fit, finite
prediction, shape, save, reload, same-seed replay, device, CPU fallback, GPU PID/UUID/VRAM when
requested, process cleanup, artifact manifest, and SHA256SUMS.

A separate integration PR may register `get_auto_timellm_class()` only after real runtime evidence
passes. It must coordinate explicitly with the existing NeuralForecast search-policy and runtime
certification PR stacks.

## Runbook

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTEST_ADDOPTS='-p no:cacheprovider' \
PYTHONPATH=src \
pytest -q tests/neuralforecast/auto_timellm

python -m compileall -q \
  src/loto/neuralforecast/auto_timellm \
  tests/neuralforecast/auto_timellm
```

## Changelog

### 1.0.0 - 2026-08-06

- add strict immutable LLM snapshot contracts;
- add complete inventory and SHA-256 verification;
- reject remote custom code and upstream identity fallback;
- add bounded architecture profiles;
- add dependency-lazy NeuralForecast runtime factories;
- add Ray and Optuna config support;
- add focused dependency-light tests;
- leave shared integration and protected data unchanged.
