from __future__ import annotations

import json
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from loto.timesfm25_campaign.certification_bundle import (
    sha256_file,
    verify_sha256_manifest,
    write_sha256_manifest,
)
from loto.timesfm25_campaign.evidence_archive import EvidenceReviewError, inspect_archive
from loto.timesfm25_campaign.evidence_review import review_archive

OFFLINE = {
    "HF_HUB_OFFLINE": "1",
    "PIP_NO_INDEX": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "UV_OFFLINE": "1",
}
RUN_ID = "timesfm25-test-001"
Mutator = Callable[[dict[str, Any]], None]


def payloads(status: str = "VERIFIED_GPU") -> dict[str, Any]:
    request = {
        "schema_version": 2,
        "run_id": RUN_ID,
        "backend": "pytorch_native",
        "repo_id": "google/timesfm-2.5-200m-pytorch",
        "revision": "1" * 40,
        "device": "cuda",
        "local_files_only": True,
        "snapshot_path": f"/snapshots/{RUN_ID}",
    }
    certification = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "backend": request["backend"],
        "repo_id": request["repo_id"],
        "revision": request["revision"],
        "device_requested": request["device"],
        "provider_exit_code": 0,
        "timed_out": False,
        "runtime_status": status,
        "gpu_certification_status": "PASS",
        "provider_response_valid": True,
        "snapshot_path": request["snapshot_path"],
        "snapshot_reloaded": True,
        "model_parameter_device": "cuda:0",
        "mean_output_device": "cuda:0",
        "quantile_output_device": "cuda:0",
        "vram_peak_bytes": 1024,
        "external_pid_match": True,
        "cpu_fallback": False,
    }
    if status == "PARTIALLY_VERIFIED_GPU":
        certification.update(
            gpu_certification_status="PARTIAL",
            mean_output_device="cpu",
            quantile_output_device="cpu",
        )
    if status == "FAILED":
        certification.update(
            gpu_certification_status="NOT_EVALUATED",
            provider_exit_code=1,
            provider_response_valid=False,
        )
    return {
        "command.json": {
            "command": [
                "uv",
                "run",
                "--locked",
                "--offline",
                "python",
                "/repo/scripts/run_timesfm25_provider.py",
            ],
            "offline_environment": OFFLINE,
        },
        "environment.json": {
            "commands": {
                "git_head": {"returncode": 0, "stdout": "a" * 40 + "\n"},
                "git_status": {"returncode": 0, "stdout": ""},
            }
        },
        "nvidia_process_samples.csv": "2026-08-06,GPU-0,123,python,1024",
        "preflight.json": {
            "schema_version": 1,
            "run_id": RUN_ID,
            "status": "PASS",
            "offline_environment": OFFLINE,
            "checks": [
                {
                    "name": "runtime_probe_exit",
                    "status": "PASS",
                    "required": True,
                    "detail": "returncode=0",
                }
            ],
            "failed_checks": [],
        },
        "provider_exit_code.txt": str(certification["provider_exit_code"]),
        "provider_request.json": request,
        "provider_response.json": {"status": "OK", "run_id": RUN_ID},
        "runtime_certification.json": certification,
        "status.txt": status,
    }


