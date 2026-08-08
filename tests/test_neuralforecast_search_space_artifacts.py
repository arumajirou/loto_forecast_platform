from __future__ import annotations

import json
from pathlib import Path

from loto.models.neuralforecast_search_space import profile_fixed_config
from loto.models.neuralforecast_search_space_artifacts import (
    MANIFEST_NAME,
    MANIFEST_SUM_NAME,
    PROFILE_NAME,
    PROFILE_SUM_NAME,
    persist_search_space_artifacts,
    verify_search_space_artifacts,
)


def test_persisted_profile_manifest_and_checksums_verify(tmp_path: Path) -> None:
    profile = profile_fixed_config(
        {"input_size": 12, "learning_rate": 1e-3},
        backend="optuna",
        model_name="AutoNHITS",
    )

    result = persist_search_space_artifacts(
        tmp_path,
        profile,
        context={"seed": 42, "stage": "hpo"},
    )

    assert result["verification_status"] == "PASS"
    assert verify_search_space_artifacts(tmp_path)["status"] == "PASS"
    assert {path.name for path in tmp_path.iterdir()} == {
        PROFILE_NAME,
        PROFILE_SUM_NAME,
        MANIFEST_NAME,
        MANIFEST_SUM_NAME,
    }
    manifest = json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["profile_sha256"] == profile.profile_sha256
    assert manifest["context"] == {"seed": 42, "stage": "hpo"}
    assert not list(tmp_path.glob(".*.tmp"))


def test_verifier_detects_profile_tampering(tmp_path: Path) -> None:
    profile = profile_fixed_config({"input_size": 12}, backend="ray", model_name="AutoTFT")
    persist_search_space_artifacts(tmp_path, profile)
    (tmp_path / PROFILE_NAME).write_text("{}\n", encoding="utf-8")

    verification = verify_search_space_artifacts(tmp_path)

    assert verification["status"] == "FAIL"
    assert "profile_checksum" in verification["failed_checks"]


def test_missing_files_fail_closed(tmp_path: Path) -> None:
    verification = verify_search_space_artifacts(tmp_path)
    assert verification["status"] == "FAIL"
    assert sorted(verification["missing"]) == sorted(
        [PROFILE_NAME, PROFILE_SUM_NAME, MANIFEST_NAME, MANIFEST_SUM_NAME]
    )
