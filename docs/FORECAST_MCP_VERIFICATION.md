# Forecast MCP verification record

## Verification planes

`SOURCE_GATES_VERIFIED=PASS` and
`TARGET_MACHINE_E2E_VERIFIED=NOT_ASSERTED_BY_SOURCE` are deliberately different
claims. Passing source checks or GitHub CI does not certify the target GPU route.

- Merge prerequisite: PR #389 merged to `main` as `c1f4ddb1f14cafbee948a5697dac2f407c2b8e4c`.
- Implementation PR: #390 (`feat/taj-69-forecast-mcp-bridge`), replayed onto that
  merged `main` with only Forecast MCP changes; the already-merged #389 Windows
  portability workflow remains supplied by `main`.
- Runtime lane: the frozen isolated `environments/forecast-mcp` project. It is not
  added to the repository-root lock and it remains separate from Memory MCP.
- Forecast route: loopback-only `http://127.0.0.1:18778/mcp`, exactly the bounded
  development-only Numbers3/Moirai-2 CUDA request documented in `FORECAST_MCP.md`.
- Holdout: `CLOSED`; Prospective: `CLOSED`; Actual access: `FALSE`.

## Source gates

The post-replay source gate completed successfully with the repository's frozen
development extra:

```text
uv run --frozen --extra dev ruff format --check <Forecast-MCP paths>
uv run --frozen --extra dev ruff check <Forecast-MCP paths>
uv run --frozen --extra dev python -m compileall -q <Forecast-MCP paths>
uv run --frozen --extra dev pytest -q tests/forecast_mcp \
  tests/gpu_exclusive/test_supervisor.py \
  tests/adapters/moirai2/test_adapter.py \
  tests/moirai2_campaign/test_certify_runtime_lane.py \
  tests/moirai2_campaign/test_p8_runner_fake_boundary.py
git diff --check
```

The exact final PR #390 head still requires one successful full repository CI run.
The six-case P8 CUDA campaign is intentionally not rerun here: this replay does not
change the certified #389 runtime lock, provider, supervisor, or Moirai model identity.

## Target-machine E2E boundary

Only fresh external evidence bound to the final PR #390 source head may set
`END_TO_END_FORECAST_KPI=PASS`. It must show one forecast flowing from OpenCode
through the selected local Qwen and this Forecast MCP endpoint, through the GPU
Exclusive Supervisor, to `Salesforce/moirai-2.0-R-small` at revision
`30f43ff08c8494f4943ae1521e9d4e94a0fbb389` on the RTX 5070 Ti. The evidence must
also bind a finite `[1, 3]` prediction and its SHA-256, `cpu_fallback=false`, return
the same result to the same selected LLM and OpenCode display, and finish with that
exact Qwen restored and the request gate `OPEN`.

That external target verification remains isolated from this source record; it cannot
be inferred from CI, source tests, or the frozen Forecast MCP lock.
