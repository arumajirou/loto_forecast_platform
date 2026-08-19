from __future__ import annotations

import hashlib
from pathlib import Path

from loto.parameter_effectiveness import (
    AdapterRegistry,
    EffectOutcome,
    EffectSurface,
    ExpectedRelation,
    FunctionProbeAdapter,
    ParameterProbeSpec,
    ParameterSuiteSpec,
    ProbeRunObservation,
    evaluate_probe,
    run_suite,
)


def observation(*, trial_count: int, prediction: str = "same") -> ProbeRunObservation:
    return ProbeRunObservation(
        accepted=True,
        success=True,
        finite=True,
        output_shape=(3, 3),
        prediction_sha256=prediction,
        observables={"trial_count": trial_count, "metric": float(trial_count)},
        runtime_seconds=0.01,
    )


def registry_for(run) -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(FunctionProbeAdapter("fake", run))
    return registry


def spec(**updates) -> ParameterProbeSpec:
    payload = {
        "probe_id": "probe",
        "library": "fake",
        "model": "Model",
        "parameter": "num_samples",
        "control": 1,
        "treatment": 2,
        "expected_surface": EffectSurface.TRIAL_COUNT,
        "expected_relation": ExpectedRelation.INCREASE,
        "seeds": (1, 42),
    }
    payload.update(updates)
    return ParameterProbeSpec(**payload)


def test_effective_requires_repeated_paired_matches() -> None:
    def run(probe, value, seed, repeat):
        del probe, seed, repeat
        return observation(trial_count=int(value), prediction=str(value))

    result = evaluate_probe(spec(), registry_for(run))

    assert result.outcome is EffectOutcome.EFFECTIVE
    assert result.pairs_total == 2
    assert result.pairs_eligible == 2
    assert result.pairs_matched == 2
    assert result.matched_fraction == 1.0
    assert result.control_aggregate is not None
    assert result.treatment_aggregate is not None
    assert result.control_aggregate.mean == 1.0
    assert result.treatment_aggregate.mean == 2.0
    assert result.holdout_evaluated is False
    assert result.prospective_evaluated is False


def test_accepted_but_no_change_is_not_effective() -> None:
    def run(probe, value, seed, repeat):
        del probe, value, seed, repeat
        return observation(trial_count=1)

    result = evaluate_probe(spec(), registry_for(run))

    assert result.outcome is EffectOutcome.ACCEPTED_NO_OBSERVABLE_EFFECT
    assert result.matched_fraction == 0.0


def test_invariant_violation_is_reported() -> None:
    def run(probe, value, seed, repeat):
        del probe, seed, repeat
        return observation(trial_count=1, prediction=f"sha-{value}")

    probe = spec(
        expected_surface=EffectSurface.PREDICTION,
        expected_relation=ExpectedRelation.INVARIANT,
    )
    result = evaluate_probe(probe, registry_for(run))

    assert result.outcome is EffectOutcome.EXPECTATION_VIOLATED
    assert result.pairs_matched == 0


def test_partial_failure_is_inconclusive() -> None:
    def run(probe, value, seed, repeat):
        del probe, repeat
        if seed == 42 and int(value) == 2:
            raise RuntimeError("synthetic treatment failure")
        return observation(trial_count=int(value))

    result = evaluate_probe(spec(), registry_for(run))

    assert result.outcome is EffectOutcome.INCONCLUSIVE
    assert result.pairs_eligible == 1
    assert result.pairs_failed == 1


def test_suite_writes_portable_hashed_evidence(tmp_path: Path) -> None:
    def run(probe, value, seed, repeat):
        del probe, seed, repeat
        return observation(trial_count=int(value), prediction=f"sha-{value}")

    suite = ParameterSuiteSpec(suite_id="suite", probes=[spec()])
    results = run_suite(suite, registry_for(run), tmp_path)

    assert results[0].outcome is EffectOutcome.EFFECTIVE

    expected = {
        "suite.json",
        "results.json",
        "environment.json",
        "summary.csv",
        "manifest.json",
        "SHA256SUMS",
    }
    assert expected.issubset({path.name for path in tmp_path.iterdir()})

    for line in (tmp_path / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, filename = line.split("  ", maxsplit=1)
        payload = (tmp_path / filename).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == digest


def test_single_seed_is_rejected() -> None:
    try:
        spec(seeds=(1,))
    except ValueError as exc:
        assert "at least two seeds" in str(exc)
    else:
        raise AssertionError("single-seed probe must be rejected")
