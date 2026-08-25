# Forecast MCP isolated runtime

This is the dedicated runtime for the loopback-only TAJ-69 Forecast MCP server. It is separate
from the repository root lock and from Memory MCP, which remains on its own MCP v1 lane.

- Python: `>=3.11,<3.13`
- MCP SDK: `mcp==2.0.0`
- Pydantic: `pydantic==2.13.4`
- Transport: Streamable HTTP at `127.0.0.1:18778/mcp`

Create a user-owned target venv strictly from the committed lock:

```bash
env UV_PROJECT_ENVIRONMENT=/home/az/.local/share/loto-forecast-mcp/.venv \
  uv sync --frozen --project /absolute/path/to/loto_forecast_platform/environments/forecast-mcp
```

Validate the lock without changing it:

```bash
uv lock --check --project /absolute/path/to/loto_forecast_platform/environments/forecast-mcp
```

The lock captures dependency integrity only. It does not certify the target host, forecast
runtime, accuracy, Holdout, Prospective, or actual data access.
