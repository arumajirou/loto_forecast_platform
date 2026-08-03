from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from functools import cache
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import yaml

from loto.probabilistic.contracts import InferenceProfileSpec, ProbabilisticModelSpec

_ALLOWED_FAMILIES = {
    "bayesian_regression",
    "calibration",
    "changepoint",
    "conjugate",
    "count",
    "copula",
    "decision",
    "deep_probabilistic",
    "dynamic_conjugate",
    "empirical_bayes",
    "fixed_subset",
    "ensemble",
    "gaussian_process",
    "hierarchical",
    "mixture",
    "nonparametric",
    "ordinal",
    "regime_switching",
    "semi_parametric",
    "state_space",
    "tree_bayesian",
}
_PPL02_CONDITIONAL_BERNOULLI_ROW: dict[str, Any] = {
    "model_id": "pp-conditional-bernoulli-fixed-k",
    "family": "fixed_subset",
    "role": "candidate",
    "likelihood": "ConditionalBernoulliFixedK",
    "latent_structure": (
        "candidate log-weights with an exact fixed-cardinality normalizer and MAP/Laplace posterior"
    ),
    "backends": ["builtin"],
    "tasks": ["fixed_cardinality_subset"],
    "priority": "p0",
    "supports_exogenous": False,
    "hierarchical": False,
    "dynamic": False,
    "experimental": True,
    "notes": "PPL-02 M01; exact O(Kk) normalizer and backward-DP sampler",
}
_PPL02_DGLM_ROW: dict[str, Any] = {
    "model_id": "pp-multinomial-dglm",
    "family": "state_space",
    "role": "candidate",
    "likelihood": "MultinomialLogit",
    "latent_structure": (
        "reference-category dynamic generalized linear model with discount evolution "
        "and sequential Laplace/EKF updates"
    ),
    "backends": ["builtin"],
    "tasks": ["dynamic_multinomial"],
    "priority": "p0",
    "supports_exogenous": True,
    "hierarchical": False,
    "dynamic": True,
    "experimental": True,
    "notes": "PPL-02 M04; predict-before-update dynamic multinomial filter",
}
_PPL02_COPULA_ROW: dict[str, Any] = {
    "model_id": "pp-gaussian-copula-categorical",
    "family": "copula",
    "role": "candidate",
    "likelihood": "LatentGaussianCopulaCategorical",
    "latent_structure": (
        "fold-fitted categorical margins with ordered Gaussian thresholds and an "
        "LKJ-regularized latent correlation matrix"
    ),
    "backends": ["pymc"],
    "tasks": ["joint_discrete_copula"],
    "priority": "p0",
    "supports_exogenous": False,
    "hierarchical": False,
    "dynamic": False,
    "experimental": True,
    "notes": "PPL-02 M05; Numbers3/4 static Gaussian copula with fixed margins",
}
_PPL02_BOCPD_ROW: dict[str, Any] = {
    "model_id": "pp-bocpd-dirichlet-categorical",
    "family": "changepoint",
    "role": "candidate",
    "likelihood": "DirichletCategoricalBOCPD",
    "latent_structure": (
        "exact online run-length posterior with constant hazard and per-run-length "
        "Dirichlet categorical sufficient statistics"
    ),
    "backends": ["builtin"],
    "tasks": ["online_changepoint"],
    "priority": "p0",
    "supports_exogenous": False,
    "hierarchical": False,
    "dynamic": True,
    "experimental": True,
    "notes": "PPL-02 M06; pruned BOCPD monitor with RETRAIN_RECOMMENDED events",
}
_PPL02_ROWS = (
    _PPL02_CONDITIONAL_BERNOULLI_ROW,
    _PPL02_DGLM_ROW,
    _PPL02_COPULA_ROW,
    _PPL02_BOCPD_ROW,
)

_ALLOWED_ROLES = {"control", "baseline", "candidate", "research", "meta"}
_ALLOWED_PRIORITIES = {"p0", "p1", "p2"}

_BACKEND_IMPORTS: dict[str, tuple[str, ...]] = {
    "builtin": (),
    "arviz": ("arviz",),
    "pymc": ("pymc",),
    "pymc_bart": ("pymc_bart",),
    "numpyro": ("numpyro", "jax"),
    "pyro": ("pyro", "torch"),
    "stan": ("cmdstanpy",),
    "cmdstanpy": ("cmdstanpy",),
    "blackjax": ("blackjax", "jax"),
    "pymc+blackjax": ("pymc", "blackjax", "jax"),
    "pymc+numpyro": ("pymc", "numpyro", "jax"),
    "tfp": ("tensorflow_probability",),
    "tensorflow_probability": ("tensorflow_probability",),
}


