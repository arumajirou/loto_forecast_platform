"""Strict YAML loader, allowlisted environment overrides, and resolved-config artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml
from pydantic import SecretStr

from .contracts import CONFIG_SCHEMA_VERSION, REDACTED_VALUE, StrictFoundationConfig
from .migration import migrate_payload, source_schema_version

Parser = Callable[[str], object]


@dataclass(frozen=True)
class OverrideSpec:
    target: tuple[str, ...]
    parser: Parser
    sensitive: bool = False


@dataclass(frozen=True)
class OverrideRecord:
    env_var: str
    target: str
    source: str
    sensitive: bool
    value: object

    def to_dict(self) -> dict[str, object]:
        return {
            "env_var": self.env_var,
            "target": self.target,
            "source": self.source,
            "sensitive": self.sensitive,
            "value": REDACTED_VALUE if self.sensitive else self.value,
        }


@dataclass(frozen=True)
class ResolvedConfig:
    config: StrictFoundationConfig
    redacted_config: dict[str, Any]
    config_sha256: str
    overrides: tuple[OverrideRecord, ...]

    def envelope(self) -> dict[str, object]:
        return {
            "resolved_config_schema_version": CONFIG_SCHEMA_VERSION,
            "resolved_config_sha256": self.config_sha256,
            "environment_overrides": [record.to_dict() for record in self.overrides],
            "resolved_config": self.redacted_config,
        }


def _parse_string(value: str) -> str:
    return value


def _parse_bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("expected a boolean environment value")


def _parse_integer_list(value: str) -> list[int]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("expected a JSON integer list") from exc
    if not isinstance(parsed, list) or any(type(item) is not int for item in parsed):
        raise ValueError("expected a JSON integer list")
    return parsed


ENVIRONMENT_OVERRIDES: dict[str, OverrideSpec] = {
    "LOTO_CONFIG_EXPERIMENT_NAME": OverrideSpec(("experiment_name",), _parse_string),
    "LOTO_CONFIG_OUTPUT_DIR": OverrideSpec(("runtime", "output_dir"), _parse_string),
    "LOTO_CONFIG_REQUESTED_DEVICE": OverrideSpec(
        ("runtime", "device", "requested"), _parse_string
    ),
    "LOTO_CONFIG_CPU_FALLBACK_POLICY": OverrideSpec(
        ("runtime", "device", "cpu_fallback_policy"), _parse_string
    ),
    "LOTO_CONFIG_SEEDS": OverrideSpec(
        ("evaluation", "seed_policy", "seeds"), _parse_integer_list
    ),
    "LOTO_CONFIG_MLFLOW_ENABLED": OverrideSpec(
        ("observability", "mlflow", "enabled"), _parse_bool
    ),
    "LOTO_CONFIG_MLFLOW_TRACKING_URI": OverrideSpec(
        ("observability", "mlflow", "tracking_uri"), _parse_string
    ),
    "LOTO_CONFIG_MLFLOW_EXPERIMENT_NAME": OverrideSpec(
        ("observability", "mlflow", "experiment_name"), _parse_string
    ),
    "LOTO_CONFIG_MLFLOW_TOKEN": OverrideSpec(
        ("observability", "mlflow", "token"), _parse_string, sensitive=True
    ),
    "LOTO_CONFIG_GIT_REQUIRE_CLEAN": OverrideSpec(
        ("git_metadata", "require_clean_worktree"), _parse_bool
    ),
}


def _set_nested(payload: dict[str, Any], target: tuple[str, ...], value: object) -> None:
    current: dict[str, Any] = payload
    for component in target[:-1]:
        existing = current.get(component)
        if existing is None:
            existing = {}
            current[component] = existing
        if not isinstance(existing, dict):
            raise ValueError(f"environment override target is not a mapping: {'.'.join(target)}")
        current = existing
    current[target[-1]] = value


def _redact(value: object) -> object:
    if isinstance(value, SecretStr):
        return REDACTED_VALUE
    if isinstance(value, dict):
        return {str(key): _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return value


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_payload(
    payload: dict[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> ResolvedConfig:
    """Validate one versioned payload after allowlisted environment overrides."""

    source_schema_version(payload)
    migrated = migrate_payload(payload)
    resolved_payload = deepcopy(migrated)
    environment = os.environ if environ is None else environ
    records: list[OverrideRecord] = []
    for env_var, spec in ENVIRONMENT_OVERRIDES.items():
        if env_var not in environment:
            continue
        parsed = spec.parser(environment[env_var])
        _set_nested(resolved_payload, spec.target, parsed)
        records.append(
            OverrideRecord(
                env_var=env_var,
                target=".".join(spec.target),
                source="environment",
                sensitive=spec.sensitive,
                value=parsed,
            )
        )
    config = StrictFoundationConfig.model_validate(resolved_payload)
    redacted = _redact(config.model_dump(mode="python"))
    if not isinstance(redacted, dict):
        raise TypeError("resolved configuration did not serialize to a mapping")
    return ResolvedConfig(
        config=config,
        redacted_config=redacted,
        config_sha256=_canonical_sha256(redacted),
        overrides=tuple(records),
    )


def load_config(
    path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> ResolvedConfig:
    source = Path(path)
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a mapping")
    return resolve_payload(raw, environ=environ)


def write_resolved_config(resolved: ResolvedConfig, output: str | Path) -> tuple[Path, Path]:
    """Atomically write redacted resolved JSON and a config-hash sidecar."""

    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    sidecar = target.with_name(f"{target.name}.sha256")
    temporary = target.with_name(f".{target.name}.tmp")
    sidecar_temporary = sidecar.with_name(f".{sidecar.name}.tmp")
    temporary.write_text(
        json.dumps(resolved.envelope(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sidecar_temporary.write_text(
        f"{resolved.config_sha256}  {target.name}\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)
    os.replace(sidecar_temporary, sidecar)
    return target, sidecar
