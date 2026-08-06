# Verification report

## Status

`PARTIALLY_VERIFIED / EIGHT_PINNED_CPU_MODELS_VERIFIED / ISOLATED_LOCK_BLOCKED`

## Revisions

- project base: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- previous PR head: `edc0e2e84182fd3487a0b170af26dfe6ef848466`;
- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`.

## TiDE source identity

- model: `0fbb98ea159ec5aa5d7afed83eddaf4c2476eaf1`;
- SHA-256: `4ab07dec4ae85f8b7c3062ff7d2fec00be342968d41cf09e48d599d8e40f6143`.

The exact source was verified before import, construction, fit, and reload. A modified
fixture under the pinned policy was rejected before construction with provider exit
code two.

## TiDE certified contract

- long-term forecast only;
- encoder depth one;
- decoder depth one;
- dropout zero;
- feature encoder width two;
- internal zero time-feature tensors only;
- exact parameter formula checked before fit and reload;
- complete geometry persisted and recomputed before strict state loading.

Depths above one are rejected because the pinned source creates repeated blocks through
Python list multiplication, which aliases the same module object rather than creating
independent layers.

## Formal CPU runtime

Configuration: sequence `8`, horizon `2`, channels `3`, width `8`, temporal decoder
width `16`, frequency `h`, one encoder, one decoder, and three bounded fit steps.

- construction: `PASS`;
- losses `0.0662962869`, `0.0656846091`, `0.0650764778`;
- prediction shape `[2, 2, 3]`: `PASS`;
- finite prediction/state: `PASS`;
- parameter count `955`: formula match;
- fit PID `665`, load PID `689`: separate processes;
- strict state load: `PASS`;
- prediction SHA `d51c2f856473776711a6a0aff537b510d40b2427c428a81aa37f49397f55713a`;
- maximum absolute roundtrip error `0.0`: `PASS`.

Six real pinned-source geometry cases passed. Coverage includes sequence lengths 4 to
24, horizons 1 to 7, one to seven channels, widths 8 to 24, six frequency modes,
finite state, one-step fit, unique one-layer modules, and exact parameter formulas.

## Focused validation

- TiDE contract and checkpoint tests: `7 passed`;
- compileall: `PASS`;
- 100-character Python line policy: `PASS`;
- Ruff: `NOT_AVAILABLE_IN_EXECUTION_ENVIRONMENT`.

The previous TimeFilter publication retained a split focused total of `35 passed` for
provider, FreTS, SCINet, SegRNN, and TimeFilter tests. Those files were not rerun in this
TiDE authoring stage, so this report does not present `42` as one combined execution.
Previously published DLinear, TSMixer, LightTS, SegRNN, FreTS, SCINet, and TimeFilter
evidence remains unchanged.

## Blocked and unclaimed

- isolated Torch 2.9.1 lock: blocked by offline cache/network limits;
- Koopa: deferred because construction opens `data_provider(..., "train")`;
- PAttn: missing `reformer_pytorch`;
- WPMixer: missing `pywt`;
- GitHub Actions: `CI_BLOCKED_PRE_RUN` from prior runs;
- GPU, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, baseline superiority, and merge
  readiness: not executed or not claimed.
