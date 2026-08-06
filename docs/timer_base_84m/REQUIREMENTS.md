# Requirements

- Model identity: `timer-base-84m`, repo `thuml/timer-base-84m`.
- HF revision: `70077a71acce1b4c00d98332fcaabc694255d8e5`.
- Weight SHA-256: `9c3d18f12ffe1ea7d4fa70eb3304b26e3841164a6a265fbae4f7a05cd213aa3d`.
- Python lane: `>=3.10,<3.11`; Transformers: `4.40.1`; Torch remains `UNPINNED`.
- Games: Numbers3, Numbers4, MiniLoto, Loto6, Loto7.
- Layouts: position-univariate and batched independent univariate only.
- Context: 96..2880 and an exact multiple of 96; horizons: 1, 2, 5.
- Quantiles, samples, multivariate inputs, past covariates, and known-future covariates are unsupported.
- Train < Validation < Holdout < Prospective; future actuals and raw-data overwrite are forbidden.
