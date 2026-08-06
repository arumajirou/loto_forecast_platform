from __future__ import annotations

from typing import Any

from loto.probabilistic.kdpp_target_contracts import TargetExecutionPlan


def _runtime_commands(
    plan: TargetExecutionPlan,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    kdpp = context["kdpp"]
    prefix = context["kdpp_prefix"]
    runner = str(kdpp / "scripts/run_kdpp_fixed_k_target_host.py")
    controller = str(kdpp / "scripts/manage_kdpp_fixed_k_target_execution.py")
    runtime = str(context["runtime"])
    return [
        {
            "stage": "runtime-prepare",
            "cwd": str(kdpp),
            "argv": [
                *prefix,
                runner,
                "prepare",
                "--history-bundle",
                str(context["bundle"]),
                "--history-approval",
                str(context["kdpp_approved"]),
                "--certifier",
                str(kdpp / "scripts/certify_kdpp_fixed_k_runtime.py"),
                "--workspace",
                runtime,
                "--run-id",
                plan.run_id,
                "--source-revision",
                plan.source_revision,
                "--config-sha256",
                plan.config_sha256,
                "--prediction-length",
                str(plan.prediction_length),
                "--seed",
                str(plan.seed),
                "--samples-per-horizon",
                str(plan.samples_per_horizon),
                "--rbf-gamma",
                str(plan.rbf_gamma),
                "--quality-pseudocount",
                str(plan.quality_pseudocount),
                "--psd-tolerance",
                str(plan.psd_tolerance),
            ],
        },
        {
            "stage": "runtime-run",
            "cwd": str(kdpp),
            "argv": [*prefix, runner, "run", "--workspace", runtime],
        },
        {
            "stage": "runtime-verify",
            "cwd": str(kdpp),
            "argv": [*prefix, runner, "verify", "--workspace", runtime],
        },
        {
            "stage": "record-cpu-formal",
            "cwd": str(kdpp),
            "argv": [
                *prefix,
                controller,
                "record-runtime",
                "--workspace",
                str(context["workspace"]),
                "--runtime-workspace",
                runtime,
            ],
        },
    ]
