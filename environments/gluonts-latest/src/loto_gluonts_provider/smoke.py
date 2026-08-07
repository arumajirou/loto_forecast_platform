from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import random
import time
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .inventory import (
    CheckState,
    FormalAvailability,
    InventoryCategory,
    RuntimeInventory,
)


class SmokeOutcome(StrEnum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


REQUIRED_CHECKS = (
    "version",
    "import",
    "constructor",
    "dataset",
    "fit",
    "predict",
    "shape",
    "finite",
    "device",
)


class DeepARCPUSmokeResult(BaseModel):
    """Bounded DeepAR CPU fit/predict certification evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    outcome: SmokeOutcome
    started_at_utc: str
    finished_at_utc: str
    duration_seconds: float = Field(ge=0.0)
    process_id: int = Field(ge=1)
    seed: int
    prediction_length: int = Field(ge=1)
    context_length: int = Field(ge=1)
    expected_shape: list[int]
    observed_shape: list[int] | None = None
    prediction_values: list[float] = Field(default_factory=list)
    observed_devices: list[str] = Field(default_factory=list)
    runtime_versions: dict[str, Any] = Field(default_factory=dict)
    checks: dict[str, CheckState]
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_outcome(self) -> DeepARCPUSmokeResult:
        missing = [name for name in REQUIRED_CHECKS if name not in self.checks]
        if missing:
            raise ValueError(f"missing required smoke checks: {missing}")
        if self.outcome is not SmokeOutcome.VERIFIED:
            if not self.errors:
                raise ValueError("non-VERIFIED smoke results require at least one error")
            return self
        if self.errors:
            raise ValueError("VERIFIED smoke results cannot contain errors")
        if any(self.checks[name] is not CheckState.PASS for name in REQUIRED_CHECKS):
            raise ValueError("VERIFIED smoke results require every required check to PASS")
        if self.observed_shape != self.expected_shape:
            raise ValueError("VERIFIED smoke result shape does not match expected shape")
        if len(self.prediction_values) != self.prediction_length:
            raise ValueError("VERIFIED smoke result has the wrong prediction length")
        if not all(math.isfinite(value) for value in self.prediction_values):
            raise ValueError("VERIFIED smoke result contains non-finite predictions")
        if not self.observed_devices or any(
            not device.startswith("cpu") for device in self.observed_devices
        ):
            raise ValueError("VERIFIED CPU smoke requires observed CPU parameters")
        return self


def smoke_sha256(result: DeepARCPUSmokeResult) -> str:
    """Hash the exact canonical JSON bytes used for atomic persistence."""

    canonical = (
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def installed_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_versions() -> dict[str, str | None]:
    return {
        "gluonts": installed_version("gluonts"),
        "torch": installed_version("torch"),
        "lightning": installed_version("lightning"),
        "pytorch_lightning": installed_version("pytorch-lightning"),
        "numpy": installed_version("numpy"),
        "pandas": installed_version("pandas"),
    }


def _version_matches(lane: str, versions: dict[str, str | None]) -> tuple[bool, str]:
    gluonts_version = versions["gluonts"]
    torch_version = versions["torch"]
    if gluonts_version is None or torch_version is None:
        return False, "GluonTS and Torch must both be installed"

    def release(value: str) -> tuple[int, int, int] | None:
        parts = value.split("+", 1)[0].split(".")
        if len(parts) < 2:
            return None
        numbers: list[int] = []
        for part in parts[:3]:
            digits = "".join(character for character in part if character.isdigit())
            if not digits:
                return None
            numbers.append(int(digits))
        while len(numbers) < 3:
            numbers.append(0)
        return tuple(numbers)

    gluonts = release(gluonts_version)
    torch = release(torch_version)
    if gluonts is None or torch is None:
        return False, "runtime versions must use numeric release components"
    if lane == "compat":
        valid = gluonts == (0, 16, 3) and torch == (2, 9, 1)
        return valid, "compat requires GluonTS 0.16.3 and Torch 2.9.1"
    valid = gluonts == (0, 17, 0) and (2, 10, 0) <= torch < (3, 0, 0)
    return valid, "latest requires GluonTS 0.17.0 and Torch >=2.10,<3"


def _blocked_result(
    lane: str,
    *,
    seed: int,
    prediction_length: int,
    context_length: int,
    started_at: str,
    started: float,
    versions: dict[str, Any],
    error: str,
) -> DeepARCPUSmokeResult:
    checks = {name: CheckState.NOT_RUN for name in REQUIRED_CHECKS}
    checks["version"] = CheckState.BLOCKED
    return DeepARCPUSmokeResult(
        lane=lane,
        outcome=SmokeOutcome.BLOCKED,
        started_at_utc=started_at,
        finished_at_utc=datetime.now(timezone.utc).isoformat(),
        duration_seconds=time.monotonic() - started,
        process_id=os.getpid(),
        seed=seed,
        prediction_length=prediction_length,
        context_length=context_length,
        expected_shape=[prediction_length],
        runtime_versions=versions,
        checks=checks,
        errors=[error],
    )


def _predictor_devices(predictor: Any) -> list[str]:
    devices: set[str] = set()
    for attribute in ("prediction_net", "network"):
        network = getattr(predictor, attribute, None)
        parameters = getattr(network, "parameters", None)
        if not callable(parameters):
            continue
        try:
            devices.update(str(parameter.device) for parameter in parameters())
        except Exception:
            continue
    return sorted(devices)


def run_deepar_cpu_smoke(
    lane: str,
    *,
    seed: int = 1,
    prediction_length: int = 1,
    context_length: int = 8,
) -> DeepARCPUSmokeResult:
    """Run one tiny DeepAR training and prediction entirely on CPU."""

    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    versions = runtime_versions()
    if os.environ.get("LOTO_GLUONTS_SKIP_DEEPAR_SMOKE") == "1":
        return _blocked_result(
            lane,
            seed=seed,
            prediction_length=prediction_length,
            context_length=context_length,
            started_at=started_at,
            started=started,
            versions=versions,
            error="DeepAR CPU smoke disabled by LOTO_GLUONTS_SKIP_DEEPAR_SMOKE",
        )
    matches, reason = _version_matches(lane, versions)
    if not matches:
        return _blocked_result(
            lane,
            seed=seed,
            prediction_length=prediction_length,
            context_length=context_length,
            started_at=started_at,
            started=started,
            versions=versions,
            error=reason,
        )

    checks = {name: CheckState.NOT_RUN for name in REQUIRED_CHECKS}
    checks["version"] = CheckState.PASS
    errors: list[str] = []
    try:
        import numpy as np
        import pandas as pd
        import torch
        from gluonts.dataset.common import ListDataset
        from gluonts.torch.distributions import StudentTOutput
        from gluonts.torch.model.deepar import DeepAREstimator

        checks["import"] = CheckState.PASS
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.set_num_threads(1)

        estimator = DeepAREstimator(
            freq="D",
            prediction_length=prediction_length,
            context_length=context_length,
            num_layers=1,
            hidden_size=4,
            batch_size=4,
            num_batches_per_epoch=1,
            num_parallel_samples=4,
            distr_output=StudentTOutput(),
            trainer_kwargs={
                "max_epochs": 1,
                "accelerator": "cpu",
                "devices": 1,
                "enable_checkpointing": False,
                "enable_progress_bar": False,
                "logger": False,
            },
        )
        checks["constructor"] = CheckState.PASS

        target = np.asarray(
            [float((index % 9) + (index / 50.0)) for index in range(48)],
            dtype=np.float32,
        )
        dataset = ListDataset(
            [
                {
                    "item_id": "deepar-cpu-smoke",
                    "start": pd.Period("2000-01-01", freq="D"),
                    "target": target,
                }
            ],
            freq="D",
        )
        checks["dataset"] = CheckState.PASS

        predictor = estimator.train(training_data=dataset)
        checks["fit"] = CheckState.PASS
        forecast = next(iter(predictor.predict(dataset)))
        checks["predict"] = CheckState.PASS

        values = np.asarray(forecast.mean, dtype=float).reshape(-1)
        observed_shape = list(values.shape)
        checks["shape"] = (
            CheckState.PASS if observed_shape == [prediction_length] else CheckState.FAIL
        )
        finite = bool(np.isfinite(values).all())
        checks["finite"] = CheckState.PASS if finite else CheckState.FAIL
        devices = _predictor_devices(predictor)
        checks["device"] = (
            CheckState.PASS
            if devices and all(device.startswith("cpu") for device in devices)
            else CheckState.FAIL
        )
        if any(checks[name] is not CheckState.PASS for name in REQUIRED_CHECKS):
            errors.append("one or more DeepAR CPU smoke checks failed")
        outcome = SmokeOutcome.VERIFIED if not errors else SmokeOutcome.FAILED
        return DeepARCPUSmokeResult(
            lane=lane,
            outcome=outcome,
            started_at_utc=started_at,
            finished_at_utc=datetime.now(timezone.utc).isoformat(),
            duration_seconds=time.monotonic() - started,
            process_id=os.getpid(),
            seed=seed,
            prediction_length=prediction_length,
            context_length=context_length,
            expected_shape=[prediction_length],
            observed_shape=observed_shape,
            prediction_values=[float(value) for value in values],
            observed_devices=devices,
            runtime_versions=versions,
            checks=checks,
            errors=errors,
            metadata={
                "model_class": "DeepAREstimator",
                "distribution_output": "StudentTOutput",
                "num_batches_per_epoch": 1,
                "max_epochs": 1,
                "num_parallel_samples": 4,
            },
        )
    except Exception as exc:
        for name in REQUIRED_CHECKS:
            if checks[name] is CheckState.NOT_RUN:
                checks[name] = CheckState.BLOCKED
        errors.append(f"{type(exc).__name__}: {exc}")
        return DeepARCPUSmokeResult(
            lane=lane,
            outcome=SmokeOutcome.FAILED,
            started_at_utc=started_at,
            finished_at_utc=datetime.now(timezone.utc).isoformat(),
            duration_seconds=time.monotonic() - started,
            process_id=os.getpid(),
            seed=seed,
            prediction_length=prediction_length,
            context_length=context_length,
            expected_shape=[prediction_length],
            runtime_versions=versions,
            checks=checks,
            errors=errors,
        )


def apply_deepar_smoke(
    inventory: RuntimeInventory,
    result: DeepARCPUSmokeResult,
) -> RuntimeInventory:
    """Apply smoke evidence only to the DeepAREstimator inventory entry."""

    if inventory.lane != result.lane:
        raise ValueError("runtime inventory and smoke lane mismatch")
    entries = []
    matched = False
    for entry in inventory.entries:
        if (
            entry.category is InventoryCategory.PYTORCH_ESTIMATOR
            and entry.name == "DeepAREstimator"
        ):
            matched = True
            if result.outcome is SmokeOutcome.VERIFIED:
                availability = FormalAvailability.VERIFIED
                errors: list[str] = []
            elif result.outcome is SmokeOutcome.FAILED:
                availability = FormalAvailability.FAILED
                errors = list(dict.fromkeys([*entry.errors, *result.errors]))
            else:
                availability = FormalAvailability.EXECUTION_PENDING
                errors = list(dict.fromkeys([*entry.errors, *result.errors]))
            entries.append(
                entry.model_copy(
                    update={
                        "constructor_state": result.checks["constructor"],
                        "fit_state": result.checks["fit"],
                        "predict_state": result.checks["predict"],
                        "device_state": result.checks["device"],
                        "formal_availability": availability,
                        "errors": errors,
                        "metadata": {
                            **entry.metadata,
                            "deep_ar_cpu_smoke": result.model_dump(mode="json"),
                        },
                    }
                )
            )
        else:
            entries.append(entry)
    if not matched:
        raise ValueError("DeepAREstimator is missing from runtime inventory")
    return RuntimeInventory(
        lane=inventory.lane,
        generated_at_utc=inventory.generated_at_utc,
        runtime_versions=inventory.runtime_versions,
        entries=entries,
        errors=inventory.errors,
    )
