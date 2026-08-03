"""First-class CLI helpers for the probabilistic execution API.

The module intentionally uses only the standard library for API client calls so
status/stop/TTS commands remain available even when the optional FastAPI server
extra is not installed.  Serving the API requires the ``api`` optional extra.
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ProbabilisticApiCliError(RuntimeError):
    """Raised for a local configuration or HTTP API error."""


def _parse_export_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(raw_value, posix=True)
        except ValueError:
            parsed = [raw_value.strip().strip("'\"")]
        values[key] = parsed[0] if parsed else ""
    return values


def resolve_root(root: str | Path | None = None) -> Path:
    candidate = root or os.environ.get("LOTO_PPL_ROOT") or Path.cwd()
    return Path(candidate).expanduser().resolve()


def create_api_environment(
    root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    voicevox_url: str = "http://127.0.0.1:50021",
    force: bool = False,
) -> dict[str, Any]:
    resolved_root = resolve_root(root)
    target = resolved_root / ".env.ppl-api"
    if target.exists() and not force:
        raise ProbabilisticApiCliError(
            f"{target} already exists; pass --force to rotate the token"
        )
    token = secrets.token_urlsafe(48)
    lines = [
        f"export LOTO_PPL_ROOT={shlex.quote(str(resolved_root))}",
        f"export LOTO_PPL_API_TOKEN={shlex.quote(token)}",
        f"export LOTO_PPL_API_HOST={shlex.quote(host)}",
        f"export LOTO_PPL_API_PORT={shlex.quote(str(port))}",
        f"export LOTO_VOICEVOX_URL={shlex.quote(voicevox_url)}",
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return {
        "status": "CREATED" if not force else "ROTATED",
        "path": str(target),
        "host": host,
        "port": port,
        "token_length": len(token),
        "token_printed": False,
    }


@dataclass(frozen=True)
class ApiClient:
    base_url: str
    token: str

    @classmethod
    def from_environment(
        cls,
        *,
        root: str | Path | None = None,
        base_url: str | None = None,
    ) -> "ApiClient":
        resolved_root = resolve_root(root)
        values = _parse_export_file(resolved_root / ".env.ppl-api")
        host = os.environ.get(
            "LOTO_PPL_API_HOST", values.get("LOTO_PPL_API_HOST", "127.0.0.1")
        )
        port = os.environ.get(
            "LOTO_PPL_API_PORT", values.get("LOTO_PPL_API_PORT", "8765")
        )
        token = os.environ.get(
            "LOTO_PPL_API_TOKEN", values.get("LOTO_PPL_API_TOKEN", "")
        )
        if not token:
            raise ProbabilisticApiCliError(
                "LOTO_PPL_API_TOKEN is missing; run api-token-create"
            )
        return cls(base_url=(base_url or f"http://{host}:{port}").rstrip("/"), token=token)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
        authenticated: bool = True,
    ) -> tuple[bytes, str]:
        data = None
        headers: dict[str, str] = {}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProbabilisticApiCliError(
                f"HTTP {exc.code} {method} {path}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ProbabilisticApiCliError(
                f"API unavailable at {self.base_url}: {exc.reason}"
            ) from exc

    def json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        body, _ = self.request(
            method,
            path,
            payload=payload,
            timeout=timeout,
            authenticated=authenticated,
        )
        value = json.loads(body.decode("utf-8"))
        if not isinstance(value, dict):
            raise ProbabilisticApiCliError("API response was not a JSON object")
        return value


def serve_api(
    *,
    root: str | Path,
    host: str | None = None,
    port: int | None = None,
    access_log: bool = True,
) -> None:
    resolved_root = resolve_root(root)
    values = _parse_export_file(resolved_root / ".env.ppl-api")
    token = os.environ.get(
        "LOTO_PPL_API_TOKEN", values.get("LOTO_PPL_API_TOKEN", "")
    )
    if not token:
        raise ProbabilisticApiCliError(
            "API token is not configured; run api-token-create first"
        )
    os.environ.setdefault("LOTO_PPL_ROOT", str(resolved_root))
    os.environ.setdefault("LOTO_PPL_API_TOKEN", token)
    selected_host = host or os.environ.get(
        "LOTO_PPL_API_HOST", values.get("LOTO_PPL_API_HOST", "127.0.0.1")
    )
    selected_port = port or int(
        os.environ.get(
            "LOTO_PPL_API_PORT", values.get("LOTO_PPL_API_PORT", "8765")
        )
    )
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ProbabilisticApiCliError(
            "uvicorn is unavailable; install the project with the api extra"
        ) from exc
    uvicorn.run(
        "loto.probabilistic.api:app",
        host=selected_host,
        port=selected_port,
        workers=1,
        access_log=access_log,
    )
