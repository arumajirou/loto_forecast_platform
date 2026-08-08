from __future__ import annotations

import argparse
from pathlib import Path

from loto.merlion_campaign.dependency_gate import write_inventory_csv, write_json
from loto.merlion_campaign.dependency_semantics import audit_uv_lock_semantic


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    report = audit_uv_lock_semantic(project / "uv.lock", project / "pyproject.toml")
    write_json(args.report, report)
    write_inventory_csv(args.inventory, report["inventory"])
    print(f"LOCK_AUDIT_STATUS={report['status']}")
    print(f"LOCK_PACKAGE_COUNT={report['package_count']}")
    print(f"LOCK_REQUIRES_PYTHON_EQUIVALENT={str(report['requires_python_equivalent']).lower()}")
    print(f"LOCK_AUDIT_REPORT={args.report.resolve()}")
    print(f"LOCK_INVENTORY={args.inventory.resolve()}")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
