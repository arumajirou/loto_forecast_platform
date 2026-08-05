from __future__ import annotations

from typing import Any

import numpy as np

from loto.adapters.toto2_4m.contracts import (
    RuntimeEvidence,
    Toto2ProviderRequest,
    Toto2ProviderResponse,
)
from loto.toto2_campaign.model_manifest import Toto2ModelManifest
from loto.toto2_campaign.quantiles import extract_native_quantiles


class Toto2ResponseAdapter:
    @staticmethod
    def identity_response() -> Toto2ProviderResponse:
        manifest = Toto2ModelManifest()
        return Toto2ProviderResponse(
            status="OK",
            phase="identity",
            message="pinned Toto 2.0 4M provider identity",
            model_identity=manifest.to_dict(),
            warnings=[
                "identity evidence is not model-load or inference evidence",
                "forecast accuracy and lottery-domain compatibility remain unverified",
            ],
        )

    @staticmethod
    def from_native(
        request: Toto2ProviderRequest,
        native_output: np.ndarray,
        *,
        runtime_evidence: RuntimeEvidence,
        artifact_reference: dict[str, Any],
    ) -> Toto2ProviderResponse:
        extracted = extract_native_quantiles(
            native_output,
            expected_series=request.game_geometry.position_count,
            expected_horizon=request.prediction_length,
        )
        if runtime_evidence.requested_device != request.device:
            raise ValueError("runtime evidence requested_device differs from request")
        if request.device == "cuda":
            if runtime_evidence.cpu_fallback:
                raise ValueError("CUDA request fell back to CPU")
            if not runtime_evidence.execution_device.startswith("cuda"):
                raise ValueError("CUDA request did not execute on CUDA")
            if runtime_evidence.peak_vram_bytes <= 0:
                raise ValueError("CUDA request has no positive VRAM evidence")
            if not runtime_evidence.external_gpu_pid_captured:
                raise ValueError("CUDA request lacks external provider-PID evidence")

        return Toto2ProviderResponse(
            status="OK",
            phase="predict",
            message="native Toto 2.0 quantiles validated",
            model_identity=Toto2ModelManifest().to_dict(),
            effective_arguments={
                "game_geometry": request.game_geometry.model_dump(mode="json"),
                "series_layout": request.series_layout.value,
                "context_length": request.context_length,
                "prediction_length": request.prediction_length,
                "batch_size": request.batch_size,
                "decode_block_size": request.decode_block_size,
                "native_shape": extracted.native_shape,
                "quantile_monotonicity": extracted.monotonic,
                "actuals_used": False,
            },
            point_forecast=extracted.point_forecast,
            quantiles=extracted.quantiles,
            series_identity=list(request.position_columns),
            prediction_index=list(range(1, request.prediction_length + 1)),
            runtime_evidence=runtime_evidence,
            artifact_reference=artifact_reference,
            warnings=[
                "raw probabilistic output is retained without lottery-domain projection",
                "forecast accuracy remains unverified",
            ],
        )
