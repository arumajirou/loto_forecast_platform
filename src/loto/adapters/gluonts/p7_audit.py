from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .p7_contract import (
    CertificationStatus,
    EvidenceState,
    P7FailureCategory,
    P7LaneAudit,
    P7ModelClassification,
    P7TargetMachineAudit,
    atomic_write_json,
    sha256_json,
)

EXPECTED_MODELS = (
    "DeepNPTSEstimator",
    "DeepAREstimator",
    "TiDEEstimator",
    "SimpleFeedForwardEstimator",
    "TemporalFusionTransformerEstimator",
    "WaveNetEstimator",
    "DLinearEstimator",
    "PatchTSTEstimator",
    "LagTSTEstimator",
)

PRIMARY_FILES = (
    "p6_campaign_result.json",
    "p6_campaign_manifest.json",
    "p6_environment_provenance.json",
    "P6_SHA256SUMS",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_checksum_path(root: Path, token: str) -> Path:
    candidate = Path(token)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()
    root_resolved = root.resolve()
    if resolved == root_resolved or root_resolved not in resolved.parents:
        raise ValueError(f"checksum path escapes artifact root: {token}")
    return resolved


def parse_checksum_file(root: Path) -> dict[Path, str]:
    checksum_path = root / "P6_SHA256SUMS"
    entries: dict[Path, str] = {}
    lines = checksum_path.read_text("utf-8").splitlines()
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ValueError(f"invalid checksum line {line_number}")
        digest, token = parts
        if token.startswith("*"):
            token = token[1:]
        path = _safe_checksum_path(root, token)
        if path in entries:
            raise ValueError(f"duplicate checksum path: {token}")
        entries[path] = digest.lower()
    if not entries:
        raise ValueError("P6_SHA256SUMS contains no entries")
    return entries


def verify_checksum_inventory(root: Path) -> None:
    entries = parse_checksum_file(root)
    observed = {
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and path.name != "P6_SHA256SUMS"
    }
    if set(entries) != observed:
        missing = sorted(str(path) for path in observed - set(entries))
        stale = sorted(str(path) for path in set(entries) - observed)
        raise ValueError(
            f"checksum inventory mismatch: missing={missing}, stale={stale}"
        )
    for path, expected in entries.items():
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"checksum mismatch: {path}")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _failure_category(value: str | None) -> P7FailureCategory:
    if value is None:
        return P7FailureCategory.UNKNOWN
    try:
        return P7FailureCategory(value)
    except ValueError:
        return P7FailureCategory.UNKNOWN


def _classify_model(lane: str, model: dict[str, Any]) -> P7ModelClassification:
    model_class = str(model.get("model_class", ""))
    model_status = str(model.get("status", "FAILED"))
    fit = model.get("fit") if isinstance(model.get("fit"), dict) else {}
    reload = model.get("reload") if isinstance(model.get("reload"), dict) else None
    fit_status = str(fit.get("status", "FAILED"))
    reload_status = str(reload.get("status")) if reload is not None else None
    fit_evidence = (
        fit.get("evidence") if isinstance(fit.get("evidence"), dict) else {}
    )
    reload_evidence = (
        reload.get("evidence")
        if reload is not None and isinstance(reload.get("evidence"), dict)
        else {}
    )
    if model_status == "VERIFIED":
        manifest_sha = fit_evidence.get("artifact_manifest_sha256")
        return P7ModelClassification(
            lane=lane,
            model_class=model_class,
            certification_status=CertificationStatus.VERIFIED,
            failed_stage="none",
            fit_status=fit_status,
            reload_status=reload_status,
            artifact_manifest_sha256=manifest_sha,
            fit_process_id=fit_evidence.get("process_id"),
            load_process_id=reload_evidence.get("process_id"),
        )
    failed_evidence = (
        reload_evidence
        if reload is not None and reload_status != "VERIFIED"
        else fit_evidence
    )
    failed_stage = (
        "load_predict"
        if failed_evidence is reload_evidence and reload is not None
        else "fit_serialize"
    )
    raw_errors = (
        model.get("errors")
        or failed_evidence.get("errors")
        or ["unclassified model failure"]
    )
    status = (
        CertificationStatus.BLOCKED
        if model_status == "BLOCKED"
        else CertificationStatus.PARTIALLY_VERIFIED
        if model_status == "PARTIALLY_VERIFIED"
        else CertificationStatus.FAILED
    )
    return P7ModelClassification(
        lane=lane,
        model_class=model_class,
        certification_status=status,
        failed_stage=failed_stage,
        failure_category=_failure_category(
            failed_evidence.get("failure_category")
        ),
        errors=[str(error) for error in raw_errors],
        fit_status=fit_status,
        reload_status=reload_status,
        artifact_manifest_sha256=fit_evidence.get("artifact_manifest_sha256"),
        fit_process_id=fit_evidence.get("process_id"),
        load_process_id=reload_evidence.get("process_id"),
    )


