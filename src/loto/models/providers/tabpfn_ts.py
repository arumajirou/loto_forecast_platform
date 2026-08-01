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
TABPFN_TS_ENV = ROOT / "environments" / "tabpfn-ts"
TABPFN_TS_RUNNER = ROOT / "scripts" / "run_tabpfn_ts_provider.py"


class TabPFNTSProvider(FoundationProvider):
    repo_id = "Prior-Labs/TabPFN-v2-reg"
    revision = "4972a65a1b30806315c6f92499959ffbfc69a673"
    weight_filename = "tabpfn-v2-regressor.ckpt"

    def validate_environment(self) -> dict[str, Any]:
        if not TABPFN_TS_ENV.exists():
            raise FoundationProviderError(
                "DEPENDENCY_MISSING", f"missing TabPFN-TS environment: {TABPFN_TS_ENV}"
            )
        if not (TABPFN_TS_ENV / "uv.lock").exists():
            raise FoundationProviderError(
                "DEPENDENCY_MISSING", f"missing TabPFN-TS lockfile: {TABPFN_TS_ENV / 'uv.lock'}"
            )
        if not TABPFN_TS_RUNNER.exists():
            raise FoundationProviderError(
                "PROVIDER_NOT_IMPLEMENTED", f"missing TabPFN-TS runner: {TABPFN_TS_RUNNER}"
            )
        return {
            "environment": str(TABPFN_TS_ENV),
            "runner": str(TABPFN_TS_RUNNER),
            "repo_id": self.repo_id,
            "revision": self.revision,
            "subprocess_contract": "json-file-v1",
        }

    def load(self) -> TabPFNTSProvider:
        self.validate_environment()
        return self

    def _run_provider(self, history: pd.DataFrame) -> dict[str, Any]:
        self.validate_environment()
        columns = [f"n{i}" for i in range(1, 8)] + ["draw_date"]
        payload = history[columns].copy()
        payload["draw_date"] = payload["draw_date"].astype(str)
        request = {
            "schema_version": 1,
            "model_id": self.spec.model_id,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "weight_filename": self.weight_filename,
            "snapshot_path": None,
            "local_files_only": True,
            "device": self.device,
            "dtype": "float32" if self.precision.startswith("32") else self.precision,
            "history": payload.to_dict(orient="records"),
            "prediction_length": 1,
        }
        validate_provider_request(request)
        with tempfile.TemporaryDirectory(prefix="loto-tabpfn-ts-") as tmp:
            request_path = Path(tmp) / "provider_request.json"
            response_path = Path(tmp) / "provider_response.json"
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(TABPFN_TS_ENV),
                    "python",
                    str(TABPFN_TS_RUNNER),
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
                    f"TabPFN-TS subprocess failed rc={proc.returncode}: {proc.stderr[-2000:] or proc.stdout[-2000:]}",
                )
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise FoundationProviderError(
                    "PREDICT_FAILED", f"TabPFN-TS provider returned invalid JSON: {exc}"
                ) from exc
        if response.get("status") != "OK":
            message = str(response.get("message", "TabPFN-TS provider failed"))
            status = str(response.get("status", "PREDICT_FAILED"))
            if "snapshot" in message or "local" in message:
                status = "MODEL_WEIGHTS_MISSING"
            raise FoundationProviderError(status, message)
        try:
            validate_provider_response(response, expected_shape=(37,))
        except SubprocessProviderContractError as exc:
            raise FoundationProviderError(exc.status, str(exc)) from exc
        self.last_response = response
        self.resolved = dict(response.get("artifact_reference", {}))
        return response

    def predict(self, history: pd.DataFrame) -> np.ndarray:
        response = self._run_provider(history)
        return np.asarray(response["predictions"], dtype=float).reshape(37)

    def save(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        payload = self.inspect_properties()
        if hasattr(self, "last_response"):
            payload["artifact_reference"] = self.last_response.get("artifact_reference", {})
            payload["provider_properties"] = self.last_response.get("properties", {})
            payload["gpu_evidence"] = self.last_response.get("gpu_evidence", {})
        (path / "provider.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def load_saved(self, path: Path) -> TabPFNTSProvider:
        if not (path / "provider.json").exists():
            raise FoundationProviderError(
                "ARTIFACT_MISSING", f"provider artifact missing: {path / 'provider.json'}"
            )
        self.saved_reference = json.loads((path / "provider.json").read_text(encoding="utf-8"))
        return self.load()

    def inspect_properties(self) -> dict[str, Any]:
        data = super().inspect_properties()
        data.update(
            {
                "repo_id": self.repo_id,
                "revision": self.revision,
                "zero_shot": True,
                "environment": str(TABPFN_TS_ENV),
                "subprocess_provider": True,
                **getattr(self, "resolved", {}),
            }
        )
        if hasattr(self, "last_response"):
            data.update(self.last_response.get("properties", {}))
        return data
