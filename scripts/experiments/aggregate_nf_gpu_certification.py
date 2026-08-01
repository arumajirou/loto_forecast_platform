from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("artifacts/runtime_certification")

SOURCES = {
    "phase1": (ROOT / "neuralforecast_fit_predict_gpu_phase1.json"),
    "phase2": (ROOT / "neuralforecast_fit_predict_gpu_phase2.json"),
    "phase3": (ROOT / "neuralforecast_fit_predict_gpu_phase3.json"),
}

OUTPUT_JSON = ROOT / "neuralforecast_gpu_certification_summary.json"

OUTPUT_MD = ROOT / "neuralforecast_gpu_certification_summary.md"


def load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)

    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    reports = {phase: load_report(path) for phase, path in SOURCES.items()}

    all_results: list[dict[str, Any]] = []

    for phase, report in reports.items():
        for result in report["results"]:
            record = dict(result)
            record["phase"] = phase
            all_results.append(record)

    passed = [result for result in all_results if result["status"] == "PASS"]

    failed = [result for result in all_results if result["status"] != "PASS"]

    total_peak_vram = sum(result["cuda_peak_memory_allocated"] for result in passed)

    max_vram_result = max(
        passed,
        key=lambda result: result["cuda_peak_memory_allocated"],
    )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": ("PASS" if len(passed) == 23 and not failed else "FAIL"),
        "gpu_name": reports["phase1"]["gpu_name"],
        "torch_version": (reports["phase1"]["torch_version"]),
        "torch_cuda_build": (reports["phase1"]["torch_cuda_build"]),
        "models": len(all_results),
        "passed": len(passed),
        "failed": len(failed),
        "phase_counts": {
            phase: {
                "models": report["models"],
                "passed": report["passed"],
                "failed": report["failed"],
            }
            for phase, report in reports.items()
        },
        "maximum_peak_vram_model": (max_vram_result["model"]),
        "maximum_peak_vram_mib": (max_vram_result["cuda_peak_memory_allocated"] / 1024**2),
        "sum_individual_peak_vram_mib": (total_peak_vram / 1024**2),
        "results": all_results,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines = [
        "# NeuralForecast GPU Runtime Certification",
        "",
        f"- Status: **{summary['status']}**",
        f"- GPU: `{summary['gpu_name']}`",
        f"- PyTorch: `{summary['torch_version']}`",
        (f"- CUDA build: `{summary['torch_cuda_build']}`"),
        (f"- Certified models: **{summary['passed']}/{summary['models']}**"),
        (
            "- Highest observed peak VRAM: "
            f"**{summary['maximum_peak_vram_model']} "
            f"{summary['maximum_peak_vram_mib']:.2f} MiB**"
        ),
        "",
        "| Phase | Model | Status | Forward calls | Peak VRAM MiB | CUDA | Finite |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]

    for result in all_results:
        if result["status"] != "PASS":
            lines.append(f"| {result['phase']} | {result['model']} | ERROR | - | - | - | - |")
            continue

        lines.append(
            f"| {result['phase']} "
            f"| {result['model']} "
            f"| PASS "
            f"| {result['forward_calls']} "
            f"| {result['cuda_peak_memory_allocated'] / 1024**2:.2f} "
            f"| {result['cuda_forward_confirmed']} "
            f"| {result['prediction_finite']} |"
        )

    lines.extend(
        [
            "",
            "## Certification criteria",
            "",
            "- Model construction succeeded.",
            "- Training reached the configured maximum steps.",
            "- Prediction completed successfully.",
            "- Forward execution occurred on CUDA.",
            "- CUDA allocation increased during execution.",
            "- Prediction output contained only finite values.",
            "",
            "xLSTM is excluded from this main-environment report because it is isolated in a separate dependency environment.",
            "",
        ]
    )

    OUTPUT_MD.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": summary["status"],
                "models": summary["models"],
                "passed": summary["passed"],
                "failed": summary["failed"],
                "maximum_peak_vram_model": (summary["maximum_peak_vram_model"]),
                "maximum_peak_vram_mib": (summary["maximum_peak_vram_mib"]),
                "json": str(OUTPUT_JSON),
                "markdown": str(OUTPUT_MD),
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    if summary["status"] != "PASS":
        raise SystemExit(1)

    print("NF_GPU_CERTIFICATION_AGGREGATE=PASS")


if __name__ == "__main__":
    main()
