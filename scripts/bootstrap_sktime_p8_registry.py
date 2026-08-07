from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.registry_transaction import bootstrap_registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-state", type=Path, required=True)
    parser.add_argument("--registry-target", required=True)
    args = parser.parse_args()
    state = bootstrap_registry(args.registry_state, args.registry_target)
    print(json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
