# Implementation status

## Verified in the build environment

- 28 bundled pytest regression tests pass.
- Python modules compile; shell scripts pass `bash -n`.
- YAML, JSON, requirements, and systemd user-unit validation pass.
- LM Studio and OpenAI-compatible adapters satisfy mocked API contracts.
- Chat/Responses/Messages streaming preserves SSE bytes.
- The context allocation totals exactly 65,536 tokens and protected-content loss is rejected.
- Uncertified native context is capped at 32,768 tokens; 64K remains virtual until live certification.
- Repeated identical loop failures trigger the rollback callback and bounded stop.
- SQLite memory is append-only; PostgreSQL/pgvector schema and implementation are included.
- Python AST code symbols and calls are indexed with source SHA-256.
- In-process GPU/CPU scheduling and cross-process advisory resource leases are implemented.
- Prometheus metrics avoid run/context SHA values as labels.
- Claude review/fix commands restrict available tools, validate path scope, and preserve evidence.
- Overlay application is backup-producing, idempotent, and preserves existing Claude instructions.

## Implemented but not live-certified

- LM Studio native model discovery, load, generation/embedding, unload, and context certification.
- llama.cpp process lifecycle, router profiles, KV/cache tuning, and speculative decoding experiments.
- PostgreSQL/pgvector store and MCP Streamable HTTP runtime.
- systemd and Docker Compose deployment.
- Claude Code execution.
- Hermes, OpenHands, Open WebUI, and AnythingLLM integrations.
- Grafana/Prometheus live dashboards.

## Not performed in the build environment

- access to `/mnt/e/env/ts/loto_forecast_platform`
- private repository full-suite tests
- Claude Code invocation (the executable/authentication are unavailable)
- Ruff and mypy (executables unavailable)
- GPU/model inference and 64K quality/VRAM tests
- GitHub push, pull request, or merge
