from __future__ import annotations

import json
from pathlib import Path

from loto.auto_campaign.model_factory import (
    _artifact_kwargs,
    _persist_search_space_profile,
    _search_space_evidence_root,
    _search_space_profile,
)
from loto.models.neuralforecast_search_policy import SearchPolicyDecision
from loto.models.neuralforecast_search_space import SearchSpaceCompleteness
from loto.models.neuralforecast_search_space_artifacts import verify_search_space_artifacts


class Choice:
    def __init__(self, categories):
        self.categories = categories


def test_trial_root_maps_to_failure_durable_task_evidence_directory(tmp_path: Path) -> None:
    trial_root = tmp_path / "run-1" / "trial_work" / "hpo" / "AutoNHITS" / "seed-42"
    expected = tmp_path / "run-1" / "search_space_profiles" / "hpo" / "AutoNHITS" / "seed-42"
    assert _search_space_evidence_root(trial_root) == expected.resolve()


def test_profile_is_persisted_before_model_runtime(tmp_path: Path) -> None:
    trial_root = tmp_path / "run-1" / "trial_work" / "hpo" / "AutoNHITS" / "seed-1"
    profile = _search_space_profile(
        model_name="AutoNHITS",
        backend="ray",
        config_value={"input_size": Choice([12, 24]), "max_steps": 500},
        fixed_values=None,
    )
    artifacts = _persist_search_space_profile(
        trial_root=trial_root,
        profile=profile,
        model_name="AutoNHITS",
        backend="ray",
        alias="candidate",
        seed=1,
        num_samples=30,
        smoke=False,
    )
    root = _search_space_evidence_root(trial_root)

    assert profile.completeness is SearchSpaceCompleteness.COMPLETE
    assert artifacts["verification_status"] == "PASS"
    assert verify_search_space_artifacts(root)["status"] == "PASS"
    manifest = json.loads((root / "SEARCH_SPACE_PROFILE_MANIFEST.json").read_text())
    assert manifest["context"]["seed"] == 1
    assert manifest["context"]["num_samples"] == 30


def test_constructor_artifact_keeps_policy_and_profile_evidence() -> None:
    profile = _search_space_profile(
        model_name="AutoTFT",
        backend="optuna",
        config_value=lambda trial: {"x": trial.suggest_int("x", 1, 3)},
        fixed_values=None,
    )
    policy = SearchPolicyDecision(model_name="AutoTFT")
    artifact = _artifact_kwargs(
        {"h": 1},
        [{"argument": "h", "status": "ACCEPTED"}],
        policy,
        search_space_profile=profile,
        search_space_artifacts={"verification_status": "PASS"},
    )

    assert artifact["search_space_profile"]["model_name"] == "AutoTFT"
    assert artifact["search_space_artifacts"]["verification_status"] == "PASS"
