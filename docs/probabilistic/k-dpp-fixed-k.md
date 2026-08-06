# k-DPP fixed-cardinality PR-A

## Status

`PARTIALLY_VERIFIED / PR_A_IMPLEMENTED / RUNTIME_PENDING`

This document defines the private contract foundation for `pp-k-dpp-fixed-k`. PR-A does not
register the model in the public probabilistic catalog or native registry and does not claim a
working fit, prediction, persistence, or runtime certification path.

## Provenance and mathematical boundary

The implementation reuses the existing project-owned exact mathematical modules:

- `loto.probabilistic.math.kdpp`
- `loto.probabilistic.math.psd`
- `loto.probabilistic.math.elementary_symmetric`
- `loto.probabilistic.math.logspace_dp`

No DPPy runtime dependency is introduced. The model revision is `k_dpp_fixed_k_v1`, the graph ID
is `k_dpp_fixed_k_v1`, and the code license field is `MIT`.

## Conditional Bernoulli comparison

Conditional Bernoulli fixed-k uses

```text
P(S | |S|=k) proportional to product(i in S) w_i
```

It conditions independent item log-weights on fixed cardinality and does not directly represent
pairwise diversity.

k-DPP uses

```text
P(S | |S|=k) proportional to det(L_S)
```

where `L` is a positive-semidefinite L-ensemble kernel. Its diagonal represents quality while its
geometry can represent similarity and diversity. A diagonal `L` degenerates to the Conditional
Bernoulli fixed-k law. The response contract therefore records `kernel_off_diagonal_norm`,
`kernel_off_diagonal_ratio`, and `DEGENERATE_TO_CONDITIONAL_BERNOULLI`.

## Explicit non-claims

- public catalog registration: not implemented
- native registry registration: not implemented
- real fit or prediction: not executed
- state save/reload: not implemented
- runtime certification: not executed
- OOF, Holdout, or Prospective evaluation: not executed
- Hit@±1 or baseline superiority: not measured
- GPU execution: not applicable to the initial CPU analytic lane
- merge readiness: not established
