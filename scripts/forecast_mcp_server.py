"""Run the TAJ-69 Forecast MCP Streamable HTTP server.

The MCP SDK is intentionally runtime-separated from the repository root lock.
Use the exact reviewed MCP runtime lane documented in docs/FORECAST_MCP.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from loto.forecast_mcp.contracts import ForecastToolRequest  # noqa: E402
from loto.forecast_mcp.service import ForecastMcpService, load_config  # noqa: E402

_SERVICE: ForecastMcpService | None = None

mcp = FastMCP(
    "Loto Forecast MCP",
    stateless_http=True,
    json_response=True,
)


def _service() -> ForecastMcpService:
    if _SERVICE is None:
        raise RuntimeError("Forecast MCP service has not been configured")
    return _SERVICE


@mcp.tool()
def forecast_status() -> dict[str, object]:
    """Read the bounded Forecast MCP route and live Qwen/GPU readiness without mutation."""

    return _service().status()


@mcp.tool()
def forecast(
    game: Literal["numbers3"] = "numbers3",
    model: Literal["moirai2"] = "moirai2",
    horizon: Literal[1] = 1,
    device: Literal["cuda"] = "cuda",
    scope: Literal["development"] = "development",
) -> dict[str, object]:
    """Run the single approved development-only Moirai-2 Numbers3 CUDA forecast route."""

    request = ForecastToolRequest(
        game=game,
        model=model,
        horizon=horizon,
        device=device,
        scope=scope,
    )
    return _service().forecast(request)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the bounded Loto Forecast MCP server")
    parser.add_argument("--config", required=True, type=Path)
    return parser


def main() -> int:
    global _SERVICE
    args = build_parser().parse_args()
    config = load_config(args.config)
    _SERVICE = ForecastMcpService(config)
    mcp.run(
        transport="streamable-http",
        host=config.server.host,
        port=config.server.port,
        streamable_http_path="/mcp",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
