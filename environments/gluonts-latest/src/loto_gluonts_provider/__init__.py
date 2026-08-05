"""Identity entry point for the GluonTS 0.17.0 latest provider."""

from __future__ import annotations

import json

LANE = "latest"
GLUONTS_VERSION = "0.17.0"
TORCH_CONSTRAINT = ">=2.10,<3"
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
