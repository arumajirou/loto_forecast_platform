from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import tempfile
import traceback
from pathlib import Path
from typing import Any

import numpy as np

from loto.basicts_campaign.installed_provenance import (
    verify_installed_basicts_provenance,
)
from loto.basicts_campaign.protocol import (
    ProviderOperation,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
)
from loto.basicts_campaign.security import resolve_import_reference

REVISION_ENV = "BASICTS_UPSTREAM_REVISION"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(text, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_basicts_version() -> str:
    """Return the installed BasicTS distribution version."""

    try:
        return importlib.metadata.version("BasicTS")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("BasicTS is not installed") from exc


def actual_upstream_revision() -> str:
    """Read the revision marker injected by the isolated launcher."""

    revision = os.environ.get(REVISION_ENV)
    if not revision:
        raise RuntimeError(f"{REVISION_ENV} is not set")
    return revision


def _verify_identity(request: ProviderRequest) -> tuple[str, str, dict[str, Any]]:
    version = installed_basicts_version()
    revision = actual_upstream_revision()
    provenance = verify_installed_basicts_provenance()
    if version != request.expected_basicts_version:
        raise RuntimeError(
            f"BasicTS version mismatch: expected {request.expected_basicts_version}, got {version}"
        )
    if provenance.get("distribution_version") != version:
        raise RuntimeError("BasicTS version metadata and provenance metadata differ")
    if provenance.get("import_origin_status") != "PASS":
        raise RuntimeError("BasicTS import origin was not verified")
    if provenance.get("import_spec_origin") != provenance.get(
        "distribution_package_init"
    ):
        raise RuntimeError("BasicTS import origin differs from the installed distribution")
    if revision != request.expected_upstream_revision:
        raise RuntimeError(
            "BasicTS revision mismatch: "
            f"expected {request.expected_upstream_revision}, got {revision}"
        )
    if provenance.get("direct_url_commit_id") != request.expected_upstream_revision:
        raise RuntimeError("BasicTS installed commit differs from the request contract")
    return version, revision, provenance


def _window_tensors(request: ProviderRequest) -> tuple[Any, Any]:
    import torch

    values = np.asarray(request.series, dtype=np.float32)
    inputs: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    for start in range(len(values) - request.input_len - request.output_len + 1):
        target_start = start + request.input_len
        inputs.append(values[start:target_start])
        targets.append(values[target_start : target_start + request.output_len])
    return torch.from_numpy(np.stack(inputs)), torch.from_numpy(np.stack(targets))


def run_dlinear_smoke(request: ProviderRequest, output_dir: Path) -> dict[str, Any]:
    """Train the upstream BasicTS DLinear module and verify persistence on CPU."""

    import torch
    from basicts.models.DLinear.arch.dlinear_arch import DLinear
    from basicts.models.DLinear.config.dlinear_config import DLinearConfig

    torch.manual_seed(request.seed)
    np.random.seed(request.seed)
    inputs, targets = _window_tensors(request)
    feature_count = inputs.shape[-1]
    config = DLinearConfig(
        input_len=request.input_len,
        output_len=request.output_len,
        num_features=int(feature_count),
        moving_avg=request.moving_avg,
        stride=1,
        individual=request.individual,
    )
    model = DLinear(config).cpu()
    optimizer = torch.optim.Adam(model.parameters(), lr=request.learning_rate)
    criterion = torch.nn.MSELoss()
    model.train()
    losses: list[float] = []
    for _ in range(request.training_steps):
        optimizer.zero_grad(set_to_none=True)
        prediction = model(inputs)
        loss = criterion(prediction, targets)
        if not torch.isfinite(loss):
            raise RuntimeError("DLinear training loss is non-finite")
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))

    model.eval()
    with torch.no_grad():
        before = model(inputs[-1:]).detach().cpu()
    if before.shape != (1, request.output_len, feature_count):
        raise RuntimeError(f"unexpected prediction shape: {tuple(before.shape)}")
    if not torch.isfinite(before).all():
        raise RuntimeError("prediction contains NaN or Inf")
    state_finite = all(
        torch.isfinite(value).all().item() for value in model.state_dict().values()
    )
    if not state_finite:
        raise RuntimeError("state_dict contains NaN or Inf")

    model_path = output_dir / "dlinear_state.pt"
    config_path = output_dir / "dlinear_config.json"
    _write_json(
        config_path,
        {
            "input_len": request.input_len,
            "output_len": request.output_len,
            "num_features": int(feature_count),
            "moving_avg": request.moving_avg,
            "stride": 1,
            "individual": request.individual,
        },
    )
    torch.save(model.state_dict(), model_path)
    if not model_path.is_file() or model_path.stat().st_size <= 0:
        raise RuntimeError("DLinear state save did not create a non-empty artifact")

    after = before.clone()
    exact_match = True
    if request.save_load:
        loaded = DLinear(config).cpu()
        state = torch.load(model_path, map_location="cpu", weights_only=True)
        loaded.load_state_dict(state, strict=True)
        loaded.eval()
        with torch.no_grad():
            after = loaded(inputs[-1:]).detach().cpu()
        exact_match = torch.equal(before, after)
        if not exact_match:
            raise RuntimeError("save/load/re-predict values changed")

    return {
        "model_name": "DLinear",
        "model_class": f"{DLinear.__module__}.{DLinear.__name__}",
        "device": "cpu",
        "cpu_fallback": False,
        "seed": request.seed,
        "training_steps": request.training_steps,
        "training_losses": losses,
        "input_shape": list(inputs.shape),
        "target_shape": list(targets.shape),
        "prediction_shape": list(before.shape),
        "prediction_finite": True,
        "state_dict_finite": state_finite,
        "prediction_before_save": before.numpy().tolist(),
        "prediction_after_load": after.numpy().tolist(),
        "save_load_exact_match": exact_match,
        "model_artifact_sha256": _sha256(model_path),
        "config_artifact_sha256": _sha256(config_path),
    }


