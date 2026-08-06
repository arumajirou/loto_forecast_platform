from __future__ import annotations

from pathlib import Path

import pytest

from loto.adapters.timer_base_84m.provider import TimerBase84MProvider, TimerProviderError


def test_environment_requires_reviewed_lock(tmp_path: Path) -> None:
    env = tmp_path / "env"
    env.mkdir()
    (env / "pyproject.toml").write_text("[project]\nname='timer'\n", encoding="utf-8")
    provider = TimerBase84MProvider(env, tmp_path / "review.json")
    with pytest.raises(TimerProviderError) as exc:
        provider.validate_environment()
    assert exc.value.status == "DEPENDENCY_LOCK_PENDING"


def test_snapshot_manifest_requires_approved_review(tmp_path: Path) -> None:
    review = tmp_path / "review.json"
    review.write_text("{}", encoding="utf-8")
    provider = TimerBase84MProvider(tmp_path, review)
    with pytest.raises(TimerProviderError) as exc:
        provider.resolve_snapshot_manifest()
    assert exc.value.status == "REMOTE_CODE_REVIEW_REQUIRED"


def test_load_and_predict_fail_closed(tmp_path: Path) -> None:
    provider = TimerBase84MProvider(tmp_path, tmp_path / "review.json")
    with pytest.raises(TimerProviderError) as load_exc:
        provider.load()
    assert load_exc.value.status == "CHECKPOINT_LOAD_PENDING"
    with pytest.raises(TimerProviderError) as predict_exc:
        provider.predict(None)  # type: ignore[arg-type]
    assert predict_exc.value.status == "RUNTIME_NOT_CERTIFIED"
