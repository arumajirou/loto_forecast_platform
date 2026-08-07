# k-DPP fixed-cardinality data contract

## Strictness

The request, response, chronology, and configuration contracts use Pydantic v2 strict mode,
`extra="forbid"`, finite-number validation, fixed model identity, lowercase SHA-256 fields, and
safe relative artifact paths. Prediction requests require `actuals_used=false`.

## Game geometry

| Game | Default layout | Cardinality |
|---|---|---:|
| Numbers3 | position-local | 1 per position |
| Numbers4 | position-local | 1 per position |
| MiniLoto | unordered fixed-cardinality | 5 |
| Loto6 | unordered fixed-cardinality | 6 |
| Loto7 | unordered fixed-cardinality | 7 |

Numbers3 and Numbers4 item IDs are position-qualified as `n<position>:<digit>`. Therefore `n1:7`
and `n2:7` are distinct full item identities and are not rejected as duplicates. A shared
position-qualified layout is representable for contract testing, but PR-A does not claim a valid
partition-constrained shared runtime.

## Chronology

Train, Validation, Holdout, and Prospective remain time ordered. Feature construction must stop at
`feature_cutoff=train_end`; `forecast_origin` must be later than all fitted rows. Known-future
covariates must be listed explicitly and must be known at prediction time. Future actual values are
forbidden.

## Response semantics

The point forecast is `SEEDED_EXACT_KDPP_SAMPLE`. Marginal top-k, greedy determinant maximization,
and Conditional Bernoulli samples are different variants and must not be labeled as the native
k-DPP point forecast. Quantiles are unsupported and must remain `null`.
