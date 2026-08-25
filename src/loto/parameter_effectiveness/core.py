"""Cross-platform paired parameter-effectiveness engine."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import statistics
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TypeGuard

from .contracts import (
    EffectOutcome,
    ExpectedRelation,
    NumericAggregate,
    PairedProbeObservation,
    ParameterProbeResult,
    ParameterProbeSpec,
    ParameterSuiteSpec,
    ProbeRunObservation,
    ScalarObservable,
)


class ParameterProbeAdapter(Protocol):
    """Library adapter contract used by the engine."""

    library: str

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]: ...

    def run(
        self,
        spec: ParameterProbeSpec,
        value: Any,
        seed: int,
        repeat: int,
    ) -> ProbeRunObservation: ...


RunFunction = Callable[[ParameterProbeSpec, Any, int, int], ProbeRunObservation]
SupportFunction = Callable[[ParameterProbeSpec], tuple[bool, str | None]]


class FunctionProbeAdapter:
    """Small adapter useful for project-specific integrations and tests."""

    def __init__(
        self,
        library: str,
        run: RunFunction,
        supports: SupportFunction | None = None,
    ) -> None:
        self.library = library
        self._run = run
        self._supports = supports

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]:
        if self._supports is None:
            return True, None
        return self._supports(spec)

    def run(
        self,
        spec: ParameterProbeSpec,
        value: Any,
        seed: int,
        repeat: int,
    ) -> ProbeRunObservation:
        return self._run(spec, value, seed, repeat)


class AdapterRegistry:
    """Case-insensitive registry of forecasting-library adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, ParameterProbeAdapter] = {}

    @staticmethod
    def _key(library: str) -> str:
        return library.strip().casefold()

    def register(self, adapter: ParameterProbeAdapter, *aliases: str) -> None:
        names = (adapter.library, *aliases)
        for name in names:
            key = self._key(name)
            if key in self._adapters:
                raise ValueError(f"adapter already registered for {name!r}")
            self._adapters[key] = adapter

    def get(self, library: str) -> ParameterProbeAdapter | None:
        return self._adapters.get(self._key(library))

    def libraries(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


def _failed_observation(error: BaseException) -> ProbeRunObservation:
    return ProbeRunObservation(
        accepted=False,
        success=False,
        finite=False,
        runtime_seconds=0.0,
        error=f"{type(error).__name__}: {error}",
    )


def _is_numeric(value: ScalarObservable) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _same(
    left: ScalarObservable,
    right: ScalarObservable,
    spec: ParameterProbeSpec,
) -> bool:
    if _is_numeric(left) and _is_numeric(right):
        return math.isclose(
            float(left),
            float(right),
            rel_tol=spec.relative_tolerance,
            abs_tol=spec.absolute_tolerance,
        )
    return left == right


def _match_relation(
    control: ScalarObservable,
    treatment: ScalarObservable,
    spec: ParameterProbeSpec,
) -> tuple[bool | None, str]:
    if control is None or treatment is None:
        return None, "selected effect surface was not observed"

    relation = spec.expected_relation

    if relation is ExpectedRelation.CHANGE:
        matched = not _same(control, treatment, spec)
    elif relation is ExpectedRelation.INVARIANT:
        matched = _same(control, treatment, spec)
    else:
        if not (_is_numeric(control) and _is_numeric(treatment)):
            return None, f"{relation.value} requires numeric surface values"
        left = float(control)
        right = float(treatment)
        if math.isclose(
            left,
            right,
            rel_tol=spec.relative_tolerance,
            abs_tol=spec.absolute_tolerance,
        ):
            matched = False
        elif relation is ExpectedRelation.INCREASE:
            matched = right > left
        else:
            matched = right < left

    return matched, f"control={control!r}; treatment={treatment!r}; expected={relation.value}"


def _aggregate(
    values: list[ScalarObservable],
    relation: ExpectedRelation,
) -> NumericAggregate | None:
    numeric = [float(value) for value in values if _is_numeric(value)]
    if not numeric:
        return None

    if relation is ExpectedRelation.DECREASE:
        worst = max(numeric)
    else:
        worst = min(numeric)

    return NumericAggregate(
        count=len(numeric),
        mean=statistics.fmean(numeric),
        std=statistics.pstdev(numeric) if len(numeric) > 1 else 0.0,
        minimum=min(numeric),
        maximum=max(numeric),
        worst=worst,
    )


def evaluate_probe(
    spec: ParameterProbeSpec,
    registry: AdapterRegistry,
) -> ParameterProbeResult:
    """Evaluate one parameter using paired repeated control/treatment runs."""

    adapter = registry.get(spec.library)
    pairs_total = len(spec.seeds) * spec.repeats

    if adapter is None:
        return ParameterProbeResult(
            probe_id=spec.probe_id,
            library=spec.library,
            model=spec.model,
            parameter=spec.parameter,
            expected_surface=spec.expected_surface,
            expected_relation=spec.expected_relation,
            outcome=EffectOutcome.UNSUPPORTED,
            supported=False,
            support_reason=f"no adapter registered for {spec.library!r}",
            pairs_total=pairs_total,
            pairs_eligible=0,
            pairs_matched=0,
            pairs_failed=0,
        )

    supported, reason = adapter.supports(spec)
    if not supported:
        return ParameterProbeResult(
            probe_id=spec.probe_id,
            library=spec.library,
            model=spec.model,
            parameter=spec.parameter,
            expected_surface=spec.expected_surface,
            expected_relation=spec.expected_relation,
            outcome=EffectOutcome.UNSUPPORTED,
            supported=False,
            support_reason=reason,
            pairs_total=pairs_total,
            pairs_eligible=0,
            pairs_matched=0,
            pairs_failed=0,
        )

    paired: list[PairedProbeObservation] = []
    control_values: list[ScalarObservable] = []
    treatment_values: list[ScalarObservable] = []

    for seed in spec.seeds:
        for repeat in range(spec.repeats):
            try:
                control = adapter.run(spec, spec.control, seed, repeat)
            except Exception as exc:  # adapters must be fail-visible
                control = _failed_observation(exc)

            try:
                treatment = adapter.run(spec, spec.treatment, seed, repeat)
            except Exception as exc:  # adapters must be fail-visible
                treatment = _failed_observation(exc)

            eligible = (
                control.success
                and treatment.success
                and control.accepted
                and treatment.accepted
                and control.finite
                and treatment.finite
            )

            if eligible:
                control_value = control.surface_value(spec.expected_surface)
                treatment_value = treatment.surface_value(spec.expected_surface)
                matched, comparison = _match_relation(control_value, treatment_value, spec)
                control_values.append(control_value)
                treatment_values.append(treatment_value)
            else:
                matched = None
                comparison = "pair not eligible because acceptance/success/finite validation failed"

            paired.append(
                PairedProbeObservation(
                    seed=seed,
                    repeat=repeat,
                    control=control,
                    treatment=treatment,
                    matched_expectation=matched,
                    comparison=comparison,
                )
            )

    eligible_pairs = [item for item in paired if item.matched_expectation is not None]
    pairs_eligible = len(eligible_pairs)
    pairs_matched = sum(item.matched_expectation is True for item in eligible_pairs)
    pairs_failed = pairs_total - pairs_eligible
    matched_fraction = pairs_matched / pairs_eligible if pairs_eligible else None

    if pairs_eligible == 0:
        outcome = EffectOutcome.FAILED
    elif pairs_failed > 0:
        outcome = EffectOutcome.INCONCLUSIVE
    elif matched_fraction is not None and matched_fraction >= spec.min_match_fraction:
        outcome = EffectOutcome.EFFECTIVE
    else:
        unchanged = all(
            _same(left, right, spec)
            for left, right in zip(control_values, treatment_values, strict=True)
        )
        if spec.expected_relation is not ExpectedRelation.INVARIANT and unchanged:
            outcome = EffectOutcome.ACCEPTED_NO_OBSERVABLE_EFFECT
        else:
            outcome = EffectOutcome.EXPECTATION_VIOLATED

    return ParameterProbeResult(
        probe_id=spec.probe_id,
        library=spec.library,
        model=spec.model,
        parameter=spec.parameter,
        expected_surface=spec.expected_surface,
        expected_relation=spec.expected_relation,
        outcome=outcome,
        supported=True,
        support_reason=reason,
        pairs_total=pairs_total,
        pairs_eligible=pairs_eligible,
        pairs_matched=pairs_matched,
        pairs_failed=pairs_failed,
        matched_fraction=matched_fraction,
        control_aggregate=_aggregate(control_values, spec.expected_relation),
        treatment_aggregate=_aggregate(treatment_values, spec.expected_relation),
        paired=paired,
        holdout_evaluated=False,
        prospective_evaluated=False,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_evidence(
    suite: ParameterSuiteSpec,
    results: list[ParameterProbeResult],
    output_dir: Path,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)

    created = datetime.now(UTC)
    suite_payload = suite.model_dump(mode="json")
    spec_bytes = json.dumps(suite_payload, sort_keys=True).encode("utf-8")
    spec_hash = hashlib.sha256(spec_bytes).hexdigest()[:10]
    run_id = f"pe-{created.strftime('%Y%m%dT%H%M%SZ')}-{spec_hash}"

    _write_json(output_dir / "suite.json", suite_payload)
    _write_json(
        output_dir / "results.json",
        [result.model_dump(mode="json") for result in results],
    )
    _write_json(
        output_dir / "environment.json",
        {
            "run_id": run_id,
            "created_at_utc": created.isoformat(),
            "platform": platform.platform(),
            "system": platform.system(),
            "machine": platform.machine(),
            "python": sys.version,
            "python_executable": sys.executable,
            "holdout_evaluated": False,
            "prospective_evaluated": False,
        },
    )

    with (output_dir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "probe_id",
                "library",
                "model",
                "parameter",
                "surface",
                "relation",
                "outcome",
                "pairs_total",
                "pairs_eligible",
                "pairs_matched",
                "pairs_failed",
                "matched_fraction",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "probe_id": result.probe_id,
                    "library": result.library,
                    "model": result.model,
                    "parameter": result.parameter,
                    "surface": result.expected_surface.value,
                    "relation": result.expected_relation.value,
                    "outcome": result.outcome.value,
                    "pairs_total": result.pairs_total,
                    "pairs_eligible": result.pairs_eligible,
                    "pairs_matched": result.pairs_matched,
                    "pairs_failed": result.pairs_failed,
                    "matched_fraction": result.matched_fraction,
                }
            )

    evidence_files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS"}
    )
    manifest = {
        "run_id": run_id,
        "schema_version": 1,
        "files": [
            {"path": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size}
            for path in evidence_files
        ],
    }
    _write_json(output_dir / "manifest.json", manifest)

    checksum_files = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    (output_dir / "SHA256SUMS").write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in checksum_files),
        encoding="utf-8",
    )
    return run_id


def run_suite(
    suite: ParameterSuiteSpec,
    registry: AdapterRegistry,
    output_dir: Path | None = None,
) -> list[ParameterProbeResult]:
    """Run every probe and optionally persist a portable evidence bundle."""

    results = [evaluate_probe(probe, registry) for probe in suite.probes]
    if output_dir is not None:
        _write_evidence(suite, results, output_dir)
    return results
