from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from loto.toto2_campaign.certification_bundle import (
    build_artifact_manifest,
    create_deterministic_zip,
    expand_formal_matrix,
    sha256_file,
    validate_lock_review,
    validate_request_case,
    verify_artifact_manifest,
)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def matrix_manifest(path: Path) -> None:
    write_json(
        path,
        {
            "schema_version": 1,
            "matrix_id": "toto2-4m-formal-v1",
            "games": ["numbers3", "numbers4", "miniloto", "loto6", "loto7"],
            "contexts": [128, 256, 512],
            "horizons": [1, 2, 5],
            "devices": ["cpu", "cuda"],
            "request_pattern": "{game}-c{context}-h{horizon}-{device}.json",
        },
    )


def test_expand_formal_matrix_has_exact_90_cases(tmp_path: Path) -> None:
    manifest = tmp_path / "matrix.json"
    matrix_manifest(manifest)
    cases = expand_formal_matrix(manifest, tmp_path / "requests")
    assert len(cases) == 90
    assert len({case.case_id for case in cases}) == 90
    assert cases[0].case_id == "numbers3-c128-h1-cpu"
    assert cases[-1].case_id == "loto7-c512-h5-cuda"


def test_matrix_rejects_missing_device(tmp_path: Path) -> None:
    manifest = tmp_path / "matrix.json"
    matrix_manifest(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["devices"] = ["cuda"]
    write_json(manifest, payload)
    with pytest.raises(ValueError, match="devices"):
        expand_formal_matrix(manifest, tmp_path / "requests")


def test_validate_request_case_rejects_metadata_drift(tmp_path: Path) -> None:
    manifest = tmp_path / "matrix.json"
    matrix_manifest(manifest)
    case = expand_formal_matrix(manifest, tmp_path / "requests")[0]
    write_json(
        case.request_path,
        {
            "operation": "predict",
            "local_files_only": True,
            "game_geometry": {"game_id": case.game},
            "context_length": case.context,
            "prediction_length": 2,
            "device": case.device,
        },
    )
    with pytest.raises(ValueError, match="horizon mismatch"):
        validate_request_case(case)


def test_lock_review_requires_exact_hash(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_text("locked\n", encoding="utf-8")
    review = tmp_path / "review.json"
    write_json(
        review,
        {
            "schema_version": 1,
            "status": "APPROVED",
            "reviewer": "reviewer",
            "reviewed_at": "2026-08-06T00:00:00Z",
            "lock_sha256": sha256_file(lock),
            "dependency_sources_reviewed": True,
            "package_hashes_reviewed": True,
            "licenses_reviewed": True,
        },
    )
    assert validate_lock_review(review, lock)["status"] == "APPROVED"
    lock.write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_lock_review(review, lock)


def test_artifact_manifest_detects_tampering(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path)
    verify_artifact_manifest(tmp_path, manifest)
    (tmp_path / "a.txt").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="size mismatch|hash mismatch"):
        verify_artifact_manifest(tmp_path, manifest)


def test_deterministic_zip_has_fixed_metadata(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    manifest = build_artifact_manifest(root)
    archive_one = tmp_path / "one.zip"
    archive_two = tmp_path / "two.zip"
    create_deterministic_zip(root, archive_one, manifest)
    create_deterministic_zip(root, archive_two, manifest)
    assert sha256_file(archive_one) == sha256_file(archive_two)
    with zipfile.ZipFile(archive_one) as archive:
        assert archive.namelist() == ["a.txt", "b.txt"]
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