def _data_path(name: str) -> Path:
    override = os.environ.get("LOTO_PPL_CONFIG_DIR")
    if override:
        candidate = Path(override) / name
        if candidate.exists():
            return candidate
    project_candidate = Path(__file__).resolve().parents[3] / "configs" / "probabilistic" / name
    if project_candidate.exists():
        return project_candidate
    package_candidate = Path(__file__).resolve().parent / "data" / name
    if package_candidate.exists():
        return package_candidate
    raise FileNotFoundError(f"probabilistic config not found: {name}")


def _safe_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return payload


def _strategy_for(model_id: str, family: str) -> str:
    if model_id == "pp-uniform-dirichlet":
        return "uniform"
    if "rolling-dirichlet" in model_id:
        return "rolling_dirichlet"
    if "discount" in model_id:
        return "discounted_dirichlet"
    if "expanding" in model_id or "static-dirichlet" in model_id:
        return "dirichlet"
    if family == "empirical_bayes":
        return "empirical_bayes"
    if family == "fixed_subset":
        return "fixed_cardinality_subset"
    if family == "hierarchical":
        return "hierarchical_pooling"
    if family in {
        "bayesian_regression",
        "copula",
        "ordinal",
        "semi_parametric",
        "tree_bayesian",
        "gaussian_process",
    }:
        return "context_transition"
    if family in {"dynamic_conjugate", "state_space", "changepoint", "regime_switching"}:
        return "dynamic_context"
    if family == "count":
        return "count_posterior"
    if family in {"mixture", "nonparametric"}:
        return "mixture_context"
    if family == "deep_probabilistic":
        return "sequence_bootstrap"
    if family == "ensemble":
        return "ensemble_reference"
    if family == "calibration":
        return "calibration_reference"
    if family == "decision":
        return "decision_reference"
    return "generic"


def load_probabilistic_catalog(
    path: str | Path | None = None,
) -> tuple[ProbabilisticModelSpec, ...]:
    source = Path(path) if path else _data_path("catalog.yaml")
    payload = _safe_yaml(source)
    schema_version = str(payload.get("schema_version", "1.0.0"))
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise ValueError(f"{source}: models must be a list")
    for ppl02_row in _PPL02_ROWS:
        if not any(
            isinstance(row, dict) and row.get("model_id") == ppl02_row["model_id"] for row in rows
        ):
            rows = [*rows, dict(ppl02_row)]
    from loto.probabilistic.native_registry import get_native_implementation

    specs: list[ProbabilisticModelSpec] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{source}: model row {index} must be a mapping")
        model_id = str(row.get("model_id", "")).strip()
        if not model_id or model_id in seen:
            raise ValueError(f"{source}: duplicate or empty model_id {model_id!r}")
        seen.add(model_id)
        family = str(row.get("family", ""))
        if family not in _ALLOWED_FAMILIES:
            raise ValueError(f"{source}: unknown family {family!r} for {model_id}")
        role = str(row.get("role", "candidate"))
        if role not in _ALLOWED_ROLES:
            raise ValueError(f"{source}: unknown role {role!r} for {model_id}")
        priority = str(row.get("priority", "p1"))
        if priority not in _ALLOWED_PRIORITIES:
            raise ValueError(f"{source}: unknown priority {priority!r} for {model_id}")
        backends = tuple(str(x) for x in row.get("backends", ()))
        tasks = tuple(str(x) for x in row.get("tasks", ()))
        if not backends or not tasks:
            raise ValueError(f"{source}: {model_id} must declare backends and tasks")
        native = get_native_implementation(model_id)
        specs.append(
            ProbabilisticModelSpec(
                schema_version=schema_version,
                model_id=model_id,
                family=family,
                role=role,  # type: ignore[arg-type]
                likelihood=str(row.get("likelihood", "")),
                latent_structure=str(row.get("latent_structure", "")),
                backends=backends,
                tasks=tasks,
                priority=priority,  # type: ignore[arg-type]
                supports_exogenous=bool(row.get("supports_exogenous", False)),
                hierarchical=bool(row.get("hierarchical", False)),
                dynamic=bool(row.get("dynamic", False)),
                experimental=bool(row.get("experimental", False)),
                notes=str(row.get("notes", "")),
                implementation_status="IMPLEMENTED",
                reference_strategy=_strategy_for(model_id, family),
                primary_backend=native.primary_backend,
                primary_profile=native.primary_profile,
                native_implementation_status="IMPLEMENTED",
                native_graph_id=native.graph_id,
            )
        )
    return tuple(specs)


