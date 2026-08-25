"""Read-only verification of Forecast MCP operator-owned runtime artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.forecast_mcp.contracts import (  # noqa: E402
    DevelopmentRequestManifest,
    ForecastMcpConfig,
)
from loto.forecast_mcp.service import ForecastMcpService, load_config  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the operator-owned Forecast MCP request/manifest pair read-only"
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--operator-runtime-root",
        type=Path,
        help="Read-only root override for validating an existing pair before config migration",
    )
    parser.add_argument("--output", type=Path)
    return parser


def _with_root_override(
    config: ForecastMcpConfig,
    operator_runtime_root: Path | None,
) -> ForecastMcpConfig:
    if operator_runtime_root is None:
        return config

    payload = config.model_dump(mode="python")
    payload["route"]["operator_runtime_root"] = operator_runtime_root.expanduser()
    return ForecastMcpConfig.model_validate(payload)


def main() -> int:
    args = build_parser().parse_args()
    config = _with_root_override(load_config(args.config), args.operator_runtime_root)
    service = ForecastMcpService(config)

    request_path = config.route.approved_request
    manifest_path = config.route.request_manifest
    if not request_path.is_file():
        raise RuntimeError(f"approved request is missing: {request_path}")
    if not manifest_path.is_file():
        raise RuntimeError(f"request manifest is missing: {manifest_path}")

    request = service._load_approved_request()
    snapshot = service._verify_approved_snapshot(request)
    manifest = DevelopmentRequestManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )

    evidence: dict[str, Any] = {
        "status": "PASS",
        "operator_runtime_root": str(config.route.operator_runtime_root),
        "approved_request": str(request_path),
        "request_manifest": str(manifest_path),
        "approved_request_sha256": _sha256(request_path),
        "request_manifest_sha256": _sha256(manifest_path),
        "manifest": manifest.model_dump(mode="json"),
        "route": {
            "operation": request.operation.value,
            "repo_id": request.repo_id,
            "revision": request.revision,
            "device": request.device,
            "local_files_only": request.local_files_only,
            "game_id": request.game_geometry.game_id,
            "position_columns": request.position_columns,
            "prediction_length": request.prediction_length,
            "seed": request.seed,
            "history_rows": len(request.history),
        },
        "snapshot": snapshot,
        "scientific_boundary": (
            "This verifies runtime/operator approval artifacts only; it does not certify "
            "Hit@±1, MAE, RMSE, Holdout, Prospective, or actual-data accuracy."
        ),
    }

    serialized = json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
