from __future__ import annotations

from pathlib import Path


def test_p7_runner_wires_both_gluonts_covariate_fields() -> None:
    source = (
        Path(__file__).resolve().parents[3] / "scripts" / "run_moirai2_provider.py"
    ).read_text(encoding="utf-8")
    assert "deferred to Moirai 2.0 phase P7" not in source
    assert "compile_covariates(" in source
    assert "attach_covariates(" in source
    assert "feat_dynamic_real_dim=covariates.known_future_dim" in source
    assert "past_feat_dynamic_real_dim=covariates.past_dim" in source
    assert "covariate_evidence=covariates.as_dict()" in source
