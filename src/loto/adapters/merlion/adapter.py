from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from loto.merlion_campaign.protocol import ProviderRequest, ProviderResponse


class MerlionProviderError(RuntimeError):
    """Raised when the isolated provider fails or violates its protocol."""


@dataclass(frozen=True)
class MerlionProviderAdapter:
    command: Sequence[str]
    timeout_seconds: float = 120.0
    max_output_bytes: int = 1_000_000

    def run(self, request: ProviderRequest, work_root: Path) -> ProviderResponse:
        work_root = work_root.resolve()
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="merlion-adapter-") as temp_dir:
            temp = Path(temp_dir)
            request_path = temp / "request.json"
            response_path = temp / "response.json"
            request_path.write_text(
                request.model_dump_json(indent=2, by_alias=True),
                encoding="utf-8",
            )
            command = [
                *self.command,
                "--request",
                str(request_path),
                "--response",
                str(response_path),
                "--work-root",
                str(work_root),
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=False,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise MerlionProviderError(
                    f"provider timed out after {self.timeout_seconds} seconds"
                ) from exc

            stdout = completed.stdout[: self.max_output_bytes].decode("utf-8", errors="replace")
            stderr = completed.stderr[: self.max_output_bytes].decode("utf-8", errors="replace")
            if not response_path.is_file():
                raise MerlionProviderError(
                    "provider did not create a response file; "
                    f"returncode={completed.returncode}; stdout={stdout!r}; stderr={stderr!r}"
                )
            if response_path.stat().st_size > self.max_output_bytes:
                raise MerlionProviderError("provider response exceeds output limit")
            try:
                response = ProviderResponse.model_validate_json(
                    response_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise MerlionProviderError("provider response is invalid") from exc
            if completed.returncode != 0 or response.status != "PASS":
                raise MerlionProviderError(
                    f"provider failed: status={response.status}; phase={response.phase}; "
                    f"message={response.message}; stderr={stderr!r}"
                )
            return response
