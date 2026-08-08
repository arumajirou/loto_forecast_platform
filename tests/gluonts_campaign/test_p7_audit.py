from __future__ import annotations

import json
from pathlib import Path

from loto.adapters.gluonts.p7_audit import (
    EXPECTED_MODELS,
    audit_lane,
    build_target_audit,
    sha256_file,
    write_target_audit,
)
from loto.adapters.gluonts.p7_contract import (
    CertificationStatus,
    EvidenceState,
    P7FailureCategory,
    atomic_write_json,
    sha256_json,
)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for lane in ("compat", "latest"):
        lane_root = repo / f"environments/gluonts-{lane}"
        lane_root.mkdir(parents=True)
        (lane_root / "pyproject.toml").write_text(f"[project]\nname='lane-{lane}'\n")
        (lane_root / "uv.lock").write_text(f"version = 1\nlane = '{lane}'\n")
    source = repo / "src/loto/adapters/gluonts"
    source.mkdir(parents=True)
    (source / "p6_registry.py").write_text("REGISTRY = 1\n")
    (source / "p6_contract.py").write_text("CONTRACT = 1\n")
    return repo


def model_payload(
    model_class: str,
    index: int,
    failed: bool = False,
) -> dict:
    manifest_sha = f"{index + 1:064x}"[-64:]
    fit_evidence = {
        "model_class": model_class,
        "operation": "fit_serialize",
        "status": "FAILED" if failed else "VERIFIED",
        "process_id": 1000 + index,
        "artifact_manifest_sha256": None if failed else manifest_sha,
        "failure_category": "FIT_FAILED" if failed else None,
        "errors": ["fit exploded"] if failed else [],
    }
    fit = {
        "status": "FAILED" if failed else "VERIFIED",
        "evidence": fit_evidence,
        "errors": ["fit exploded"] if failed else [],
    }
    reload = (
        None
        if failed
        else {
            "status": "VERIFIED",
            "evidence": {
                "model_class": model_class,
                "operation": "load_predict",
                "status": "VERIFIED",
                "process_id": 2000 + index,
                "fit_process_id": 1000 + index,
                "artifact_manifest_sha256": manifest_sha,
                "errors": [],
            },
            "errors": [],
        }
    )
    return {
        "model_class": model_class,
        "status": "FAILED" if failed else "VERIFIED",
        "fit": fit,
        "reload": reload,
        "errors": ["fit exploded"] if failed else [],
    }


def make_lane_artifacts(
    repo: Path,
    tmp_path: Path,
    lane: str,
    *,
    failed_model: str | None = None,
    registry_sha: str = "a" * 64,
) -> Path:
    root = tmp_path / f"artifacts-{lane}"
    root.mkdir()
    models = [
        model_payload(name, index, failed=name == failed_model)
        for index, name in enumerate(EXPECTED_MODELS)
    ]
    campaign_status = "FAILED" if failed_model else "VERIFIED"
    campaign = {
        "schema_version": 1,
        "run_id": f"run-{lane}",
        "lane": lane,
        "status": campaign_status,
        "workers": 8,
        "registry_sha256": registry_sha,
        "models": models,
        "errors": (["one or more model lifecycles failed"] if failed_model else []),
    }
    result_path = root / "p6_campaign_result.json"
    result_sha = atomic_write_json(result_path, campaign)
    manifest = {
        "schema_version": 1,
        "run_id": campaign["run_id"],
        "lane": lane,
        "workers": 8,
        "registry_sha256": registry_sha,
        "campaign_result_sha256": result_sha,
        "campaign_payload_sha256": sha256_json(campaign),
        "model_statuses": {row["model_class"]: row["status"] for row in models},
    }
    manifest_path = root / "p6_campaign_manifest.json"
    atomic_write_json(manifest_path, manifest)
    lane_root = repo / f"environments/gluonts-{lane}"
    provenance = {
        "schema_version": 1,
        "phase": "P6_ALL_NINE_ESTIMATORS",
        "run_id": campaign["run_id"],
        "lane": lane,
        "status": campaign_status,
        "workers": 8,
        "python": "3.13.0",
        "python_executable": str(lane_root / ".venv/bin/python"),
        "python_prefix": str(lane_root / ".venv"),
        "versions": {
            "gluonts": "0.16.3" if lane == "compat" else "0.17.0",
            "torch": "2.9.1" if lane == "compat" else "2.10.0",
            "lightning": "2.4.0" if lane == "compat" else "2.6.0",
            "pytorch_lightning": None,
        },
        "sha256": {
            "lane_pyproject": sha256_file(lane_root / "pyproject.toml"),
            "lane_uv_lock": sha256_file(lane_root / "uv.lock"),
            "campaign_result": sha256_file(result_path),
            "campaign_manifest": sha256_file(manifest_path),
            "registry_source": sha256_file(repo / "src/loto/adapters/gluonts/p6_registry.py"),
            "contract_source": sha256_file(repo / "src/loto/adapters/gluonts/p6_contract.py"),
        },
    }
    atomic_write_json(root / "p6_environment_provenance.json", provenance)
    (root / "p6_campaign.stdout.log").write_text("done\n")
    (root / "p6_campaign.stderr.log").write_text("")
    lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "P6_SHA256SUMS"
    ]
    (root / "P6_SHA256SUMS").write_text("\n".join(lines) + "\n")
    return root


