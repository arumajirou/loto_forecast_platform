from __future__ import annotations

import argparse
import json
import os
import tempfile
import traceback
from pathlib import Path

from loto.merlion_campaign.protocol import ProviderRequest, ProviderResponse
from loto.merlion_campaign.provider import execute


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
        temp_path = Path(stream.name)
    temp_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    args = parser.parse_args()

    request_id = "unknown"
    try:
        request = ProviderRequest.model_validate_json(
            args.request.read_text(encoding="utf-8")
        )
        request_id = request.request_id
        response = execute(request, args.work_root.resolve())
        return_code = 0 if response.status == "PASS" else 2
    except Exception as exc:
        response = ProviderResponse(
            request_id=request_id,
            status="FAILED",
            phase="provider",
            message=f"{type(exc).__name__}: {exc}",
            process_id=os.getpid(),
            evidence={
                "traceback": traceback.format_exc(limit=20),
            },
        )
        return_code = 2
    _atomic_write(args.response, response.model_dump_json(indent=2) + "\n")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
