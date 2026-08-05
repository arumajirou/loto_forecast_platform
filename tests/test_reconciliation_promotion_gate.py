from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hierarchicalforecast_target import promotion_gate as gate

COMMIT = "a" * 40


def _result(
    command: Sequence[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    code: int = 0,
) -> dict[str, object]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text("", encoding="utf-8")
    return {
        "command": list(command),
        "cwd": str(cwd),
        "returncode": code,
        "started_at": "s",
        "finished_at": "f",
        "duration_seconds": 0.1,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _probe(commit: str = COMMIT, clean: bool = True) -> dict[str, object]:
    return {
        "commit": commit,
        "branch": "test",
        "clean": clean,
        "status_porcelain": [] if clean else [" M file"],
    }


def _seal(directory: Path, report_name: str, report: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    gate.atomic_write(directory / report_name, gate.canonical(report))
    gate.atomic_write(directory / "COMMANDS.json", gate.canonical({"commands": []}))
    gate.atomic_write(directory / "stage.stdout.log", b"ok\n")
    files = sorted(directory.iterdir(), key=lambda path: path.name)
    manifest = {
        "files": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": gate.sha_file(path)}
            for path in files
        ]
    }
    manifest_path = directory / "ARTIFACT_MANIFEST.json"
    gate.atomic_write(manifest_path, gate.canonical(manifest))
    gate.atomic_write(
        directory / "SHA256SUMS",
        "".join(
            f"{gate.sha_file(path)}  {path.name}\n" for path in [*files, manifest_path]
        ).encode(),
    )


def _runner_factory(
    root: Path,
    *,
    quality_code: int = 0,
    target_code: int = 0,
    verifier_code: int = 0,
    tamper_quality: bool = False,
    verifier_run_id: str | None = None,
):
    quality_root = root / "artifacts/quality"
    runtime_root = root / "artifacts/runtime"
    operator_root = root / "artifacts/operator"
    calls: list[str] = []

    def runner(command, cwd, stdout_path, stderr_path):
        name = stdout_path.name.removesuffix(".stdout.log")
        calls.append(name)
        if name == "quality":
            directory = quality_root / "quality-1"
            report = {
                "status": "VERIFIED" if quality_code == 0 else "FAILED_RUFF_LINT",
                "formal_success": quality_code == 0,
                "evidence_directory": str(directory),
                "git_commit": COMMIT,
            }
            _seal(directory, "QUALITY_REPORT.json", report)
            if tamper_quality:
                (directory / "stage.stdout.log").write_text("tampered\n", encoding="utf-8")
            stdout_path.write_text(json.dumps(report), encoding="utf-8")
            return _result(command, cwd, stdout_path, stderr_path, quality_code)
        if name == "target":
            runtime_root.mkdir(parents=True, exist_ok=True)
            zip_path = runtime_root / "runtime-1.zip"
            zip_path.write_bytes(b"zip")
            directory = operator_root / "operator-1"
            report = {
                "status": "VERIFIED" if target_code == 0 else "FAILED_RUNTIME",
                "formal_success": target_code == 0,
                "operator_directory": str(directory),
                "certification": {
                    "run_id": "runtime-1",
                    "zip_path": str(zip_path),
                    "zip_sha256": gate.sha_file(zip_path),
                },
            }
            _seal(directory, "OPERATOR_REPORT.json", report)
            stdout_path.write_text(json.dumps(report), encoding="utf-8")
            return _result(command, cwd, stdout_path, stderr_path, target_code)
        if name == "package_verification":
            zip_path = runtime_root / "runtime-1.zip"
            report = {
                "status": "VERIFIED" if verifier_code == 0 else "FAILED_PACKAGE_VERIFICATION",
                "formal_success": verifier_code == 0,
                "run_id": verifier_run_id or "runtime-1",
                "zip_path": str(zip_path),
                "zip_sha256": gate.sha_file(zip_path),
            }
            stdout_path.write_text(json.dumps(report), encoding="utf-8")
            return _result(command, cwd, stdout_path, stderr_path, verifier_code)
        raise AssertionError(name)

    return runner, calls


def _execute(root: Path, runner, probe=lambda _: _probe()):
    return gate.execute(
        root,
        Path("artifacts/promotion"),
        Path("artifacts/quality"),
        Path("artifacts/runtime"),
        Path("artifacts/operator"),
        COMMIT,
        test_mode=True,
        runner=runner,
        probe=probe,
    )


def test_success_runs_all_stages_and_seals_promotion_evidence(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    runner, calls = _runner_factory(root)

    report, code = _execute(root, runner)

    assert code == 0
    assert report["status"] == "LOCAL_GATES_VERIFIED"
    assert report["formal_success"] is True
    assert report["ready_for_review"] is False
    assert calls == ["quality", "target", "package_verification"]
    directory = Path(str(report["promotion_directory"]))
    assert (directory / "PROMOTION_REPORT.json").is_file()
    assert (directory / "ARTIFACT_MANIFEST.json").is_file()
    assert (directory / "SHA256SUMS").is_file()


def test_production_requires_expected_git_sha(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    runner, calls = _runner_factory(root)

    report, code = gate.execute(
        root,
        Path("artifacts/promotion"),
        Path("artifacts/quality"),
        Path("artifacts/runtime"),
        Path("artifacts/operator"),
        None,
        runner=runner,
        probe=lambda _: _probe(),
    )

    assert code == 3
    assert report["status"] == "FAILED_PREFLIGHT"
    assert calls == []


def test_quality_failure_stops_before_target(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    runner, calls = _runner_factory(root, quality_code=2)

    report, code = _execute(root, runner)

    assert code == 2
    assert report["status"] == "FAILED_QUALITY_GATE"
    assert calls == ["quality"]


def test_tampered_quality_evidence_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    runner, calls = _runner_factory(root, tamper_quality=True)

    report, code = _execute(root, runner)

    assert code == 2
    assert report["status"] == "FAILED_QUALITY_GATE"
    assert "SHA256SUMS mismatch" in str(report["error"])
    assert calls == ["quality"]


def test_target_failure_stops_before_standalone_verifier(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    runner, calls = _runner_factory(root, target_code=2)

    report, code = _execute(root, runner)

    assert code == 2
    assert report["status"] == "FAILED_TARGET_CERTIFICATION"
    assert calls == ["quality", "target"]


def test_standalone_verifier_failure_is_preserved(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    runner, calls = _runner_factory(root, verifier_code=2)

    report, code = _execute(root, runner)

    assert code == 2
    assert report["status"] == "FAILED_PACKAGE_VERIFICATION"
    assert calls == ["quality", "target", "package_verification"]


def test_standalone_verifier_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    runner, _ = _runner_factory(root, verifier_run_id="other-run")

    report, code = _execute(root, runner)

    assert code == 2
    assert report["status"] == "FAILED_PACKAGE_VERIFICATION"
    assert "does not match target evidence" in str(report["error"])


def test_postflight_git_drift_fails_after_all_local_stages(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    runner, calls = _runner_factory(root)
    probes = iter([_probe(), _probe("b" * 40)])

    report, code = _execute(root, runner, probe=lambda _: next(probes))

    assert code == 3
    assert report["status"] == "FAILED_POSTFLIGHT_GIT_DRIFT"
    assert calls == ["quality", "target", "package_verification"]
