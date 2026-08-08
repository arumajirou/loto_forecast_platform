from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from loto.basicts_campaign.basicts_module_closure import (
    DECOMPOSITION_MODULE,
    MODEL_CONFIG_MODULE,
    RUNTIME_CRITICAL_MODULES,
)
from loto.basicts_campaign.certification import (
    EXPECTED_UPSTREAM_REVISION,
    CertificationError,
    certify_p0,
    verify_provider_bundle,
)
from loto.basicts_campaign.dlinear_runtime_provenance import (
    DLINEAR_MODULE_CONTRACTS,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _closure_item(module_name: str, index: int) -> dict[str, object]:
    root = "/venv/site-packages/"
    entry = module_name.replace(".", "/")
    is_package = module_name in {"basicts", "basicts.configs"}
    entry = f"{entry}/__init__.py" if is_package else f"{entry}.py"
    path = root + entry
    return {
        "module_name": module_name,
        "distribution_entry": entry,
        "distribution_path": path,
        "import_spec_origin": path,
        "loaded_module_file": path,
        "record_status": "PASS",
        "record_hash_mode": "sha256",
        "record_hash_value": chr(67 + index) * 43,
        "record_size_bytes": 200 + index,
        "module_file_sha256": f"{index + 1:064x}",
        "is_package": is_package,
    }


def _dlinear_module_evidence(
    *,
    bad_path: bool = False,
    closure_count_delta: int = 0,
    dependency_identity: bool = True,
) -> dict[str, object]:
    root = "/venv/site-packages/"
    modules = []
    for label, module_name, entry, symbol in DLINEAR_MODULE_CONTRACTS:
        path = root + entry
        if bad_path and label == "dlinear_arch":
            path = "/shadow/dlinear_arch.py"
        modules.append(
            {
                "label": label,
                "module_name": module_name,
                "required_symbol": symbol,
                "symbol_module": module_name,
                "distribution_entry": entry,
                "distribution_path": path,
                "import_spec_origin": path,
                "loaded_module_file": path,
                "record_status": "PASS",
                "record_hash_mode": "sha256",
                "record_hash_value": "C" * 43,
                "record_size_bytes": 200,
                "module_file_sha256": "d" * 64,
                "module_already_loaded": False,
            }
        )
    closure_names = sorted(RUNTIME_CRITICAL_MODULES | {"basicts"})
    expected_base = f"{MODEL_CONFIG_MODULE}.BasicTSModelConfig"
    closure = [_closure_item(module_name, index) for index, module_name in enumerate(closure_names)]
    return {
        "dlinear_module_provenance_status": "PASS",
        "dlinear_runtime_modules": modules,
        "basicts_module_closure_status": "PASS",
        "preloaded_basicts_modules": [],
        "loaded_basicts_module_count": len(closure) + closure_count_delta,
        "loaded_basicts_modules": closure,
        "dlinear_dependency_binding_status": "PASS",
        "dlinear_dependency_bindings": {
            "decomposition_symbol": (f"{DECOMPOSITION_MODULE}.MovingAverageDecomposition"),
            "config_base_symbol": expected_base,
            "dlinear_config_direct_base": expected_base,
            "arch_decomposition_object_identity": dependency_identity,
            "config_model_config_object_identity": True,
            "configs_export_object_identity": True,
            "dlinear_config_direct_base_identity": True,
        },
    }


def _write_bundle(
    directory: Path,
    operation: str,
    *,
    identity_commit: str = EXPECTED_UPSTREAM_REVISION,
    import_origin: str = "/venv/site-packages/basicts/__init__.py",
    package_record_status: str = "PASS",
    bad_dlinear_module_path: bool = False,
    closure_count_delta: int = 0,
    dependency_identity: bool = True,
) -> None:
    directory.mkdir(parents=True)
    if operation == "identity":
        evidence = {
            "identity_status": "PASS",
            "python_process_boundary": True,
            "device": "cpu",
            "cpu_fallback": False,
            "installed_provenance_status": "PASS",
            "installed_record_integrity_status": "PASS",
            "distribution_name": "BasicTS",
            "distribution_version": "1.1.0",
            "direct_url_repository": "https://github.com/GestaltCogTeam/BasicTS",
            "direct_url_vcs": "git",
            "direct_url_commit_id": identity_commit,
            "direct_url_requested_revision": EXPECTED_UPSTREAM_REVISION,
            "direct_url_sha256": "a" * 64,
            "direct_url_record_entry": "BasicTS-1.1.0.dist-info/direct_url.json",
            "direct_url_record_path": (
                "/venv/site-packages/BasicTS-1.1.0.dist-info/direct_url.json"
            ),
            "direct_url_record_status": "PASS",
            "direct_url_record_hash_mode": "sha256",
            "direct_url_record_hash_value": "A" * 43,
            "direct_url_record_size_bytes": 200,
            "import_origin_status": "PASS",
            "import_name": "basicts",
            "import_provider_distributions": ["BasicTS"],
            "distribution_package_entry": "basicts/__init__.py",
            "distribution_package_init": "/venv/site-packages/basicts/__init__.py",
            "import_spec_origin": import_origin,
            "import_submodule_search_locations": ["/venv/site-packages/basicts"],
            "import_origin_sha256": "b" * 64,
            "module_already_loaded": False,
            "package_init_record_status": package_record_status,
            "package_init_record_hash_mode": "sha256",
            "package_init_record_hash_value": "B" * 43,
            "package_init_record_size_bytes": 120,
        }
    elif operation == "validate_config":
        evidence = {
            "config_import_policy": "ALLOWLIST",
            "resolved_count": 1,
            "resolved": ["torch.optim.Adam"],
        }
    else:
        evidence = {
            "model_name": "DLinear",
            "device": "cpu",
            "cpu_fallback": False,
            "prediction_finite": True,
            "state_dict_finite": True,
            "save_load_exact_match": True,
            "prediction_shape": [1, 1, 3],
            **_dlinear_module_evidence(
                bad_path=bad_dlinear_module_path,
                closure_count_delta=closure_count_delta,
                dependency_identity=dependency_identity,
            ),
        }
        (directory / "dlinear_state.pt").write_bytes(b"state")

    response = {
        "schema_version": "1.0",
        "status": "PASS",
        "operation": operation,
        "provider": "basicts",
        "environment_lane": "basicts-py311",
        "expected_basicts_version": "1.1.0",
        "actual_basicts_version": "1.1.0",
        "expected_upstream_revision": EXPECTED_UPSTREAM_REVISION,
        "actual_upstream_revision": EXPECTED_UPSTREAM_REVISION,
        "evidence": evidence,
        "artifacts": {},
        "error": None,
    }
    _write_json(directory / "response.json", response)
    evidence_files = sorted(
        path
        for path in directory.iterdir()
        if path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": "PASS",
        "operation": operation,
        "files": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in evidence_files
        ],
    }
    _write_json(directory / "ARTIFACT_MANIFEST.json", manifest)
    hashed = sorted(path for path in directory.iterdir() if path.name != "SHA256SUMS")
    (directory / "SHA256SUMS").write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in hashed),
        encoding="utf-8",
    )


