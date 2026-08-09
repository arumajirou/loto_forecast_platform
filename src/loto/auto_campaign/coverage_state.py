"""Resolve static API plans into auditable execution and verification states.

The resolver is CPU-safe: it joins the static argument catalog, API case results,
and an all-AutoModel constructor matrix without claiming GPU runtime success.
"""

from __future__ import annotations

import argparse
import inspect
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd

from .arguments import build_argument_catalog
from .persistence import write_json, write_sha256s
from .registry import discover_auto_models, get_auto_class, get_default_config


class VerificationStatus(StrEnum):
    EXECUTION_PENDING = "EXECUTION_PENDING"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


_TERMINAL_CASE_STATUSES = {
    "EXECUTED",
    "EXECUTED_ALTERNATE",
    "FIXED_BY_DATA_CONTRACT",
    "NOT_APPLICABLE",
    "UNSUPPORTED_BY_VERSION",
}


def _case_value(row: Mapping[str, Any], key: str) -> Any:
    nested = row.get("case")
    if isinstance(nested, Mapping) and key in nested:
        return nested[key]
    dotted = f"case.{key}"
    return row[dotted] if dotted in row else row.get(key)


def _normalize_case_results(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for source in rows:
        row = dict(source)
        case_id = str(_case_value(row, "case_id") or "").strip()
        layer = str(_case_value(row, "layer") or "").strip()
        argument = str(_case_value(row, "argument") or "").strip()
        status = str(row.get("status") or "").strip()
        if not case_id or not layer or not argument or not status:
            raise ValueError(f"malformed API coverage result: {row}")
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate API coverage case_id: {case_id}")
        seen_case_ids.add(case_id)
        normalized.append(
            {
                "case_id": case_id,
                "layer": layer,
                "argument": argument,
                "status": status,
                "expected": str(_case_value(row, "expected") or "PASS"),
                "error_type": row.get("error_type"),
                "error": row.get("error"),
                "artifacts": row.get("artifacts"),
            }
        )
    return normalized


def build_constructor_contract_matrix(
    *,
    expected_model_count: int = 36,
    probe_default_configs: bool = True,
) -> list[dict[str, Any]]:
    """Build one constructor/default-config contract row per AutoModel.

    No model is fitted and no CUDA work is performed.
    """

    records = discover_auto_models()
    if len(records) != expected_model_count:
        raise RuntimeError(
            "AutoModel inventory count mismatch: "
            f"expected={expected_model_count}, actual={len(records)}"
        )

    rows: list[dict[str, Any]] = []
    for record in records:
        signature = inspect.signature(get_auto_class(record.name))
        parameters = [name for name in signature.parameters if name not in {"self", "cls"}]
        backend_results: dict[str, dict[str, Any]] = {}
        for backend in ("ray", "optuna"):
            if backend not in record.supported_backends:
                backend_results[backend] = {
                    "status": "NOT_APPLICABLE",
                    "reason": record.unsupported_backend_reason,
                }
            elif not probe_default_configs:
                backend_results[backend] = {
                    "status": "EXECUTION_PENDING",
                    "reason": "default-config probe disabled",
                }
            else:
                try:
                    config = get_default_config(
                        record.name,
                        h=1,
                        backend=backend,
                        n_series=5 if record.requires_n_series else None,
                    )
                    if config is None and not record.is_hint:
                        raise RuntimeError("get_default_config returned None")
                    backend_results[backend] = {
                        "status": "VERIFIED",
                        "config_type": type(config).__name__,
                        "special_constructor": record.is_hint,
                    }
                except Exception as exc:
                    backend_results[backend] = {
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }

        missing_required = sorted({"h", "config"} - set(parameters))
        failed_backends = sorted(
            name for name, result in backend_results.items() if result["status"] == "FAILED"
        )
        pending_backends = sorted(
            name
            for name, result in backend_results.items()
            if result["status"] == "EXECUTION_PENDING"
        )
        if missing_required or failed_backends:
            verification = VerificationStatus.FAILED.value
        elif pending_backends:
            verification = VerificationStatus.PARTIALLY_VERIFIED.value
        else:
            verification = VerificationStatus.VERIFIED.value

        rows.append(
            {
                **asdict(record),
                "constructor_parameters": parameters,
                "constructor_has_h": "h" in parameters,
                "constructor_has_config": "config" in parameters,
                "missing_required_arguments": missing_required,
                "ray_default_config_status": backend_results["ray"]["status"],
                "optuna_default_config_status": backend_results["optuna"]["status"],
                "backend_results": backend_results,
                "failed_backends": failed_backends,
                "pending_backends": pending_backends,
                "verification_status": verification,
            }
        )
    return rows


def _constructor_evidence(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    failed = [row for row in rows if row.get("verification_status") == "FAILED"]
    pending = [row for row in rows if row.get("verification_status") == "PARTIALLY_VERIFIED"]
    if failed:
        status = VerificationStatus.FAILED.value
    elif pending:
        status = VerificationStatus.PARTIALLY_VERIFIED.value
    else:
        status = VerificationStatus.VERIFIED.value
    evidence = {
        "verification_status": status,
        "model_count": len(rows),
        "models": sorted(str(row.get("name")) for row in rows),
        "failed_models": sorted(str(row.get("name")) for row in failed),
        "pending_models": sorted(str(row.get("name")) for row in pending),
        "evidence_type": "all-automodel-constructor-contract",
    }
    return {
        ("BaseAuto", "cls_model"): evidence,
        ("BaseAuto", "config"): evidence,
    }


def resolve_argument_catalog(
    case_results: Iterable[Mapping[str, Any]],
    *,
    catalog: Sequence[Mapping[str, Any]] | None = None,
    constructor_matrix: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Merge declared catalog rows with observed API and constructor evidence."""

    normalized = _normalize_case_results(case_results)
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        by_key[(row["layer"], row["argument"])].append(row)
    constructor = _constructor_evidence(constructor_matrix) if constructor_matrix else {}

    resolved: list[dict[str, Any]] = []
    for source in catalog or build_argument_catalog():
        row = dict(source)
        key = (str(row["layer"]), str(row["argument"]))
        cases = by_key.get(key, [])
        statuses = [case["status"] for case in cases]
        failed_case_ids = [case["case_id"] for case in cases if case["status"] == "FAILED"]
        unknown = sorted(
            status
            for status in statuses
            if status not in _TERMINAL_CASE_STATUSES and status != "FAILED"
        )
        constructor_result = constructor.get(key)
        if failed_case_ids or unknown:
            verification = VerificationStatus.FAILED.value
        elif cases and all(status in _TERMINAL_CASE_STATUSES for status in statuses):
            verification = VerificationStatus.VERIFIED.value
        elif constructor_result is not None:
            verification = str(constructor_result["verification_status"])
        else:
            verification = VerificationStatus.EXECUTION_PENDING.value

        resolved.append(
            {
                **row,
                "declared_status": str(row.get("status")),
                "observed_statuses": sorted(set(statuses)),
                "verification_status": verification,
                "case_count": len(cases),
                "case_ids": [case["case_id"] for case in cases],
                "failed_case_ids": failed_case_ids,
                "unrecognized_case_statuses": unknown,
                "constructor_evidence": constructor_result,
            }
        )
    return resolved


def summarize_resolved_catalog(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["verification_status"]) for row in rows)
    failed = counts[VerificationStatus.FAILED.value]
    verified = counts[VerificationStatus.VERIFIED.value]
    pending = counts[VerificationStatus.EXECUTION_PENDING.value]
    partial = counts[VerificationStatus.PARTIALLY_VERIFIED.value]
    if failed:
        overall = VerificationStatus.FAILED.value
    elif verified == len(rows):
        overall = VerificationStatus.VERIFIED.value
    elif verified or partial:
        overall = VerificationStatus.PARTIALLY_VERIFIED.value
    else:
        overall = VerificationStatus.EXECUTION_PENDING.value
    return {
        "overall_status": overall,
        "argument_count": len(rows),
        "verification_status_counts": dict(sorted(counts.items())),
        "verified_arguments": verified,
        "pending_arguments": pending,
        "partially_verified_arguments": partial,
        "failed_arguments": failed,
    }


def _load_results(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path).to_dict(orient="records")
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path).to_dict(orient="records")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [dict(row) for row in payload]
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            return [dict(row) for row in payload["results"]]
    raise ValueError(f"unsupported API coverage result format: {path}")


def _tabular_frame(rows: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Convert nested or heterogeneous audit values to deterministic JSON strings."""

    json_columns: set[str] = set()
    scalar_types: dict[str, set[type[Any]]] = defaultdict(set)
    for source in rows:
        for key, value in source.items():
            if isinstance(value, (dict, list, tuple, set)):
                json_columns.add(key)
            elif value is not None:
                scalar_types[key].add(type(value))
    json_columns.update(key for key, types in scalar_types.items() if len(types) > 1)

    normalized: list[dict[str, Any]] = []
    for source in rows:
        row: dict[str, Any] = {}
        for key, value in source.items():
            if key in json_columns:
                row[key] = json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=repr,
                )
            else:
                row[key] = value
        normalized.append(row)
    return pd.DataFrame(normalized)


def write_coverage_state_bundle(
    *,
    output_dir: Path,
    api_results: Sequence[Mapping[str, Any]],
    expected_model_count: int = 36,
    probe_default_configs: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    constructor_matrix = build_constructor_contract_matrix(
        expected_model_count=expected_model_count,
        probe_default_configs=probe_default_configs,
    )
    resolved = resolve_argument_catalog(api_results, constructor_matrix=constructor_matrix)
    summary = summarize_resolved_catalog(resolved)

    write_json(output_dir / "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.json", constructor_matrix)
    constructor_frame = _tabular_frame(constructor_matrix)
    constructor_frame.to_csv(output_dir / "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.csv", index=False)
    constructor_frame.to_parquet(
        output_dir / "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.parquet",
        index=False,
    )
    write_json(output_dir / "API_ARGUMENT_COVERAGE_RESOLVED.json", resolved)
    resolved_frame = _tabular_frame(resolved)
    resolved_frame.to_csv(output_dir / "API_ARGUMENT_COVERAGE_RESOLVED.csv", index=False)
    resolved_frame.to_parquet(
        output_dir / "API_ARGUMENT_COVERAGE_RESOLVED.parquet",
        index=False,
    )
    write_json(output_dir / "COVERAGE_SUMMARY.json", summary)

    constructor_statuses = Counter(str(row["verification_status"]) for row in constructor_matrix)
    manifest = {
        "schema_version": "all-auto-coverage-state-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": summary["overall_status"],
        "argument_coverage": summary,
        "constructor_model_count": len(constructor_matrix),
        "constructor_status_counts": dict(sorted(constructor_statuses.items())),
        "api_result_count": len(api_results),
        "gpu_runtime_status": VerificationStatus.EXECUTION_PENDING.value,
        "gpu_runtime_reason": (
            "No local or self-hosted GPU runner evidence was supplied to this CPU-safe bundle."
        ),
    }
    write_json(output_dir / "manifest.json", manifest)
    write_sha256s(output_dir)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve NeuralForecast API coverage and constructor contract states."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-results", type=Path)
    parser.add_argument("--expected-model-count", type=int, default=36)
    parser.add_argument("--skip-default-config-probes", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = write_coverage_state_bundle(
        output_dir=args.output,
        api_results=_load_results(args.api_results),
        expected_model_count=args.expected_model_count,
        probe_default_configs=not args.skip_default_config_probes,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if manifest["status"] != VerificationStatus.FAILED.value else 1


if __name__ == "__main__":
    raise SystemExit(main())
