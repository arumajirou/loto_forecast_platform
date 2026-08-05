"""Identity entry point for the GluonTS 0.16.3 compatibility provider."""

from __future__ import annotations

import json

LANE = "compat"
GLUONTS_VERSION = "0.16.3"
TORCH_CONSTRAINT = "==2.9.1"
PROVIDER_STATUS = "EXECUTION_PENDING"


def main() -> None:
    """Print machine-readable provider identity without importing GluonTS."""

    print(
        json.dumps(
            {
                "lane": LANE,
                "gluonts_version": GLUONTS_VERSION,
                "torch_constraint": TORCH_CONSTRAINT,
                "status": PROVIDER_STATUS,
            },
            sort_keys=True,
        )
    )
