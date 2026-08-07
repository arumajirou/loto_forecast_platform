# TiRex-2 runbook

Use the dedicated Python 3.12 environment. Set `HF_HOME` or `HF_HUB_CACHE` to the trusted cache
root containing the pinned snapshot. The runner accepts `--request` and `--response`; output is
written atomically. A CUDA request fails when CUDA is unavailable instead of falling back.

Do not enable network model resolution: `local_files_only=true` is mandatory. Do not treat the
reference manifest as model serialization. Preserve request, response, environment lock hash,
model hashes, logs, process evidence, and exit code for each run ID.

Run the reload gate with `python -m loto.tirex2_campaign.runtime_certification` and explicit
`--request`, `--output-root`, and `--provider-script` arguments. A provider or certification
failure returns a non-zero process exit code after preserving structured JSON evidence.