def make_archive(
    tmp_path: Path,
    *,
    status: str = "VERIFIED_GPU",
    mutate: Mutator | None = None,
) -> tuple[Path, Path]:
    bundle = tmp_path / "bundle" / RUN_ID
    bundle.mkdir(parents=True)
    values = payloads(status)
    if mutate:
        mutate(values)
    for name, value in values.items():
        text = value if isinstance(value, str) else json.dumps(value, indent=2)
        (bundle / name).write_text(text + "\n", encoding="utf-8")
    write_sha256_manifest(bundle)
    archive = tmp_path / f"{RUN_ID}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(bundle.iterdir()):
            output.write(path, f"{RUN_ID}/{path.name}")
    sidecar = archive.with_suffix(".zip.sha256")
    sidecar.write_text(f"{sha256_file(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, sidecar


def review(tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
    archive, sidecar = make_archive(tmp_path, **kwargs)
    _, report = review_archive(archive, sidecar, tmp_path / "reviews")
    return report


def test_strict_gpu_is_formal_and_outer_seal_passes(tmp_path: Path) -> None:
    archive, sidecar = make_archive(tmp_path)
    review_dir, report = review_archive(archive, sidecar, tmp_path / "reviews")
    assert (report["formal_status"], report["exit_code"]) == ("FORMAL_GPU_CERTIFIED", 0)
    ok, failures = verify_sha256_manifest(review_dir, manifest_name="REVIEW_SHA256SUMS")
    assert ok, failures


def test_partial_gpu_is_never_promoted(tmp_path: Path) -> None:
    report = review(tmp_path, status="PARTIALLY_VERIFIED_GPU")
    assert (report["formal_status"], report["exit_code"]) == ("PARTIALLY_VERIFIED_GPU", 2)


@pytest.mark.parametrize("field", ["mean_output_device", "quantile_output_device"])
def test_cpu_output_rejects_verified_gpu_claim(tmp_path: Path, field: str) -> None:
    def mutate(values: dict[str, Any]) -> None:
        values["runtime_certification.json"][field] = "cpu"

    report = review(tmp_path, mutate=mutate)
    assert report["formal_status"] == "REJECTED"
    assert f"STRICT_GPU_{field.upper()}_FAILED" in report["reasons"]


@pytest.mark.parametrize(
    ("target", "change", "reason"),
    [
        ("provider_request.json", {"run_id": "different-run"}, "REQUEST_RUN_ID_MISMATCH"),
        ("preflight.json", {"status": "FAIL"}, "PREFLIGHT_STATUS_NOT_PASS"),
    ],
)
def test_identity_or_preflight_mismatch_is_rejected(
    tmp_path: Path, target: str, change: dict[str, Any], reason: str
) -> None:
    def mutate(values: dict[str, Any]) -> None:
        values[target].update(change)

    assert reason in review(tmp_path, mutate=mutate)["reasons"]


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("dirty", "GIT_WORKTREE_DIRTY"),
        ("samples", "STRICT_GPU_NVIDIA_SAMPLES_MISSING"),
    ],
)
def test_runtime_provenance_is_required(tmp_path: Path, case: str, reason: str) -> None:
    def mutate(values: dict[str, Any]) -> None:
        if case == "dirty":
            values["environment.json"]["commands"]["git_status"]["stdout"] = " M src/x.py\n"
        else:
            values.pop("nvidia_process_samples.csv")

    assert reason in review(tmp_path, mutate=mutate)["reasons"]


def test_internal_manifest_tampering_is_rejected(tmp_path: Path) -> None:
    archive, _ = make_archive(tmp_path)
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(tampered, "w") as output:
        for info in source.infolist():
            data = b"FAILED\n" if info.filename.endswith("status.txt") else source.read(info)
            output.writestr(info, data)
    sidecar = tampered.with_suffix(".zip.sha256")
    sidecar.write_text(f"{sha256_file(tampered)}  {tampered.name}\n", encoding="utf-8")
    _, report = review_archive(tampered, sidecar, tmp_path / "reviews")
    assert "INTERNAL_SHA256_FAILED" in report["reasons"]


@pytest.mark.parametrize("case", ["digest", "filename", "expected_run"])
def test_external_archive_identity_mismatch_stops_review(tmp_path: Path, case: str) -> None:
    archive, sidecar = make_archive(tmp_path)
    expected = None
    if case == "digest":
        sidecar.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")
    elif case == "filename":
        sidecar.write_text(f"{sha256_file(archive)}  wrong.zip\n", encoding="utf-8")
    else:
        expected = "other-run"
    with pytest.raises(EvidenceReviewError):
        review_archive(archive, sidecar, tmp_path / "reviews", expected_run_id=expected)


@pytest.mark.parametrize("case", ["zip_slip", "duplicate", "symlink", "two_roots"])
def test_unsafe_zip_topology_is_rejected(tmp_path: Path, case: str) -> None:
    archive = tmp_path / f"{case}.zip"
    with zipfile.ZipFile(archive, "w") as output:
        if case == "zip_slip":
            output.writestr("safe-run/../escape.txt", "x")
        elif case == "duplicate":
            output.writestr("safe-run/a.txt", "a")
            with pytest.warns(UserWarning, match="Duplicate name"):
                output.writestr("safe-run/a.txt", "b")
        elif case == "symlink":
            info = zipfile.ZipInfo("safe-run/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            output.writestr(info, "target")
        else:
            output.writestr("run-a/a.txt", "a")
            output.writestr("run-b/b.txt", "b")
    with pytest.raises(EvidenceReviewError):
        inspect_archive(archive)


def test_failed_runtime_rejected_and_review_directory_is_immutable(tmp_path: Path) -> None:
    archive, sidecar = make_archive(tmp_path, status="FAILED")
    _, report = review_archive(archive, sidecar, tmp_path / "reviews")
    assert "RUNTIME_STATUS_FAILED" in report["reasons"]
    with pytest.raises(FileExistsError):
        review_archive(archive, sidecar, tmp_path / "reviews")
