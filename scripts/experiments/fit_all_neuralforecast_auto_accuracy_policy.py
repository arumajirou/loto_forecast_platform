#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from loto.auto_campaign.accuracy import AccuracySettings, fit_accuracy_policy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-run", type=Path, required=True)
    parser.add_argument("--oof-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/auto_campaign/accuracy.yaml"),
    )
    args = parser.parse_args()
    settings = AccuracySettings.from_yaml(args.config.resolve())
    policy = fit_accuracy_policy(
        args.validation_run.resolve(),
        args.oof_run.resolve(),
        args.output.resolve(),
        settings,
    )
    print("ACCURACY_POLICY=PASS")
    print(f"DECODER_ENABLED={policy['decoder']['enabled']}")
    print(f"OUTPUT={args.output.resolve()}")


if __name__ == "__main__":
    main()
