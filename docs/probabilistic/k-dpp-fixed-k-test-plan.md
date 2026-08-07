# k-DPP fixed-cardinality PR-A test plan

## Focused contract tests

- unknown fields fail closed
- model ID, graph ID, model revision, and schema version are fixed
- SHA-256 and Git revision formats are strict
- NaN and infinity are rejected
- horizons are limited to 1, 2, and 5
- CPU-only device evidence and null GPU fields are enforced
- `actuals_used=false` is enforced
- Numbers3/4 use position-qualified item identity
- MiniLoto, Loto6, and Loto7 cardinalities are fixed
- kernel shape equals item count
- cardinality is smaller than candidate count
- PSD repair defaults to `REJECT`
- quantiles are unsupported
- artifact paths are safe relative POSIX paths
- config hashing is deterministic
- the model skeleton fails closed for fit, predict, save, and load

## Existing regression targets

The following existing tests must remain green when a complete checkout is available:

- `tests/probabilistic/test_ppl02_math_foundation.py`
- `tests/probabilistic/test_ppl02_conditional_bernoulli.py`

PR-A does not duplicate the exact sampler, PSD implementation, or elementary-symmetric
normalizer. PR-B will add real kernel preparation, sampling, marginal inclusion probabilities,
state persistence, and separate-process replay tests.