def load_inference_profiles(path: str | Path | None = None) -> tuple[InferenceProfileSpec, ...]:
    source = Path(path) if path else _data_path("inference_profiles.yaml")
    payload = _safe_yaml(source)
    rows = payload.get("profiles")
    if not isinstance(rows, list):
        raise ValueError(f"{source}: profiles must be a list")
    profiles: list[InferenceProfileSpec] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{source}: profile rows must be mappings")
        profile_id = str(row.get("profile_id", "")).strip()
        if not profile_id or profile_id in seen:
            raise ValueError(f"{source}: duplicate or empty profile_id {profile_id!r}")
        seen.add(profile_id)
        profiles.append(
            InferenceProfileSpec(
                profile_id=profile_id,
                backend=str(row.get("backend", "")),
                algorithm=str(row.get("algorithm", "")),
                tier=str(row.get("tier", "")),
                continuous_only=bool(row.get("continuous_only", False)),
                default=dict(row.get("default") or {}),
            )
        )
    return tuple(profiles)


_MODEL_SPECS = load_probabilistic_catalog()
_INFERENCE_PROFILES = load_inference_profiles()


def list_probabilistic_model_specs(
    *, family: str | None = None, priority: str | None = None, experimental: bool | None = None
) -> list[ProbabilisticModelSpec]:
    rows: Iterable[ProbabilisticModelSpec] = _MODEL_SPECS
    if family:
        rows = (x for x in rows if x.family == family)
    if priority:
        rows = (x for x in rows if x.priority == priority)
    if experimental is not None:
        rows = (x for x in rows if x.experimental is experimental)
    return list(rows)


def get_probabilistic_model_spec(model_id: str) -> ProbabilisticModelSpec:
    for spec in _MODEL_SPECS:
        if spec.model_id == model_id:
            return spec
    raise KeyError(model_id)


def list_inference_profiles(*, backend: str | None = None) -> list[InferenceProfileSpec]:
    return [x for x in _INFERENCE_PROFILES if backend is None or x.backend == backend]


def get_inference_profile(profile_id: str) -> InferenceProfileSpec:
    for spec in _INFERENCE_PROFILES:
        if spec.profile_id == profile_id:
            return spec
    raise KeyError(profile_id)


@cache
def backend_available(backend: str) -> bool:
    modules = _BACKEND_IMPORTS.get(backend, (backend,))
    if not modules:
        return True
    if not all(find_spec(module) is not None for module in modules):
        return False
    script = ";".join(f"import {module}" for module in modules)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def backend_availability() -> dict[str, bool]:
    names = {"builtin"}
    for spec in _MODEL_SPECS:
        names.update(spec.backends)
    for profile in _INFERENCE_PROFILES:
        names.add(profile.backend)
    return {name: backend_available(name) for name in sorted(names)}


def catalog_counts() -> dict[str, Any]:
    by_family: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for spec in _MODEL_SPECS:
        by_family[spec.family] = by_family.get(spec.family, 0) + 1
        by_priority[spec.priority] = by_priority.get(spec.priority, 0) + 1
    canonical = [spec.to_dict() for spec in _MODEL_SPECS]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return {
        "probabilistic_models": len(_MODEL_SPECS),
        "inference_profiles": len(_INFERENCE_PROFILES),
        "by_family": dict(sorted(by_family.items())),
        "by_priority": dict(sorted(by_priority.items())),
        "catalog_sha256": digest,
        "backend_availability": backend_availability(),
    }


def build_unified_catalog_rows() -> list[dict[str, Any]]:
    """Return existing and probabilistic entries without any model-ID collision."""
    from loto.models.catalog_full import build_catalog

    existing = [entry.to_row() | {"catalog_source": "existing"} for entry in build_catalog()]
    probabilistic = [
        {
            "model_id": spec.model_id,
            "family": spec.family,
            "library": "probabilistic",
            "class_name": spec.likelihood,
            "priority": spec.priority,
            "role": spec.role,
            "capabilities": [
                "probability",
                "posterior_distribution",
                "posterior_predictive",
                "uncertainty_diagnostics",
                "probabilistic_programming",
            ],
            "available": True,
            "implementation_status": spec.implementation_status,
            "reference_strategy": spec.reference_strategy,
            "primary_backend": spec.primary_backend,
            "primary_profile": spec.primary_profile,
            "native_implementation_status": spec.native_implementation_status,
            "native_graph_id": spec.native_graph_id,
            "catalog_source": "probabilistic",
        }
        for spec in _MODEL_SPECS
    ]
    ids = [str(row["model_id"]) for row in [*existing, *probabilistic]]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError(f"unified catalog model_id collision: {duplicates}")
    return [*existing, *probabilistic]


def unified_catalog_counts() -> dict[str, int]:
    rows = build_unified_catalog_rows()
    return {
        "existing": sum(row["catalog_source"] == "existing" for row in rows),
        "probabilistic": sum(row["catalog_source"] == "probabilistic" for row in rows),
        "total": len(rows),
    }
