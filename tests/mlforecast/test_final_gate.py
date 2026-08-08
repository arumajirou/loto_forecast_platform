from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from loto.mlforecast import final_gate
from loto.mlforecast.final_gate import REQUIRED_HANDOFF_FILES, finalize_final_gate


def _write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)


def _sidecar(zip_path: Path) -> None:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    _write(zip_path.with_suffix(".zip.sha256"), f"{digest}  {zip_path.name}\n")


def _run(
    tmp_path: Path,
    *,
    status: str = "FINAL_VERIFICATION_PASSED",
    include_required: bool = True,
    runtime_source: str = "RUNTIME_CERTIFIED",
) -> Path:
    run_id = "mlforecast-final-20260805-123456-123456789-aaaaaaaaaaaa"
    run_dir = tmp_path / run_id
    _write(
        run_dir / "FINAL_VERIFICATION.json",
        json.dumps({"run_id": run_id, "status": status}, sort_keys=True) + "\n",
    )
    handoff_zip = run_dir / "handoff" / "mlforecast-handoff-aaaaaaaaaaaa.zip"
    handoff_zip.parent.mkdir(parents=True)
    names = set(REQUIRED_HANDOFF_FILES)
    if not include_required:
        names.remove("docs/mlforecast/run_final_verification_complete.sh")
    with zipfile.ZipFile(handoff_zip, "w") as archive:
        for name in sorted(names):
            archive.writestr(name, b"content")
    _sidecar(handoff_zip)

    if status == "FINAL_VERIFICATION_PASSED":
        source_dir = tmp_path / "runtime-source"
        bundle = source_dir / "mlforecast-runtime-20260805-123456-123456.zip"
        _write(bundle, b"runtime")
        _sidecar(bundle)
        verification = source_dir / "mlforecast-runtime-20260805-123456-123456.verification.json"
        digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
        _write(
            verification,
            json.dumps(
                {
                    "status": "BUNDLE_VERIFIED",
                    "source_status": runtime_source,
                    "zip_sha256": digest,
                },
                sort_keys=True,
            )
            + "\n",
        )
        _write(
            run_dir / "logs" / "08-installed-runtime.log",
            "\n".join(
                (
                    f"BUNDLE={bundle}",
                    f"BUNDLE_SHA256={bundle.with_suffix('.zip.sha256')}",
                    f"BUNDLE_VERIFICATION_REPORT={verification}",
                )
            )
            + "\n",
        )
    return run_dir


def test_final_gate_copies_runtime_and_rewrites_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run(tmp_path)
    monkeypatch.setattr(
        final_gate,
        "verify_guarded_handoff",
        lambda *_args: {"status": "HANDOFF_VERIFIED"},
    )
    result = finalize_final_gate(run_dir)
    assert result["status"] == "FINAL_GATE_VERIFIED"
    assert result["source_status"] == "FINAL_VERIFICATION_PASSED"
    assert len(result["runtime_files"]) == 3
    assert (run_dir / "ARTIFACT_MANIFEST.json").is_file()
    assert (run_dir / "SHA256SUMS").is_file()
    assert (run_dir / "FINAL_GATE_VERIFICATION.json").is_file()


def test_final_gate_rejects_handoff_without_complete_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run(tmp_path, include_required=False)
    monkeypatch.setattr(
        final_gate,
        "verify_guarded_handoff",
        lambda *_args: {"status": "HANDOFF_VERIFIED"},
    )
    with pytest.raises(RuntimeError, match="handoff omits final-gate files"):
        finalize_final_gate(run_dir)


def test_passed_final_gate_requires_certified_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run(tmp_path, runtime_source="FAILED")
    monkeypatch.setattr(
        final_gate,
        "verify_guarded_handoff",
        lambda *_args: {"status": "HANDOFF_VERIFIED"},
    )
    with pytest.raises(RuntimeError, match="not RUNTIME_CERTIFIED"):
        finalize_final_gate(run_dir)


def test_blocked_final_gate_preserves_integrity_without_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run(tmp_path, status="FINAL_VERIFICATION_BLOCKED")
    monkeypatch.setattr(
        final_gate,
        "verify_guarded_handoff",
        lambda *_args: {"status": "HANDOFF_VERIFIED"},
    )
    result = finalize_final_gate(run_dir)
    assert result["source_status"] == "FINAL_VERIFICATION_BLOCKED"
    assert result["runtime_files"] == []


def test_complete_wrapper_calls_source_and_finalizer() -> None:
    script = (
        Path(__file__).parents[2] / "docs/mlforecast/run_final_verification_complete.sh"
    ).read_text(encoding="utf-8")
    assert "run_final_verification.sh" in script
    assert "loto.mlforecast.final_gate" in script
    assert "FINAL_GATE_CERTIFIED" in script
    assert "FINAL_GATE_EVIDENCE_PRESERVED" in script
