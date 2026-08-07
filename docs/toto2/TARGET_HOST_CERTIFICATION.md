# Toto 2.0 4M target-host certification

Status: `IMPLEMENTED / DEPENDENCY_LIGHT_VERIFIED / TARGET_HOST_EXECUTION_PENDING`.

This layer executes the existing two-process runtime certifier across the exact formal matrix:

- games: Numbers3, Numbers4, MiniLoto, Loto6, Loto7;
- context lengths: 128, 256, 512;
- horizons: 1, 2, 5;
- devices: CPU and CUDA;
- total: 90 cases, with two independent provider processes per case.

## Mandatory lock review

The runner refuses to execute unless `environments/toto2-4m-py312/uv.lock` exists and a separate
review JSON records `APPROVED`, its exact SHA-256, a reviewer, a UTC review timestamp, and explicit
confirmation that dependency sources, package hashes, and licenses were reviewed.

The example review file is a template only. Replacing its placeholders without performing the review
would not satisfy the evidence requirement.

## Request files

Prepare one schema-v2 request for every case under a request directory using this exact pattern:

```text
{game}-c{context}-h{horizon}-{device}.json
```

Each request is parsed before execution. Its game, context, horizon, device, operation, and
offline-only setting must match the matrix case.

## Execution

```bash
environments/toto2-4m-py312/run-python.sh \
  scripts/run_toto2_4m_target_host_certification.py \
  --matrix-manifest configs/toto2_campaign/formal_runtime_matrix.json \
  --requests-root /absolute/path/to/requests \
  --snapshot /absolute/path/to/models--Datadog--Toto-2.0-4m/snapshots/8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9 \
  --isolated-python "$PWD/environments/toto2-4m-py312/.venv/bin/python" \
  --lock-review /absolute/path/to/lock-review.json \
  --output-root "$PWD/artifacts/toto2-4m-target-host-certification"
```

The command exits nonzero on the first failed case. A PASS produces the full run directory, an
artifact manifest, SHA256SUMS, a deterministic ZIP, and a ZIP SHA-256 file.

## Certification boundary

A matrix PASS certifies model loading, inference, output validation, external GPU evidence, and exact
two-process replay for the supplied requests. It does not certify forecast accuracy, lottery-domain
compatibility, Hit@±1, MAE, MSE, RMSE, Holdout, Prospective, or baseline superiority.
