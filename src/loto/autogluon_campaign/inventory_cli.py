from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from loto.adapters.autogluon.inventory import (
    InventoryStatus,
    TARGET_AUTOGLUON_VERSION,
    discover_runtime_inventory,
    write_runtime_inventory,
)

DEFAULT_OUTPUT = Path("artifacts/autogluon/runtime-inventory/inventory.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover AutoGluon TimeSeries models and ensembles at runtime."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--requested-version", default=TARGET_AUTOGLUON_VERSION)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Return success for PARTIAL inventory; ERROR remains non-zero.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inventory = discover_runtime_inventory(requested_version=args.requested_version)
    output_path = write_runtime_inventory(inventory, args.output)

    print(f"AUTOGLUON_INVENTORY_STATUS={inventory.status.value}")
    print(f"AUTOGLUON_REQUESTED_VERSION={inventory.requested_version}")
    print(f"AUTOGLUON_INSTALLED_VERSION={inventory.installed_version or 'NOT_FOUND'}")
    print(f"AUTOGLUON_SOURCE_MODELS={inventory.source_model_count}")
    print(f"AUTOGLUON_RUNTIME_MODELS={inventory.runtime_discovered_model_count}")
    print(f"AUTOGLUON_IMPORTABLE_MODELS={inventory.runtime_importable_model_count}")
    print(f"AUTOGLUON_CERTIFIED_MODELS={inventory.runtime_certified_model_count}")
    print(f"AUTOGLUON_SOURCE_ENSEMBLES={inventory.source_ensemble_name_count}")
    print(f"AUTOGLUON_RUNTIME_ENSEMBLES={inventory.runtime_discovered_ensemble_count}")
    print(f"AUTOGLUON_INVENTORY_SHA256={inventory.inventory_sha256}")
    print(f"AUTOGLUON_INVENTORY_PATH={output_path}")

    if inventory.status is InventoryStatus.OK:
        return 0
    if inventory.status is InventoryStatus.PARTIAL and args.allow_partial:
        return 0
    return 2 if inventory.status is InventoryStatus.ERROR else 1


if __name__ == "__main__":
    raise SystemExit(main())
