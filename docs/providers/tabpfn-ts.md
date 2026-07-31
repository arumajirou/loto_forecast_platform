# TabPFN-TS Provider Research (Phase 1)

Status: research complete. This document is the evidence record required before any
adapter/provider code is written for the `tabpfn-ts` catalog model. All facts below were
confirmed by fetching the actual PyPI package metadata, the actual `tabpfn` /
`tabpfn_time_series` source, and the actual Hugging Face repo/license text — not from
memory or assumption. Access date for every external source below: **2026-07-31**.

## 1. Package identity

- Distribution: [`tabpfn-time-series`](https://pypi.org/project/tabpfn-time-series/) —
  version **1.2.0** on PyPI (confirmed via PyPI JSON API,
  `https://pypi.org/pypi/tabpfn-time-series/json`, accessed 2026-07-31).
- Import module: `tabpfn_time_series`.
- Source repo: `https://github.com/PriorLabs/tabpfn-time-series`.
- `requires_python`: `>=3.10`.
- Main user-facing entry point: `tabpfn_time_series.pipeline.TabPFNTSPipeline`, method
  `predict_df(context_df, future_df=None, prediction_length=None, quantiles=DEFAULT_QUANTILE_CONFIG)`.
  Exactly one of `future_df` / `prediction_length` is required. `context_df` needs
  `timestamp`, `target`, optional `item_id` columns; any additional columns are treated as
  known covariates.
- Lower-level API: `tabpfn_time_series.predictor.TimeSeriesPredictor`, with a
  `TabPFNMode` enum (`LOCAL` vs `CLIENT`). `LOCAL` mode selects
  `GPUParallelWorker`/`CPUParallelWorker` based on `torch.cuda.is_available()`; CPU
  inference is functional but the package itself emits a `UserWarning` that it is slow.
- Direct runtime dependencies declared by `tabpfn-time-series==1.2.0`
  (`requires_dist` from the PyPI JSON metadata):
  `backoff>=2.2.1`, `datasets>=2.15`, `fev>=0.6.1`, `gluonts>=0.16.0`,
  `pandas>=2.1.2`, `python-dotenv>=1.1.0`, `pyyaml>=6.0.1`, `statsmodels>=0.14.5`,
  `tabpfn-client>=0.2.8`, `tabpfn-common-utils[telemetry-interactive]>=0.2.2`,
  `tabpfn>=8.0.0`, `tqdm`. An optional `benchmarking` extra additionally pulls
  `autogluon-timeseries>=1.5.0,<2.0` — not needed for zero-shot prediction and will not be
  installed in `environments/tabpfn-ts/`.
- `tabpfn_client` is imported **unconditionally** at the top of
  `tabpfn_time_series/worker/model_adapters/tabpfn_adapter.py`, even though this provider
  only ever runs in `LOCAL` mode — it must stay in the environment's dependency set even
  though it is never invoked.

## 2. Underlying `tabpfn` package

- Distribution: [`tabpfn`](https://pypi.org/project/tabpfn/) — version **8.2.0** on PyPI
  (confirmed via `https://pypi.org/pypi/tabpfn/json`, accessed 2026-07-31).
- `requires_python`: `>=3.10`. Key deps: `torch>=2.5`, `safetensors>=0.4.0`,
  `numpy>=1.21.6`, `scikit-learn>=1.2.0`, `huggingface-hub>=0.23.0`, `pydantic>=2.8.0`,
  `lightgbm>=3.0`.
- The PyPI package metadata's own `license` field embeds the *source code* license text:
  "Prior Labs License (Apache 2.0 with ADDITIONAL PROVISION), **Version 1.2, Dec 2025**".
  This governs the `tabpfn` Python source code itself and is a separate document from the
  *model weights* licenses discussed below (each weight repo on Hugging Face carries its
  own, independently versioned license file).

### 2.1 Two independent weight sources exist, with two different licenses

`tabpfn.model_loading` resolves checkpoints per `ModelVersion` and only gates
`V2_5`, `V2_6`, and `V3` behind an interactive browser license-acceptance flow
(`ensure_license_accepted`, in `tabpfn/browser_auth.py`) — confirmed by reading the
`_HF_REPOS` gated-repo dict directly:

```python
_HF_REPOS = {
    ModelVersion.V2_5: "tabpfn_2_5",
    ModelVersion.V2_6: "tabpfn_2_6",
    ModelVersion.V3: "tabpfn_3",
}
if version in _HF_REPOS:
    from tabpfn.browser_auth import ensure_license_accepted
    ensure_license_accepted(hf_repo_id=_HF_REPOS[version])
```

`ModelVersion.V2` (the original TabPFN v2 regressor/classifier) is **not** in this dict
and requires no license-acceptance flow.

**Option A — default V3 timeseries checkpoint** (what `tabpfn_time_series` uses if no
`model_path` override is given, via `defaults.py`'s `resolve_default_ckpt`):
- HF repo: `Prior-Labs/tabpfn_3`, file `tabpfn-v3-regressor-v3_20260506_timeseries.ckpt`.
- License: **TABPFN-3 Non-Commercial License** (fetched from the repo's `LICENSE.txt`,
  saved to `/tmp/tabpfn3_license.txt`, accessed 2026-07-31). Explicitly
  non-commercial/non-production only: *"freely available for your non-commercial and
  non-production use"*; *"You may only ... use ... the TABPFN-3 Model ... for
  Non-Commercial Purposes"*; commercial/production use requires a separate paid license
  from Prior Labs (`sales@priorlabs.ai`).
- Access requires completing `ensure_license_accepted()`, which opens a browser-based
  OAuth-style flow (`tabpfn/browser_auth.py`) or accepts a pre-obtained `TABPFN_TOKEN`
  environment variable. In this sandbox: no TTY (`try_browser_login()` returns `None`
  immediately when `not sys.stdin.isatty()`), no `TABPFN_TOKEN` available — this path is
  **not completable** here.
- **Conclusion: rejected.** Both the license terms (non-commercial-only, unsuitable for a
  platform doing more than internal benchmarking) and the technical gate (interactive
  browser auth, impossible in a non-interactive sandbox) rule this checkpoint out.

**Option B — V2 regressor checkpoint (chosen)**:
- HF repo: `Prior-Labs/TabPFN-v2-reg`, file `tabpfn-v2-regressor.ckpt` (alternates also
  present: `tabpfn-v2-regressor-v2_default.ckpt`, and seed-specific variants). Repo
  metadata confirmed via `https://huggingface.co/api/models/Prior-Labs/TabPFN-v2-reg`
  (accessed 2026-07-31): `"gated": false`, `"sha": "4972a65a1b30806315c6f92499959ffbfc69a673"`,
  `"license": "other"`, `"license_name": "priorlabs-1-1"`.
- License: **Prior Labs License, Version 1.1, May 2025** (fetched from
  `huggingface.co/Prior-Labs/TabPFN-v2-reg/resolve/main/LICENSE.txt`, accessed
  2026-07-31). This is an **Apache-2.0 derivative** with a single addition (Section 10:
  attribution — "Built with PriorLabs-TabPFN" plus a "TabPFN"-prefixed name for any
  distributed derived model — required only on external distribution; the license text
  explicitly exempts "internal benchmarking and testing without external communication").
  **Commercial use is permitted**; there is no non-commercial restriction anywhere in this
  document.
- Not gated: `ModelVersion.V2` is absent from `_HF_REPOS`, so `resolve_regressor_v2()` /
  `download_model()` runs with no `ensure_license_accepted()` call and no browser flow.
- **Conclusion: adopted.** This is a real, officially-supported configuration path, not a
  substitute model: `tabpfn_time_series.worker.model_adapters.tabpfn_adapter.TabPFNModelAdapter._init_local_tabpfn_regressor`
  reads whatever `model_path` string is present in the config dict and resolves it through
  `tabpfn.model_loading.resolve_model_path` / `download_model` — the same code path used
  for the default checkpoint, just pointed at a different, ungated, permissively-licensed
  file of the same TabPFN regressor family. Confirmed by reading
  `tabpfn_time_series/defaults.py` (`resolve_default_ckpt` only fills `model_path` when
  absent/`None`; a caller-supplied value passes through unchanged) and
  `tabpfn_time_series/worker/model_adapters/tabpfn_adapter.py` in full.

**Design decision for the provider**: construct
`TabPFNTSPipeline(tabpfn_mode=TabPFNMode.LOCAL, tabpfn_model_config={"model_path": "tabpfn-v2-regressor.ckpt"}, ...)`
so the provider downloads and uses the ungated, commercially-licensed V2 regressor
checkpoint instead of the default gated, non-commercial V3 timeseries checkpoint. The
provider's `properties.license` field must record `Prior Labs License 1.1` (commercial use
permitted, attribution required only on external distribution) — distinct from, and not to
be confused with, the rejected V3 checkpoint's non-commercial license.

## 3. Runtime characteristics relevant to the adapter design

- `max_context_length` default: 32768 (practical ceiling documented around 65536).
- Forecast horizon: flexible, via `prediction_length` (int) or an explicit `future_df`.
- Multivariate series are decomposed into independent univariate series by the pipeline;
  known-future covariates are supported as extra `context_df`/`future_df` columns.
- `.fit()`-equivalent behavior: TabPFN is an in-context-learning tabular foundation model —
  there is no gradient-based training step; "fitting" only caches the context rows that are
  then used as the in-context example set at prediction time. Consistent with how other
  foundation models in this catalog are classified, this means the model can only ever
  reach `ZERO_SHOT_PASS`, never `PASS`.
- CPU execution is functional (confirmed by package's own code path — `CPUParallelWorker`
  is a first-class, non-experimental option in `_select_local_worker_class()`), but slow;
  GPU is preferred when available. Device honesty fields (`requested_device`,
  `execution_device`, `cuda_available`, `gpu_used`) must be recorded regardless of which is
  used, per the platform's existing GPU-evidence contract.

## 4. Dependency footprint for `environments/tabpfn-ts/pyproject.toml`

`tabpfn-time-series==1.2.0` (pinned) pulling in `tabpfn==8.2.0`, plus:
`tabpfn-client>=0.2.8`, `tabpfn-common-utils[telemetry-interactive]>=0.2.2`,
`torch>=2.5`, `gluonts>=0.16.0`, `datasets>=2.15`, `fev>=0.6.1`, `backoff>=2.2.1`,
`python-dotenv>=1.1.0`, `pyyaml>=6.0.1`, `statsmodels>=0.14.5`, `pandas>=2.1.2`,
`tqdm`, `huggingface-hub>=0.23.0`. Python constraint: `>=3.10,<3.13` (matching the other
per-model environments in this repo, and satisfying `tabpfn-time-series`'s own
`>=3.10` floor).

## 5. Sources consulted (URL / accessed date / version)

- `https://pypi.org/pypi/tabpfn-time-series/json` — 2026-07-31 — package version 1.2.0.
- `https://pypi.org/pypi/tabpfn/json` — 2026-07-31 — package version 8.2.0.
- `https://raw.githubusercontent.com/priorlabs/tabpfn/main/src/tabpfn/browser_auth.py` — 2026-07-31.
- `https://raw.githubusercontent.com/priorlabs/tabpfn/main/src/tabpfn/model_loading.py` — 2026-07-31.
- `https://huggingface.co/api/models/Prior-Labs/TabPFN-v2-reg` — 2026-07-31 — repo sha
  `4972a65a1b30806315c6f92499959ffbfc69a673`.
- `https://huggingface.co/Prior-Labs/TabPFN-v2-reg/resolve/main/LICENSE.txt` — 2026-07-31 —
  Prior Labs License, Version 1.1, May 2025.
- TABPFN-3 Non-Commercial License text (from the gated `Prior-Labs/tabpfn_3` repo) — 2026-07-31.
- `tabpfn_time_series` package source (`pipeline.py`, `predictor.py`, `defaults.py`,
  `worker/model_adapters/tabpfn_adapter.py`, `worker/model_adapters/base.py`) extracted
  from the sdist/wheel — 2026-07-31 — version 1.2.0.

## 6. Phase 2 adapter design (resolved)

The catalog entry for `tabpfn-ts` (`catalog.py` line ~198) has
`task="candidate"`, `library="tabpfn_time_series"`. Three independent dispatch
systems exist in `scripts/all_model_runtime_validation.py`'s `main()`:
`task="candidate"` → `run_candidate_lifecycle` (in-process sklearn, `RuntimeModel`),
`task="foundation"` → `run_foundation_lifecycle` (subprocess-provider based, shape
`(7,)`), `task in {"position","position_series","candidate_series"}` →
`run_worker_lifecycle` (in-process pickle-based reload/retrain).

`run_worker_lifecycle` was ruled out: although it validates
`output.candidate_probabilities` generically for `task in {"candidate",
"candidate_series"}`, its reload/retrain paths import and pickle the target
library directly in the main process (neuralforecast, statsforecast, mlforecast,
lag_regression, reservoirpy_esn, darts_ensemble, gluonts_deepar,
autohint_fixed). `tabpfn_time_series` must stay isolated in its own uv
environment per rule 6, and cross-environment pickling is forbidden per rule 7,
so this branch cannot be used regardless of the catalog `task` value.

**Adopted design: subprocess-provider architecture** (the same shape used by
`run_foundation_lifecycle`/`FoundationProvider`/`environments/tirex/` etc.),
wired into a new, parallel `task="candidate"` dispatch branch rather than the
existing `run_candidate_lifecycle`:

- **Series construction** — mirrors `PositionSeriesWorker._candidate_series_frame()`
  in `workers.py`: build 37 independent one-hot series, one per candidate number
  1–37, each row `item_id=f"candidate-{candidate:02d}"`, `timestamp=draw_date`,
  `target=float(candidate in selected_numbers)`, across all historical draws in
  `context_df`. This is a single multivariate `predict_df` call keyed by
  `item_id` (not 7 independent per-position calls) — a candidate-probability
  model, not a per-position model, matching how every other `task="candidate"`
  model in the catalog is scored. `prediction_length=1` supplies the next-draw
  point forecast per candidate.
- **Probability mapping** — the pipeline returns one continuous regression score
  per candidate `item_id` (TabPFN-v2-reg has no native `[0,1]` output
  constraint). These 37 raw scores are passed through the platform's existing
  `normalize_worker_predictions()` (`workers.py` lines 129-156): clip to
  non-negative, scale to sum to 7.0 (uniform `7/37` fallback if all-zero). This
  is the same normalization every other candidate-probability model in the
  catalog uses — no new probability-mapping logic is introduced.
- **Leakage prevention** — `context_df` is built only from `master.iloc[:-1]`
  (all draws strictly before the one being predicted), matching
  `run_candidate_lifecycle`'s `build_candidate_features(master.iloc[:-1]...)`
  and every foundation provider's context-construction pattern. No calendar or
  covariate feature derived from the held-out draw is ever passed to the
  pipeline.
- **New code, following existing per-model templates 1:1**:
  - `environments/tabpfn-ts/{pyproject.toml,uv.lock,README.md,provider-contract.md}`
    — cloned from `environments/tirex/`; `provider-contract.md` documents
    `prediction_shape: [37]` request/response semantics instead of `[7]`.
  - `src/loto/models/providers/tabpfn_ts.py` — `TabPFNTSProvider(FoundationProvider)`,
    cloned from `providers/tirex.py`; `predict()` reshapes to `(37,)`.
  - `scripts/run_tabpfn_ts_provider.py` — subprocess runner, cloned from
    `scripts/run_tirex_provider.py`; internally builds the 37-series one-hot
    frame described above, downloads/loads the V2 regressor checkpoint
    (`Prior-Labs/TabPFN-v2-reg`, `tabpfn-v2-regressor.ckpt`), records
    `properties.license = "Prior Labs License 1.1"` (commercial use permitted,
    attribution required only on external distribution — see section 2.1
    Option B above) and honest `gpu_evidence`.
  - `src/loto/models/providers/registry.py` — register
    `"tabpfn-ts": TabPFNTSProvider` in `FOUNDATION_PROVIDERS`, keyed by
    `model_id` exactly like `chronos-2-small`/`chronos-bolt-tiny`.
  - `scripts/all_model_runtime_validation.py` — new
    `run_foundation_candidate_lifecycle()`, cloned from `run_foundation_lifecycle()`
    with the 3 `(7,)`/`.reshape(7)` hardcode points changed to `(37,)`/
    `.reshape(37)`, additionally computing `candidate_metrics()` /
    `validate_candidate_probabilities()` against the held-out draw the same way
    `run_candidate_lifecycle` does. `main()`'s dispatch gains a
    `FOUNDATION_CANDIDATE_LIBRARIES = {"tabpfn_time_series"}` set; the
    `if not spec.available and spec.task != "foundation"` gate is broadened to
    also exempt `spec.library in FOUNDATION_CANDIDATE_LIBRARIES`, and a new
    `elif spec.task == "candidate" and spec.library in FOUNDATION_CANDIDATE_LIBRARIES`
    branch is inserted before the existing generic `elif spec.task ==
    "candidate"` branch, so sklearn-based candidate models are unaffected.
- Since TabPFN-TS is in-context-learning only (no gradient training step; see
  section 3), the model can only ever reach `ZERO_SHOT_PASS`, never `PASS` —
  matching every other foundation model in the catalog.
