from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.special import logsumexp

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]
MODEL_ID = "pp-bocpd-dirichlet-categorical"
RETRAIN_EVENT = "RETRAIN_RECOMMENDED"


def _validate_observations(y: np.ndarray, classes: int) -> FloatArray:
    values = np.asarray(y, dtype=np.float64)
    if values.ndim == 1:
        values = values[:, None]
    if values.ndim != 2 or values.shape[0] < 1 or values.shape[1] < 1:
        raise ValueError("BOCPD observations must have shape (time, position)")
    finite = values[np.isfinite(values)]
    if finite.size and (np.any(finite < 0) or np.any(finite >= classes)):
        raise ValueError("BOCPD observations contain an out-of-range category")
    if finite.size and not np.allclose(finite, np.round(finite)):
        raise ValueError("BOCPD observations must be integer categories or NaN")
    return values


def _dirichlet_means(alpha: FloatArray) -> FloatArray:
    totals = alpha.sum(axis=-1, keepdims=True)
    if np.any(totals <= 0.0) or not np.isfinite(totals).all():
        raise ValueError("CHANGEPOINT_UNSTABLE: invalid Dirichlet sufficient statistics")
    return alpha / totals


def _mixture_probabilities(posterior: FloatArray, alpha: FloatArray) -> FloatArray:
    means = _dirichlet_means(alpha)
    probabilities = np.einsum("r,rpc->pc", posterior, means, optimize=True)
    probabilities = np.clip(probabilities, 1e-15, None)
    probabilities /= probabilities.sum(axis=-1, keepdims=True)
    return probabilities


def _row_counts(row: FloatArray, *, positions: int, classes: int) -> FloatArray:
    counts = np.zeros((positions, classes), dtype=np.float64)
    for position, value in enumerate(row):
        if np.isfinite(value):
            counts[position, int(value)] = 1.0
    return counts


def _row_log_predictive(alpha: FloatArray, row: FloatArray) -> FloatArray:
    log_probability = np.zeros(alpha.shape[0], dtype=np.float64)
    for position, value in enumerate(row):
        if not np.isfinite(value):
            continue
        category = int(value)
        log_probability += np.log(alpha[:, position, category])
        log_probability -= np.log(alpha[:, position, :].sum(axis=-1))
    return log_probability


def _constant_hazard(expected_run_length: float) -> float:
    if expected_run_length <= 1.0:
        raise ValueError("bocpd_expected_run_length must be greater than one")
    return 1.0 / expected_run_length


def _quality_pass(row: FloatArray, minimum_fraction: float) -> bool:
    observed_fraction = float(np.isfinite(row).sum()) / float(row.size)
    return observed_fraction >= minimum_fraction