def _write_response_bundle(output_dir: Path, response: ProviderResponse) -> None:
    response.artifacts.setdefault("response", "response.json")
    response.artifacts.setdefault("manifest", "ARTIFACT_MANIFEST.json")
    response.artifacts.setdefault("sha256sums", "SHA256SUMS")
    _write_json(output_dir / "response.json", response.model_dump(mode="json"))

    evidence_files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": response.status.value,
        "operation": response.operation.value,
        "files": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in evidence_files
        ],
    }
    _write_json(output_dir / "ARTIFACT_MANIFEST.json", manifest)
    hashed = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    _atomic_write_text(
        output_dir / "SHA256SUMS",
        "".join(f"{_sha256(path)}  {path.name}\n" for path in hashed),
    )


def execute_request(request: ProviderRequest) -> ProviderResponse:
    """Execute one request and retain PASS or failure evidence atomically."""

    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    version: str | None = None
    revision: str | None = None
    provenance: dict[str, Any] | None = None
    try:
        version, revision, provenance = _verify_identity(request)
        if request.operation is ProviderOperation.IDENTITY:
            evidence = {
                "identity_status": "PASS",
                "python_process_boundary": True,
                "device": "cpu",
                "cpu_fallback": False,
                **provenance,
            }
        elif request.operation is ProviderOperation.VALIDATE_CONFIG:
            resolved = [
                resolve_import_reference(reference)
                for reference in request.import_references
            ]
            evidence = {
                "config_import_policy": "ALLOWLIST",
                "resolved_count": len(resolved),
                "resolved": resolved,
            }
        elif request.operation is ProviderOperation.DLINEAR_SMOKE:
            evidence = run_dlinear_smoke(request, output_dir)
            _write_json(output_dir / "DLINEAR_SMOKE.json", evidence)
        else:  # pragma: no cover
            raise RuntimeError(f"unsupported operation: {request.operation}")
        response = ProviderResponse(
            status=ProviderStatus.PASS,
            operation=request.operation,
            expected_basicts_version=request.expected_basicts_version,
            actual_basicts_version=version,
            expected_upstream_revision=request.expected_upstream_revision,
            actual_upstream_revision=revision,
            evidence=evidence,
            artifacts=(
                {"dlinear_smoke": "DLINEAR_SMOKE.json"}
                if request.operation is ProviderOperation.DLINEAR_SMOKE
                else {}
            ),
        )
    except Exception as exc:
        unavailable = "not installed" in str(exc)
        response = ProviderResponse(
            status=ProviderStatus.UNAVAILABLE if unavailable else ProviderStatus.FAILED,
            operation=request.operation,
            expected_basicts_version=request.expected_basicts_version,
            actual_basicts_version=version,
            expected_upstream_revision=request.expected_upstream_revision,
            actual_upstream_revision=revision,
            error={
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
    _write_response_bundle(output_dir, response)
    return response
