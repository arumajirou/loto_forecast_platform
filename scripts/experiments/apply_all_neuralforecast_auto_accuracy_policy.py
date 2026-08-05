#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from loto.auto_campaign.accuracy import AccuracySettings, apply_accuracy_policy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/auto_campaign/accuracy.yaml"),
    )
    args = parser.parse_args()
    settings = AccuracySettings.from_yaml(args.config.resolve())
    manifest = apply_accuracy_policy(
        args.run.resolve(),
        args.policy.resolve(),
        args.output.resolve(),
        settings,
    )
    print("ACCURACY_APPLICATION=PASS")
    if manifest.get("metrics"):
        metrics = manifest["metrics"]
        print(f"HIT_PM1={metrics['hit_pm1']:.6f}")
        print(f"ALL_POSITIONS_HIT_PM1={metrics['all_positions_hit_pm1']:.6f}")
        print(f"MAE={metrics['mae']:.6f}")
        print(f"RMSE={metrics['rmse']:.6f}")
    print(f"OUTPUT={args.output.resolve()}")


if __name__ == "__main__":
    main()