@dataclass
class BOCPDDirichletCategoricalState:
    model_id: str
    game: str
    classes: int
    positions: int
    run_lengths: IntArray
    run_length_posterior: FloatArray
    dirichlet_alpha: FloatArray
    prior_alpha: FloatArray
    current_step: int
    evidence_count: int
    one_step_probabilities: FloatArray
    changepoint_probabilities: FloatArray
    map_run_length_history: IntArray
    pruned_mass_history: FloatArray
    data_quality_pass: BoolArray
    alert_events: tuple[dict[str, Any], ...]
    last_alert_step: int | None
    hazard_type: str
    expected_run_length: float
    max_run_length: int
    posterior_mass_prune: float
    alert_threshold: float
    minimum_evidence_count: int
    cooldown: int
    minimum_observed_fraction: float
    seed: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def predictive_probabilities(self) -> FloatArray:
        return _mixture_probabilities(self.run_length_posterior, self.dirichlet_alpha)

    def probability_draws(self, draws: int, seed: int | None = None) -> FloatArray:
        if draws < 1:
            raise ValueError("draws must be positive")
        rng = np.random.default_rng(self.seed if seed is None else seed)
        components = rng.choice(
            len(self.run_lengths), size=draws, p=self.run_length_posterior
        )
        output = np.empty((draws, self.positions, self.classes), dtype=np.float64)
        for draw, component in enumerate(components):
            for position in range(self.positions):
                output[draw, position] = rng.dirichlet(
                    self.dirichlet_alpha[component, position]
                )
        return output

    @property
    def current_changepoint_probability(self) -> float:
        indexes = np.flatnonzero(self.run_lengths == 0)
        if indexes.size == 0:
            return 0.0
        return float(self.run_length_posterior[indexes[0]])

    @property
    def map_run_length(self) -> int:
        return int(self.run_lengths[int(np.argmax(self.run_length_posterior))])

    @property
    def cumulative_pruned_mass(self) -> float:
        return float(self.pruned_mass_history.sum())

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "game": self.game,
            "classes": self.classes,
            "positions": self.positions,
            "current_step": self.current_step,
            "evidence_count": self.evidence_count,
            "active_run_lengths": int(len(self.run_lengths)),
            "map_run_length": self.map_run_length,
            "current_changepoint_probability": self.current_changepoint_probability,
            "cumulative_pruned_mass": self.cumulative_pruned_mass,
            "alert_count": len(self.alert_events),
            "last_alert_step": self.last_alert_step,
            "hazard_type": self.hazard_type,
            "expected_run_length": self.expected_run_length,
            "max_run_length": self.max_run_length,
            "posterior_mass_prune": self.posterior_mass_prune,
            "alert_threshold": self.alert_threshold,
            "minimum_evidence_count": self.minimum_evidence_count,
            "cooldown": self.cooldown,
            "minimum_observed_fraction": self.minimum_observed_fraction,
            "seed": self.seed,
            "metadata": self.metadata,
        }

    def save(self, directory: str | Path) -> list[Path]:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        metadata_path = root / "bocpd_state.json"
        arrays_path = root / "bocpd_state.npz"
        metadata = self.to_metadata_dict()
        metadata["alert_events"] = list(self.alert_events)
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        np.savez_compressed(
            arrays_path,
            run_lengths=self.run_lengths,
            run_length_posterior=self.run_length_posterior,
            dirichlet_alpha=self.dirichlet_alpha,
            prior_alpha=self.prior_alpha,
            one_step_probabilities=self.one_step_probabilities,
            changepoint_probabilities=self.changepoint_probabilities,
            map_run_length_history=self.map_run_length_history,
            pruned_mass_history=self.pruned_mass_history,
            data_quality_pass=self.data_quality_pass,
        )
        return [metadata_path, arrays_path]

    @classmethod
    def load(cls, directory: str | Path) -> BOCPDDirichletCategoricalState:
        root = Path(directory)
        metadata = json.loads((root / "bocpd_state.json").read_text(encoding="utf-8"))
        with np.load(root / "bocpd_state.npz") as arrays:
            return cls(
                model_id=str(metadata["model_id"]),
                game=str(metadata["game"]),
                classes=int(metadata["classes"]),
                positions=int(metadata["positions"]),
                run_lengths=arrays["run_lengths"].astype(np.int64),
                run_length_posterior=arrays["run_length_posterior"].astype(np.float64),
                dirichlet_alpha=arrays["dirichlet_alpha"].astype(np.float64),
                prior_alpha=arrays["prior_alpha"].astype(np.float64),
                current_step=int(metadata["current_step"]),
                evidence_count=int(metadata["evidence_count"]),
                one_step_probabilities=arrays["one_step_probabilities"].astype(np.float64),
                changepoint_probabilities=arrays["changepoint_probabilities"].astype(
                    np.float64
                ),
                map_run_length_history=arrays["map_run_length_history"].astype(np.int64),
                pruned_mass_history=arrays["pruned_mass_history"].astype(np.float64),
                data_quality_pass=arrays["data_quality_pass"].astype(bool),
                alert_events=tuple(dict(item) for item in metadata.get("alert_events", [])),
                last_alert_step=(
                    int(metadata["last_alert_step"])
                    if metadata.get("last_alert_step") is not None
                    else None
                ),
                hazard_type=str(metadata["hazard_type"]),
                expected_run_length=float(metadata["expected_run_length"]),
                max_run_length=int(metadata["max_run_length"]),
                posterior_mass_prune=float(metadata["posterior_mass_prune"]),
                alert_threshold=float(metadata["alert_threshold"]),
                minimum_evidence_count=int(metadata["minimum_evidence_count"]),
                cooldown=int(metadata["cooldown"]),
                minimum_observed_fraction=float(metadata["minimum_observed_fraction"]),
                seed=int(metadata["seed"]),
                metadata=dict(metadata.get("metadata", {})),
            )


