from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.adapters.gluonts.p7d_bundle import (
    P7DBundleError,
    create_evidence_bundle,
    sha256_file,
    verify_evidence_bundle,
    verify_and_extract_bundle,
)
from loto.adapters.gluonts.p7d_contract import (
    P7DBundleEntry,
    P7DBundleManifest,
    atomic_write_json,
)


def write_inventory(root: Path, name: str, excluded: set[str]) -> None:
    lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in excluded
    ]
    (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_run(tmp_path: Path, *, p8: bool = False) -> Path:
    run = tmp_path / "run-source"
    p7b = run / "p7b"
    audit = p7b / "audit"
    p7c = run / "p7c"
    audit.mkdir(parents=True)
    p7c.mkdir(parents=True)
    run_id = "p7d-run"
    commit = "a" * 40
    audit_sha = atomic_write_json(
        audit / "p7_target_machine_audit.json",
        {"run_id": run_id, "evidence_state": "VALID"},
    )
    matrix_sha = atomic_write_json(
        audit / "p7_failure_matrix.json",
        {"run_id": run_id, "rows": []},
    )
    atomic_write_json(
        audit / "p7_artifact_manifest.json",
        {
            "run_id": run_id,
            "audit_sha256": audit_sha,
            "failure_matrix_sha256": matrix_sha,
        },
    )
    write_inventory(audit, "P7_SHA256SUMS", {"P7_SHA256SUMS"})
    journal_sha = atomic_write_json(
        p7b / "p7b_execution_journal.json",
        {
            "run_id": run_id,
            "execution_state": "COMPLETED",
        },
    )
    atomic_write_json(
        p7b / "p7b_execution_manifest.json",
        {
            "run_id": run_id,
            "commit_sha": commit,
            "journal_sha256": journal_sha,
        },
    )
    (p7b / "P7B_EXECUTION_COMPLETE").write_text(
        f"RUN_ID={run_id}\nCOMMIT_SHA={commit}\n",
        encoding="utf-8",
    )
    (p7b / ".p7b.lock").write_text("123\n", encoding="utf-8")
    write_inventory(
        p7b,
        "P7B_EXECUTION_SHA256SUMS",
        {"P7B_EXECUTION_SHA256SUMS", "P7B_PARTIAL_SHA256SUMS", ".p7b.lock"},
    )
    p7b_manifest_sha = sha256_file(p7b / "p7b_execution_manifest.json")
    p7b_checksums_sha = sha256_file(p7b / "P7B_EXECUTION_SHA256SUMS")
    verified = 18 if p8 else 17
    status = "VERIFIED" if p8 else "FAILED"
    plan = {
        "phase": "P7C_RESULT_TRIAGE_AND_REMEDIATION",
        "source": {
            "p7b_output_directory": str(p7b),
            "run_id": run_id,
            "commit_sha": commit,
            "execution_manifest_sha256": p7b_manifest_sha,
            "execution_checksum_sha256": p7b_checksums_sha,
            "audit_sha256": audit_sha,
            "failure_matrix_sha256": matrix_sha,
        },
        "evidence_state": "VALID",
        "certification_status": status,
        "verified_model_lifecycles": verified,
        "p8_eligible": p8,
        "items": [],
        "recommended_next_action": "next",
        "counts": {},
        "errors": [],
    }
    plan_sha = atomic_write_json(p7c / "p7c_remediation_plan.json", plan)
    (p7c / "p7c_remediation_queue.tsv").write_text("priority\n", encoding="utf-8")
    (p7c / "p7c_remediation_report.md").write_text("# report\n", encoding="utf-8")
    atomic_write_json(
        p7c / "p7c_artifact_manifest.json",
        {
            "schema_version": 1,
            "phase": plan["phase"],
            "run_id": run_id,
            "source_commit_sha": commit,
            "source_execution_manifest_sha256": p7b_manifest_sha,
            "source_execution_checksum_sha256": p7b_checksums_sha,
            "source_audit_sha256": audit_sha,
            "source_failure_matrix_sha256": matrix_sha,
            "plan_sha256": plan_sha,
            "queue_sha256": sha256_file(p7c / "p7c_remediation_queue.tsv"),
            "report_sha256": sha256_file(p7c / "p7c_remediation_report.md"),
            "p8_eligible": p8,
        },
    )
    write_inventory(p7c, "P7C_SHA256SUMS", {"P7C_SHA256SUMS"})
    (run / "RUN_ID").write_text(run_id + "\n", encoding="utf-8")
    (run / "p7b.rc").write_text("0\n", encoding="utf-8")
    (run / "p7c.rc").write_text("0\n" if p8 else "10\n", encoding="utf-8")
    (run / "p7b.stdout.log").write_text("done\n", encoding="utf-8")
    (run / "p7b.stderr.log").write_text("", encoding="utf-8")
    (run / "p7c.stdout.log").write_text("done\n", encoding="utf-8")
    (run / "p7c.stderr.log").write_text("", encoding="utf-8")
    write_inventory(
        run,
        "P7C_ORCHESTRATION_SHA256SUMS",
        {"P7C_ORCHESTRATION_SHA256SUMS"},
    )
    return run


def rewrite_zip(source: Path, target: Path, mutate) -> None:
    with zipfile.ZipFile(source, "r") as current:
        records = [(info, current.read(info.filename)) for info in current.infolist()]
    with zipfile.ZipFile(target, "w") as output:
        for info, payload in records:
            new_info, new_payload = mutate(info, payload)
            output.writestr(new_info, new_payload)


def test_manifest_rejects_false_p8_gate() -> None:
    with pytest.raises(ValidationError):
        P7DBundleManifest(
            run_id="run",
            source_commit_sha="a" * 40,
            created_at_utc="2026-08-05T00:00:00Z",
            p7b_execution_manifest_sha256="b" * 64,
            p7b_execution_checksum_sha256="c" * 64,
            p7c_manifest_sha256="d" * 64,
            p7c_checksum_sha256="e" * 64,
            orchestration_checksum_sha256="f" * 64,
            audit_sha256="1" * 64,
            failure_matrix_sha256="2" * 64,
            p7b_return_code=0,
            p7c_return_code=0,
            evidence_state="VALID",
            certification_status="VERIFIED",
            verified_model_lifecycles=18,
            p8_eligible=False,
            entries=[P7DBundleEntry(path="run/a", sha256="3" * 64, size_bytes=1)],
        )


def test_export_verify_round_trip(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    bundle = tmp_path / "handoff.zip"
    manifest, archive_sha = create_evidence_bundle(run, bundle)
    report = verify_evidence_bundle(bundle)
    assert report.archive_sha256 == archive_sha
    assert report.run_id == manifest.run_id
    assert report.verified_model_lifecycles == 17
    assert not report.p8_eligible
    assert bundle.with_suffix(".zip.sha256").is_file()


def test_p8_status_survives_round_trip(tmp_path: Path) -> None:
    run = make_run(tmp_path, p8=True)
    bundle = tmp_path / "handoff.zip"
    create_evidence_bundle(run, bundle)
    report = verify_evidence_bundle(bundle)
    assert report.p8_eligible
    assert report.verified_model_lifecycles == 18


def test_source_tampering_is_rejected(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    (run / "p7c/p7c_remediation_report.md").write_text("tampered\n")
    with pytest.raises(P7DBundleError, match="checksum mismatch"):
        create_evidence_bundle(run, tmp_path / "handoff.zip")


def test_archive_must_be_outside_run(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        create_evidence_bundle(run, run / "handoff.zip")


def test_existing_archive_is_rejected(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    bundle = tmp_path / "handoff.zip"
    bundle.write_bytes(b"existing")
    with pytest.raises(ValueError, match="must not already exist"):
        create_evidence_bundle(run, bundle)


def test_tampered_archive_is_rejected(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    source = tmp_path / "source.zip"
    target = tmp_path / "tampered.zip"
    create_evidence_bundle(run, source)

    def mutate(info: zipfile.ZipInfo, payload: bytes):
        if info.filename == "run/RUN_ID":
            payload = b"changed\n"
        return info, payload

    rewrite_zip(source, target, mutate)
    with pytest.raises(P7DBundleError, match="checksum mismatch"):
        verify_evidence_bundle(target)


def test_duplicate_member_is_rejected(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    bundle = tmp_path / "handoff.zip"
    create_evidence_bundle(run, bundle)
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("run/RUN_ID", b"duplicate\n")
    with pytest.raises(P7DBundleError, match="duplicate member"):
        verify_evidence_bundle(bundle)


def test_traversal_member_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "traversal.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../escape", b"bad")
    with pytest.raises(P7DBundleError, match="unsafe relative path"):
        verify_evidence_bundle(bundle)


def test_symlink_member_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("run/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(info, b"target")
    with pytest.raises(P7DBundleError, match="symlink"):
        verify_evidence_bundle(bundle)


def test_verify_extract_refuses_nonempty_output(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    bundle = tmp_path / "handoff.zip"
    create_evidence_bundle(run, bundle)
    output = tmp_path / "verified"
    output.mkdir()
    (output / "keep.txt").write_text("keep\n")
    with pytest.raises(ValueError, match="absent or empty"):
        verify_and_extract_bundle(bundle, output)


def test_verify_extract_writes_complete_inventory(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    bundle = tmp_path / "handoff.zip"
    create_evidence_bundle(run, bundle)
    output = tmp_path / "verified"
    report = verify_and_extract_bundle(bundle, output)
    assert report.verification_state.value == "VERIFIED"
    assert (output / "run/P7C_ORCHESTRATION_SHA256SUMS").is_file()
    assert (output / "p7d_verification_report.json").is_file()
    assert (output / "P7D_VERIFY_SHA256SUMS").is_file()
