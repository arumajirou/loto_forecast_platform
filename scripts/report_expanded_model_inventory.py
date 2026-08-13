#!/usr/bin/env python3
"""Print the authoritative source-backed Expanded v2 inventory as JSON."""

from __future__ import annotations

import json

from loto.models.expanded_inventory_v2 import (
    expanded_implementation_catalog,
    expanded_inventory_counts,
)


def main() -> None:
    payload = {
        "counts": expanded_inventory_counts(),
        "implementations": [row.to_dict() for row in expanded_implementation_catalog()],
        "scientific_boundaries": {
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "registration_implies_runtime_certified": False,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
