# Verification report

## Status

`PARTIALLY_VERIFIED / SEVEN_PINNED_CPU_MODELS_VERIFIED / ISOLATED_LOCK_BLOCKED`

## Revisions

- project base: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- previous PR head: `c5145e49e220ee11a88bbdd03ceafcf07756e9d2`;
- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`.

## TimeFilter source closure

- model: `ff952b4a7741ad2772fde3e41b0d97bc2bbe7e19`;
- graph layers: `437c3bfd135c2d2b907c7332311ac553c8a2d523`;
- normalization: `990d0fdc17751b724354e70b89fd6d3ff0f4dd29`;
- embedding: `977e25568d37b9dd0efd442dcc5b33eab9843d71`.

All four identities were verified. A separately modified embedding dependency was
rejected before construction with provider exit code two.

## Formal CPU runtime

Configuration: sequence `8`, horizon `2`, channels `3`, width `8`, heads `2`,
feed-forward width `16`, patch length `2`, one graph block, `alpha=0.1`, `top_p=0.5`.

- construction: `PASS`;
- three bounded fit steps: `PASS`;
- losses `0.0600307249`, `0.0568433367`, `0.0539623499`;
- prediction shape `[2, 2, 3]`: `PASS`;
- finite prediction/state: `PASS`;
- parameter count `586`: formula match;
- mask shape `[12, 3, 12]`: `PASS`;
- mask region sizes `2`, `3`, and `6`: `PASS`;
- fit PID `56652`, load PID `56676`: separate processes;
- strict state load: `PASS`;
- prediction SHA `2270fb92bcfb02ffa8fd4c8203dc4f33438b4b029d0c2be39cd4678775824850`;
- maximum absolute roundtrip error `0.0`: `PASS`.

Six real pinned-source geometry cases passed. Coverage includes sequence lengths 4 to
24, patch lengths 2 to 6, one to seven channels, two to six heads, one to three graph
blocks, identity gating, noisy gating, finite state, graph-mask counts, and exact
parameter formulas.

## Focused validation

- provider contract: `6 passed`;
- FreTS: `7 passed`;
- SCINet: `7 passed`;
- SegRNN: `8 passed`;
- TimeFilter: `7 passed`;
- split focused total: `35 passed`;
- compileall: `PASS`;
- 100-character Python line policy: `PASS`;
- Ruff: `NOT_AVAILABLE_IN_EXECUTION_ENVIRONMENT`.

Dedicated TSMixer and LightTS test files were not present in this local publication
stage, so this increment does not claim that they were rerun. Their previously
published evidence is retained unchanged.

## Blocked and unclaimed

- isolated Torch 2.9.1 lock: blocked by offline cache/network limits;
- PAttn: missing `reformer_pytorch`;
- WPMixer: missing `pywt`;
- GitHub Actions: `CI_BLOCKED_PRE_RUN` from prior runs;
- GPU, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, baseline superiority, and merge
  readiness: not executed or not claimed.
