#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.chronos2_campaign.evaluation import (  # noqa: E402
    OOFConfig,
    PredictionBundle,
    persist_oof_result,
    run_oof_evaluation,
)


def _build_predictor(
    provider_script: Path,
    base_request: dict[str, Any],
    positions: tuple[str, ...],
):
    def predict(
        history: pd.DataFrame,
        *,
        horizon: int,
        seed: int,
        fold_id: str,
    ) -> PredictionBundle:
        request = json.loads(json.dumps(base_request))
        request["run_id"] = f"{base_request['run_id']}-{fold_id}-seed-{seed}"
        request["history"] = history.to_dict(orient="records")
        request["prediction_length"] = horizon
        request["seed"] = seed
        request["artifact_dir"] = None
        request["past_covariates"] = []
        request["future_covariates"] = []
        with tempfile.TemporaryDirectory(prefix="chronos2-oof-") as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            response_path = root / "response.json"
            request_path.write_text(
                json.dumps(request, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(provider_script),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0 or not response_path.is_file():
                raise RuntimeError(
                    "Chronos-2 provider failed: "
                    f"rc={completed.returncode}, stderr={completed.stderr}"
                )
            response = json.loads(response_path.read_text(encoding="utf-8"))
        if response.get("status") != "OK":
            raise RuntimeError(f"Chronos-2 provider returned {response.get('status')}")
        if tuple(response.get("series_identity", ())) != positions:
            raise RuntimeError("Chronos-2 series identity mismatch")
        return PredictionBundle(
            point=tuple(tuple(row) for row in response["point_forecast"]),
            quantiles={
                key: tuple(tuple(row) for row in values)
                for key, values in response.get("quantiles", {}).items()
            },
            metadata={"runtime_evidence": response.get("runtime_evidence")},
        )

    return predict


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    history = pd.read_csv(args.history)
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    config = OOFConfig.model_validate_json(Path(args.config).read_text(encoding="utf-8"))
    provider_script = PROJECT_ROOT / "scripts" / "run_chronos2_provider.py"
    predictor = _build_predictor(provider_script, request, config.position_columns)
    result = run_oof_evaluation(history, config, predictor)
    artifacts = persist_oof_result(result, args.output)
    print(json.dumps(artifacts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