def _incomplete_lane(
    lane: str,
    bootstrap_return_code: int,
    errors: list[str],
) -> P7LaneAudit:
    category = (
        P7FailureCategory.BOOTSTRAP_FAILED
        if bootstrap_return_code != 0
        else P7FailureCategory.MISSING_ARTIFACT
    )
    return P7LaneAudit(
        lane=lane,
        bootstrap_return_code=bootstrap_return_code,
        evidence_state=EvidenceState.INCOMPLETE,
        certification_status=CertificationStatus.BLOCKED,
        failure_categories=[category],
        errors=errors,
    )


def _invalid_lane(
    lane: str,
    bootstrap_return_code: int,
    category: P7FailureCategory,
    error: str,
) -> P7LaneAudit:
    return P7LaneAudit(
        lane=lane,
        bootstrap_return_code=bootstrap_return_code,
        evidence_state=EvidenceState.INVALID,
        certification_status=CertificationStatus.NOT_EVALUATED,
        failure_categories=[category],
        errors=[error],
    )


def audit_lane(
    *,
    lane: str,
    artifact_root: Path,
    bootstrap_return_code: int,
    repo_root: Path,
    lane_root: Path,
) -> P7LaneAudit:
    if lane not in {"compat", "latest"}:
        raise ValueError("lane must be compat or latest")
    missing = [
        name for name in PRIMARY_FILES if not (artifact_root / name).is_file()
    ]
    if missing:
        return _incomplete_lane(
            lane,
            bootstrap_return_code,
            [f"missing P6 artifacts: {missing}"],
        )
    try:
        verify_checksum_inventory(artifact_root)
    except Exception as exc:
        category = (
            P7FailureCategory.CHECKSUM_INVENTORY_MISMATCH
            if "inventory" in str(exc)
            else P7FailureCategory.CHECKSUM_MISMATCH
        )
        return _invalid_lane(lane, bootstrap_return_code, category, str(exc))

    try:
        result_path = artifact_root / "p6_campaign_result.json"
        manifest_path = artifact_root / "p6_campaign_manifest.json"
        provenance_path = artifact_root / "p6_environment_provenance.json"
        campaign = _load_json(result_path)
        manifest = _load_json(manifest_path)
        provenance = _load_json(provenance_path)
        result_sha = sha256_file(result_path)
        manifest_sha = sha256_file(manifest_path)
        provenance_sha = sha256_file(provenance_path)
        checksum_sha = sha256_file(artifact_root / "P6_SHA256SUMS")

        if (
            campaign.get("lane") != lane
            or manifest.get("lane") != lane
            or provenance.get("lane") != lane
        ):
            raise ValueError("lane identity mismatch across P6 artifacts")
        run_id = campaign.get("run_id")
        if (
            not run_id
            or manifest.get("run_id") != run_id
            or provenance.get("run_id") != run_id
        ):
            raise ValueError("run identity mismatch across P6 artifacts")
        if manifest.get("campaign_result_sha256") != result_sha:
            raise ValueError("campaign result file SHA-256 mismatch")
        if manifest.get("campaign_payload_sha256") != sha256_json(campaign):
            raise ValueError("campaign canonical payload SHA-256 mismatch")
        if provenance.get("status") != campaign.get("status"):
            raise ValueError("campaign and provenance status mismatch")
        if provenance.get("workers") != campaign.get("workers"):
            raise ValueError("campaign and provenance worker count mismatch")

        provenance_hashes = provenance.get("sha256")
        if not isinstance(provenance_hashes, dict):
            raise ValueError("provenance SHA-256 map is missing")
        expected_source_hashes = {
            "lane_pyproject": sha256_file(lane_root / "pyproject.toml"),
            "lane_uv_lock": sha256_file(lane_root / "uv.lock"),
            "campaign_result": result_sha,
            "campaign_manifest": manifest_sha,
            "registry_source": sha256_file(
                repo_root / "src/loto/adapters/gluonts/p6_registry.py"
            ),
            "contract_source": sha256_file(
                repo_root / "src/loto/adapters/gluonts/p6_contract.py"
            ),
        }
        for key, expected in expected_source_hashes.items():
            if provenance_hashes.get(key) != expected:
                category = (
                    P7FailureCategory.LOCKFILE_MISMATCH
                    if key in {"lane_pyproject", "lane_uv_lock"}
                    else P7FailureCategory.PROVENANCE_MISMATCH
                )
                raise RuntimeError(
                    f"{category.value}:{key} SHA-256 mismatch"
                )

        lane_resolved = lane_root.resolve()
        python_executable = Path(
            str(provenance.get("python_executable", ""))
        ).resolve()
        python_prefix = Path(
            str(provenance.get("python_prefix", ""))
        ).resolve()
        if lane_resolved not in python_executable.parents:
            raise RuntimeError(
                "PROVENANCE_MISMATCH:python executable is outside isolated lane"
            )
        if (
            lane_resolved not in python_prefix.parents
            and python_prefix != lane_resolved
        ):
            raise RuntimeError(
                "PROVENANCE_MISMATCH:python prefix is outside isolated lane"
            )
        versions = provenance.get("versions")
        if (
            not isinstance(versions, dict)
            or not versions.get("gluonts")
            or not versions.get("torch")
        ):
            raise RuntimeError(
                "PROVENANCE_MISMATCH:isolated runtime versions are incomplete"
            )

        raw_models = campaign.get("models")
        if not isinstance(raw_models, list) or len(raw_models) != 9:
            raise ValueError(
                "campaign must contain exactly nine model lifecycles"
            )
        names = [str(model.get("model_class", "")) for model in raw_models]
        if tuple(names) != EXPECTED_MODELS:
            raise ValueError(f"campaign model order/set mismatch: {names}")
        model_statuses = manifest.get("model_statuses")
        expected_statuses = {
            str(model["model_class"]): str(model["status"])
            for model in raw_models
        }
        if model_statuses != expected_statuses:
            raise ValueError("campaign manifest model statuses mismatch")
        if manifest.get("registry_sha256") != campaign.get("registry_sha256"):
            raise ValueError("campaign registry identity mismatch")

        models = [_classify_model(lane, model) for model in raw_models]
        statuses = {model.certification_status for model in models}
        if statuses == {CertificationStatus.VERIFIED}:
            certification = CertificationStatus.VERIFIED
            errors: list[str] = []
        elif CertificationStatus.FAILED in statuses:
            certification = CertificationStatus.FAILED
            errors = ["one or more model lifecycles failed"]
        elif statuses == {CertificationStatus.BLOCKED}:
            certification = CertificationStatus.BLOCKED
            errors = ["all nine model lifecycles are blocked"]
        else:
            certification = CertificationStatus.PARTIALLY_VERIFIED
            errors = ["lane contains mixed model lifecycle states"]
        categories = sorted(
            {
                model.failure_category
                for model in models
                if model.failure_category is not None
            },
            key=lambda item: item.value,
        )
        return P7LaneAudit(
            lane=lane,
            bootstrap_return_code=bootstrap_return_code,
            evidence_state=EvidenceState.VALID,
            certification_status=certification,
            run_id=str(run_id),
            registry_sha256=str(campaign["registry_sha256"]),
            campaign_result_sha256=result_sha,
            campaign_manifest_sha256=manifest_sha,
            provenance_sha256=provenance_sha,
            checksum_file_sha256=checksum_sha,
            runtime_versions={
                str(key): None if value is None else str(value)
                for key, value in (provenance.get("versions") or {}).items()
            },
            models=models,
            failure_categories=categories,
            errors=errors,
        )
    except RuntimeError as exc:
        prefix, _, detail = str(exc).partition(":")
        try:
            category = P7FailureCategory(prefix)
        except ValueError:
            category = P7FailureCategory.PROVENANCE_MISMATCH
        return _invalid_lane(
            lane,
            bootstrap_return_code,
            category,
            detail or str(exc),
        )
    except Exception as exc:
        text = str(exc)
        if "model order/set" in text:
            category = P7FailureCategory.MODEL_SET_MISMATCH
        elif "registry" in text:
            category = P7FailureCategory.REGISTRY_MISMATCH
        else:
            category = P7FailureCategory.MANIFEST_MISMATCH
        return _invalid_lane(lane, bootstrap_return_code, category, text)


