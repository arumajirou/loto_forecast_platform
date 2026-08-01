#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"

MODEL_SPECS: dict[str, dict[str, Any]] = {
    "lag-llama": {
        "repo_ids": [
            "time-series-foundation-models/Lag-Llama",
            "lag-llama/Lag-Llama",
        ],
        "cache_patterns": [
            "models--time-series-foundation-models--Lag-Llama",
            "models--lag-llama--Lag-Llama",
        ],
        "required_any": [
            ["model.safetensors", "pytorch_model.bin", "lag-llama.ckpt"],
        ],
        "license_scope": "VERIFY_FROM_MODEL_CARD",
        "provider_candidates": [
            "scripts/run_lag_llama_provider.py",
            "scripts/run_lag_llama_runtime_provider.py",
        ],
    },
    "moirai-1.0-base": {
        "repo_ids": [
            "Salesforce/moirai-moe-1.0-R-base",
            "Salesforce/moirai-1.0-R-base",
        ],
        "cache_patterns": [
            "models--Salesforce--moirai-moe-1.0-R-base",
            "models--Salesforce--moirai-1.0-R-base",
        ],
        "required_any": [
            ["model.safetensors", "pytorch_model.bin"],
        ],
        "license_scope": "PERSONAL_NONCOMMERCIAL_ONLY",
        "provider_candidates": [
            "scripts/run_moirai_1_0_base_provider.py",
            "scripts/run_moirai_moe_provider.py",
        ],
    },
    "t0-alpha": {
        "repo_ids": [
            "theforecastingcompany/t0-alpha",
        ],
        "cache_patterns": [
            "models--theforecastingcompany--t0-alpha",
        ],
        "required_any": [
            ["model.safetensors", "pytorch_model.bin"],
        ],
        "license_scope": "APACHE_2_0",
        "provider_candidates": [
            "scripts/run_t0_alpha_provider.py",
        ],
    },
    "toto-open-base": {
        "repo_ids": [
            "Datadog/Toto-Open-Base-1.0",
        ],
        "cache_patterns": [
            "models--Datadog--Toto-Open-Base-1.0",
        ],
        "required_any": [
            ["model.safetensors", "pytorch_model.bin"],
        ],
        "license_scope": "APACHE_2_0",
        "provider_candidates": [
            "scripts/run_toto_open_base_provider.py",
        ],
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def load_status() -> dict[str, Any]:
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def ledger_row(
    status: dict[str, Any],
    model_id: str,
) -> dict[str, Any] | None:
    return next(
        (row for row in status["results"] if row.get("model_id") == model_id),
        None,
    )


def find_snapshots(
    patterns: list[str],
) -> list[Path]:
    hf_root = Path(
        os.environ.get(
            "HF_HUB_CACHE",
            "/mnt/e/env/huggingface/hub",
        )
    )

    snapshots: list[Path] = []

    for pattern in patterns:
        root = hf_root / pattern / "snapshots"

        if not root.is_dir():
            continue

        for candidate in root.iterdir():
            if candidate.is_dir():
                snapshots.append(candidate)

    return sorted(
        snapshots,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def inspect_snapshot(
    path: Path,
    required_any: list[list[str]],
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}

    for candidate in sorted(path.iterdir()):
        if not candidate.is_file():
            continue

        files[candidate.name] = {
            "size_bytes": candidate.stat().st_size,
            "sha256": sha256(candidate),
            "resolved_path": str(candidate.resolve()),
        }

    required_groups: list[dict[str, Any]] = []

    for group in required_any:
        existing = [name for name in group if (path / name).is_file()]

        required_groups.append(
            {
                "alternatives": group,
                "existing": existing,
                "satisfied": bool(existing),
            }
        )

    return {
        "snapshot_path": str(path),
        "revision": path.name,
        "files": files,
        "required_groups": required_groups,
        "weights_available": all(group["satisfied"] for group in required_groups),
        "config_available": ((path / "config.json").is_file()),
        "readme_available": ((path / "README.md").is_file()),
    }


def provider_status(
    candidates: list[str],
) -> dict[str, Any]:
    existing = [name for name in candidates if (ROOT / name).is_file()]

    return {
        "candidates": candidates,
        "existing": existing,
        "available": bool(existing),
    }


def classify(
    model_id: str,
    snapshot: dict[str, Any] | None,
    provider: dict[str, Any],
) -> tuple[str, str | None]:
    if snapshot is None:
        if model_id == "t0-alpha":
            return (
                "BLOCKED",
                "GATED_MODEL_ACCESS_OR_SNAPSHOT_MISSING",
            )

        return (
            "BLOCKED",
            "LOCAL_SNAPSHOT_MISSING",
        )

    if not snapshot["config_available"]:
        return (
            "BLOCKED",
            "CONFIG_MISSING",
        )

    if not snapshot["weights_available"]:
        return (
            "BLOCKED",
            "MODEL_WEIGHTS_MISSING",
        )

    if not provider["available"]:
        return (
            "READY_FOR_PROVIDER_IMPLEMENTATION",
            "PROVIDER_SCRIPT_MISSING",
        )

    return (
        "READY_FOR_RUNTIME",
        None,
    )


def main() -> int:
    status = load_status()

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    output_root = Path("/mnt/e/env/logs") / f"remaining-four-tsfm-{timestamp}"

    output_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    results: list[dict[str, Any]] = []

    for model_id, spec in MODEL_SPECS.items():
        model_dir = output_root / model_id
        model_dir.mkdir(parents=True)

        row = ledger_row(status, model_id)
        snapshots = find_snapshots(spec["cache_patterns"])

        snapshot = (
            inspect_snapshot(
                snapshots[0],
                spec["required_any"],
            )
            if snapshots
            else None
        )

        provider = provider_status(spec["provider_candidates"])

        classification, blocked_reason = classify(
            model_id,
            snapshot,
            provider,
        )

        result = {
            "schema_version": 1,
            "model_id": model_id,
            "repo_ids": spec["repo_ids"],
            "ledger_row": row,
            "license_scope": spec["license_scope"],
            "snapshot_candidates": [str(item) for item in snapshots],
            "selected_snapshot": snapshot,
            "provider": provider,
            "classification": classification,
            "blocked_reason": blocked_reason,
            "audited_at": datetime.now(UTC).isoformat(),
        }

        (model_dir / "batch-audit.json").write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        results.append(result)

    summary = {
        "schema_version": 1,
        "output_root": str(output_root),
        "total_models": len(results),
        "ready_for_runtime": sum(item["classification"] == "READY_FOR_RUNTIME" for item in results),
        "ready_for_provider_implementation": sum(
            item["classification"] == "READY_FOR_PROVIDER_IMPLEMENTATION" for item in results
        ),
        "blocked": sum(item["classification"] == "BLOCKED" for item in results),
        "results": results,
    }

    (output_root / "summary.json").write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Remaining Four TSFM Batch Audit",
        "",
        f"- Output: `{output_root}`",
        f"- Total: {summary['total_models']}",
        (f"- Ready for runtime: {summary['ready_for_runtime']}"),
        (f"- Provider implementation required: {summary['ready_for_provider_implementation']}"),
        f"- Blocked: {summary['blocked']}",
        "",
        "| Model | Classification | Blocked reason | Snapshot | Provider |",
        "|---|---|---|---|---|",
    ]

    for item in results:
        snapshot_path = (
            item["selected_snapshot"]["snapshot_path"] if item["selected_snapshot"] else "-"
        )

        provider_names = ", ".join(item["provider"]["existing"]) or "-"

        lines.append(
            "| "
            + item["model_id"]
            + " | "
            + item["classification"]
            + " | "
            + str(item["blocked_reason"] or "-")
            + " | `"
            + snapshot_path
            + "` | "
            + provider_names
            + " |"
        )

    (output_root / "report.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    Path("/tmp/latest-remaining-four-tsfm-dir").write_text(
        str(output_root) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
