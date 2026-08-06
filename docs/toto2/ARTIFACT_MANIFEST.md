# Artifact manifest

Owned paths remain limited to:

- `environments/toto2-4m-py312/**`
- `scripts/run_toto2_4m_provider.py`
- `scripts/run_toto2_4m_isolated.py`
- `scripts/certify_toto2_4m_runtime.py`
- `src/loto/adapters/toto2_4m/**`
- `src/loto/toto2_campaign/**`
- `tests/adapters/toto2_4m/**`
- `tests/toto2_campaign/**`
- `configs/toto2_campaign/**`
- `docs/toto2/**`

Runtime outputs are expected under `artifacts/toto2-4m-runtime/<RUN_ID>/` and are not committed by
this change. The lock-candidate bootstrap writes review evidence under
`artifacts/toto2-4m-lock-candidate/<RUN_ID>/`.

No model weights, raw data, predictions, secrets, root dependency changes, shared provider
registration, common CLI, top-level README, or workflow changes are included.
