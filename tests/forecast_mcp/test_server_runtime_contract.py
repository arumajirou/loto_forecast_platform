"""Keep the source entrypoint aligned with the isolated MCP v2 runtime lane."""

from pathlib import Path


def test_server_uses_mcp_v2_streamable_http_contract() -> None:
    source = (Path(__file__).parents[2] / "scripts" / "forecast_mcp_server.py").read_text(
        encoding="utf-8"
    )

    assert "from mcp.server import MCPServer" in source
    assert "from mcp.server.fastmcp import FastMCP" not in source
    assert 'mcp = MCPServer("Loto Forecast MCP")' in source
    assert 'transport="streamable-http"' in source
    assert "stateless_http=True" in source
    assert "json_response=True" in source
