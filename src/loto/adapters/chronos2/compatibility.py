from __future__ import annotations

from typing import Any

from .contracts import Chronos2RequestV2
from .manifest import CHRONOS_MODEL_REVISION


def adapt_schema_v1(payload: dict[str, Any]) -> Chronos2RequestV2:
    if int(payload.get("schema_version", 1)) != 1:
        raise ValueError("payload is not schema v1")
    if payload.get("model_id", "chronos-2") != "chronos-2":
        raise ValueError("schema-v1 adapter only supports chronos-2")
    revision = str(payload.get("revision") or CHRONOS_MODEL_REVISION)
    if revision != CHRONOS_MODEL_REVISION:
        raise ValueError("schema-v1 adapter only supports the certified legacy revision")
    history = payload.get("history")
    if not isinstance(history, list):
        raise ValueError("schema-v1 history must be a list")
    return Chronos2RequestV2.model_validate(
        {
            "schema_version": 2,
            "run_id": payload.get("run_id", "chronos2-schema-v1-adapter"),
            "operation": "predict",
            "model_id": "chronos-2",
            "repo_id": "amazon/chronos-2",
            "revision": revision,
            "game_geometry": {
                "game_id": "loto7",
                "position_count": 7,
                "candidate_min": 1,
                "candidate_max": 37,
            },
            "series_layout": "position_local",
            "position_columns": [f"n{i}" for i in range(1, 8)],
            "history": history,
            "context_length": payload.get("context_length", 512),
            "prediction_length": payload.get("prediction_length", 1),
            "quantile_levels": payload.get(
                "quantile_levels", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
            ),
            "cross_learning": False,
            "batch_size": payload.get("batch_size", 7),
            "device": payload.get("device", "cuda"),
            "dtype": payload.get("dtype", "float32"),
            "attention_implementation": payload.get("attention_implementation", "sdpa"),
            "seed": payload.get("seed", 42),
            "local_files_only": True,
            "snapshot_path": payload.get("snapshot_path"),
            "artifact_dir": payload.get("artifact_dir"),
        }
    )