def audit(
    repo: Path,
    root: Path,
    lane: str,
    rc: int = 0,
):
    return audit_lane(
        lane=lane,
        artifact_root=root,
        bootstrap_return_code=rc,
        repo_root=repo,
        lane_root=repo / f"environments/gluonts-{lane}",
    )


def test_verified_cross_lane_audit_and_outputs(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    compat_root = make_lane_artifacts(repo, tmp_path, "compat")
    latest_root = make_lane_artifacts(repo, tmp_path, "latest")
    compat = audit(repo, compat_root, "compat")
    latest = audit(repo, latest_root, "latest")
    target = build_target_audit(
        run_id="p7-run",
        compat=compat,
        latest=latest,
    )
    assert target.evidence_state is EvidenceState.VALID
    assert target.certification_status is CertificationStatus.VERIFIED
    assert target.verified_model_lifecycles == 18
    output = tmp_path / "p7"
    identities = write_target_audit(output, target)
    assert set(identities) == {
        "audit_sha256",
        "failure_matrix_sha256",
        "manifest_sha256",
        "checksums_sha256",
    }
    assert (output / "P7_SHA256SUMS").is_file()


def test_model_failure_is_valid_classified_evidence(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    root = make_lane_artifacts(
        repo,
        tmp_path,
        "compat",
        failed_model="WaveNetEstimator",
    )
    lane = audit(repo, root, "compat", rc=1)
    assert lane.evidence_state is EvidenceState.VALID
    assert lane.certification_status is CertificationStatus.FAILED
    failed = next(row for row in lane.models if row.model_class == "WaveNetEstimator")
    assert failed.failure_category is P7FailureCategory.FIT_FAILED
    assert failed.failed_stage == "fit_serialize"


def test_tampered_file_is_invalid_evidence(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    root = make_lane_artifacts(repo, tmp_path, "compat")
    path = root / "p6_campaign_result.json"
    path.write_text(path.read_text() + " ")
    lane = audit(repo, root, "compat")
    assert lane.evidence_state is EvidenceState.INVALID
    assert lane.certification_status is CertificationStatus.NOT_EVALUATED
    assert P7FailureCategory.CHECKSUM_MISMATCH in lane.failure_categories


def test_unlisted_extra_file_is_invalid_evidence(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    root = make_lane_artifacts(repo, tmp_path, "latest")
    (root / "after-the-fact.txt").write_text("tamper")
    lane = audit(repo, root, "latest")
    assert lane.evidence_state is EvidenceState.INVALID
    assert P7FailureCategory.CHECKSUM_INVENTORY_MISMATCH in lane.failure_categories


def test_missing_campaign_is_incomplete_not_tampered(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    root = tmp_path / "missing"
    root.mkdir()
    lane = audit(repo, root, "compat", rc=2)
    assert lane.evidence_state is EvidenceState.INCOMPLETE
    assert lane.certification_status is CertificationStatus.BLOCKED
    assert P7FailureCategory.BOOTSTRAP_FAILED in lane.failure_categories


def test_cross_lane_registry_divergence_fails_certification(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    compat = audit(
        repo,
        make_lane_artifacts(
            repo,
            tmp_path,
            "compat",
            registry_sha="a" * 64,
        ),
        "compat",
    )
    latest = audit(
        repo,
        make_lane_artifacts(
            repo,
            tmp_path,
            "latest",
            registry_sha="b" * 64,
        ),
        "latest",
    )
    target = build_target_audit(
        run_id="p7-run",
        compat=compat,
        latest=latest,
    )
    assert target.evidence_state is EvidenceState.VALID
    assert target.certification_status is CertificationStatus.FAILED
    assert not target.registry_match
    assert target.failure_counts["REGISTRY_MISMATCH"] == 1


def test_lockfile_change_after_run_is_invalid_provenance(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    root = make_lane_artifacts(repo, tmp_path, "compat")
    lock_path = repo / "environments/gluonts-compat/uv.lock"
    lock_path.write_text("changed = true\n")
    lane = audit(repo, root, "compat")
    assert lane.evidence_state is EvidenceState.INVALID
    assert P7FailureCategory.LOCKFILE_MISMATCH in lane.failure_categories


def test_absolute_checksum_paths_inside_root_are_supported(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    root = make_lane_artifacts(repo, tmp_path, "latest")
    checksum = root / "P6_SHA256SUMS"
    lines = []
    for line in checksum.read_text().splitlines():
        digest, relative = line.split(maxsplit=1)
        lines.append(f"{digest}  {(root / relative).resolve()}")
    checksum.write_text("\n".join(lines) + "\n")
    lane = audit(repo, root, "latest")
    assert lane.evidence_state is EvidenceState.VALID
    assert lane.certification_status is CertificationStatus.VERIFIED


def test_provenance_must_use_isolated_lane_python(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    root = make_lane_artifacts(repo, tmp_path, "compat")
    provenance_path = root / "p6_environment_provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["python_executable"] = "/usr/bin/python3"
    atomic_write_json(provenance_path, provenance)
    lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "P6_SHA256SUMS"
    ]
    (root / "P6_SHA256SUMS").write_text("\n".join(lines) + "\n")
    lane = audit(repo, root, "compat")
    assert lane.evidence_state is EvidenceState.INVALID
    assert P7FailureCategory.PROVENANCE_MISMATCH in lane.failure_categories
