"""Synthetic sealed evidence used by target-certification tests."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from hierarchicalforecast_target import constants as c
from hierarchicalforecast_target.integrity import canonical


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array(shape: list[int], token: str = "a") -> dict[str, object]:
    return {
        "shape": shape,
        "dtype": "float64-le",
        "finite": True,
        "sha256": token * 64,
        "minimum": 0.0,
        "maximum": 1.0,
    }


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def refresh_runtime_integrity(run_dir: Path) -> None:
    manifest = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "files": [
            {
                "path": name,
                "bytes": (run_dir / name).stat().st_size,
                "sha256": sha(run_dir / name),
            }
            for name in c.PRIMARY[:3]
        ],
    }
    write_json(run_dir / "ARTIFACT_MANIFEST.json", manifest)
    (run_dir / "SHA256SUMS").write_text(
        "".join(f"{sha(run_dir / name)}  {name}\n" for name in c.PRIMARY),
        encoding="utf-8",
    )


def make_success_bundle(output_root: Path, git_sha: str = "a" * 40) -> dict[str, object]:
    run_id = "hierarchicalforecast-runtime-20260805T000000Z-123"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True)
    certification = _certification(output_root, run_dir, run_id, git_sha)
    results, geometry = _method_results(run_id)
    inputs = _input_evidence(run_id, geometry)
    write_json(run_dir / "RUNTIME_CERTIFICATION.json", certification)
    write_json(run_dir / "METHOD_RESULTS.json", results)
    write_json(run_dir / "INPUT_EVIDENCE.json", inputs)
    refresh_runtime_integrity(run_dir)
    package = _package(output_root, run_dir, run_id)
    return {"certification": certification, "package": package}


def _certification(
    output_root: Path,
    run_dir: Path,
    run_id: str,
    git_sha: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "status": "VERIFIED",
        "formal_success": True,
        "run_directory": str(run_dir.resolve()),
        "config": {
            "output_root": str(output_root.resolve()),
            "games": list(c.GAMES),
            "expected_version": c.TARGET_VERSION,
            "seed": c.FORMAL_SEED,
            "horizon": c.FORMAL_HORIZON,
            "insample_size": c.FORMAL_INSAMPLE_SIZE,
            "coherence_tolerance": c.FORMAL_TOLERANCE,
        },
        "summary": {
            "expected_cases": 40,
            "executed_cases": 40,
            "passed_cases": 40,
            "failed_cases": 0,
            "exact_version_match": True,
            "module_distribution_version_consistent": True,
        },
        "dependency": {
            "import_status": "PASS",
            "installed_version": c.TARGET_VERSION,
            "module_version": c.TARGET_VERSION,
            "distribution_version": c.TARGET_VERSION,
            "version_consistent": True,
        },
        "runtime": {
            "git_commit": git_sha,
            "device": "cpu",
            "gpu_expected": False,
            "packages": {"hierarchicalforecast": c.TARGET_VERSION},
        },
    }


def _method_results(run_id: str) -> tuple[dict[str, object], dict[str, tuple[int, int]]]:
    rows = []
    geometry = {game: (10 + index, 5 + index) for index, game in enumerate(c.GAMES)}
    for game in c.GAMES:
        n_total, n_bottom = geometry[game]
        for method in c.METHODS:
            expected = c.EXPECTED_STATUS[method]
            result = (
                _executable_result(method, n_total, n_bottom)
                if method in c.EXECUTABLE
                else _rejected_result(method)
            )
            rows.append(
                {
                    "game": game,
                    "method": method,
                    "expected_status": expected,
                    "case_status": "PASS",
                    "checks": {"all_contract_checks": True},
                    "hierarchy": {
                        "n_total": n_total,
                        "n_bottom": n_bottom,
                        "labels_sha256": "d" * 64,
                    },
                    "result": result,
                }
            )
    return {"schema_version": 1, "run_id": run_id, "results": rows}, geometry


def _executable_result(method: str, n_total: int, n_bottom: int) -> dict[str, object]:
    return {
        "status": "VERIFIED",
        "method": method,
        "actual_execution": True,
        "upstream_version": c.TARGET_VERSION,
        "finite": True,
        "shape": [n_total, c.FORMAL_HORIZON],
        "coherence_error": 0.0,
        "coherence_tolerance": c.FORMAL_TOLERANCE,
        "bottom": array([n_bottom, c.FORMAL_HORIZON], "b"),
        "reconciled": array([n_total, c.FORMAL_HORIZON], "c"),
    }


def _rejected_result(method: str) -> dict[str, object]:
    return {
        "status": "UNSUPPORTED_HIERARCHY",
        "method": method,
        "actual_execution": False,
        "hierarchy_is_strict": False,
        "error": "grouped hierarchy is not a strict tree",
    }


def _input_evidence(
    run_id: str,
    geometry: dict[str, tuple[int, int]],
) -> dict[str, object]:
    games = {}
    for index, game in enumerate(c.GAMES):
        n_total, n_bottom = geometry[game]
        games[game] = {
            "seed": c.FORMAL_SEED + index * 10_000,
            "hierarchy": {"n_total": n_total, "n_bottom": n_bottom},
            "inputs": {
                "base_forecasts": array([n_total, c.FORMAL_HORIZON], "e"),
                "insample_actuals": array([n_total, c.FORMAL_INSAMPLE_SIZE], "f"),
                "insample_forecasts": array([n_total, c.FORMAL_INSAMPLE_SIZE], "1"),
                "summing_matrix": array([n_total, n_bottom], "2"),
            },
        }
    return {"schema_version": 1, "run_id": run_id, "games": games}


def _package(output_root: Path, run_dir: Path, run_id: str) -> dict[str, object]:
    rows = [
        {
            "path": name,
            "bytes": (run_dir / name).stat().st_size,
            "sha256": sha(run_dir / name),
        }
        for name in c.REQUIRED
    ]
    manifest = {
        "run_id": run_id,
        "certification_status": "VERIFIED",
        "files": rows,
        "content_set_sha256": hashlib.sha256(canonical(rows)).hexdigest(),
    }
    zip_path = output_root / f"{run_id}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in c.REQUIRED:
            archive.writestr(zip_info(f"{run_id}/{name}"), (run_dir / name).read_bytes())
        archive.writestr(zip_info(f"{run_id}/{c.PACKAGE_MANIFEST}"), canonical(manifest))
    digest = sha(zip_path)
    sidecar = Path(f"{zip_path}.sha256")
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return {
        "status": "VERIFIED",
        "path": str(zip_path.resolve()),
        "sha256": digest,
        "sha256_sidecar": str(sidecar.resolve()),
        "run_id": run_id,
        "certification_status": "VERIFIED",
        "member_count": 6,
        "bytes": zip_path.stat().st_size,
        "content_set_sha256": manifest["content_set_sha256"],
    }


def fake_success_runner(output: Path):
    def run(command, cwd, stdout_path, stderr_path):
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text("", encoding="utf-8")
        if "-c" in command:
            stdout_path.write_text(f"{c.TARGET_VERSION}\n", encoding="utf-8")
        else:
            stdout_path.write_text(json.dumps(make_success_bundle(output)), encoding="utf-8")
        return {
            "command": list(command),
            "cwd": str(cwd),
            "returncode": 0,
            "started_at": "s",
            "finished_at": "f",
            "duration_seconds": 0.1,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }

    return run


def clean_state(commit: str = "a" * 40) -> dict[str, object]:
    return {
        "commit": commit,
        "branch": "test",
        "clean": True,
        "status_porcelain": [],
    }
