#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.chronos2_campaign.calibration import (  # noqa: E402
    CalibrationConfig,
    persist_calibration_result,
    run_calibration_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--folds", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    predictions = pd.read_csv(args.predictions)
    folds = pd.read_csv(args.folds)
    config = CalibrationConfig.model_validate_json(Path(args.config).read_text(encoding="utf-8"))
    result = run_calibration_evaluation(predictions, folds, config)
    artifacts = persist_calibration_result(result, args.output)
    print(json.dumps(artifacts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
