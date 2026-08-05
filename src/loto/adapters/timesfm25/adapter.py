from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from loto.adapters.timesfm25.contracts import (
    Backend,
    ForecastConfigLedger,
    GameGeometry,
    TimesFM25Request,
    TimesFM25Response,
)
from loto.timesfm25_campaign.backend_registry import BackendRegistry
from loto.timesfm25_campaign.geometry import infer_position_columns, validate_geometry_columns
from loto.timesfm25_campaign.model_manifest import ModelManifest, load_default_manifest

ROOT = Path(__file__).resolve().parents[4]
RUNNER = ROOT / "scripts" / "run_timesfm25_provider.py"
ENVIRONMENTS = {
    Backend.PYTORCH_NATIVE: ROOT / "environments" / "timesfm25-pytorch",
    Backend.PYTORCH_SOURCE: ROOT / "environments" / "timesfm25-pytorch-source",
    Backend.TRANSFORMERS: ROOT / "environments" / "timesfm25-transformers",
    Backend.XREG: ROOT / "environments" / "timesfm25-xreg",
}


class TimesFM25Adapter:
    def __init__(self, manifest: ModelManifest | None = None) -> None:
        self.manifest = manifest or load_default_manifest()
        self.registry = BackendRegistry(self.manifest)

    def build_request(
        self,
        history: pd.DataFrame,
        *,
        run_id: str,
        backend: Backend,
        geometry: GameGeometry,
        context_length: int,
        prediction_length: int,
        device: str,
        seed: int = 1,
        position_columns: list[str] | None = None,
        forecast_config: ForecastConfigLedger | None = None,
    ) -> TimesFM25Request:
        columns = position_columns or infer_position_columns(history)
        validate_geometry_columns(geometry, columns)
        backend_manifest = self.registry.resolve(backend)
        selected = history.loc[:, columns].tail(context_length)
        return TimesFM25Request(
            run_id=run_id,
            backend=backend,
            repo_id=backend_manifest.repo_id,
            revision=backend_manifest.revision,
            game_geometry=geometry,
            series_ids=columns,
            history={column: selected[column].astype(float).tolist() for column in columns},
            context_length=context_length,
            prediction_length=prediction_length,
            forecast_config=(
                forecast_config or ForecastConfigLedger(per_core_batch_size=len(columns))
            ),
            device=device,
            seed=seed,
        )

    def verify_separate_process_reload(
        self,
        request: TimesFM25Request,
        *,
        timeout: int = 600,
        tolerance: float = 1e-5,
    ):
        from loto.timesfm25_campaign.serialization import verify_separate_process_reload

        return verify_separate_process_reload(
            lambda candidate: self.execute(candidate, timeout=timeout),
            request,
            tolerance=tolerance,
        )

    def execute(self, request: TimesFM25Request, *, timeout: int = 600) -> TimesFM25Response:
        self.registry.validate_identity(request.backend, request.repo_id, request.revision)
        environment = ENVIRONMENTS[request.backend]
        if not environment.exists():
            raise FileNotFoundError(f"TimesFM 2.5 environment is missing: {environment}")
        if not RUNNER.exists():
            raise FileNotFoundError(f"TimesFM 2.5 runner is missing: {RUNNER}")
        with tempfile.TemporaryDirectory(prefix="loto-timesfm25-") as temporary:
            request_path = Path(temporary) / "request.json"
            response_path = Path(temporary) / "response.json"
            request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(environment),
                    "python",
                    str(RUNNER),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr[-4000:] or result.stdout[-4000:])
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            if payload.get("status") != "OK":
                raise RuntimeError(str(payload))
            return TimesFM25Response.model_validate(payload)


def upgrade_v1_request(
    request: dict[str, Any],
    *,
    manifest: ModelManifest | None = None,
) -> TimesFM25Request:
    active_manifest = manifest or load_default_manifest()
    backend = Backend.PYTORCH_NATIVE
    backend_manifest = active_manifest.backends[backend]
    rows = request.get("history")
    if not isinstance(rows, list) or not rows:
        raise ValueError("schema-v1 history must be a non-empty row list")
    frame = pd.DataFrame(rows)
    columns = infer_position_columns(frame)
    position_count = len(columns)
    return TimesFM25Request(
        run_id=str(request.get("run_id", "timesfm25-v1-compat")),
        backend=backend,
        repo_id=backend_manifest.repo_id,
        revision=str(request.get("revision") or backend_manifest.revision),
        game_geometry=GameGeometry(
            game_id=str(request.get("game_id", "legacy")),
            position_count=position_count,
            candidate_min=int(request.get("candidate_min", 0)),
            candidate_max=int(request.get("candidate_max", 999)),
            strictly_increasing=bool(request.get("strictly_increasing", False)),
        ),
        series_ids=columns,
        history={column: frame[column].astype(float).tolist() for column in columns},
        context_length=len(frame),
        prediction_length=int(request.get("prediction_length", 1)),
        device=str(request.get("device", "cpu")),
        dtype=str(request.get("dtype", "float32")),
        seed=int(request.get("seed", 1)),
        local_files_only=True,
    )


def downgrade_v2_response(response: TimesFM25Response) -> dict[str, Any]:
    predictions = [row[0] for row in response.median_forecast]
    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 2,
        "repo_id": response.model_identity.checkpoint_repo_id,
        "predictions": predictions,
        "prediction_shape": [len(predictions)],
        "finite": True,
        "properties": {
            "library": "timesfm",
            "license": "apache-2.0",
            "backend": response.model_identity.backend.value,
            "prediction_length": len(response.prediction_index),
            "quantile_support": True,
            "quantile_shape": [
                len(response.series_identity),
                len(response.prediction_index),
                10,
            ],
            "weight_sha256": response.artifact_reference.weight_sha256,
            "config_sha256": response.artifact_reference.config_sha256,
        },
        "gpu_evidence": response.gpu_evidence.model_dump(mode="json"),
        "artifact_reference": response.artifact_reference.model_dump(mode="json"),
    }
