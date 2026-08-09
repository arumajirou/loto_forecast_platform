from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import loto.adapters.timer_base_84m.provider as provider_module
from loto.adapters.timer_base_84m.provider import TimerBase84MProvider, TimerProviderError
from loto.timer_base_84m_campaign.provenance import (
    CONFIG_SHA256,
    ProvenanceError,
    load_review,
    validate_remote_code_review,
)


def make_provider(tmp_path: Path) -> TimerBase84MProvider:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir()
    review_path = tmp_path / "remote-code-review.json"
    return TimerBase84MProvider(
        environment_dir=environment_dir,
        review_path=review_path,
        snapshot_dir=tmp_path / "snapshot",
    )


def approved_review_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "audit"
        / "tsfm-runtime"
        / "timer-base-84m"
        / "remote-code-review.json"
    )


def test_identity_exposes_certified_exact_config_and_lock(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    identity = provider.identity()

    assert identity["runtime_status"] == "RUNTIME_CERTIFIED"
    assert identity["config_sha256"] == CONFIG_SHA256
    assert identity["config_sha256"] != "UNVERIFIED"
    assert identity["dependency_lock_sha256"] == provider_module.DEPENDENCY_LOCK_SHA256
    assert identity["python_lane"] == ">=3.10,<3.11"


def test_validate_environment_rejects_mutated_lock(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    (provider.environment_dir / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (provider.environment_dir / "uv.lock").write_text("not-the-reviewed-lock\n", encoding="utf-8")

    with pytest.raises(TimerProviderError) as raised:
        provider.validate_environment()

    assert raised.value.status == "DEPENDENCY_LOCK_INVALID"


def test_predict_requires_explicit_load(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)

    with pytest.raises(TimerProviderError) as raised:
        provider.predict(None)  # type: ignore[arg-type]

    assert raised.value.status == "MODEL_NOT_LOADED"


def test_snapshot_verification_is_exact_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = make_provider(tmp_path)
    provider.snapshot_dir.mkdir(parents=True)
    target = provider.snapshot_dir / "config.json"
    target.write_bytes(b"reviewed-bytes")
    import hashlib

    expected = hashlib.sha256(b"reviewed-bytes").hexdigest()
    monkeypatch.setattr(provider_module, "SNAPSHOT_FILE_SHA256S", {"config.json": expected})
    assert provider._verify_snapshot_bytes() == provider.snapshot_dir.resolve()

    target.write_bytes(b"changed-after-review")
    with pytest.raises(TimerProviderError) as raised:
        provider._verify_snapshot_bytes()
    assert raised.value.status == "SNAPSHOT_HASH_MISMATCH"


def test_inspect_properties_declares_no_cpu_fallback(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    properties = provider.inspect_properties()

    assert properties["checkpoint_load"] is True
    assert properties["predict"] is True
    assert properties["cpu_fallback_allowed"] is False
    assert properties["retained_layouts"] == [
        "position_univariate",
        "position_panel_batched_univariate",
    ]
    assert properties["supported_horizons"] == [1, 2, 5]


def test_committed_human_approval_review_schema_is_accepted() -> None:
    review = load_review(approved_review_path())

    validate_remote_code_review(review)

    assert review["review_status"] == "HUMAN_REVIEW_APPROVED"
    assert review["approved"] is True
    assert review["trust_remote_code_allowed"] is True
    assert review["reviewer"] == "arumajirou"


def test_human_approval_record_preserves_pre_execution_boundary() -> None:
    review = deepcopy(load_review(approved_review_path()))
    review["execution_boundary"]["checkpoint_load_executed"] = True

    with pytest.raises(ProvenanceError, match="pre-execution boundary"):
        validate_remote_code_review(review)
