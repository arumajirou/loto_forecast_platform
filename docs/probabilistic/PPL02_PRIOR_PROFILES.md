# PPL-02 Batch 9 — Prior Profile Contract

## Scope

Batch 9 adds `r2d2` and `spike_slab` as **prior profiles**, not model IDs. The structural model ID remains unchanged, preventing catalog inflation and avoiding false comparisons between identical likelihood structures that differ only in prior choice.

The initial Batch 9 scope is deliberately limited to:

- validated configuration schema;
- registry loading and duplicate detection;
- backend and exogenous-feature compatibility gates;
- deterministic mathematical toy verification;
- execution fingerprint coverage;
- fail-closed planning.

Applying either profile to every exogenous PyMC or NumPyro model is P1 work and is not claimed here.

## Configuration

```yaml
model_id: pp-multinomial-logit-normal
prior_profile: r2d2
```

Registry definitions:

```yaml
prior_profiles:
  r2d2:
    family: r2d2
    r2_alpha: 1.0
    r2_beta: 4.0
    allocation: dirichlet
  spike_slab:
    family: spike_slab
    inclusion_probability: 0.1
    slab_scale: 1.0
```

The runtime registry is `src/loto/probabilistic/data/prior_profiles.yaml`.

## R2-D2 toy contract

The toy verifier samples:

1. `R² ~ Beta(r2_alpha, r2_beta)`;
2. a symmetric Dirichlet allocation over exogenous coefficients;
3. total coefficient variance `R² / (1 - R²)`;
4. local variances whose sum equals the total variance;
5. zero-centred Gaussian coefficients using those local variances.

Acceptance checks cover finite values, allocation simplex validity, exact variance decomposition, deterministic replay, and consistency of the sampled mean R² with the configured beta prior.

## Spike-and-slab toy contract

The toy verifier samples explicit Bernoulli inclusion indicators and Gaussian slab coefficients. Excluded coefficients are exactly zero.

An orthogonal Gaussian normal-means toy model computes an exact posterior inclusion probability from the prior inclusion probability, slab scale, observation scale, and observed effect. This verifies that inclusion is explicit rather than being silently approximated by a continuous shrinkage prior.

## Compatibility and fail-closed behavior

`r2d2` and `spike_slab` require:

- a structural model declaring `supports_exogenous=true`;
- at least one exogenous feature;
- a declared PyMC or NumPyro backend.

Both profiles are marked `CONTRACT_ONLY` in Batch 9. Planning an experiment with either profile is therefore blocked with `PRIOR_PROFILE_CONTRACT_ONLY`; the runner must not silently fall back to a normal, Laplace, horseshoe, or unprofiled prior.

## Non-claims

- No new probabilistic model ID is added.
- No model accuracy improvement is claimed.
- No full PyMC/NumPyro model adapter is claimed.
- No profile is eligible for promotion from toy verification alone.
