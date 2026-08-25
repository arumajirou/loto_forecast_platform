# Forecast MCP bridge (TAJ-69)

## Status

`SOURCE_IMPLEMENTED / TARGET_MACHINE_E2E_PENDING / HOLDOUT_CLOSED / PROSPECTIVE_CLOSED`

This bridge exposes the existing forecast runtime to OpenCode through a deliberately small
Model Context Protocol surface. It does **not** create a second forecast engine.

Target flow:

```text
OpenCode
  -> selected local LLM
  -> Forecast MCP http://127.0.0.1:18778/mcp
  -> GPU Exclusive Supervisor
  -> pinned Moirai-2 provider
  -> prediction
  -> Qwen restore + gate reopen
  -> same selected LLM
  -> OpenCode
```

The Memory MCP remains a separate endpoint.

## Security boundary

The LLM-facing `forecast` tool accepts only:

- `game = numbers3`
- `model = moirai2`
- `horizon = 1`
- `device = cuda`
- `scope = development`

There is no LLM-facing command, shell, path, history file, Holdout, Prospective, or actual-access
parameter. Pydantic uses `extra="forbid"`, so an attempted extra field is rejected.

All filesystem paths and control-plane URLs are operator configuration. The approved provider
request is also operator-owned and must be accompanied by a manifest that states:

```json
{
  "schema_version": 1,
  "data_scope": "development",
  "actuals_used": false,
  "holdout_used": false,
  "prospective_used": false,
  "request_sha256": "<sha256-of-approved-request>"
}
```

The service verifies the manifest hash before the GPU supervisor can run.

## Pinned model route

- repository: `Salesforce/moirai-2.0-R-small`
- revision: `30f43ff08c8494f4943ae1521e9d4e94a0fbb389`
- geometry: Numbers3, positions `n1,n2,n3`, digits `0..9`
- horizon: `1`
- device: `cuda`
- local files only: `true`
- license lane: inherited from the reviewed Moirai-2 request contract

A route mismatch fails closed.

## MCP transport

Use the official MCP Python SDK v2 Streamable HTTP implementation. The v2 SDK supports the
2026-07-28 protocol and legacy handshake-era clients on the same endpoint.

Authoritative upstream:

- https://github.com/modelcontextprotocol/python-sdk
- https://pypi.org/project/mcp/2.0.0/

The source tree intentionally does not add MCP to the repository root `uv.lock`. The server is
an operator runtime and uses the isolated, frozen `environments/forecast-mcp` project. Its exact
top-level pins are `mcp==2.0.0` and `pydantic==2.13.4`; use `uv sync --frozen` against that
project. The committed lock makes the runtime reproducible, but target-machine acceptance remains
separate from source validation. Its committed review artifacts are explicitly automated
integrity/policy evidence only; they do not fabricate a human approval.

## Configuration

Copy `config/forecast_mcp.example.json` outside the repository and replace `<MODEL_ALIAS>` with
the exact currently approved llama-swap alias. Do not guess it.

The approved request and manifest are intentionally not committed because they bind the live
development snapshot and local frozen model snapshot.

## Start

Prepare the isolated runtime from its committed lock. The target installation may keep the venv in
user-owned application data while using the repository's immutable project and lock:

```bash
env UV_PROJECT_ENVIRONMENT=/home/az/.local/share/loto-forecast-mcp/.venv \
  uv sync --frozen --project /mnt/e/env/ts/loto_forecast_platform/environments/forecast-mcp
/home/az/.local/share/loto-forecast-mcp/.venv/bin/python \
  scripts/forecast_mcp_server.py \
  --config /home/az/.config/loto/forecast-mcp.json
```

The server binds only to loopback and exposes the Streamable HTTP endpoint at:

```text
http://127.0.0.1:18778/mcp
```

An example systemd user unit is provided at:

```text
deploy/systemd/loto-forecast-mcp.service.example
```

The example is inert; source installation does not enable or restart a target-machine service.
The default `/tmp/loto-gpu-exclusive.lock` is shared with every GPU Exclusive
Supervisor contender, so the example explicitly uses `PrivateTmp=false`. Do not
enable a private `/tmp` namespace unless every contender is configured to use the
same alternate shared lock directory.

## OpenCode

Current OpenCode remote-MCP configuration uses `type="remote"` and a Streamable HTTP URL.
Add the following entry to the existing `mcp` object without deleting other servers:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "loto-forecast": {
      "type": "remote",
      "url": "http://127.0.0.1:18778/mcp",
      "enabled": true,
      "timeout": 900000
    }
  }
}
```

Do not let an automated source PR overwrite the user's existing OpenCode configuration.

## Tool behavior

### `forecast_status`

Read-only. It checks:

- approved development request + SHA-256 manifest
- selected-Qwen reachability
- NVIDIA GPU snapshot
- exact route identity

It does not unload a model or run a forecast.

### `forecast`

The service:

1. revalidates the fixed tool request;
2. revalidates the approved development request and its SHA-256 manifest;
3. creates a unique Run ID and immutable run directory;
4. builds a fixed argument vector for `scripts/run_moirai2_provider.py`;
5. hands that vector to the existing `ExclusiveGpuSupervisor`;
6. requires Qwen to have been live before the handoff;
7. requires Qwen restore and gate reopen after the forecast;
8. validates exact model revision, output shape `[1,3]`, finite point values, CUDA execution,
   provider PID evidence, positive peak VRAM, and `cpu_fallback=false`;
9. hashes the prediction;
10. writes `FORECAST_MCP_RESULT.json`, `ARTIFACT_MANIFEST.json`, and `SHA256SUMS`.

The MCP layer does not legalize or alter the Moirai point forecast. Any downstream decoding or
lottery-domain post-processing requires a separately frozen scientific identity.

## Evidence boundary

The provider currently reports its CUDA PID and peak VRAM. Formal TAJ-69 target-machine
acceptance additionally requires independent external GPU PID/UUID correlation while the
provider is resident. That is intentionally **not** fabricated by the source bridge.

`END_TO_END_FORECAST_KPI=PASS` is allowed only after a target run proves the complete lineage:

```text
OpenCode selected provider/model
-> same LLM tool call
-> Forecast MCP
-> exact Moirai route
-> external RTX 5070 Ti PID/UUID/VRAM
-> finite prediction + prediction SHA-256
-> Qwen restored
-> gate OPEN
-> same prediction returned to same LLM
-> same prediction displayed in OpenCode
```

## Local focused checks

During source development run the focused checks before repository-wide CI:

```bash
uv run ruff check \
  src/loto/forecast_mcp \
  scripts/forecast_mcp_server.py \
  tests/forecast_mcp

uv run ruff format --check \
  src/loto/forecast_mcp \
  scripts/forecast_mcp_server.py \
  tests/forecast_mcp

uv run pytest -q tests/forecast_mcp
```

The source PR still requires the normal final repository CI gate.
