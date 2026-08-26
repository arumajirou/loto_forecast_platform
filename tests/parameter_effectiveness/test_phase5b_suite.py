from __future__ import annotations

from pathlib import Path

from loto.parameter_effectiveness.contracts import ParameterSuiteSpec


ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "examples/parameter_effectiveness/phase5b_runtime_family_smoke.json"


def test_phase5b_suite_contract() -> None:
    suite = ParameterSuiteSpec.model_validate_json(SPEC.read_text(encoding="utf-8"))

    assert suite.suite_id == "phase5b-runtime-family-parameter-smoke-v1"
    assert [probe.probe_id for probe in suite.probes] == [
        "darts-naive-seasonal-k-prediction",
        "sktime-naive-strategy-prediction",
        "gluonts-seasonal-naive-season-length-prediction",
        "toto2-context-length-history",
    ]
    assert all(len(probe.seeds) == 2 for probe in suite.probes)
    assert all(probe.min_match_fraction == 1.0 for probe in suite.probes)
