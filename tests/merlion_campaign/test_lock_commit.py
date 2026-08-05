from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

import pytest

from loto.merlion_campaign.lock_commit import (
    ALLOWED_LOCK_PATH,
    canonical_sha256,
    evaluate_lock_commit,
    validate_lock_commit_report,
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def setup_case(tmp_path: Path, *, extra: bool = False) -> tuple[Path, str, str, bytes]:
    root = tmp_path / "repo"
    lock = root / ALLOWED_LOCK_PATH
    lock.parent.mkdir(parents=True)
    git(tmp_path, "init", str(root))
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test User")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "base")
    parent = git(root, "rev-parse", "HEAD")
    lock_bytes = b"version = 1\n"
    lock.write_bytes(lock_bytes)
    git(root, "add", ALLOWED_LOCK_PATH)
    if extra:
        (root / "extra.txt").write_text("extra\n", encoding="utf-8")
        git(root, "add", "extra.txt")
    git(root, "commit", "-m", "commit admitted lock")
    return root, parent, git(root, "rev-parse", "HEAD"), lock_bytes


def inputs(tmp_path: Path, parent: str, lock_bytes: bytes) -> tuple[Path, Path, Path]:
    evidence = tmp_path / "evidence.zip"
    evidence.write_bytes(b"evidence")
    review = tmp_path / "review.json"
    review.write_text('{"overall_decision":"APPROVED"}\n', encoding="utf-8")
    lock_hash = digest(lock_bytes)
    admission: dict[str, Any] = {
        "schema_version": "merlion-lock-admission-v1",
        "status": "ADMITTED",
        "expected_head": parent,
        "actual_head": parent,
        "evidence_head": parent,
        "lock_path": ALLOWED_LOCK_PATH,
        "lock_sha256": lock_hash,
        "workspace_lock_sha256": lock_hash,
        "evidence_zip_sha256": digest(evidence.read_bytes()),
        "license_review_sha256": digest(review.read_bytes()),
        "blockers": [],
    }
    admission["report_sha256"] = canonical_sha256(admission)
    report = tmp_path / "admission.json"
    report.write_text(json.dumps(admission) + "\n", encoding="utf-8")
    return report, evidence, review


def verify_evidence(path: Path) -> Mapping[str, Any]:
    return {
        "status": "PASS",
        "evidence_status": "BOOTSTRAP_PASS",
        "zip_sha256": digest(path.read_bytes()),
    }


def read_payloads(_: Path) -> Mapping[str, bytes]:
    return {
        "run/DEPENDENCY_INVENTORY.csv": (
            b"name,version,source_kind,source\nmerlion,2.0.4,registry,pypi\n"
        )
    }


def validate_license(
    review: Mapping[str, Any],
    inventory: bytes,
    evidence_hash: str,
    lock_hash: str,
) -> list[str]:
    assert review["overall_decision"] == "APPROVED"
    assert inventory and len(evidence_hash) == len(lock_hash) == 64
    return []


def evaluate(tmp_path: Path, *, extra: bool = False) -> tuple[Path, dict[str, Any]]:
    root, parent, head, lock_bytes = setup_case(tmp_path, extra=extra)
    admission, evidence, review = inputs(tmp_path, parent, lock_bytes)
    result = evaluate_lock_commit(
        root,
        admission,
        evidence,
        review,
        expected_head=head,
        evidence_verifier=verify_evidence,
        evidence_payload_reader=read_payloads,
        license_validator=validate_license,
    )
    return root, result


def test_certifies_exact_lock_only_commit(tmp_path: Path) -> None:
    root, report = evaluate(tmp_path)
    assert report["status"] == "LOCK_COMMIT_CERTIFIED"
    assert report["changed_paths"] == [ALLOWED_LOCK_PATH]
    assert validate_lock_commit_report(root, report, expected_head=report["commit_sha"]) == []


def test_blocks_unrelated_committed_file(tmp_path: Path) -> None:
    _, report = evaluate(tmp_path, extra=True)
    assert "LOCK_COMMIT_SCOPE_INVALID" in report["blockers"]


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("workspace", "CURRENT_LOCK_HASH_MISMATCH"),
        ("report", "LOCK_COMMIT_REPORT_SELF_HASH_MISMATCH"),
        ("head", "REPORT_GIT_HEAD_MISMATCH"),
    ],
)
def test_runtime_reverification_blocks_drift(
    tmp_path: Path,
    mutation: str,
    expected: str,
) -> None:
    root, report = evaluate(tmp_path)
    expected_head = report["commit_sha"]
    if mutation == "workspace":
        (root / ALLOWED_LOCK_PATH).write_text("tampered\n", encoding="utf-8")
    elif mutation == "report":
        report["lock_sha256"] = "0" * 64
    else:
        expected_head = "f" * 40
    blockers = validate_lock_commit_report(root, report, expected_head=expected_head)
    assert expected in blockers


def test_rejects_symlinked_license_review(tmp_path: Path) -> None:
    root, parent, head, lock_bytes = setup_case(tmp_path)
    admission, evidence, review = inputs(tmp_path, parent, lock_bytes)
    review.unlink()
    review.symlink_to(admission)
    with pytest.raises(ValueError, match="license review is missing or unsafe"):
        evaluate_lock_commit(
            root,
            admission,
            evidence,
            review,
            expected_head=head,
            evidence_verifier=verify_evidence,
            evidence_payload_reader=read_payloads,
            license_validator=validate_license,
        )
