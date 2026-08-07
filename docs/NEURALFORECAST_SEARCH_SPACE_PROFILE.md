# NeuralForecast Search-Space Profile

## Status

`PROFILE_FOUNDATION / DRAFT / CAMPAIGN_PERSISTENCE_PENDING`

This change adds dependency-light evidence for the search space visible to a
NeuralForecast AutoModel plan. It does not change the sampler selected by the
search-policy foundation and does not claim an accuracy improvement.

## Planning states

Every profile has one explicit completeness state:

| State | Meaning |
|---|---|
| `COMPLETE` | A supplied static Ray-compatible dictionary or fixed configuration was fully inspected. |
| `PARTIAL` | An Optuna define-by-run callable was observed through deterministic probes; unvisited branches may remain. |
| `UNAVAILABLE` | The dependency-light plan delegated the official default space to the installed NeuralForecast runtime. |
| `FAILED` | A runtime configuration existed, but no probe completed successfully. |

An empty or unavailable space is never presented as a successfully inspected
official default.

## Dimension evidence

The profiler records observed dimensions as constant, categorical, integer, or
float. Numeric evidence includes bounds, inclusivity, step and log scaling when
available. It also records tunable and constant counts, whether different probes
observed different branches, finite combination counts when proven, and a stable
SHA-256 of the serialized profile.

## Backend behavior

Ray-compatible static dictionaries are inspected without importing Ray. Objects
with `categories`, or with numeric `lower` and `upper` attributes, are classified
from those public attributes. Integer upper bounds follow Ray's exclusive-bound
contract.

Optuna configurations are define-by-run callables. Low, middle and high recording
trials observe `suggest_float`, `suggest_int`, and `suggest_categorical` calls.
Because finite probes cannot prove that no other branch exists, a successfully
observed Optuna callable remains `PARTIAL`.

## Conservative eligibility evidence

The profile reports evidence only; it does not switch the effective sampler.

- Random and TPE require at least one supported tunable dimension.
- CMA-ES requires an Optuna backend, a `COMPLETE` profile, numeric dimensions,
  no categorical dimensions, and no conditional branch.
- Grid requires a `COMPLETE`, finite, non-conditional space within the configured
  combination limit.
- A fixed configuration has no tunable dimensions and is not treated as HPO.

## Adapter integration

The dependency-light planning adapter behaves as follows:

- explicit user configuration: profile as fixed and `COMPLETE`;
- empty configuration: record `UNAVAILABLE`, because the official model-specific
  default is delegated to the installed NeuralForecast runtime;
- constructed runtime model: attempt to inspect its resolved `config`, replacing
  the unavailable plan evidence when possible;
- attach the serialized profile to the model object for downstream persistence.

The atomic writer contract produces `SEARCH_SPACE_PROFILE.json` and
`SEARCH_SPACE_PROFILE.sha256`. Connecting those files to every database campaign
model directory is intentionally deferred to the next stacked PR so this review
remains independent of campaign execution and trial persistence.

## Evaluation boundary

Search-space evidence is not forecasting performance evidence. Random-versus-TPE
or other policy comparisons must retain identical chronological Train, Validation
and Holdout splits, official search spaces, trial budgets, resource limits and
multiple seeds. Formal reporting remains Hit@±1 first, with MAE, MSE, RMSE,
position-level and all-position Hit@±1, mean, variance, worst seed, and required
Random, fixed, mean, median, last-value, frequency and statistical baselines.

Scaler, encoder, feature selection and hyperparameter decisions must be fitted on
Train data only. Holdout and Prospective values must not influence the profile or
sampler decision. Prospective predictions remain SHA-256 and timestamp locked
before actual values are known.

## Runtime boundary

This profile is not runtime certification. Formal model success still requires
load, input, inference, output shape, finite values, device, GPU PID, VRAM,
training-worker evidence, reload inference, and no CPU fallback when GPU execution
is required.
