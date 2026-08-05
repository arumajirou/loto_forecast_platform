from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_hierarchicalforecast_target_certification.py"
)
SPEC = importlib.util.spec_from_file_location("hf_target_certification", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _make_success_bundle(output_root: Path, git_sha: str = "a" * 40) -> dict[str, object]:
    run_id = "hierarchicalforecast-runtime-20260805T000000Z-123"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True)
    summary = {
        "expected_cases": 40,
        "executed_cases": 40,
        "passed_cases": 40,
        "failed_cases": 0,
        "exact_version_match": True,
        "module_distribution_version_consistent": True,
    }
    certification = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "VERIFIED",
        "formal_success": True,
        "run_directory": str(run_dir.resolve()),
        "summary": summary,
        "dependency": {"installed_version": "1.5.1"},
        "runtime": {"git_commit": git_sha},
    }
    results = []
    for game in target.GAMES:
        for method in target.METHODS:
            expected_status = target.EXPECTED_STATUS[method]
            results.append(
                {
                    "game": game,
                    "method": method,
                    "expected_status": expected_status,
                    "case_status": "PASS",
                    "checks": {"expected_status": True},
                    "result": {
                        "status": expected_status,
                        "actual_execution": method in target.EXECUTABLE,
                    },
                }
            )
    method_results = {"schema_version": 1, "run_id": run_id, "results": results}
    inputs = {
        "schema_version": 1,
        "run_id": run_id,
        "games": {game: {} for game in target.GAMES},
    }
    _write_json(run_dir / "RUNTIME_CERTIFICATION.json", certification)
    _write_json(run_dir / "METHOD_RESULTS.json", method_results)
    _write_json(run_dir / "INPUT_EVIDENCE.json", inputs)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "files": [
            {
                "path": name,
                "bytes": (run_dir / name).stat().st_size,
                "sha256": _sha(run_dir / name),
            }
            for name in target.PRIMARY[:3]
        ],
    }
    _write_json(run_dir / "ARTIFACT_MANIFEST.json", manifest)
    (run_dir / "SHA256SUMS").write_text(
        "".join(
            f"{_sha(run_dir / name)}  {name}\n"
            for name in target.PRIMARY
        ),
        encoding="utf-8",
    )
    file_rows = [
        {
            "path": name,
            "bytes": (run_dir / name).stat().st_size,
            "sha256": _sha(run_dir / name),
        }
        for name in target.REQUIRED
    ]
    package_manifest = {
        "run_id": run_id,
        "certification_status": "VERIFIED",
        "files": file_rows,
        "content_set_sha256": hashlib.sha256(
            (
                json.dumps(
                    file_rows,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
        ).hexdigest(),
    }
    zip_path = output_root / f"{run_id}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in target.REQUIRED:
            archive.writestr(_zip_info(f"{run_id}/{name}"), (run_dir / name).read_bytes())
        archive.writestr(
            _zip_info(f"{run_id}/{target.PACKAGE_MANIFEST}"),
            (
                json.dumps(
                    package_manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ).encode()
                + b"\n"
            ),
        )
    digest = _sha(zip_path)
    sidecar = Path(f"{zip_path}.sha256")
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return {
        "certification": certification,
        "package": {
            "status": "VERIFIED",
            "path": str(zip_path.resolve()),
            "sha256": digest,
            "sha256_sidecar": str(sidecar.resolve()),
            "run_id": run_id,
            "certification_status": "VERIFIED",
            "member_count": 6,
            "bytes": zip_path.stat().st_size,
            "content_set_sha256": package_manifest["content_set_sha256"],
        },
    }


def test_verify_formal_result_accepts_complete_bundle(tmp_path: Path) -> None:
    payload = _make_success_bundle(tmp_path)
    result = target.verify_formal(payload, tmp_path, "a" * 40)
    assert result["summary"]["passed_cases"] == 40
    assert result["zip_member_count"] == 6
    assert result["method_partition"] == {
        "executed_cases": 24,
        "rejected_cases": 16,
    }


def test_verify_formal_result_rejects_bad_case_count(tmp_path: Path) -> None:
    payload = _make_success_bundle(tmp_path)
    payload["certification"]["summary"]["passed_cases"] = 39
    with pytest.raises(target.CertificationError, match="summary mismatch"):
        target.verify_formal(payload, tmp_path, "a" * 40)


def test_verify_formal_result_rejects_sidecar_mismatch(tmp_path: Path) -> None:
    payload = _make_success_bundle(tmp_path)
    Path(payload["package"]["sha256_sidecar"]).write_text("0" * 64 + "  bad.zip\n")
    with pytest.raises(target.CertificationError, match="sidecar"):
        target.verify_formal(payload, tmp_path, "a" * 40)


def test_verify_formal_result_rejects_missing_execution_evidence(tmp_path: Path) -> None:
    payload = _make_success_bundle(tmp_path)
    run_dir = Path(payload["certification"]["run_directory"])
    method_path = run_dir / "METHOD_RESULTS.json"
    method_payload = json.loads(method_path.read_text(encoding="utf-8"))
    method_payload["results"][0]["result"]["actual_execution"] = False
    _write_json(method_path, method_payload)
    manifest_path = run_dir / "ARTIFACT_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        if row["path"] == "METHOD_RESULTS.json":
            row["bytes"] = method_path.stat().st_size
            row["sha256"] = _sha(method_path)
    _write_json(manifest_path, manifest)
    (run_dir / "SHA256SUMS").write_text(
        "".join(
            f"{_sha(run_dir / name)}  {name}\n"
            for name in target.PRIMARY
        ),
        encoding="utf-8",
    )
    with pytest.raises(target.CertificationError, match="execution evidence"):
        target.verify_formal(payload, tmp_path, "a" * 40)


def test_read_checksums_rejects_traversal(tmp_path: Path) -> None:
    path = tmp_path / "SHA256SUMS"
    path.write_text(f"{'0' * 64}  ../escape\n", encoding="utf-8")
    with pytest.raises(target.CertificationError, match="unsafe"):
        target.checksums(path, {"../escape"})


def test_run_target_certification_success(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    output = repo / "artifacts/runtime"

    def fake_runner(command, cwd, stdout_path, stderr_path):
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text("", encoding="utf-8")
        if "-c" in command:
            stdout_path.write_text("1.5.1\n", encoding="utf-8")
            return {"command": list(command), "cwd": str(cwd), "returncode": 0,
                    "started_at": "s", "finished_at": "f", "duration_seconds": 0.1,
                    "stdout_path": str(stdout_path), "stderr_path": str(stderr_path)}
        payload = _make_success_bundle(output)
        stdout_path.write_text(json.dumps(payload), encoding="utf-8")
        return {"command": list(command), "cwd": str(cwd), "returncode": 0,
                "started_at": "s", "finished_at": "f", "duration_seconds": 0.1,
                "stdout_path": str(stdout_path), "stderr_path": str(stderr_path)}

    report, code = target.execute(
        repo,
        Path("artifacts/runtime"),
        Path("artifacts/operator"),
        skip_sync=True,
        runner=fake_runner,
        probe=lambda _: {
            "commit": "a" * 40,
            "branch": "test",
            "clean": True,
            "status_porcelain": [],
        },
    )
    assert code == 0
    assert report["status"] == "VERIFIED"
    operator_dir = Path(report["operator_directory"])
    assert (operator_dir / "OPERATOR_REPORT.json").is_file()
    assert (operator_dir / "SHA256SUMS").is_file()


def test_run_target_certification_version_mismatch_retains_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_runner(command, cwd, stdout_path, stderr_path):
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("1.5.0\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return {"command": list(command), "cwd": str(cwd), "returncode": 0,
                "started_at": "s", "finished_at": "f", "duration_seconds": 0.1,
                "stdout_path": str(stdout_path), "stderr_path": str(stderr_path)}

    report, code = target.execute(
        repo,
        Path("runtime"),
        Path("operator"),
        skip_sync=True,
        runner=fake_runner,
        probe=lambda _: {
            "commit": "a" * 40,
            "branch": "test",
            "clean": True,
            "status_porcelain": [],
        },
    )
    assert code == 2
    assert report["status"] == "FAILED_VERSION_MISMATCH"
    assert Path(report["operator_directory"], "OPERATOR_REPORT.json").is_file()


def test_run_target_certification_dirty_worktree_fails_preflight(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    report, code = target.execute(
        repo,
        Path("runtime"),
        Path("operator"),
        skip_sync=True,
        probe=lambda _: {
            "commit": "a" * 40,
            "branch": "test",
            "clean": False,
            "status_porcelain": ["?? dirty.txt"],
        },
    )
    assert code == 3
    assert report["status"] == "FAILED_PREFLIGHT"
    assert "clean worktree" in report["error"]