def _initial_state(
    *,
    game: str,
    classes: int,
    positions: int,
    config: Any,
    seed: int,
) -> BOCPDDirichletCategoricalState:
    concentration = float(config.bocpd_prior_concentration)
    prior_alpha = np.full((positions, classes), concentration, dtype=np.float64)
    return BOCPDDirichletCategoricalState(
        model_id=MODEL_ID,
        game=game,
        classes=classes,
        positions=positions,
        run_lengths=np.array([0], dtype=np.int64),
        run_length_posterior=np.array([1.0], dtype=np.float64),
        dirichlet_alpha=prior_alpha[None, :, :].copy(),
        prior_alpha=prior_alpha,
        current_step=0,
        evidence_count=0,
        one_step_probabilities=np.empty((0, positions, classes), dtype=np.float64),
        changepoint_probabilities=np.empty(0, dtype=np.float64),
        map_run_length_history=np.empty(0, dtype=np.int64),
        pruned_mass_history=np.empty(0, dtype=np.float64),
        data_quality_pass=np.empty(0, dtype=bool),
        alert_events=(),
        last_alert_step=None,
        hazard_type=str(config.bocpd_hazard_type),
        expected_run_length=float(config.bocpd_expected_run_length),
        max_run_length=int(config.bocpd_max_run_length),
        posterior_mass_prune=float(config.bocpd_posterior_mass_prune),
        alert_threshold=float(config.bocpd_alert_threshold),
        minimum_evidence_count=int(config.bocpd_min_evidence_count),
        cooldown=int(config.bocpd_cooldown),
        minimum_observed_fraction=float(config.bocpd_min_observed_fraction),
        seed=seed,
        metadata={
            "inference": "exact_bocpd_message_passing",
            "observation_order": "predict_before_update",
            "predictive_model": "dirichlet_categorical",
            "automatic_retraining": False,
        },
    )


def _validate_resume(
    state: BOCPDDirichletCategoricalState,
    *,
    game: str,
    classes: int,
    positions: int,
    config: Any,
) -> None:
    if state.model_id != MODEL_ID:
        raise ValueError("initial BOCPD state has a different model_id")
    if state.game != game or state.classes != classes or state.positions != positions:
        raise ValueError("initial BOCPD state game/classes/positions do not match")
    expected = {
        "hazard_type": str(config.bocpd_hazard_type),
        "expected_run_length": float(config.bocpd_expected_run_length),
        "max_run_length": int(config.bocpd_max_run_length),
        "posterior_mass_prune": float(config.bocpd_posterior_mass_prune),
        "alert_threshold": float(config.bocpd_alert_threshold),
        "minimum_evidence_count": int(config.bocpd_min_evidence_count),
        "cooldown": int(config.bocpd_cooldown),
        "minimum_observed_fraction": float(config.bocpd_min_observed_fraction),
    }
    actual = {
        "hazard_type": state.hazard_type,
        "expected_run_length": state.expected_run_length,
        "max_run_length": state.max_run_length,
        "posterior_mass_prune": state.posterior_mass_prune,
        "alert_threshold": state.alert_threshold,
        "minimum_evidence_count": state.minimum_evidence_count,
        "cooldown": state.cooldown,
        "minimum_observed_fraction": state.minimum_observed_fraction,
    }
    if actual != expected:
        raise ValueError("initial BOCPD state configuration does not match current configuration")
    expected_prior = float(config.bocpd_prior_concentration)
    if not np.allclose(state.prior_alpha, expected_prior):
        raise ValueError("initial BOCPD prior does not match current configuration")