def build_target_audit(
    *,
    run_id: str,
    compat: P7LaneAudit,
    latest: P7LaneAudit,
) -> P7TargetMachineAudit:
    if EvidenceState.INVALID in {compat.evidence_state, latest.evidence_state}:
        evidence_state = EvidenceState.INVALID
    elif EvidenceState.INCOMPLETE in {
        compat.evidence_state,
        latest.evidence_state,
    }:
        evidence_state = EvidenceState.INCOMPLETE
    else:
        evidence_state = EvidenceState.VALID
    registry_match = (
        compat.registry_sha256 is not None
        and compat.registry_sha256 == latest.registry_sha256
    )
    compat_names = {model.model_class for model in compat.models}
    latest_names = {model.model_class for model in latest.models}
    model_set_match = (
        bool(compat_names)
        and compat_names == latest_names == set(EXPECTED_MODELS)
    )
    all_models = [*compat.models, *latest.models]
    verified = sum(
        model.certification_status is CertificationStatus.VERIFIED
        for model in all_models
    )
    counts = Counter(
        model.failure_category.value
        for model in all_models
        if model.failure_category is not None
    )
    errors: list[str] = []
    if evidence_state is EvidenceState.INVALID:
        certification = CertificationStatus.NOT_EVALUATED
        errors.append("one or more lane evidence sets are invalid")
    elif evidence_state is EvidenceState.INCOMPLETE:
        certification = CertificationStatus.BLOCKED
        errors.append("one or more lane evidence sets are incomplete")
    elif not registry_match:
        certification = CertificationStatus.FAILED
        counts[P7FailureCategory.REGISTRY_MISMATCH.value] += 1
        errors.append("compat and latest registry identities differ")
    elif not model_set_match:
        certification = CertificationStatus.FAILED
        counts[P7FailureCategory.MODEL_SET_MISMATCH.value] += 1
        errors.append("compat and latest model sets differ")
    elif (
        compat.certification_status is CertificationStatus.VERIFIED
        and latest.certification_status is CertificationStatus.VERIFIED
    ):
        certification = CertificationStatus.VERIFIED
    elif CertificationStatus.FAILED in {
        compat.certification_status,
        latest.certification_status,
    }:
        certification = CertificationStatus.FAILED
        errors.append("one or more lanes contain failed model lifecycles")
    elif CertificationStatus.BLOCKED in {
        compat.certification_status,
        latest.certification_status,
    }:
        certification = CertificationStatus.BLOCKED
        errors.append("one or more lanes are blocked")
    else:
        certification = CertificationStatus.PARTIALLY_VERIFIED
        errors.append("cross-lane certification is partially verified")
    return P7TargetMachineAudit(
        run_id=run_id,
        evidence_state=evidence_state,
        certification_status=certification,
        compat=compat,
        latest=latest,
        registry_match=registry_match,
        model_set_match=model_set_match,
        verified_model_lifecycles=verified,
        failure_counts=dict(sorted(counts.items())),
        errors=errors,
    )


