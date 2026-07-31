from __future__ import annotations

# ruff: noqa: E501
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.models.providers.base import FoundationProvider, FoundationProviderError
from loto.models.providers.subprocess import (
    SubprocessProviderContractError,
    validate_provider_request,
    validate_provider_response,
)

ROOT = Path(__file__).resolve().parents[4]
TIREX_ENV = ROOT / "environments" / "tirex"
TIREX_RUNNER = ROOT / "scripts" / "run_tirex_provider.py"


class TiRexProvider(FoundationProvider):
    repo_id = "NX-AI/TiRex-2"
    revision = "05e5b26db52bfb256f1ae1bdf785589850482de3"

    def validate_environment(self) -> dict[str, Any]:
        if not TIREX_ENV.exists():
            raise FoundationProviderError("DEPENDENCY_MISSING", f"missing TiRex environment: {TIREX_ENV}")
        if not (TIREX_ENV / "uv.lock").exists():
            raise FoundationProviderError("DEPENDENCY_MISSING", f"missing TiRex lockfile: {TIREX_ENV / 'uv.lock'}")
        if not TIREX_RUNNER.exists():
            raise FoundationProviderError("PROVIDER_NOT_IMPLEMENTED", f"missing TiRex runner: {TIREX_RUNNER}")
        return {
            "environment": str(TIREX_ENV),
            "runner": str(TIREX_RUNNER),
            "repo_id": self.repo_id,
            "revision": self.revision,
            "subprocess_contract": "json-file-v1",
        }

    def load(self) -> TiRexProvider:
        self.validate_environment()
        return self

    def _run_provider(self, history: pd.DataFrame) -> dict[str, Any]:
        self.validate_environment()
        request = {
            "schema_version": 1,
            "model_id": self.spec.model_id,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "local_files_only": True,
            "device": self.device,
            "dtype": "float32" if self.precision.startswith("32") else self.precision,
            "history": history[[f"n{i}" for i in range(1, 8)]].to_dict(orient="records"),
            "prediction_length": 1,
        }
        validate_provider_request(request)
        with tempfile.TemporaryDirectory(prefix="loto-tirex-") as tmp:
            request_path = Path(tmp) / "provider_request.json"
            response_path = Path(tmp) / "provider_response.json"
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(TIREX_ENV),
                    "python",
                    str(TIREX_RUNNER),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=int(self.params.get("provider_timeout", 900)),
                check=False,
            )
            if proc.returncode != 0:
                raise FoundationProviderError(
                    "PREDICT_FAILED",
                    f"TiRex subprocess failed rc={proc.returncode}: {proc.stderr[-2000:] or proc.stdout[-2000:]}",
                )
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise FoundationProviderError("PREDICT_FAILED", f"TiRex provider returned invalid JSON: {exc}") from exc
        if response.get("status") != "OK":
            message = str(response.get("message", "TiRex provider failed"))
            status = str(response.get("status", "PREDICT_FAILED"))
            if "snapshot" in message or "local" in message:
                status = "MODEL_WEIGHTS_MISSING"
            raise FoundationProviderError(status, message)
        try:
            validate_provider_response(response, expected_shape=(7,))
        except SubprocessProviderContractError as exc:
            raise FoundationProviderError(exc.status, str(exc)) from exc
        self.last_response = response
        self.resolved = dict(response.get("artifact_reference", {}))
        return response

    def predict(self, history: pd.DataFrame) -> np.ndarray:
        response = self._run_provider(history)
        return np.asarray(response["predictions"], dtype=float).reshape(7)

    def save(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        payload = self.inspect_properties()
        if hasattr(self, "last_response"):
            payload["artifact_reference"] = self.last_response.get("artifact_reference", {})
            payload["provider_properties"] = self.last_response.get("properties", {})
            payload["gpu_evidence"] = self.last_response.get("gpu_evidence", {})
        (path / "provider.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def load_saved(self, path: Path) -> TiRexProvider:
        if not (path / "provider.json").exists():
            raise FoundationProviderError("ARTIFACT_MISSING", f"provider artifact missing: {path / 'provider.json'}")
        self.saved_reference = json.loads((path / "provider.json").read_text(encoding="utf-8"))
        return self.load()

    def inspect_properties(self) -> dict[str, Any]:
        data = super().inspect_properties()
        data.update({
            "repo_id": self.repo_id,
            "revision": self.revision,
            "zero_shot": True,
            "environment": str(TIREX_ENV),
            "subprocess_provider": True,
            **getattr(self, "resolved", {}),
        })
        if hasattr(self, "last_response"):
            data.update(self.last_response.get("properties", {}))
        return data
