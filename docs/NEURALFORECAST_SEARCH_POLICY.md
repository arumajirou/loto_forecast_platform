# NeuralForecast Search Policy

## Status

`FOUNDATION / DRAFT / RUNTIME_COMPARISON_PENDING`

This document defines the shared search-policy contract used by the NeuralForecast
planning API and the database AutoModel campaign. It does not claim an accuracy
improvement. Search-policy candidates must still be compared under identical temporal
splits, search spaces, trial budgets, seeds, and resource limits.

## Goals

- remove the previous mismatch between API planning and campaign execution;
- resolve policy without importing heavy optional dependencies;
- instantiate the selected sampler or searcher only at execution time;
- fail closed when a required dependency is unavailable unless fallback is explicitly enabled;
- persist requested, resolved, and effective policy evidence with every model run;
- retain official model-specific NeuralForecast search spaces.

## Versioned decision contract

Every decision uses `schema_version=1.0.0` and records:

- model name and backend;
- requested and resolved strategy;
- algorithm module, class, and constructor arguments;
- search seed and number of samples;
- deterministic reason codes;
- effective algorithm and any explicit fallback evidence.

## Foundation policy

| Backend | Requested strategy | Condition | Resolved algorithm |
|---|---|---|---|
| Optuna | `auto` | samples below 10 | `RandomSampler` |
| Optuna | `auto` | samples at least 10 | `TPESampler(multivariate=True, group=True)` |
| Optuna | `random` | any | `RandomSampler` |
| Optuna | `tpe` | any | `TPESampler(multivariate=True, group=True)` |
| Optuna | `cmaes` | explicit only | `CmaEsSampler` |
| Ray | `auto` | samples below 10 | `BasicVariantGenerator` |
| Ray | `auto` | samples at least 10 | `OptunaSearch` |
| Ray | `random` | any | `BasicVariantGenerator` |
| Ray | `tpe` | any | `OptunaSearch` |
| Ray | `cmaes` | any | rejected |

`AutoHINT + Optuna` is rejected for the pinned NeuralForecast runtime. The installed
runtime inventory remains the source of truth for model/backend availability.

## Fallback contract

Fallback is disabled by default. Dependency absence or an unsupported policy raises
before model training. When `allow_fallback=true` is explicitly configured, the model
may delegate to the library default, but the effective decision must record:

- `fallback_used=true`;
- `effective_algorithm_name=library_default`;
- a non-empty fallback reason.

A fallback run is not equivalent to the requested search policy and must be grouped
separately in comparisons.

## Evaluation boundary

The internal AutoModel objective remains its configured validation loss. Formal model
selection must evaluate frozen OOF and Holdout predictions with:

- Hit@±1 as the primary metric;
- MAE, MSE, RMSE;
- position-level and all-position Hit@±1;
- multiple seeds with mean, variance, and worst value;
- random, fixed, mean, median, last-value, frequency, and statistical baselines.

No Prospective result may influence search-policy selection. Prospective predictions
must be SHA-256 locked with a timestamp before actual values are known.

## Follow-up work

A separate stacked change will profile Ray domains and Optuna define-by-run spaces,
classify continuous/integer/categorical/conditional dimensions, and decide whether a
sampler is eligible. CMA-ES is never selected automatically by this foundation policy.
