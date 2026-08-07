from __future__ import annotations

import argparse
from pathlib import Path

from loto.sktime_campaign.deployment_canary import bootstrap_deployment_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment-state", required=True, type=Path)
    parser.add_argument("--deployment-target", required=True)
    args = parser.parse_args()
    state = bootstrap_deployment_state(args.deployment_state, args.deployment_target)
    print(state.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