def test_certify_p0_accepts_complete_evidence(tmp_path: Path) -> None:
    identity = tmp_path / "identity"
    config = tmp_path / "config"
    dlinear = tmp_path / "dlinear"
    _write_bundle(identity, "identity")
    _write_bundle(config, "validate_config")
    _write_bundle(dlinear, "dlinear_smoke")
    lockfile = tmp_path / "uv.lock"
    lock_text = (
        'name = "basicts"\n'
        f'source = {{ git = "https://example.invalid#{EXPECTED_UPSTREAM_REVISION}" }}\n'
    )
    lockfile.write_text(lock_text, encoding="utf-8")

    report = certify_p0(
        lockfile=lockfile,
        identity_dir=identity,
        config_dir=config,
        dlinear_dir=dlinear,
    )

    assert report["status"] == "PASS"
    certified = report["certified"]
    assert certified["installed_package_git_provenance"] is True
    assert certified["installed_record_integrity"] is True
    assert certified["import_origin_bound_to_distribution"] is True
    assert certified["dlinear_module_origin_bound_to_distribution"] is True
    assert certified["basicts_loaded_module_closure_bound_to_distribution"] is True
    assert certified["dlinear_dependency_object_binding"] is True


def test_verify_provider_bundle_rejects_tampering(tmp_path: Path) -> None:
    directory = tmp_path / "identity"
    _write_bundle(directory, "identity")
    response = directory / "response.json"
    response.write_text(response.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(CertificationError, match="SHA-256 mismatch"):
        verify_provider_bundle(directory, "identity")


def test_identity_bundle_rejects_installed_commit_drift(tmp_path: Path) -> None:
    directory = tmp_path / "identity"
    _write_bundle(directory, "identity", identity_commit="b" * 40)

    with pytest.raises(CertificationError, match="direct_url_commit_id"):
        verify_provider_bundle(directory, "identity")


def test_identity_bundle_rejects_import_origin_drift(tmp_path: Path) -> None:
    directory = tmp_path / "identity"
    _write_bundle(
        directory,
        "identity",
        import_origin="/shadow/basicts/__init__.py",
    )

    with pytest.raises(CertificationError, match="import origin differs"):
        verify_provider_bundle(directory, "identity")


def test_identity_bundle_rejects_record_integrity_drift(tmp_path: Path) -> None:
    directory = tmp_path / "identity"
    _write_bundle(
        directory,
        "identity",
        package_record_status="FAILED",
    )

    with pytest.raises(CertificationError, match="package_init_record_status"):
        verify_provider_bundle(directory, "identity")


def test_dlinear_bundle_rejects_module_path_drift(tmp_path: Path) -> None:
    directory = tmp_path / "dlinear"
    _write_bundle(
        directory,
        "dlinear_smoke",
        bad_dlinear_module_path=True,
    )

    with pytest.raises(CertificationError, match="path suffix mismatch"):
        verify_provider_bundle(directory, "dlinear_smoke")


def test_dlinear_bundle_rejects_closure_count_drift(tmp_path: Path) -> None:
    directory = tmp_path / "dlinear"
    _write_bundle(
        directory,
        "dlinear_smoke",
        closure_count_delta=1,
    )

    with pytest.raises(CertificationError, match="closure count is inconsistent"):
        verify_provider_bundle(directory, "dlinear_smoke")


def test_dlinear_bundle_rejects_dependency_identity_drift(tmp_path: Path) -> None:
    directory = tmp_path / "dlinear"
    _write_bundle(
        directory,
        "dlinear_smoke",
        dependency_identity=False,
    )

    with pytest.raises(CertificationError, match="binding evidence is inconsistent"):
        verify_provider_bundle(directory, "dlinear_smoke")


def test_certify_p0_rejects_lock_without_frozen_revision(tmp_path: Path) -> None:
    identity = tmp_path / "identity"
    config = tmp_path / "config"
    dlinear = tmp_path / "dlinear"
    _write_bundle(identity, "identity")
    _write_bundle(config, "validate_config")
    _write_bundle(dlinear, "dlinear_smoke")
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text('name = "basicts"\n', encoding="utf-8")

    with pytest.raises(CertificationError, match="frozen BasicTS revision"):
        certify_p0(
            lockfile=lockfile,
            identity_dir=identity,
            config_dir=config,
            dlinear_dir=dlinear,
        )
