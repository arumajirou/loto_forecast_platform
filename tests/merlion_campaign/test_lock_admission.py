from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

from loto.merlion_campaign.lock_admission import evaluate_lock_admission
from loto.merlion_campaign.license_review import (
    LICENSE_REVIEW_SCHEMA,
    canonical_sha256,
)

HEAD = "a" * 40


def _inventory_bytes() -> bytes:
    stream = io.StringIO()
    writer = csv.DictWriter(
        stream,
        fieldnames=["name", "version", "source_kind", "source"],
    )
    writer.writeheader()
    writer.writerow(
        {
            "name": "loto-merlion-provider",
            "version": "0.1.0",
            "source_kind": "virtual",
            "source": ".",
        }
    )
    writer.writerow(
        {
            "name": "numpy",
            "version": "1.26.4",
            "source_kind": "registry",
            "source": "https://pypi.org/simple",
        }
    )
    writer.writerow(
        {
            "name": "salesforce-merlion",
            "version": "2.0.4",
            "source_kind": "registry",
            "source": "https://pypi.org/simple",
        }
    )
    return stream.getvalue().encode("utf-8")


def _make_evidence(tmp_path: Path, *, status: str = "BOOTSTRAP_PASS") -> tuple[Path, bytes]:
    lock = b"version = 1\n"
    audit = {
        "status": "PASS",
        "lock_sha256": hashlib.sha256(lock).hexdigest(),
    }
    path = tmp_path / "evidence.zip"
    provenance: dict[str, object] = {
        "schema_version": "merlion-bootstrap-git-provenance-v1",
        "created_at_utc": "2026-08-05T00:00:00+00:00",
        "status": "CLEAN",
        "root": "/repo",
        "head_sha": HEAD,
        "branch": "feat/merlion-time-series-intelligence-v1",
        "changes": [],
        "blockers": [],
    }
    provenance["report_sha256"] = canonical_sha256(provenance)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("environment/uv.lock", lock)
        archive.writestr("run/DEPENDENCY_AUDIT.json", json.dumps(audit))
        archive.writestr("run/DEPENDENCY_INVENTORY.csv", _inventory_bytes())
        archive.writestr("run/GIT_PROVENANCE.json", json.dumps(provenance))
    path.with_suffix(".status").write_text(status, encoding="utf-8")
    return path, lock


def _verifier(path: Path) -> dict[str, str]:
    return {
        "status": "PASS",
        "evidence_status": path.with_suffix(".status").read_text(encoding="utf-8"),
        "zip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "manifest_sha256": "b" * 64,
    }


def _git_probe(_root: Path) -> dict[str, object]:
    return {
        "head_sha": HEAD,
        "changes": [{"status": " M", "path": "environments/merlion-core-py311/uv.lock"}],
    }


