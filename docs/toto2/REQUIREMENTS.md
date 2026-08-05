# Requirements

## Functional

- Support Numbers3, Numbers4, MiniLoto, Loto6, and Loto7 geometry.
- Support position-univariate and position-multivariate contracts.
- Support formal horizons 1, 2, and 5.
- Retain q0.1 through q0.9 exactly; q0.5 is the point forecast.
- Reject unknown fields, revision drift, shape drift, non-finite values, and crossing quantiles.
- Reject CUDA fallback and missing external GPU PID or positive VRAM evidence.

## Reproducibility

- Model revision, source revision, package versions, license, artifact hashes, and seed are explicit.
- Raw historical failure evidence remains retained and is superseded rather than deleted.
- Root `pyproject.toml`, root `uv.lock`, shared workers, catalogs, CLI, and workflows stay unchanged.