def fit_bocpd_dirichlet_categorical(
    y: np.ndarray,
    *,
    game: str,
    classes: int,
    config: Any,
    seed: int,
    initial_state: BOCPDDirichletCategoricalState | None = None,
) -> BOCPDDirichletCategoricalState:
    values = _validate_observations(y, classes)
    positions = values.shape[1]
    if str(config.bocpd_hazard_type) != "constant":
        raise ValueError("only constant BOCPD hazard is implemented")
    hazard = _constant_hazard(float(config.bocpd_expected_run_length))

    if initial_state is None:
        state = _initial_state(
            game=game,
            classes=classes,
            positions=positions,
            config=config,
            seed=seed,
        )
    else:
        _validate_resume(
            initial_state,
            game=game,
            classes=classes,
            positions=positions,
            config=config,
        )
        state = initial_state

    run_lengths = state.run_lengths.copy()
    posterior = state.run_length_posterior.copy()
    alpha = state.dirichlet_alpha.copy()
    probability_history = [row.copy() for row in state.one_step_probabilities]
    changepoint_history = list(state.changepoint_probabilities)
    map_history = [int(item) for item in state.map_run_length_history]
    pruned_history = list(state.pruned_mass_history)
    quality_history = [bool(item) for item in state.data_quality_pass]
    alerts = [dict(item) for item in state.alert_events]
    last_alert_step = state.last_alert_step
    evidence_count = state.evidence_count

    for offset, row in enumerate(values):
        step = state.current_step + offset
        probability_history.append(_mixture_probabilities(posterior, alpha))
        quality = _quality_pass(row, state.minimum_observed_fraction)
        quality_history.append(quality)
        if quality:
            evidence_count += 1

        log_posterior = np.log(np.clip(posterior, 1e-300, None))
        log_growth_predictive = _row_log_predictive(alpha, row)
        log_prior_predictive = float(_row_log_predictive(state.prior_alpha[None], row)[0])
        log_changepoint = logsumexp(log_posterior + np.log(hazard))
        log_changepoint += log_prior_predictive
        log_growth = log_posterior + np.log1p(-hazard) + log_growth_predictive
        log_joint = np.concatenate(([log_changepoint], log_growth))
        log_joint -= logsumexp(log_joint)
        candidate_posterior = np.exp(log_joint)

        counts = _row_counts(row, positions=positions, classes=classes)
        candidate_alpha = np.concatenate(
            (
                (state.prior_alpha + counts)[None, :, :],
                alpha + counts[None, :, :],
            ),
            axis=0,
        )
        candidate_run_lengths = np.concatenate(
            (np.array([0], dtype=np.int64), run_lengths + 1)
        )

        within_cap = candidate_run_lengths <= state.max_run_length
        above_mass = candidate_posterior >= state.posterior_mass_prune
        keep = within_cap & above_mass
        keep[0] = True
        within_indexes = np.flatnonzero(within_cap)
        best_within = within_indexes[int(np.argmax(candidate_posterior[within_indexes]))]
        keep[best_within] = True
        kept_mass = float(candidate_posterior[keep].sum())
        if not np.isfinite(kept_mass) or kept_mass <= 0.0:
            raise ValueError("CHANGEPOINT_UNSTABLE: posterior pruning removed all mass")
        discarded_mass = float(np.clip(1.0 - kept_mass, 0.0, 1.0))
        run_lengths = candidate_run_lengths[keep]
        posterior = candidate_posterior[keep] / kept_mass
        alpha = candidate_alpha[keep]

        changepoint_indexes = np.flatnonzero(run_lengths == 0)
        changepoint_probability = (
            float(posterior[changepoint_indexes[0]]) if changepoint_indexes.size else 0.0
        )
        changepoint_history.append(changepoint_probability)
        map_history.append(int(run_lengths[int(np.argmax(posterior))]))
        pruned_history.append(discarded_mass)

        cooldown_ok = (
            last_alert_step is None or step - last_alert_step >= state.cooldown
        )
        if (
            changepoint_probability >= state.alert_threshold
            and evidence_count >= state.minimum_evidence_count
            and cooldown_ok
            and quality
        ):
            alerts.append(
                {
                    "event_type": RETRAIN_EVENT,
                    "step": step,
                    "changepoint_probability": changepoint_probability,
                    "evidence_count": evidence_count,
                    "data_quality_gate": "PASS",
                    "automatic_retraining": False,
                }
            )
            last_alert_step = step

    final = BOCPDDirichletCategoricalState(
        model_id=MODEL_ID,
        game=game,
        classes=classes,
        positions=positions,
        run_lengths=run_lengths,
        run_length_posterior=posterior,
        dirichlet_alpha=alpha,
        prior_alpha=state.prior_alpha.copy(),
        current_step=state.current_step + len(values),
        evidence_count=evidence_count,
        one_step_probabilities=np.asarray(probability_history, dtype=np.float64),
        changepoint_probabilities=np.asarray(changepoint_history, dtype=np.float64),
        map_run_length_history=np.asarray(map_history, dtype=np.int64),
        pruned_mass_history=np.asarray(pruned_history, dtype=np.float64),
        data_quality_pass=np.asarray(quality_history, dtype=bool),
        alert_events=tuple(alerts),
        last_alert_step=last_alert_step,
        hazard_type=state.hazard_type,
        expected_run_length=state.expected_run_length,
        max_run_length=state.max_run_length,
        posterior_mass_prune=state.posterior_mass_prune,
        alert_threshold=state.alert_threshold,
        minimum_evidence_count=state.minimum_evidence_count,
        cooldown=state.cooldown,
        minimum_observed_fraction=state.minimum_observed_fraction,
        seed=seed,
        metadata=dict(state.metadata),
    )
    if not np.isfinite(final.run_length_posterior).all():
        raise ValueError("CHANGEPOINT_UNSTABLE: run-length posterior is non-finite")
    if not np.isclose(final.run_length_posterior.sum(), 1.0, atol=1e-12):
        raise ValueError("CHANGEPOINT_UNSTABLE: run-length posterior is not normalized")
    return final


__all__ = [
    "MODEL_ID",
    "RETRAIN_EVENT",
    "BOCPDDirichletCategoricalState",
    "fit_bocpd_dirichlet_categorical",
]
