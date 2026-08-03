from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

import yaml

from loto.probabilistic.contracts import ProbabilisticRunConfig


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_run_config(path: str | Path) -> ProbabilisticRunConfig:
    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("run config must be a YAML mapping")
    return ProbabilisticRunConfig.model_validate(payload)


def write_resolved_config(config: ProbabilisticRunConfig, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return target


def environment_fingerprint() -> dict[str, Any]:
    payload = {
        "python": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    payload["environment_hash"] = stable_hash(payload)
    return payload


def execution_fingerprint(
    *,
    protocol_hash: str,
    model_spec: Any,
    run_config: ProbabilisticRunConfig,
    backend: str,
    inference_profile_id: str | None = None,
) -> dict[str, str]:
    model_spec_hash = stable_hash(model_spec.to_dict())
    prior_spec_hash = stable_hash(
        {
            "prior_concentration": run_config.prior_concentration,
            "rolling_window": run_config.rolling_window,
            "discount_factor": run_config.discount_factor,
        }
    )
    inference_profile_hash = stable_hash(
        {
            "backend": backend,
            "selected_profile": inference_profile_id,
            "profiles": run_config.inference_profiles,
            "posterior_draws": run_config.posterior_draws,
            "native_draws": run_config.native_draws,
            "native_warmup": run_config.native_warmup,
            "native_chains": run_config.native_chains,
            "native_svi_steps": run_config.native_svi_steps,
            "native_particles": run_config.native_particles,
            "native_device": run_config.native_device,
            "native_inner_cores": run_config.native_inner_cores,
            "scheduling_policy": run_config.scheduling_policy,
            "gpu_priority": run_config.gpu_priority,
            "gpu_backends": run_config.gpu_backends,
        }
    )
    decision_rule_hash = stable_hash({"lambda_mse": run_config.utility_lambda_mse})
    environment_hash = environment_fingerprint()["environment_hash"]
    fingerprint = stable_hash(
        {
            "protocol_hash": protocol_hash,
            "model_spec_hash": model_spec_hash,
            "prior_spec_hash": prior_spec_hash,
            "inference_profile_hash": inference_profile_hash,
            "decision_rule_hash": decision_rule_hash,
            "environment_hash": environment_hash,
        }
    )
    return {
        "protocol_hash": protocol_hash,
        "model_spec_hash": model_spec_hash,
        "prior_spec_hash": prior_spec_hash,
        "inference_profile_hash": inference_profile_hash,
        "decision_rule_hash": decision_rule_hash,
        "environment_hash": environment_hash,
        "execution_fingerprint": fingerprint,
    }
