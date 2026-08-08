from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from ..indexing.sqlite_index import SQLiteCodeIndex
from ..security import ensure_allowed_path
from .factory import create_memory_store
from .models import MemoryEvent


def build_server(
    memory_location: str | None = None,
    *,
    streamable_http: bool = False,
    host: str = "127.0.0.1",
    port: int = 17231,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("install the harness extra containing mcp>=1.28,<2") from exc

    default_location = (
        os.getenv("LOTO_HARNESS_MEMORY_URL")
        or os.getenv("LOTO_HARNESS_MEMORY_DB")
        or "artifacts/harness/memory.sqlite3"
    )
    location: str = memory_location or default_location
    store = create_memory_store(location)
    repo_root = Path(os.getenv("LOTO_HARNESS_REPO_ROOT", ".")).resolve()
    code_index_path = os.getenv("LOTO_HARNESS_CODE_INDEX", "artifacts/harness/code-index.sqlite3")
    code_index = SQLiteCodeIndex(code_index_path)
    if streamable_http:
        server = FastMCP(
            "loto-harness-memory",
            stateless_http=True,
            json_response=True,
            host=host,
            port=port,
        )
    else:
        server = FastMCP("loto-harness-memory")

    @server.tool()
    def memory_search(project: str, query: str, limit: int = 20) -> list[dict]:
        """Search append-only harness events."""
        return store.search_events(project, query, min(max(limit, 1), 100))

    @server.tool()
    def observation_record(
        project: str,
        task_id: str,
        event_type: str,
        source: str,
        payload: dict,
        commit_sha: str | None = None,
        branch: str | None = None,
        protocol_hash: str | None = None,
    ) -> dict:
        """Append an observation; this does not promote it to a verified claim."""
        event = MemoryEvent(
            event_id=str(uuid.uuid4()),
            project=project,
            task_id=task_id,
            event_type=event_type,
            payload=payload,
            source=source,
            commit_sha=commit_sha,
            branch=branch,
            protocol_hash=protocol_hash,
        )
        store.append_event(event)
        return {"event_id": event.event_id, "status": "RECORDED"}

    @server.tool()
    def task_status(project: str, task_id: str) -> dict:
        """Return the latest event and claim counts for one task."""
        return store.task_status(project, task_id)

    @server.tool()
    def code_index_refresh() -> dict:
        """Refresh the read-only Python symbol index for the repository."""
        fixed_root = ensure_allowed_path(repo_root, [repo_root])
        return code_index.index_repository(fixed_root)

    @server.tool()
    def code_symbol_search(query: str, limit: int = 20) -> list[dict]:
        """Search indexed functions, classes, signatures, paths, and calls."""
        return code_index.search(query, min(max(limit, 1), 100))

    return server


def main() -> None:
    build_server().run()


def main_http() -> None:
    host = os.getenv("LOTO_HARNESS_MCP_HOST", "127.0.0.1")
    port = int(os.getenv("LOTO_HARNESS_MCP_PORT", "17231"))
    if host == "0.0.0.0" and os.getenv("HARNESS_ALLOW_PUBLIC_BIND") != "1":
        raise RuntimeError("public MCP bind requires HARNESS_ALLOW_PUBLIC_BIND=1")
    build_server(streamable_http=True, host=host, port=port).run(transport="streamable-http")


if __name__ == "__main__":
    main()
