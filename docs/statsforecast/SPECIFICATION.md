# StatsForecast model contract v1

## Scope

Owned paths are limited to `src/loto/statsforecast/**`, `tests/statsforecast/**`,
`configs/statsforecast/**`, and `docs/statsforecast/**`.

## Model outcome states

- `EXPECTED_PASS`
- `EXPECTED_NEGATIVE_PASS`
- `EXPECTED_DATA_PRECONDITION`
- `UNSUPPORTED_BY_VERSION`
- `BLOCKED_OPTIONAL_DEPENDENCY`
- `UNEXPECTED_FAILURE`

`NaNModel` succeeds only when the validator detects and rejects non-finite output. Models
with constructor or minimum-history requirements must report a precondition state rather
than being mislabeled as runtime failures.

## Data and leakage boundary

Raw data is copied and never repaired in place. Duplicate, missing, unordered, non-finite,
out-of-range, or gap-bearing draw-sequence data fails closed. Train, Validation, and
Holdout are split chronologically per series. Prospective predictions must carry
`actual_known=false` and a timestamped SHA-256 seal.

## Runtime boundary

Formal success requires installed-version evidence, import, constructor argument ledger,
fit or forecast, complete inventory evidence, per-series horizon identity checks, finite
values, and lifecycle validation.
Static inventory and fake-runtime tests are only local contract evidence.

## Upstream inventory boundary

The pinned inventory is an exact transcription of StatsForecast 2.1.1
`statsforecast.models.__all__`. `ConformalSeasonalPool` is included. A separate project
extension must not replace, masquerade as, or be required from the upstream module.
