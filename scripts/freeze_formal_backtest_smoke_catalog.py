#!/usr/bin/env python
# ruff: noqa: E402,E501
"""Freeze the resolved smoke-stage parameters for every catalog model.

Writes configs/formal_backtest_smoke_catalog.json: a per-model_id snapshot of
`resolve_model_params(spec, "smoke")` plus the spec's own config hash and the
current code fingerprint. This is the source of truth for "did the resolved
smoke config for this model change since the freeze" -- a future formal run
(or a test) can re-resolve and diff against this file rather than relying on
"it worked before" as evidence of correctness.

Regenerate only when an intentional smoke-parameter change is made; a diff
against this file is a signal to review, not to blindly re-freeze.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from run_formal_model_backtest import compute_code_fingerprint, resolve_model_params

from loto.data.lineage import atomic_write_json
from loto.models.catalog import list_model_specs

STAGE = "smoke"


def build_catalog_snapshot() -> dict[str, Any]:
    specs = list_model_specs(available_only=False)
    models: dict[str, Any] = {}
    for spec in specs:
        model_config_hash = hashlib.sha256(
            json.dumps(spec.to_dict(), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        try:
            resolved_params = resolve_model_params(spec, STAGE)
            resolve_error = None
        except Exception as e:
            resolved_params = None
            resolve_error = str(e)

        models[spec.model_id] = {
            "library": spec.library,
            "family": spec.family,
            "class_name": spec.class_name,
            "priority": spec.priority,
            "capabilities": list(spec.capabilities),
            "available": spec.available,
            "model_config_hash": model_config_hash,
            "resolved_smoke_params": resolved_params,
            "resolve_error": resolve_error,
        }

    return {
        "schema_version": 1,
        "stage": STAGE,
        "generated_at": datetime.now(UTC).isoformat(),
        "code_fingerprint": compute_code_fingerprint(),
        "model_count": len(models),
        "models": models,
    }


def main() -> None:
    snapshot = build_catalog_snapshot()
    out_path = ROOT / "configs" / "formal_backtest_smoke_catalog.json"
    atomic_write_json(out_path, snapshot)
    errors = {k: v["resolve_error"] for k, v in snapshot["models"].items() if v["resolve_error"]}
    print(
        f"Wrote {out_path} ({snapshot['model_count']} models, code_fingerprint={snapshot['code_fingerprint']})"
    )
    if errors:
        print(f"WARNING: {len(errors)} models failed to resolve params: {errors}", file=sys.stderr)


if __name__ == "__main__":
    main()
