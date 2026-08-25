from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from loto.evaluation import resumable_campaign as resumable
from loto.evaluation.metric_registry import REQUIRED_POINT_METRICS
from loto.evaluation.path_codec import encode_path_component
from loto.evaluation.protocol_v2 import canonical_json_bytes
from loto.evaluation.unified_campaign import UnifiedCampaignConfig


class _FakeProtocol:
    protocol_hash = "b" * 64
    comparison_budget_hash = "c" * 64

    def canonical_payload(self) -> dict[str, Any]:
        return {"schema_version": "2.0.0", "test_protocol": "taj21-resume"}


def _config(tmp_path, name: str, **overrides: Any) -> UnifiedCampaignConfig:
    values: dict[str, Any] = {
        "output_dir": tmp_path / name,
        "git_commit": "a" * 40,
        "games": ("numbers3",),
        "seeds": (42,),
        "folds": 1,
        "test_size": 1,
        "min_train_size": 2,
        "holdout_size": 0,
        "feature_windows": (5, 10),
    }
    values.update(overrides)
    return UnifiedCampaignConfig(**values)


def _resume(tmp_path, name: str, digest: str = "1" * 64) -> resumable.UnifiedCampaignResumeConfig:
    return resumable.UnifiedCampaignResumeConfig(
        checkpoint_dir=tmp_path / f"{name}.checkpoints",
        input_sha256={"numbers3": digest},
    )


def _metric_summary(value: float) -> dict[str, Any]:
    return {
        "mean": value,
        "population_variance": 0.0,
        "worst_value": value,
        "worst_seed": 42,
    }


def _write_lock(
    config: UnifiedCampaignConfig,
    *,
    candidate_id: str,
    seed: int = 42,
) -> dict[str, Any]:
    path = (
        config.output_dir
        / "prediction_locks"
        / "numbers3"
        / encode_path_component(candidate_id)
        / f"seed-{seed}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    sealed_at = "2026-08-26T00:00:00+00:00"
    payload = {
        "schema_version": "prediction-lock-v1",
        "protocol_hash": _FakeProtocol.protocol_hash,
        "game": "numbers3",
        "candidate_id": candidate_id,
        "seed": seed,
        "actuals_known": False,
        "sealed_at_utc": sealed_at,
        "predictions": [],
    }
    data = canonical_json_bytes(payload) + b"\n"
    path.write_bytes(data)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sealed_at_utc": sealed_at,
        "bytes": len(data),
    }


def _result(
    config: UnifiedCampaignConfig,
    *,
    candidate_id: str,
    source: str,
    library: str,
    task: str,
) -> dict[str, Any]:
    metric_values = {
        "hit_at_1": 0.5,
        "position_hit_at_1": 0.5,
        "all_positions_hit_at_1": 0.25,
        "mae": 1.0,
        "mse": 2.0,
        "rmse": 2.0**0.5,
    }
    lock = _write_lock(config, candidate_id=candidate_id)
    return {
        "game": "numbers3",
        "candidate_id": candidate_id,
        "source": source,
        "library": library,
        "task": task,
        "status": "SUCCEEDED",
        "reason": "",
        "failures": [],
        "protocol_hash": _FakeProtocol.protocol_hash,
        "seed_results": [
            {
                "seed": 42,
                "metrics": metric_values,
                "prediction_lock": lock,
                "runtime_samples": [],
            }
        ],
        "seed_summary": {
            metric_id: _metric_summary(metric_values[metric_id])
            for metric_id in REQUIRED_POINT_METRICS
        },
    }


def _install_fake_campaign(monkeypatch, state: dict[str, Any]) -> None:
    entry = SimpleNamespace(model_id="fake:model", library="fake", task="position")
    prepared = SimpleNamespace(
        geometry=SimpleNamespace(key="numbers3"),
        protocol=_FakeProtocol(),
    )
    monkeypatch.setattr(resumable, "_selected_entries", lambda config: [entry])
    monkeypatch.setattr(resumable, "_selected_probabilistic_routes", lambda config: [])
    monkeypatch.setattr(
        resumable,
        "build_campaign_plan",
        lambda config: [
            {
                "game": "numbers3",
                "candidate_id": entry.model_id,
                "library": entry.library,
                "task": entry.task,
            }
        ],
    )
    monkeypatch.setattr(resumable, "_prepare_game", lambda game, frame, config: prepared)

    def fake_evaluate(prepared, config, **kwargs):
        state["calls"] = state.get("calls", 0) + 1
        candidate_id = kwargs["candidate_id"]
        state.setdefault("executed", []).append(candidate_id)
        interrupt_on = state.get("interrupt_on")
        if interrupt_on is not None and state["calls"] == interrupt_on:
            if state.get("write_partial_lock"):
                partial_lock = _write_lock(config, candidate_id=candidate_id)
                state["partial_lock"] = partial_lock["path"]
                state["partial_candidate"] = candidate_id
            raise InterruptedError("simulated interruption")
        if state.get("expect_clean_candidate") == candidate_id:
            lock_dir = (
                config.output_dir
                / "prediction_locks"
                / "numbers3"
                / encode_path_component(candidate_id)
            )
            assert not lock_dir.exists()
            state["clean_rerun_observed"] = True
        return _result(
            config,
            candidate_id=candidate_id,
            source=kwargs["source"],
            library=kwargs["library"],
            task=kwargs["task"],
        )

    monkeypatch.setattr(resumable, "_evaluate_candidate", fake_evaluate)


