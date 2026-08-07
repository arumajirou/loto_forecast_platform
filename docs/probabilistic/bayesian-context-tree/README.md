# Bayesian Context Tree PR-A

Status: `CONTRACT_ONLY / MODEL_RUNTIME_NOT_IMPLEMENTED / ACTIVE_CATALOG_REGISTRATION=false`.

This directory defines the PR-A boundary for logical model ID
`pp-bayesian-context-tree`. PR-A adds provenance, a clean-room license boundary,
strict Pydantic contracts, an inactive configuration, and focused contract tests.
It does not implement a context tree, posterior update, inference, persistence,
runtime certification, catalog registration, backend dispatch, or forecasting
accuracy.

## Upstream facts

The public Bayesian Context Trees work addresses exact Bayesian inference for
discrete time series and describes CTW, MAP BCT, and top-k BCT operations. The
current CRAN `BCT` package is implemented with R, Rcpp, and C++ and is licensed
GPL-2-or-later. The standalone historical C++ repository did not expose a
confirmed license in the PR-A investigation. There is no checkpoint and no
confirmed Hugging Face model repository; `HF_REPO=UNKNOWN`.

## Project design

The project design is a future independent Python implementation based on the
paper and public API behavior, not a translation of upstream source. The formal
native target is one-step categorical prediction for a per-position univariate
series on CPU. Horizons 2 and 5 are future project extensions through recursive
rollout. A shared model is optional and is not the default.

## Non-claims

- No upstream R or C++ source was copied.
- No mathematical kernel exists in PR-A.
- No suffix tree, posterior update, or inference exists in PR-A.
- No catalog row or native registry row exists in PR-A.
- No runtime, GPU, Holdout, Prospective, or accuracy result is claimed.
