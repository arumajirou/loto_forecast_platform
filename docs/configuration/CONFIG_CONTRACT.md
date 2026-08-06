# Strict Configuration Contract v1

## Status

`FOUNDATION_ONLY / NOT_ADOPTED_BY_LEGACY_CONFIGS`

This contract defines a strict configuration boundary for new workflows. It does not reinterpret,
rewrite, or bulk-migrate the existing experiment, Auto Campaign, provider, Holdout, or Prospective
configuration files.

## Canonical schema

The schema identity is:

```text
config_schema_version=1.0.0
```

All models use Pydantic v2 with:

```python
ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)
```

Unknown keys, implicit string-to-number coercion, invalid ranges, inconsistent device/fallback
settings, missing required metrics, duplicate seeds, and unsafe protected-stage settings fail
validation.

## Split and leakage policy

The v1 foundation fixes the following values:

```text
immutable=true
chronological=true
model_fit_scope=train_only
scaler_fit_scope=train_only
encoder_fit_scope=train_only
feature_selection_scope=train_only
hyperparameter_tuning_scope=train_only
```

Holdout and Prospective both default to and require:

```text
auto_run=false
auto_open_actuals=false
explicit_approval_required=true
```

The v1 schema does not contain an automatic opening switch. A future schema must add such a workflow
only through a reviewed migration and an explicit evidence gate.

## Metric and seed policy

The primary metric is fixed to `Hit@±1`. Every resolved config must also report `MAE`, `MSE`, and
`RMSE`. Position and all-position Hit@±1 are supported reporting metrics.

The seed policy requires one or more unique non-negative integer seeds. Formal aggregation is
`mean_variance_worst`, and `best_seed_only_selection=false` is fixed by schema.

## Device policy

A requested device and CPU fallback policy are separate fields:

- `requested=cpu` requires `cpu_fallback_policy=not_applicable`;
- `requested=cuda` requires either `forbid` or `allow_with_partial_status`;
- CUDA availability is not inferred from configuration validation;
- this foundation performs no GPU execution.

## MLflow and secrets

MLflow is disabled by default. Enabling it requires a non-empty tracking URI. Tokens use Pydantic
`SecretStr` and are always emitted as `<redacted>` in resolved artifacts and override provenance.

The resolved-config SHA-256 covers the canonical redacted configuration and redacted override
provenance. Secret bytes are not persisted and are deliberately excluded from the digest. The digest
therefore identifies non-secret execution policy and value origin, not credential identity.

## Git metadata policy

The config records whether Git metadata is enabled, whether a commit is required, whether dirty state
must be captured, and whether a clean worktree is required. This foundation validates the policy only;
it does not execute Git commands or claim a clean repository.

## Environment overrides

Environment overrides are allowlisted. The v1 allowlist is:

| Environment variable | Target | Sensitive |
|---|---|---:|
| `LOTO_CONFIG_EXPERIMENT_NAME` | `experiment_name` | no |
| `LOTO_CONFIG_OUTPUT_DIR` | `runtime.output_dir` | no |
| `LOTO_CONFIG_REQUESTED_DEVICE` | `runtime.device.requested` | no |
| `LOTO_CONFIG_CPU_FALLBACK_POLICY` | `runtime.device.cpu_fallback_policy` | no |
| `LOTO_CONFIG_SEEDS` | `evaluation.seed_policy.seeds` | no |
| `LOTO_CONFIG_MLFLOW_ENABLED` | `observability.mlflow.enabled` | no |
| `LOTO_CONFIG_MLFLOW_TRACKING_URI` | `observability.mlflow.tracking_uri` | no |
| `NEURALFORECAST_MLFLOW_TRACKING_URI` | `observability.mlflow.tracking_uri` | no |
| `LOTO_CONFIG_MLFLOW_EXPERIMENT_NAME` | `observability.mlflow.experiment_name` | no |
| `LOTO_CONFIG_MLFLOW_TOKEN` | `observability.mlflow.token` | yes |
| `LOTO_CONFIG_GIT_REQUIRE_CLEAN` | `git_metadata.require_clean_worktree` | no |

Each applied override records `env_var`, dotted target, `source=environment`, sensitivity,
`redacted=true` for secrets, and a safe value representation. Unknown environment variables are
ignored rather than interpreted dynamically. Setting two allowlisted keys for the same target fails
closed instead of applying last-one-wins precedence.

## Resolved artifact

Validate and write a redacted resolved config with:

```bash
python -m loto.configuration.cli \
  configs/configuration/strict_foundation.example.yaml \
  --resolved-output artifacts/config/resolved.json
```

Outputs:

```text
resolved.json
resolved.json.sha256
```

The JSON contains the schema version, redacted resolved config, environment override provenance, and
resolved-config SHA-256. The sidecar contains the SHA-256 of the exact JSON artifact bytes. Writes use
fsynced temporary sibling files followed by atomic replacement.

## Scope boundary

This foundation does not:

- migrate existing YAML files;
- replace `ExperimentConfig` or `CampaignConfig`;
- change current model defaults or prior experiment results;
- open Holdout actuals;
- run Prospective forecasts;
- execute CPU or GPU models;
- connect to MLflow;
- collect Git metadata;
- change root dependencies or `uv.lock`.
