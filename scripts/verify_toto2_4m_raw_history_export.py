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

from loto.toto2_campaign.raw_history_verify import verify_export_bundle  # noqa: E402


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently verify a Toto 2.0 raw-history export bundle"
    )
    parser.add_argument("--export-root", type=Path, required=True)
    parser.add_argument("--verification-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_export_bundle(args.export_root)
    except (OSError, RuntimeError, ValueError) as exc:
        failure = {
            "schema_version": 1,
            "status": "FAILED",
            "error": f"{type(exc).__name__}: {exc}",
        }
        _atomic_write_json(args.verification_output, failure)
        print(f"TOTO2_RAW_HISTORY_VERIFY=FAILED\nERROR={failure['error']}")
        return 2
    _atomic_write_json(args.verification_output, result)
    print("TOTO2_RAW_HISTORY_VERIFY=PASS")
    print(f"VERIFICATION_OUTPUT={args.verification_output.resolve()}")
    print("RAW_DATA_MODIFIED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
