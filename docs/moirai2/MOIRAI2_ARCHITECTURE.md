# Moirai 2.0 Architecture

```text
caller
  -> Moirai2Adapter
  -> Pydantic Contract v2
  -> isolated uv runtime lane
  -> run_moirai2_provider.py
  -> pinned local Hugging Face snapshot
  -> Moirai2Module / Moirai2Forecast
  -> native quantile validator
  -> structured response and runtime evidence
```

The supported and CUDA13-experimental lanes are separate identities. Shared worker/catalog
integration is a later change. The old multi-provider audit branch is read-only provenance.
