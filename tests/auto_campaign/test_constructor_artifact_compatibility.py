from __future__ import annotations

from loto.auto_campaign.model_factory import _artifact_kwargs


def test_constructor_artifact_preserves_legacy_top_level_arguments() -> None:
    effective = {"h": 1, "alias": "candidate", "backend": "optuna"}
    ledger = [
        {
            "argument": "h",
            "status": "ACCEPTED",
            "reason": "constructor signature accepts argument",
            "value_repr": "1",
        }
    ]

    artifact = _artifact_kwargs(effective, ledger)

    assert artifact["h"] == 1
    assert artifact["alias"] == "candidate"
    assert artifact["backend"] == "optuna"
    assert artifact["effective_constructor_kwargs"] == effective
    assert artifact["argument_coverage"] == ledger
    assert artifact["unexplained_dropped_arguments"] == []
