from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from loto.adapters.timer_base_84m.contracts import TimerRequest
from loto.timer_base_84m_campaign.provenance import (
    LICENSE,
    MODEL_ID,
    MODEL_REVISION,
    OBSERVED_SOURCE_HEAD,
    PYTHON_LANE,
    REPO_ID,
    SOURCE_REPOSITORY,
    SOURCE_REVISION,
    TRANSFORMERS_VERSION,
    WEIGHT_SHA256,
    load_review,
    validate_remote_code_review,
)


class TimerProviderError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class TimerBase84MProvider:
    environment_dir: Path
    review_path: Path

    def identity(self) -> dict[str, Any]:
        return {
            "model_id": MODEL_ID,
            "repo_id": REPO_ID,
            "model_revision": MODEL_REVISION,
            "weight_sha256": WEIGHT_SHA256,
            "source_repository": SOURCE_REPOSITORY,
            "source_revision": SOURCE_REVISION,
            "observed_source_head": OBSERVED_SOURCE_HEAD,
            "transformers_version": TRANSFORMERS_VERSION,
            "python_lane": PYTHON_LANE,
            "license": LICENSE,
            "runtime_status": "EXECUTION_PENDING",
        }

    def validate_request(self, payload: dict[str, Any]) -> TimerRequest:
        return TimerRequest.model_validate(payload)

    def validate_request_json(self, payload: str | bytes | bytearray) -> TimerRequest:
        return TimerRequest.model_validate_json(payload)

    def validate_environment(self) -> dict[str, Any]:
        project_file = self.environment_dir / "pyproject.toml"
        if not project_file.is_file():
            raise TimerProviderError("DEPENDENCY_LOCK_PENDING", f"missing {project_file}")
        lock_file = self.environment_dir / "uv.lock"
        if not lock_file.is_file():
            raise TimerProviderError(
                "DEPENDENCY_LOCK_PENDING",
                "isolated uv.lock is intentionally absent until torch compatibility review",
            )
        return {"project_file": str(project_file), "lock_file": str(lock_file)}

    def resolve_snapshot_manifest(self) -> dict[str, Any]:
        if not self.review_path.is_file():
            raise TimerProviderError("REMOTE_CODE_REVIEW_REQUIRED", "remote-code review is missing")
        review = load_review(self.review_path)
        try:
            validate_remote_code_review(review)
        except ValueError as exc:
            raise TimerProviderError("REMOTE_CODE_REVIEW_REQUIRED", str(exc)) from exc
        return review

    def inspect_properties(self) -> dict[str, Any]:
        return {
            **self.identity(),
            "point_forecast": True,
            "quantiles": False,
            "samples": False,
            "multivariate": False,
            "past_covariates": False,
            "known_future_covariates": False,
            "checkpoint_load": False,
            "predict": False,
        }

    @staticmethod
    def _pending(status: str, message: str) -> NoReturn:
        raise TimerProviderError(status, message)

    def load(self) -> NoReturn:
        self._pending("CHECKPOINT_LOAD_PENDING", "real checkpoint load is deferred to PR-B")

    def predict(self, request: TimerRequest) -> NoReturn:
        del request
        self._pending("RUNTIME_NOT_CERTIFIED", "real Timer inference is deferred to PR-B")

    def close(self) -> None:
        return None