def _scientific_signature(summary: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in summary["results"]:
        rows.append(
            {
                "game": row["game"],
                "candidate_id": row["candidate_id"],
                "source": row["source"],
                "library": row["library"],
                "task": row["task"],
                "status": row["status"],
                "reason": row["reason"],
                "protocol_hash": row["protocol_hash"],
                "seed_summary": row["seed_summary"],
            }
        )
    return {
        "schema_version": summary["schema_version"],
        "status": summary["status"],
        "git_commit": summary["git_commit"],
        "code_hash": summary["code_hash"],
        "games": summary["games"],
        "catalog_models": summary["catalog_models"],
        "expected_model_game_pairs": summary["expected_model_game_pairs"],
        "observed_model_game_pairs": summary["observed_model_game_pairs"],
        "matrix_complete": summary["matrix_complete"],
        "status_counts": summary["status_counts"],
        "results": rows,
        "leaderboards": summary["leaderboards"],
        "macro_summary": summary["macro_summary"],
        "holdout_evaluated": summary["holdout_evaluated"],
        "prospective_evaluated": summary["prospective_evaluated"],
        "promotion": summary["promotion"],
    }


def test_interrupted_unit_is_rerun_and_fresh_resume_results_match(tmp_path, monkeypatch) -> None:
    interrupted_state: dict[str, Any] = {"interrupt_on": 4, "write_partial_lock": True}
    _install_fake_campaign(monkeypatch, interrupted_state)
    resumed_config = _config(tmp_path, "resumed")
    resumed_checkpoint = _resume(tmp_path, "resumed")
    frames = {"numbers3": pd.DataFrame()}

    with pytest.raises(InterruptedError, match="simulated interruption"):
        resumable.run_resumable_unified_campaign(
            frames,
            resumed_config,
            resume=resumed_checkpoint,
        )

    assert len(list((resumed_checkpoint.checkpoint_dir / "units").rglob("*.json"))) == 3
    assert Path(interrupted_state["partial_lock"]).exists()

    resume_state: dict[str, Any] = {
        "expect_clean_candidate": interrupted_state["partial_candidate"],
    }
    _install_fake_campaign(monkeypatch, resume_state)
    resumed_summary = resumable.run_resumable_unified_campaign(
        frames,
        resumed_config,
        resume=resumed_checkpoint,
    )
    assert resume_state["calls"] == 5
    assert resume_state["clean_rerun_observed"] is True
    assert len(list((resumed_checkpoint.checkpoint_dir / "units").rglob("*.json"))) == 8

    fresh_state: dict[str, Any] = {}
    _install_fake_campaign(monkeypatch, fresh_state)
    fresh_config = _config(tmp_path, "fresh")
    fresh_checkpoint = _resume(tmp_path, "fresh")
    fresh_summary = resumable.run_resumable_unified_campaign(
        frames,
        fresh_config,
        resume=fresh_checkpoint,
    )
    assert fresh_state["calls"] == 8

    assert _scientific_signature(resumed_summary) == _scientific_signature(fresh_summary)
    assert (resumed_config.output_dir / "model_game_results.csv").read_bytes() == (
        fresh_config.output_dir / "model_game_results.csv"
    ).read_bytes()
    assert (resumed_config.output_dir / "all_game_macro_summary.csv").read_bytes() == (
        fresh_config.output_dir / "all_game_macro_summary.csv"
    ).read_bytes()


def test_corrupt_unit_checkpoint_fails_closed(tmp_path, monkeypatch) -> None:
    state: dict[str, Any] = {"interrupt_on": 2}
    _install_fake_campaign(monkeypatch, state)
    config = _config(tmp_path, "corrupt-unit")
    resume = _resume(tmp_path, "corrupt-unit")
    frames = {"numbers3": pd.DataFrame()}

    with pytest.raises(InterruptedError):
        resumable.run_resumable_unified_campaign(frames, config, resume=resume)
    checkpoint = next((resume.checkpoint_dir / "units").rglob("*.json"))
    checkpoint.write_text("{not-json", encoding="utf-8")

    state.clear()
    _install_fake_campaign(monkeypatch, state)
    with pytest.raises(ValueError, match="corrupt checkpoint JSON"):
        resumable.run_resumable_unified_campaign(frames, config, resume=resume)


def test_input_sha_mismatch_fails_closed(tmp_path, monkeypatch) -> None:
    state: dict[str, Any] = {"interrupt_on": 2}
    _install_fake_campaign(monkeypatch, state)
    config = _config(tmp_path, "input-mismatch")
    resume = _resume(tmp_path, "input-mismatch", "1" * 64)
    frames = {"numbers3": pd.DataFrame()}

    with pytest.raises(InterruptedError):
        resumable.run_resumable_unified_campaign(frames, config, resume=resume)

    state.clear()
    _install_fake_campaign(monkeypatch, state)
    changed = resumable.UnifiedCampaignResumeConfig(
        checkpoint_dir=resume.checkpoint_dir,
        input_sha256={"numbers3": "2" * 64},
    )
    with pytest.raises(RuntimeError, match="resume contract SHA mismatch"):
        resumable.run_resumable_unified_campaign(frames, config, resume=changed)


@pytest.mark.parametrize(
    "override",
    [
        {"git_commit": "d" * 40},
        {"seeds": (43,)},
        {"folds": 2},
        {"feature_windows": (5, 10, 20)},
    ],
)
def test_result_affecting_config_mismatch_fails_closed(tmp_path, monkeypatch, override) -> None:
    state: dict[str, Any] = {"interrupt_on": 2}
    _install_fake_campaign(monkeypatch, state)
    config = _config(tmp_path, "config-mismatch")
    resume = _resume(tmp_path, "config-mismatch")
    frames = {"numbers3": pd.DataFrame()}

    with pytest.raises(InterruptedError):
        resumable.run_resumable_unified_campaign(frames, config, resume=resume)

    state.clear()
    _install_fake_campaign(monkeypatch, state)
    changed = _config(tmp_path, "config-mismatch", **override)
    with pytest.raises(RuntimeError, match="resume contract SHA mismatch"):
        resumable.run_resumable_unified_campaign(frames, changed, resume=resume)


def test_model_universe_mismatch_fails_closed(tmp_path, monkeypatch) -> None:
    state: dict[str, Any] = {"interrupt_on": 2}
    _install_fake_campaign(monkeypatch, state)
    config = _config(tmp_path, "model-mismatch")
    resume = _resume(tmp_path, "model-mismatch")
    frames = {"numbers3": pd.DataFrame()}

    with pytest.raises(InterruptedError):
        resumable.run_resumable_unified_campaign(frames, config, resume=resume)

    other = SimpleNamespace(model_id="fake:other", library="fake", task="position")
    monkeypatch.setattr(resumable, "_selected_entries", lambda config: [other])
    monkeypatch.setattr(resumable, "_selected_probabilistic_routes", lambda config: [])
    monkeypatch.setattr(
        resumable,
        "build_campaign_plan",
        lambda config: [
            {
                "game": "numbers3",
                "candidate_id": other.model_id,
                "library": other.library,
                "task": other.task,
            }
        ],
    )
    with pytest.raises(RuntimeError, match="resume contract SHA mismatch"):
        resumable.run_resumable_unified_campaign(frames, config, resume=resume)


def test_checkpointed_prediction_lock_tamper_fails_closed(tmp_path, monkeypatch) -> None:
    state: dict[str, Any] = {"interrupt_on": 2}
    _install_fake_campaign(monkeypatch, state)
    config = _config(tmp_path, "lock-tamper")
    resume = _resume(tmp_path, "lock-tamper")
    frames = {"numbers3": pd.DataFrame()}

    with pytest.raises(InterruptedError):
        resumable.run_resumable_unified_campaign(frames, config, resume=resume)
    checkpoint = next((resume.checkpoint_dir / "units").rglob("*.json"))
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    lock_path = Path(payload["result"]["seed_results"][0]["prediction_lock"]["path"])
    lock_path.write_text("tampered\n", encoding="utf-8")

    state.clear()
    _install_fake_campaign(monkeypatch, state)
    with pytest.raises(RuntimeError, match="Prediction Lock SHA mismatch"):
        resumable.run_resumable_unified_campaign(frames, config, resume=resume)
