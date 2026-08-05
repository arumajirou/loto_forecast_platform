from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from loto.mlforecast import final_evidence
from loto.mlforecast.final_evidence import (
    REQUIRED_HANDOFF,
    build,
    verify,
)


def _write(path: Path, payload: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_bytes(payload)


def _zip_bytes(names: set[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            archive.writestr(name, b"x")
    return buffer.getvalue()


def _source_run(tmp_path: Path, *, status: str = "FINAL_VERIFICATION_PASSED") -> Path:
    run_id = "mlforecast-final-20260805-120000-123456789-abcdef123456"
    root = tmp_path / run_id
    handoff_zip = root / "handoff/mlforecast-handoff-abcdef123456.zip"
    _write(handoff_zip, _zip_bytes(REQUIRED_HANDOFF))
    handoff_digest = hashlib.sha256(handoff_zip.read_bytes()).hexdigest()
    _write(handoff_zip.with_suffix(".zip.sha256"), f"{handoff_digest}  {handoff_zip.name}\n")
    _write(root / "logs/01.log", "PASS\n")
    runtime_files: list[str] = []
    if status == "FINAL_VERIFICATION_PASSED":
        runtime_zip = root / "runtime/mlforecast-runtime-20260805-120000-123456.zip"
        _write(runtime_zip, b"runtime")
        digest = hashlib.sha256(runtime_zip.read_bytes()).hexdigest()
        _write(runtime_zip.with_suffix(".zip.sha256"), f"{digest}  {runtime_zip.name}\n")
        report = runtime_zip.with_name(runtime_zip.stem + ".verification.json")
        _write(
            report,
            json.dumps(
                {
                    "status": "BUNDLE_VERIFIED",
                    "run_id": "mlforecast-runtime-20260805-120000-123456",
                    "source_status": "RUNTIME_CERTIFIED",
                    "zip_sha256": digest,
                }
            )
            + "\n",
        )
        runtime_files = [runtime_zip.name, runtime_zip.with_suffix(".zip.sha256").name, report.name]
    _write(
        root / "FINAL_VERIFICATION.json",
        json.dumps({"run_id": run_id, "status": status}) + "\n",
    )
    records = []
    excluded = {"ARTIFACT_MANIFEST.json", "SHA256SUMS", "FINAL_GATE_VERIFICATION.json"}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        if name in excluded:
            continue
        payload = path.read_bytes()
        records.append(
            {
                "path": name,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = json.dumps({"format": 2, "artifacts": records}, indent=2, sort_keys=True) + "\n"
    sums = "".join(f"{item['sha256']}  {item['path']}\n" for item in records)
    _write(root / "ARTIFACT_MANIFEST.json", manifest)
    _write(root / "SHA256SUMS", sums)
    gate = {
        "status": "FINAL_GATE_VERIFIED",
        "source_status": status,
        "run_id": run_id,
        "runtime_files": runtime_files,
        "handoff_status": "HANDOFF_VERIFIED",
        "file_count": len(records),
        "manifest_sha256": hashlib.sha256(manifest.encode()).hexdigest(),
        "sums_sha256": hashlib.sha256(sums.encode()).hexdigest(),
    }
    _write(root / "FINAL_GATE_VERIFICATION.json", json.dumps(gate, indent=2, sort_keys=True) + "\n")
    return root


def _patch_verifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        final_evidence,
        "verify_guarded_handoff",
        lambda *_args, **_kwargs: {"status": "HANDOFF_VERIFIED"},
    )
    monkeypatch.setattr(
        final_evidence,
        "verify_bundle_archive",
        lambda *_args, **_kwargs: SimpleNamespace(
            run_id="mlforecast-runtime-20260805-120000-123456",
            source_status="RUNTIME_CERTIFIED",
        ),
    )


def test_build_and_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_verifiers(monkeypatch)
    root = _source_run(tmp_path)
    result = build(root, tmp_path / "out")
    verified = verify(
        result[0],
        result[1],
        report_path=tmp_path / "verification.json",
    )
    assert verified["source_status"] == "FINAL_VERIFICATION_PASSED"
    assert (tmp_path / "verification.json").is_file()
    report = json.loads((tmp_path / "verification.json").read_text())
    assert report["status"] == "FINAL_EVIDENCE_VERIFIED"


def test_final_evidence_is_deterministic(tmp_path: Path) -> None:
    root = _source_run(tmp_path)
    one = build(root, tmp_path / "one")
    two = build(root, tmp_path / "two")
    assert final_evidence.sha_file(one[0]) == final_evidence.sha_file(two[0])
    assert one[0].read_bytes() == two[0].read_bytes()


def test_verify_rejects_sidecar_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_verifiers(monkeypatch)
    result = build(_source_run(tmp_path), tmp_path / "out")
    result[1].write_text("0" * 64 + f"  {result[0].name}\n")
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        verify(result[0], result[1])


def test_build_rejects_symlink_in_run(tmp_path: Path) -> None:
    root = _source_run(tmp_path)
    target = root / "target.txt"
    target.write_text("x")
    (root / "link.txt").symlink_to(target)
    with pytest.raises(RuntimeError, match="symlink"):
        build(root, tmp_path / "out")


def test_failed_source_is_preserved_without_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verifiers(monkeypatch)
    root = _source_run(tmp_path, status="FINAL_VERIFICATION_BLOCKED")
    result = build(root, tmp_path / "out")
    verified = verify(result[0], result[1])
    assert verified["source_status"] == "FINAL_VERIFICATION_BLOCKED"


def test_verify_rejects_handoff_missing_portable_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        final_evidence,
        "verify_guarded_handoff",
        lambda *_args, **_kwargs: {"status": "HANDOFF_VERIFIED"},
    )
    zip_name = "handoff/mlforecast-handoff-abcdef123456.zip"
    payloads = {
        zip_name: _zip_bytes({"README.md"}),
    }
    digest = hashlib.sha256(payloads[zip_name]).hexdigest()
    payloads[f"{zip_name}.sha256"] = (
        f"{digest}  {Path(zip_name).name}\n".encode()
    )
    with pytest.raises(RuntimeError, match="omits final-evidence files"):
        final_evidence.verify_nested(
            payloads,
            "FINAL_VERIFICATION_BLOCKED",
            {"runtime_files": []},
        )


def test_rejects_final_gate_file_count_mismatch(tmp_path: Path) -> None:
    root = _source_run(tmp_path)
    gate_path = root / "FINAL_GATE_VERIFICATION.json"
    gate = json.loads(gate_path.read_text())
    gate["file_count"] += 1
    gate_path.write_text(json.dumps(gate) + "\n")
    with pytest.raises(RuntimeError, match="file_count mismatch"):
        build(root, tmp_path / "out")


def test_safe_path_rejects_windows_reserved_name() -> None:
    with pytest.raises(RuntimeError, match="non-portable"):
        final_evidence.safe_name("runtime/CON.txt")
