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

from loto.basicts_campaign.basicts_module_closure import (
    DECOMPOSITION_MODULE,
    MODEL_CONFIG_MODULE,
    RUNTIME_CRITICAL_MODULES,
    verify_dlinear_import_closure,
)
from loto.basicts_campaign.dlinear_runtime_provenance import (
    DLINEAR_ARCH_MODULE,
    DLINEAR_CONFIG_MODULE,
    DLINEAR_MODULE_CONTRACTS,
)
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
    if provenance.get("installed_record_integrity_status") != "PASS":
        raise RuntimeError("BasicTS installed RECORD integrity was not verified")
    if provenance.get("direct_url_record_status") != "PASS":
        raise RuntimeError("BasicTS direct_url.json RECORD integrity was not verified")
    if provenance.get("package_init_record_status") != "PASS":
        raise RuntimeError("BasicTS package __init__.py RECORD integrity was not verified")
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


def _verify_dlinear_module_evidence(evidence: dict[str, Any]) -> None:
    if evidence.get("dlinear_module_provenance_status") != "PASS":
        raise RuntimeError("DLinear module provenance was not verified")
    modules = evidence.get("dlinear_runtime_modules")
    if not isinstance(modules, list) or len(modules) != len(DLINEAR_MODULE_CONTRACTS):
        raise RuntimeError("DLinear module provenance evidence is incomplete")
    actual_names = {item.get("module_name") for item in modules if isinstance(item, dict)}
    expected_names = {contract[1] for contract in DLINEAR_MODULE_CONTRACTS}
    if actual_names != expected_names:
        raise RuntimeError("DLinear module provenance names are inconsistent")

    if evidence.get("basicts_module_closure_status") != "PASS":
        raise RuntimeError("BasicTS loaded module closure was not verified")
    if evidence.get("preloaded_basicts_modules") != []:
        raise RuntimeError("BasicTS modules were preloaded before closure verification")
    closure = evidence.get("loaded_basicts_modules")
    count = evidence.get("loaded_basicts_module_count")
    if not isinstance(closure, list) or not isinstance(count, int) or count != len(closure):
        raise RuntimeError("BasicTS loaded module closure count is inconsistent")
    if count < len(RUNTIME_CRITICAL_MODULES):
        raise RuntimeError("BasicTS loaded module closure is unexpectedly small")

    closure_names: set[str] = set()
    for item in closure:
        if not isinstance(item, dict):
            raise RuntimeError("BasicTS loaded module closure entry is invalid")
        module_name = item.get("module_name")
        if (
            not isinstance(module_name, str)
            or not module_name
            or not (module_name == "basicts" or module_name.startswith("basicts."))
            or module_name in closure_names
        ):
            raise RuntimeError("BasicTS loaded module closure names are invalid")
        closure_names.add(module_name)
        if item.get("record_status") != "PASS":
            raise RuntimeError(f"BasicTS loaded module RECORD failed: {module_name}")
        if item.get("record_hash_mode") != "sha256":
            raise RuntimeError(f"BasicTS loaded module hash mode is invalid: {module_name}")
        path = item.get("distribution_path")
        if (
            not isinstance(path, str)
            or path != item.get("import_spec_origin")
            or path != item.get("loaded_module_file")
        ):
            raise RuntimeError(f"BasicTS loaded module path mismatch: {module_name}")
        if not isinstance(item.get("is_package"), bool):
            raise RuntimeError(f"BasicTS loaded module package flag is invalid: {module_name}")
    if not RUNTIME_CRITICAL_MODULES.issubset(closure_names):
        raise RuntimeError("DLinear critical modules are missing from the loaded closure")

    if evidence.get("dlinear_dependency_binding_status") != "PASS":
        raise RuntimeError("DLinear dependency object bindings were not verified")
    expected_base = f"{MODEL_CONFIG_MODULE}.BasicTSModelConfig"
    expected_bindings = {
        "decomposition_symbol": (
            f"{DECOMPOSITION_MODULE}.MovingAverageDecomposition"
        ),
        "config_base_symbol": expected_base,
        "dlinear_config_direct_base": expected_base,
        "arch_decomposition_object_identity": True,
        "config_model_config_object_identity": True,
        "configs_export_object_identity": True,
        "dlinear_config_direct_base_identity": True,
    }
    if evidence.get("dlinear_dependency_bindings") != expected_bindings:
        raise RuntimeError("DLinear dependency object binding evidence is inconsistent")


def run_dlinear_smoke(request: ProviderRequest, output_dir: Path) -> dict[str, Any]:
    """Train the upstream BasicTS DLinear module and verify persistence on CPU."""

    module_provenance = verify_dlinear_import_closure()
    _verify_dlinear_module_evidence(module_provenance)

    import torch
    from basicts.models.DLinear.arch.dlinear_arch import DLinear
    from basicts.models.DLinear.config.dlinear_config import DLinearConfig

    if DLinear.__module__ != DLINEAR_ARCH_MODULE:
        raise RuntimeError("DLinear class was imported from an unexpected module")
    if DLinearConfig.__module__ != DLINEAR_CONFIG_MODULE:
        raise RuntimeError("DLinearConfig class was imported from an unexpected module")

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
        "config_class": f"{DLinearConfig.__module__}.{DLinearConfig.__name__}",
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
        **module_provenance,
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
