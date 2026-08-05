from __future__ import annotations

from typing import Any

from loto.adapters.timesfm25.contracts import ForecastConfigLedger, TimesFM25Request


def build_native_forecast_config(request: TimesFM25Request) -> dict[str, Any]:
    config = request.forecast_config
    return {
        "max_context": request.context_length,
        "max_horizon": config.max_horizon,
        "normalize_inputs": config.normalize_inputs,
        "use_continuous_quantile_head": config.use_continuous_quantile_head,
        "force_flip_invariance": config.force_flip_invariance,
        "infer_is_positive": config.infer_is_positive,
        "fix_quantile_crossing": config.fix_quantile_crossing,
        "return_backcast": config.return_backcast,
        "per_core_batch_size": config.per_core_batch_size,
    }


def effective_argument_ledger(request: TimesFM25Request) -> dict[str, Any]:
    return {
        "context_length": request.context_length,
        "prediction_length": request.prediction_length,
        "device": request.device,
        "dtype": request.dtype,
        "seed": request.seed,
        "local_files_only": request.local_files_only,
        "series_layout": request.series_layout,
        "forecast_config": request.forecast_config.model_dump(mode="json"),
    }
