from __future__ import annotations

from pathlib import Path
from typing import Any


class MlflowBridge:
    def __init__(self, tracking_uri: str, experiment_name: str):
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name

    def record_run(
        self,
        run_name: str,
        params: dict[str, Any],
        metrics: dict[str, float],
        artifacts: list[str | Path],
    ) -> dict:
        try:
            import mlflow
        except ImportError:
            return {
                "enabled": False,
                "tracking_uri": self.tracking_uri,
                "experiment_name": self.experiment_name,
                "reason": "mlflow_not_installed",
            }
        try:
            mlflow.set_tracking_uri(self.tracking_uri)
            mlflow.set_experiment(self.experiment_name)
            with mlflow.start_run(run_name=run_name) as run:
                safe_params = {k: str(v)[:500] for k, v in params.items()}
                mlflow.log_params(safe_params)
                mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
                for artifact in artifacts:
                    p = Path(artifact)
                    if p.exists() and p.is_file():
                        mlflow.log_artifact(str(p))
                return {
                    "enabled": True,
                    "tracking_uri": self.tracking_uri,
                    "experiment_name": self.experiment_name,
                    "run_id": run.info.run_id,
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "enabled": False,
                "tracking_uri": self.tracking_uri,
                "experiment_name": self.experiment_name,
                "reason": f"mlflow_error:{type(exc).__name__}",
                "detail": str(exc)[:500],
            }
