from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from importlib import import_module, metadata
from pathlib import Path
from typing import Any

from .certification_io import (
    sha256_file,
    utc_now,
    write_csv,
    write_json,
    write_manifest_and_sums,
)
from .certification_models import certify_model, compare_predictions
from .contracts import RuntimeStatus
from .inventory import MODEL_NAMES
from .runtime import discover_runtime_inventory

TARGET_VERSION = "2.1.1"
_PASS = {RuntimeStatus.VERIFIED.value, RuntimeStatus.EXPECTED_NEGATIVE_PASS.value}


def _package_evidence(injected_version: str | None = None) -> dict[str, Any]:
    try:
        version = injected_version or metadata.version("statsforecast")
    except metadata.PackageNotFoundError:
        return {
            "status": RuntimeStatus.DEPENDENCY_MISSING.value,
            "target_version": TARGET_VERSION,
        }
    status = (
        RuntimeStatus.VERIFIED.value
        if version == TARGET_VERSION
        else RuntimeStatus.UNSUPPORTED_BY_VERSION.value
    )
    files = []
    if injected_version is None:
        distribution = metadata.distribution("statsforecast")
        for item in distribution.files or ():
            path = Path(distribution.locate_file(item))
            if path.is_file():
                files.append(
                    {
                        "path": str(item),
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
    return {
        "status": status,
        "target_version": TARGET_VERSION,
        "installed_version": version,
        "files": files,
    }


def _load_parameters(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    values_are_objects = isinstance(payload, dict) and all(
        isinstance(value, dict) for value in payload.values()
    )
    if not values_are_objects:
        raise ValueError("model parameter file must contain an object of objects")
    return {str(key): value for key, value in payload.items()}


def certify_installed_runtime(
    output_root: Path | str,
    *,
    run_id: str | None = None,
    selected_models: Iterable[str] | None = None,
    model_parameters: dict[str, dict[str, Any]] | None = None,
    horizon: int = 1,
    seed: int = 1,
    lifecycle: bool = True,
    core_class: type | None = None,
    models_module: Any | None = None,
    injected_version: str | None = None,
) -> Path:
    if horizon < 1:
        raise ValueError("horizon must be positive")
    chosen = tuple(selected_models or MODEL_NAMES)
    if len(chosen) != len(set(chosen)):
        raise ValueError("selected models must be unique")
    unknown = sorted(set(chosen).difference(MODEL_NAMES))
    if unknown:
        raise ValueError(f"unknown model names: {unknown}")
    run_id = run_id or datetime.now(UTC).strftime("statsforecast-runtime-%Y%m%d-%H%M%S")
    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        run_dir / "CONFIG.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "target_version": TARGET_VERSION,
            "selected_models": list(chosen),
            "horizon": horizon,
            "seed": seed,
            "lifecycle": lifecycle,
            "n_jobs": 1,
            "actual_known": False,
            "python": sys.version,
            "platform": platform.platform(),
            "started_at_utc": utc_now(),
        },
    )
    package = _package_evidence(injected_version)
    write_json(run_dir / "PACKAGE_EVIDENCE.json", package)
    results = []
    if package["status"] == RuntimeStatus.VERIFIED.value:
        models_module = models_module or import_module("statsforecast.models")
        core_class = core_class or import_module("statsforecast").StatsForecast
        inventory = discover_runtime_inventory(models_module)
        for model_name in chosen:
            results.append(
                certify_model(
                    run_dir=run_dir,
                    model_name=model_name,
                    core_class=core_class,
                    models_module=models_module,
                    horizon=horizon,
                    seed=seed,
                    overrides=(model_parameters or {}).get(model_name),
                    lifecycle=lifecycle,
                )
            )
    else:
        inventory = {
            "status": package["status"],
            "pinned_count": len(MODEL_NAMES),
            "missing": list(MODEL_NAMES),
            "complete": False,
        }
    write_json(run_dir / "RUNTIME_INVENTORY.json", inventory)
    write_json(run_dir / "MODEL_RUNTIME_MATRIX.json", results)
    write_csv(run_dir / "MODEL_RUNTIME_MATRIX.csv", results)
    status_counts: dict[str, int] = {}
    for result in results:
        status = str(result.get("status", "UNKNOWN"))
        status_counts[status] = status_counts.get(status, 0) + 1
    formal_pass = bool(
        package["status"] == RuntimeStatus.VERIFIED.value
        and inventory.get("status") == RuntimeStatus.VERIFIED
        and set(chosen) == set(MODEL_NAMES)
        and len(results) == len(MODEL_NAMES)
        and all(result.get("status") in _PASS for result in results)
    )
    write_json(
        run_dir / "VERIFICATION_REPORT.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": "VERIFIED" if formal_pass else "PARTIALLY_VERIFIED",
            "formal_pass": formal_pass,
            "package_status": package["status"],
            "inventory_status": str(inventory.get("status")),
            "selected_all_models": set(chosen) == set(MODEL_NAMES),
            "selected_model_count": len(chosen),
            "executed_model_count": len(results),
            "status_counts": status_counts,
            "lifecycle_requested": lifecycle,
            "finished_at_utc": utc_now(),
            "holdout_opened": False,
            "prospective_actual_known": False,
            "accuracy_improvement_claimed": False,
        },
    )
    write_manifest_and_sums(run_dir)
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Certify an installed StatsForecast 2.1.1 runtime."
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--models", nargs="*")
    parser.add_argument("--model-parameters", type=Path)
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--skip-lifecycle", action="store_true")
    args = parser.parse_args(argv)
    run_dir = certify_installed_runtime(
        args.output_root,
        run_id=args.run_id,
        selected_models=args.models,
        model_parameters=_load_parameters(args.model_parameters),
        horizon=args.horizon,
        seed=args.seed,
        lifecycle=not args.skip_lifecycle,
    )
    report = json.loads((run_dir / "VERIFICATION_REPORT.json").read_text(encoding="utf-8"))
    print(f"RUN_DIR={run_dir}")
    print(f"STATUS={report['status']}")
    print(f"FORMAL_PASS={str(report['formal_pass']).lower()}")
    return 0 if report["formal_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

__all__ = ["TARGET_VERSION", "certify_installed_runtime", "compare_predictions", "main"]
