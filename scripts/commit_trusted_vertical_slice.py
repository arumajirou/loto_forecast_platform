#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.orchestration.pipeline_downstream_commit import (
    DownstreamCommitError,
    execute_downstream_commit,
)
from loto.orchestration.pipeline_downstream_effects import (
    DefaultDownstreamEffects,
    DownstreamCommitConfig,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Commit a passing staged pipeline run to downstream systems "
            "through an idempotent journaled transaction."
        )
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--secret-env",
        default="LOTO_FORECAST_SEAL_SECRET",
    )
    parser.add_argument("--registry-path", default=None)
    parser.add_argument("--platform-registry-url", default=None)
    parser.add_argument("--artifact-store", default=None)
    parser.add_argument("--events-path", default=None)
    parser.add_argument(
        "--mlflow-tracking-uri",
        default=os.environ.get(
            "MLFLOW_TRACKING_URI",
            "http://127.0.0.1:5050",
        ),
    )
    parser.add_argument(
        "--mlflow-experiment-name",
        default=os.environ.get(
            "MLFLOW_EXPERIMENT_NAME",
            "loto-trusted-vertical-slice",
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.output).expanduser().resolve()
    secret_value = os.environ.get(args.secret_env)
    if secret_value is None:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": f"missing secret env: {args.secret_env}",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    config = DownstreamCommitConfig(
        registry_path=Path(args.registry_path or root / "registry.sqlite3").expanduser().resolve(),
        platform_registry_url=(
            args.platform_registry_url
            or os.environ.get(
                "LOTO_REGISTRY_URL",
                str(root / "platform.sqlite3"),
            )
        ),
        artifact_store_root=Path(args.artifact_store or root / "artifact_store")
        .expanduser()
        .resolve(),
        events_path=Path(args.events_path or root / "events.jsonl").expanduser().resolve(),
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment_name=args.mlflow_experiment_name,
    )
    try:
        receipt = execute_downstream_commit(
            root,
            secret=secret_value.encode("utf-8"),
            effects=DefaultDownstreamEffects(config),
        )
    except DownstreamCommitError as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            receipt.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