def write_target_audit(
    output_dir: Path,
    audit: P7TargetMachineAudit,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output_dir / "p7_target_machine_audit.json"
    matrix_path = output_dir / "p7_failure_matrix.json"
    audit_sha = atomic_write_json(
        audit_path,
        audit.model_dump(mode="json"),
    )
    matrix = {
        "schema_version": 1,
        "run_id": audit.run_id,
        "rows": [
            model.model_dump(mode="json")
            for model in [*audit.compat.models, *audit.latest.models]
        ],
    }
    matrix_sha = atomic_write_json(matrix_path, matrix)
    manifest = {
        "schema_version": 1,
        "run_id": audit.run_id,
        "evidence_state": audit.evidence_state.value,
        "certification_status": audit.certification_status.value,
        "audit_sha256": audit_sha,
        "failure_matrix_sha256": matrix_sha,
        "compat_inputs": {
            "campaign_result_sha256": audit.compat.campaign_result_sha256,
            "campaign_manifest_sha256": audit.compat.campaign_manifest_sha256,
            "provenance_sha256": audit.compat.provenance_sha256,
            "checksum_file_sha256": audit.compat.checksum_file_sha256,
        },
        "latest_inputs": {
            "campaign_result_sha256": audit.latest.campaign_result_sha256,
            "campaign_manifest_sha256": audit.latest.campaign_manifest_sha256,
            "provenance_sha256": audit.latest.provenance_sha256,
            "checksum_file_sha256": audit.latest.checksum_file_sha256,
        },
    }
    manifest_path = output_dir / "p7_artifact_manifest.json"
    manifest_sha = atomic_write_json(manifest_path, manifest)
    sums_path = output_dir / "P7_SHA256SUMS"
    lines = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "P7_SHA256SUMS":
            relative = path.relative_to(output_dir).as_posix()
            lines.append(f"{sha256_file(path)}  {relative}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "audit_sha256": audit_sha,
        "failure_matrix_sha256": matrix_sha,
        "manifest_sha256": manifest_sha,
        "checksums_sha256": sha256_file(sums_path),
    }
