from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_config_is_fail_closed() -> None:
    payload = json.loads(
        (
            ROOT
            / "configs"
            / "moirai2_campaign"
            / "p8d_target_execution.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["human_approval_required"] is True
    assert payload["automatic_approval"] is False
    assert payload["automatic_installation"] is False
    assert payload["automatic_runtime_execution"] is False
    assert payload["p9_oof_gate_open_only_after_pair_verification"] is True
    assert payload["accuracy_claimed"] is False


def test_owned_paths_do_not_include_shared_or_oof_code() -> None:
    payload = json.loads(
        (ROOT / "docs" / "moirai2" / "P8D_CHANGE_SCOPE.json").read_text(
            encoding="utf-8"
        )
    )
    owned = "\n".join(payload["owned_paths"])
    assert ".github/workflows" not in owned
    assert "shared" not in owned
    assert "oof" not in owned.lower()
    assert payload["merge_allowed"] is False
    assert payload["real_runtime_claimed"] is False
