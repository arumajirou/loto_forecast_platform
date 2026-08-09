from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from loto.adapters.moirai2.contracts import (
    GameGeometry,
    Moirai2ProviderRequest,
    Moirai2ProviderResponse,
)
from loto.moirai2_campaign.model_manifest import MODEL_ID, MODEL_REVISION, REPO_ID

ROOT = Path(__file__).resolve().parents[4]
RUNNER = ROOT / "scripts" / "run_moirai2_provider.py"
RUNTIME_LANES = {
    "supported-py311": ROOT / "environments" / "moirai2-supported-py311",
    "cuda13-experimental": ROOT / "environments" / "moirai2-cuda13-experimental",
}


class Moirai2AdapterError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


class Moirai2Adapter:
    """Isolated Moirai 2.0 process adapter without shared catalog registration."""

    def __init__(self, *, runtime_lane: str, timeout_seconds: int = 900):
        if runtime_lane not in RUNTIME_LANES:
            raise Moirai2AdapterError("INVALID_RUNTIME_LANE", runtime_lane)
        self.runtime_lane = runtime_lane
        self.environment = RUNTIME_LANES[runtime_lane]
        self.timeout_seconds = timeout_seconds

    def validate_environment(self) -> dict[str, str]:
        if not RUNNER.is_file():
            raise Moirai2AdapterError("PROVIDER_NOT_IMPLEMENTED", str(RUNNER))
        if not (self.environment / "pyproject.toml").is_file():
            raise Moirai2AdapterError("DEPENDENCY_MISSING", str(self.environment))
        return {
            "runner": str(RUNNER),
            "environment": str(self.environment),
            "runtime_lane": self.runtime_lane,
        }

    def build_request(
        self,
        history: pd.DataFrame,
        *,
        run_id: str,
        geometry: GameGeometry,
        position_columns: list[str],
        prediction_length: int = 1,
        context_length: int = 128,
        timestamps: list[Any] | None = None,
        time_semantics: str = "draw_sequence",
        past_covariates: dict[str, list[float]] | None = None,
        future_covariates: dict[str, list[float]] | None = None,
        future_covariate_availability: dict[str, str] | None = None,
        device: str = "cpu",
        snapshot_path: str | None = None,
    ) -> Moirai2ProviderRequest:
        rows = history[position_columns].to_dict(orient="records")
        return Moirai2ProviderRequest.model_validate(
            {
                "run_id": run_id,
                "operation": "predict",
                "model_id": MODEL_ID,
                "repo_id": REPO_ID,
                "revision": MODEL_REVISION,
                "license_lane": "personal_noncommercial_research",
                "game_geometry": geometry.model_dump(),
                "series_layout": (
                    "position_univariate" if len(position_columns) == 1 else "position_multivariate"
                ),
                "position_columns": position_columns,
                "history": rows,
                "timestamps": timestamps or [],
                "time_semantics": time_semantics,
                "past_covariates": past_covariates or {},
                "future_covariates": future_covariates or {},
                "future_covariate_availability": future_covariate_availability or {},
                "context_length": context_length,
                "prediction_length": prediction_length,
                "device": device,
                "seed": 1,
                "snapshot_path": snapshot_path,
            }
        )

    def parse_response(self, payload: dict[str, Any]) -> Moirai2ProviderResponse:
        response = Moirai2ProviderResponse.model_validate(payload)
        if response.status != "OK":
            raise Moirai2AdapterError(response.phase, response.message)
        if response.gpu_evidence is None or response.runtime_evidence is None:
            raise Moirai2AdapterError("INCOMPLETE_RUNTIME_EVIDENCE", "runtime evidence is required")
        if response.gpu_evidence.cpu_fallback or response.runtime_evidence.cpu_fallback:
            raise Moirai2AdapterError(
                "FAILED_CPU_FALLBACK",
                "formal execution forbids CPU fallback",
            )
        return response

    @staticmethod
    def _verify_covariate_response(
        request: Moirai2ProviderRequest,
        response: Moirai2ProviderResponse,
    ) -> None:
        expected_past = sorted(request.past_covariates)
        expected_future = sorted(request.future_covariates)
        evidence = response.covariate_evidence
        if evidence is None:
            raise Moirai2AdapterError(
                "COVARIATE_EVIDENCE_MISSING",
                "provider response must retain covariate evidence",
            )
        if evidence.past.names != expected_past:
            raise Moirai2AdapterError(
                "COVARIATE_IDENTITY_MISMATCH",
                "past covariate names differ from the request",
            )
        if evidence.known_future.names != expected_future:
            raise Moirai2AdapterError(
                "COVARIATE_IDENTITY_MISMATCH",
                "known-future covariate names differ from the request",
            )
        if expected_past and evidence.past.sha256 is None:
            raise Moirai2AdapterError(
                "COVARIATE_HASH_MISSING",
                "past covariate matrix SHA-256 is required",
            )
        if expected_future and (
            evidence.known_future.sha256 is None or evidence.known_future_tail_sha256 is None
        ):
            raise Moirai2AdapterError(
                "COVARIATE_HASH_MISSING",
                "known-future matrix and tail SHA-256 values are required",
            )
        if evidence.actuals_used:
            raise Moirai2AdapterError(
                "FUTURE_LEAKAGE_DETECTED",
                "provider reported actual values in covariate construction",
            )

    def run(self, request: Moirai2ProviderRequest) -> Moirai2ProviderResponse:
        self.validate_environment()
        with tempfile.TemporaryDirectory(prefix="loto-moirai2-") as temporary:
            request_path = Path(temporary) / "request.json"
            response_path = Path(temporary) / "response.json"
            request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
            environment = os.environ.copy()
            if request.device == "cpu":
                environment["CUDA_VISIBLE_DEVICES"] = ""
            process = subprocess.run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(self.environment),
                    "python",
                    str(RUNNER),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                    "--runtime-lane",
                    self.runtime_lane,
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if not response_path.is_file():
                raise Moirai2AdapterError(
                    "PROVIDER_RESPONSE_MISSING",
                    process.stderr[-2000:] or process.stdout[-2000:],
                )
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            if process.returncode != 0 and payload.get("status") == "OK":
                raise Moirai2AdapterError("PROVIDER_EXIT_MISMATCH", str(process.returncode))
        response = self.parse_response(payload)
        self._verify_covariate_response(request, response)
        return response
