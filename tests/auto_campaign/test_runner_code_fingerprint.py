"""Driver-side aggregation of the Ray worker/driver code-hash comparison.

`_verify_worker_code_fingerprints` reads each *successful* trial's persisted
`worker_code_fingerprint.json` (written by `PersistentTrialMixin` inside the
Ray/Optuna trial itself) and compares it against the driver's own
`code_environment_fingerprint()`. A missing fingerprint file on a successful
trial must FAIL exactly like a real mismatch would -- silence is not
evidence that the worker ran the same code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loto.auto_campaign.runner import _verify_worker_code_fingerprints
from loto.auto_campaign.runtime import code_environment_fingerprint


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_trial(
    trials_root: Path,
    name: str,
    *,
    manifest_status: str = "PASS",
    fingerprint: dict[str, Any] | None = None,
    write_fingerprint: bool = True,
) -> None:
    trial_dir = trials_root / name
    trial_dir.mkdir(parents=True, exist_ok=True)
    _write_json(trial_dir / "manifest.json", {"status": manifest_status})
    if write_fingerprint:
        _write_json(
            trial_dir / "worker_code_fingerprint.json",
            fingerprint if fingerprint is not None else code_environment_fingerprint(),
        )


def test_matching_fingerprints_pass(tmp_path: Path) -> None:
    driver = code_environment_fingerprint()
    trials_root = tmp_path / "trials"
    _make_trial(trials_root, "trial_0", fingerprint=driver)

    result = _verify_worker_code_fingerprints(trials_root, driver)

    assert result["status"] == "PASS"
    assert result["missing_fingerprint_trials"] == []
    assert result["mismatched_trials"] == []


def test_missing_fingerprint_on_successful_trial_fails(tmp_path: Path) -> None:
    driver = code_environment_fingerprint()
    trials_root = tmp_path / "trials"
    _make_trial(trials_root, "trial_0", write_fingerprint=False)

    result = _verify_worker_code_fingerprints(trials_root, driver)

    assert result["status"] == "FAIL"
    assert result["missing_fingerprint_trials"] == ["trial_0"]


def test_diverged_worker_fingerprint_fails(tmp_path: Path) -> None:
    driver = code_environment_fingerprint()
    worker = code_environment_fingerprint()
    worker["file_sha256"]["persistence.py"] = "0" * 64
    trials_root = tmp_path / "trials"
    _make_trial(trials_root, "trial_0", fingerprint=worker)

    result = _verify_worker_code_fingerprints(trials_root, driver)

    assert result["status"] == "FAIL"
    assert result["mismatched_trials"] == ["trial_0"]


def test_failed_trial_without_fingerprint_is_ignored(tmp_path: Path) -> None:
    driver = code_environment_fingerprint()
    trials_root = tmp_path / "trials"
    _make_trial(trials_root, "trial_0", manifest_status="FAIL", write_fingerprint=False)

    result = _verify_worker_code_fingerprints(trials_root, driver)

    assert result["status"] == "PASS"
    assert result["missing_fingerprint_trials"] == []
    assert result["mismatched_trials"] == []
