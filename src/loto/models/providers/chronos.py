from __future__ import annotations

# ruff: noqa: E501
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.models.providers.base import FoundationProvider, FoundationProviderError

ROOT = Path(__file__).resolve().parents[4]
CHRONOS_BOLT_ENV = ROOT / "environments" / "autogluon-timeseries"
CHRONOS_BOLT_RUNNER = ROOT / "scripts" / "run_chronos_bolt_provider.py"
CHRONOS_T5_RUNNER = ROOT / "scripts" / "run_chronos_t5_provider.py"
HF_HOME = Path(
    os.environ.get(
        "HF_HOME",
        str(Path.home() / ".cache" / "huggingface"),
    )
)


class ChronosProvider(FoundationProvider):
    def _model_name(self) -> str:
        model_name = self.params.get("model_name")
        if not model_name:
            raise FoundationProviderError("CLASS_MISSING", "Chronos provider requires model_name")
        return str(model_name)

    def _revision(self) -> str | None:
        revision = self.params.get("revision")
        return str(revision) if revision else None

    def validate_environment(self) -> dict[str, Any]:
        try:
            import chronos  # noqa: F401
            import huggingface_hub
            import torch
        except ImportError as exc:
            raise FoundationProviderError("DEPENDENCY_MISSING", str(exc)) from exc
        return {
            "torch_cuda_available": torch.cuda.is_available(),
            "chronos_module": True,
            "huggingface_hub_version": getattr(huggingface_hub, "__version__", "unknown"),
        }

    def resolve_model(self) -> dict[str, Any]:
        self.validate_environment()
        from huggingface_hub import snapshot_download

        model_name = self._model_name()
        revision = self._revision()
        try:
            snapshot = Path(
                snapshot_download(
                    repo_id=model_name,
                    revision=revision,
                    local_files_only=True,
                    allow_patterns=[
                        "*.json",
                        "*.safetensors",
                        "*.bin",
                        "*.model",
                        "*.txt",
                        "*.py",
                    ],
                )
            )
        except Exception as exc:
            snapshot = self._fallback_cached_snapshot(model_name, revision)
            if snapshot is None:
                raise FoundationProviderError(
                    "MODEL_WEIGHTS_MISSING",
                    f"local_files_only snapshot not found for {model_name}"
                    f"{f' at revision {revision}' if revision else ''}: {exc}",
                ) from exc
        weights = self._weight_files(snapshot)
        config_path = snapshot / "config.json"
        if not config_path.exists():
            raise FoundationProviderError("PARTIAL_SNAPSHOT", f"config.json missing in {snapshot}")
        if not weights:
            raise FoundationProviderError(
                "MODEL_WEIGHTS_MISSING", f"no local weight files found in {snapshot}"
            )
        self.snapshot_path = snapshot
        self.weight_paths = weights
        resolved_revision = revision or snapshot.name
        return {
            "repo_id": model_name,
            "revision": resolved_revision,
            "snapshot_path": str(snapshot),
            "config_path": str(config_path),
            "weight_paths": [str(path) for path in weights],
            "weight_sha256": {str(path): self._sha256(path) for path in weights},
            "config_sha256": self._sha256(config_path),
            "snapshot_complete": True,
            "snapshot_files": sorted(
                str(path.relative_to(snapshot)) for path in snapshot.rglob("*") if path.is_file()
            ),
        }

    def _is_chronos_bolt_tiny(self) -> bool:
        return (
            self.spec.model_id == "chronos-bolt-tiny"
            and self._model_name() == "amazon/chronos-bolt-tiny"
            and self._revision() == "a0e552de83495b5c28c14c71c374f3e33280b340"
        )

    def _is_chronos_t5_small(self) -> bool:
        return (
            self.spec.model_id == "chronos-t5-small"
            and self._model_name() == "amazon/chronos-t5-small"
            and self._revision() == "a971ba21945c4f1796b17a91fe69214b5f4ad472"
        )

    def _fixed_t5_snapshot_path(self) -> Path:
        revision = "a971ba21945c4f1796b17a91fe69214b5f4ad472"
        snapshot = HF_HOME / "hub" / "models--amazon--chronos-t5-small" / "snapshots" / revision

        required = [
            snapshot / "model.safetensors",
            snapshot / "config.json",
            snapshot / "generation_config.json",
        ]

        if not snapshot.is_dir():
            raise FoundationProviderError(
                "MODEL_WEIGHTS_MISSING",
                (f"fixed Chronos-T5 snapshot missing: {snapshot}"),
            )

        for path in required:
            if not path.is_file():
                raise FoundationProviderError(
                    "PARTIAL_SNAPSHOT",
                    f"required file missing: {path}",
                )

        return snapshot.resolve()

    def _fixed_bolt_snapshot_path(self) -> Path:
        revision = "a0e552de83495b5c28c14c71c374f3e33280b340"
        snapshot = HF_HOME / "hub" / "models--amazon--chronos-bolt-tiny" / "snapshots" / revision

        weight = snapshot / "model.safetensors"
        config = snapshot / "config.json"

        if not snapshot.is_dir():
            raise FoundationProviderError(
                "MODEL_WEIGHTS_MISSING",
                (f"fixed Chronos-Bolt snapshot missing: {snapshot}"),
            )

        if not weight.is_file():
            raise FoundationProviderError(
                "MODEL_WEIGHTS_MISSING",
                (f"fixed Chronos-Bolt weight missing: {weight}"),
            )

        if not config.is_file():
            raise FoundationProviderError(
                "PARTIAL_SNAPSHOT",
                (f"fixed Chronos-Bolt config missing: {config}"),
            )

        return snapshot.resolve()

    def _run_bolt_provider(
        self,
        history: pd.DataFrame,
    ) -> dict[str, Any]:
        python_path = CHRONOS_BOLT_ENV / ".venv" / "bin" / "python"

        if not python_path.is_file():
            raise FoundationProviderError(
                "DEPENDENCY_MISSING",
                (f"Chronos-Bolt Python missing: {python_path}"),
            )

        if not CHRONOS_BOLT_RUNNER.is_file():
            raise FoundationProviderError(
                "PROVIDER_NOT_IMPLEMENTED",
                (f"Chronos-Bolt runner missing: {CHRONOS_BOLT_RUNNER}"),
            )

        columns = [f"n{i}" for i in range(1, 8)] + ["draw_date"]

        missing = [column for column in columns if column not in history.columns]

        if missing:
            raise FoundationProviderError(
                "INVALID_REQUEST",
                f"missing history columns: {missing}",
            )

        request = {
            "schema_version": 1,
            "model_id": "chronos-bolt-tiny",
            "repo_id": "amazon/chronos-bolt-tiny",
            "revision": ("a0e552de83495b5c28c14c71c374f3e33280b340"),
            "snapshot_path": str(self._fixed_bolt_snapshot_path()),
            "local_files_only": True,
            "device": self.device,
            "dtype": "float32",
            "prediction_length": 1,
            "history": history[columns].to_dict(orient="records"),
        }

        with tempfile.TemporaryDirectory(prefix="chronos-bolt-provider-") as tmp:
            tmp_path = Path(tmp)
            request_path = tmp_path / "request.json"
            response_path = tmp_path / "response.json"

            request_path.write_text(
                json.dumps(
                    request,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    str(python_path),
                    str(CHRONOS_BOLT_RUNNER),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "HF_HOME": str(HF_HOME),
                },
                check=False,
                capture_output=True,
                text=True,
            )

            if not response_path.is_file():
                raise FoundationProviderError(
                    "PROVIDER_EXECUTION_FAILED",
                    (
                        "Chronos-Bolt runner produced no "
                        f"response; rc={completed.returncode}; "
                        f"stderr={completed.stderr}"
                    ),
                )

            response = json.loads(response_path.read_text(encoding="utf-8"))

        if response.get("status") != "OK":
            raise FoundationProviderError(
                str(
                    response.get(
                        "status",
                        "PROVIDER_EXECUTION_FAILED",
                    )
                ),
                str(
                    response.get(
                        "message",
                        "Chronos-Bolt provider failed",
                    )
                ),
            )

        self.resolved = {
            "repo_id": response["repo_id"],
            "revision": response["revision"],
            "snapshot_path": response["snapshot_path"],
            "weight_paths": [response["properties"]["weight_path"]],
            "weight_sha256": {
                response["properties"]["weight_path"]: response["properties"]["weight_sha256"]
            },
            "config_sha256": response["properties"]["config_sha256"],
            "runtime_response": response,
        }

        return response

    def _run_t5_provider(
        self,
        history: pd.DataFrame,
    ) -> dict[str, Any]:
        python_path = CHRONOS_BOLT_ENV / ".venv" / "bin" / "python"

        if not python_path.is_file():
            raise FoundationProviderError(
                "DEPENDENCY_MISSING",
                (f"Chronos-T5 Python missing: {python_path}"),
            )

        if not CHRONOS_T5_RUNNER.is_file():
            raise FoundationProviderError(
                "PROVIDER_NOT_IMPLEMENTED",
                (f"Chronos-T5 runner missing: {CHRONOS_T5_RUNNER}"),
            )

        columns = [f"n{i}" for i in range(1, 8)] + ["draw_date"]

        missing = [column for column in columns if column not in history.columns]

        if missing:
            raise FoundationProviderError(
                "INVALID_REQUEST",
                f"missing history columns: {missing}",
            )

        request = {
            "schema_version": 1,
            "model_id": "chronos-t5-small",
            "repo_id": "amazon/chronos-t5-small",
            "revision": ("a971ba21945c4f1796b17a91fe69214b5f4ad472"),
            "snapshot_path": str(self._fixed_t5_snapshot_path()),
            "local_files_only": True,
            "device": self.device,
            "dtype": "float32",
            "seed": 42,
            "prediction_length": 1,
            "num_samples": 20,
            "temperature": 1.0,
            "top_k": 50,
            "top_p": 1.0,
            "history": history[columns].to_dict(orient="records"),
        }

        with tempfile.TemporaryDirectory(prefix="chronos-t5-provider-") as tmp:
            tmp_path = Path(tmp)
            request_path = tmp_path / "request.json"
            response_path = tmp_path / "response.json"

            request_path.write_text(
                json.dumps(
                    request,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    str(python_path),
                    str(CHRONOS_T5_RUNNER),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "HF_HOME": str(HF_HOME),
                },
                check=False,
                capture_output=True,
                text=True,
            )

            if not response_path.is_file():
                raise FoundationProviderError(
                    "PROVIDER_EXECUTION_FAILED",
                    (
                        "Chronos-T5 runner produced no "
                        f"response; rc={completed.returncode}; "
                        f"stderr={completed.stderr}"
                    ),
                )

            response = json.loads(response_path.read_text(encoding="utf-8"))

        if response.get("status") != "OK":
            raise FoundationProviderError(
                str(
                    response.get(
                        "status",
                        "PROVIDER_EXECUTION_FAILED",
                    )
                ),
                str(
                    response.get(
                        "message",
                        "Chronos-T5 provider failed",
                    )
                ),
            )

        properties = response["properties"]

        self.resolved = {
            "repo_id": response["repo_id"],
            "revision": response["revision"],
            "snapshot_path": response["snapshot_path"],
            "weight_paths": [properties["weight_path"]],
            "weight_sha256": {properties["weight_path"]: properties["weight_sha256"]},
            "config_sha256": properties["config_sha256"],
            "runtime_response": response,
        }

        return response

    def load(self) -> ChronosProvider:
        if self._is_chronos_bolt_tiny():
            self.validate_environment()
            self._fixed_bolt_snapshot_path()
            return self

        if self._is_chronos_t5_small():
            self.validate_environment()
            self._fixed_t5_snapshot_path()
            return self

        resolved = self.resolve_model()
        import chronos
        import torch

        dtype = torch.float32
        device_map = "cuda" if self.device == "cuda" and torch.cuda.is_available() else "cpu"
        cls = getattr(chronos, self.spec.class_name, chronos.ChronosPipeline)
        self.pipeline = cls.from_pretrained(
            resolved["snapshot_path"],
            device_map=device_map,
            torch_dtype=dtype,
            local_files_only=True,
        )
        self.device = device_map
        self.resolved = resolved
        return self

    def predict(self, history: pd.DataFrame) -> np.ndarray:
        if self._is_chronos_bolt_tiny():
            response = self._run_bolt_provider(history)
            values = np.asarray(
                response["predictions"],
                dtype=float,
            )

            if values.shape != (7,):
                raise FoundationProviderError(
                    "INVALID_OUTPUT",
                    (f"unexpected Chronos-Bolt prediction shape: {values.shape}"),
                )

            return values

        if self._is_chronos_t5_small():
            response = self._run_t5_provider(history)
            values = np.asarray(
                response["predictions"],
                dtype=float,
            )

            if values.shape != (7,):
                raise FoundationProviderError(
                    "INVALID_OUTPUT",
                    (f"unexpected Chronos-T5 prediction shape: {values.shape}"),
                )

            return values

        if not hasattr(self, "pipeline"):
            self.load()
        import torch

        raw = history[[f"n{i}" for i in range(1, 8)]].to_numpy(float).T
        context = torch.tensor(raw, dtype=torch.float32)
        if self.spec.class_name == "Chronos2Pipeline":
            context = context.unsqueeze(1)
        samples = self.pipeline.predict(context, prediction_length=1)
        if isinstance(samples, list):
            values = []
            for item in samples:
                array = item.detach().cpu().numpy() if hasattr(item, "detach") else np.asarray(item)
                # Chronos-2 returns quantiles with shape (n_variates, n_quantiles, prediction_length).
                values.append(float(array[0, array.shape[1] // 2, 0]))
            return np.asarray(values, dtype=float).reshape(7)
        if hasattr(samples, "detach"):
            array = samples.detach().cpu().numpy()
        else:
            array = np.asarray(samples)
        return np.median(array, axis=1).reshape(7)

    def save(self, path: Path) -> Path:
        return self.save_reference(path)

    def save_reference(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        payload = self.inspect_properties()
        payload.update(getattr(self, "resolved", {}))
        (path / "provider.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def load_saved(self, path: Path) -> ChronosProvider:
        provider_file = path / "provider.json"
        if not provider_file.exists():
            raise FoundationProviderError(
                "ARTIFACT_MISSING", f"provider artifact missing: {provider_file}"
            )
        payload = json.loads(provider_file.read_text(encoding="utf-8"))
        self.params["model_name"] = (
            payload.get("model_name") or payload.get("repo_id") or self._model_name()
        )
        return self.load()

    def inspect_properties(self) -> dict[str, Any]:
        data: dict[str, Any] = super().inspect_properties()
        resolved = getattr(self, "resolved", {})
        data.update(
            {
                "model_name": self.params.get("model_name"),
                "revision": resolved.get("revision") or self.params.get("revision"),
                "zero_shot": True,
                "snapshot_path": resolved.get("snapshot_path"),
                "snapshot_complete": resolved.get("snapshot_complete"),
                "config_sha256": resolved.get("config_sha256"),
                "weight_paths": resolved.get("weight_paths"),
                "weight_sha256": resolved.get("weight_sha256"),
                "runtime_response": resolved.get("runtime_response"),
            }
        )
        return data

    @staticmethod
    def _weight_files(snapshot: Path) -> list[Path]:
        return sorted(
            [
                path
                for pattern in ("*.safetensors", "*.bin")
                for path in snapshot.rglob(pattern)
                if path.is_file()
            ]
        )

    def _fallback_cached_snapshot(self, model_name: str, revision: str | None) -> Path | None:
        if revision:
            return None
        try:
            from huggingface_hub import constants
        except Exception:
            return None
        repo_cache = (
            Path(constants.HF_HUB_CACHE) / f"models--{model_name.replace('/', '--')}" / "snapshots"
        )
        if not repo_cache.exists():
            return None
        candidates = sorted(
            [path for path in repo_cache.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for candidate in candidates:
            if (candidate / "config.json").exists() and self._weight_files(candidate):
                return candidate
        return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
