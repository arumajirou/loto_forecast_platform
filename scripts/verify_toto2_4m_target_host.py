from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.toto2_campaign.target_host_verify import (  # noqa: E402
    verify_certification_archive,
)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_expected_sha(path: Path) -> str:
    parts = path.read_text(encoding="utf-8").strip().split()
    if len(parts) != 2:
        raise ValueError("archive SHA-256 file must contain '<hash>  <filename>'")
    return parts[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently verify a Toto 2.0 4M certification archive"
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_certification_archive(
            args.archive,
            expected_sha256=_read_expected_sha(args.archive_sha256_file),
        )
        _atomic_write_json(args.output, result)
    except (OSError, ValueError) as exc:
        failure = {
            "schema_version": 1,
            "status": "FAILED",
            "error": f"{type(exc).__name__}: {exc}",
        }
        _atomic_write_json(args.output, failure)
        print(f"TARGET_HOST_ARCHIVE_VERIFY=FAILED\nERROR={failure['error']}")
        return 2
    print("TARGET_HOST_ARCHIVE_VERIFY=PASS")
    print(f"TOTAL_CASES={result['total_cases']}")
    print(f"GPU_PROCESSES_VERIFIED={result['gpu_processes_verified']}")
    print(f"OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