def _license_review(path: Path, evidence_zip: Path, lock: bytes, *, decision: str) -> None:
    packages = [
        {
            "name": "numpy",
            "version": "1.26.4",
            "license_expression": "BSD-3-Clause",
            "license_evidence": "installed METADATA and upstream license file",
            "decision": decision,
            "notes": "",
        },
        {
            "name": "salesforce-merlion",
            "version": "2.0.4",
            "license_expression": "Apache-2.0",
            "license_evidence": "installed METADATA and upstream LICENSE",
            "decision": decision,
            "notes": "",
        },
    ]
    payload = {
        "schema_version": LICENSE_REVIEW_SCHEMA,
        "reviewer": "reviewer@example.invalid",
        "reviewed_at_utc": "2026-08-05T00:00:00+00:00",
        "evidence_zip_sha256": hashlib.sha256(evidence_zip.read_bytes()).hexdigest(),
        "lock_sha256": hashlib.sha256(lock).hexdigest(),
        "package_count": 2,
        "packages": packages,
        "overall_decision": decision,
    }
    payload["review_sha256"] = canonical_sha256(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _workspace(tmp_path: Path, lock: bytes) -> Path:
    root = tmp_path / "repo"
    target = root / "environments/merlion-core-py311/uv.lock"
    target.parent.mkdir(parents=True)
    target.write_bytes(lock)
    return root


def test_admission_passes_only_with_all_gates(tmp_path: Path) -> None:
    evidence, lock = _make_evidence(tmp_path)
    root = _workspace(tmp_path, lock)
    review = tmp_path / "license-review.json"
    _license_review(review, evidence, lock, decision="APPROVED")
    report = evaluate_lock_admission(
        root,
        evidence,
        review,
        expected_head=HEAD,
        evidence_verifier=_verifier,
        git_probe=_git_probe,
    )
    assert report["status"] == "ADMITTED"
    assert report["blockers"] == []
    assert report["registry_package_count"] == 2


def test_pending_license_blocks_admission(tmp_path: Path) -> None:
    evidence, lock = _make_evidence(tmp_path)
    root = _workspace(tmp_path, lock)
    review = tmp_path / "license-review.json"
    _license_review(review, evidence, lock, decision="PENDING")
    report = evaluate_lock_admission(
        root,
        evidence,
        review,
        expected_head=HEAD,
        evidence_verifier=_verifier,
        git_probe=_git_probe,
    )
    assert report["status"] == "BLOCKED"
    assert any(value.startswith("LICENSE_NOT_APPROVED") for value in report["blockers"])


def test_workspace_lock_drift_blocks_admission(tmp_path: Path) -> None:
    evidence, lock = _make_evidence(tmp_path)
    root = _workspace(tmp_path, b"tampered\n")
    review = tmp_path / "license-review.json"
    _license_review(review, evidence, lock, decision="APPROVED")
    report = evaluate_lock_admission(
        root,
        evidence,
        review,
        expected_head=HEAD,
        evidence_verifier=_verifier,
        git_probe=_git_probe,
    )
    assert "WORKSPACE_LOCK_HASH_MISMATCH" in report["blockers"]


def test_bootstrap_blocked_evidence_cannot_be_admitted(tmp_path: Path) -> None:
    evidence, lock = _make_evidence(tmp_path, status="BOOTSTRAP_BLOCKED")
    root = _workspace(tmp_path, lock)
    review = tmp_path / "license-review.json"
    _license_review(review, evidence, lock, decision="APPROVED")
    report = evaluate_lock_admission(
        root,
        evidence,
        review,
        expected_head=HEAD,
        evidence_verifier=_verifier,
        git_probe=_git_probe,
    )
    assert "EVIDENCE_STATUS_NOT_BOOTSTRAP_PASS" in report["blockers"]


def test_unrelated_git_change_blocks_admission(tmp_path: Path) -> None:
    evidence, lock = _make_evidence(tmp_path)
    root = _workspace(tmp_path, lock)
    review = tmp_path / "license-review.json"
    _license_review(review, evidence, lock, decision="APPROVED")

    def probe(_root: Path) -> dict[str, object]:
        return {
            "head_sha": HEAD,
            "changes": [
                {"status": " M", "path": "environments/merlion-core-py311/uv.lock"},
                {"status": " M", "path": "pyproject.toml"},
            ],
        }

    report = evaluate_lock_admission(
        root,
        evidence,
        review,
        expected_head=HEAD,
        evidence_verifier=_verifier,
        git_probe=probe,
    )
    assert "GIT_SCOPE_VIOLATION:pyproject.toml" in report["blockers"]


def test_invalid_expected_head_is_blocked(tmp_path: Path) -> None:
    evidence, lock = _make_evidence(tmp_path)
    root = _workspace(tmp_path, lock)
    review = tmp_path / "license-review.json"
    _license_review(review, evidence, lock, decision="APPROVED")
    report = evaluate_lock_admission(
        root,
        evidence,
        review,
        expected_head="not-a-sha",
        evidence_verifier=_verifier,
        git_probe=_git_probe,
    )
    assert "EXPECTED_HEAD_INVALID" in report["blockers"]
