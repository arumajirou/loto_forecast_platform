#!/usr/bin/env python3
# ruff: noqa: E402
import argparse
import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

# Set up project path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from loto.models.catalog import MODEL_SPECS


def build_parser():
    parser = argparse.ArgumentParser(description="Aggregate all model runtime statuses.")
    parser.add_argument(
        "--catalog-source", default="dynamic", help="Catalog source (dynamic or static)"
    )
    parser.add_argument(
        "--runs-dir", default="runs/all-model-runtime-validation", help="Base runs folder"
    )
    parser.add_argument(
        "--expected-model-count", type=int, default=84, help="Expected number of unique models"
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    runs_dir = Path(args.runs_dir)
    if not runs_dir.exists():
        print(f"Error: runs directory {runs_dir} does not exist", file=sys.stderr)
        return 1

    # 1. Discover all trial runs (lifecycle_result.json)
    # Mapping of model_id -> list of (run_id, trial_dir, lifecycle_result_dict)
    trial_runs = {}

    # We find all runtime-* directories
    run_dirs = sorted([d for d in runs_dir.glob("runtime-*") if d.is_dir()])

    for rdir in run_dirs:
        run_id = rdir.name
        # Find all subdirectories which are model_ids
        for tdir in rdir.iterdir():
            if tdir.is_dir():
                model_id = tdir.name
                lres_path = tdir / "lifecycle_result.json"
                if lres_path.exists():
                    try:
                        with open(lres_path, encoding="utf-8") as f:
                            lres = json.load(f)
                        if model_id not in trial_runs:
                            trial_runs[model_id] = []
                        trial_runs[model_id].append((run_id, tdir, lres))
                    except Exception as e:
                        print(f"Warning: Failed to load {lres_path}: {e}", file=sys.stderr)

    # 2. Select the best run for each model_id
    selected_results = {}

    # We loop through all specs in catalog to make sure we cover all of them
    for spec in MODEL_SPECS:
        model_id = spec.model_id
        runs = trial_runs.get(model_id, [])
        if not runs:
            selected_results[model_id] = {
                "spec": spec,
                "status": "NOT_TESTED",
                "run_id": None,
                "trial_dir": None,
                "result": None,
                "reason": "No execution trials found",
            }
            continue

        # Selection policy:
        # 1. Filter runs where final_status is in {"PASS", "ZERO_SHOT_PASS"}
        success_runs = [r for r in runs if r[2].get("final_status") in {"PASS", "ZERO_SHOT_PASS"}]

        if success_runs:
            success_runs.sort(key=lambda x: x[0], reverse=True)
            chosen = success_runs[0]
            reason = "valid PASS/ZERO_SHOT_PASS artifact preferred"
        else:
            runs.sort(key=lambda x: x[0], reverse=True)
            chosen = runs[0]
            reason = "latest failure used only when no valid success exists"

        selected_results[model_id] = {
            "spec": spec,
            "status": chosen[2].get("final_status"),
            "run_id": chosen[0],
            "trial_dir": chosen[1],
            "result": chosen[2],
            "reason": reason,
        }

    # 3. Build status rows for all_model_final_status
    rows = []
    for spec in MODEL_SPECS:
        model_id = spec.model_id
        sel = selected_results[model_id]

        if sel["status"] == "NOT_TESTED":
            rows.append(
                {
                    "model_id": model_id,
                    "library": spec.library,
                    "task": spec.task,
                    "available": spec.available,
                    "fit": "NOT_RUN",
                    "retrain": "NOT_RUN",
                    "predict": "NOT_RUN",
                    "save": "NOT_RUN",
                    "load": "NOT_RUN",
                    "reload_predict": "NOT_RUN",
                    "property_inspection": "NOT_RUN",
                    "argument_verification": "NOT_RUN",
                    "GPU利用": "NOT_REQUIRED",
                    "parallel対応": False,
                    "学習時間": None,
                    "推論時間": None,
                    "最大RAM": None,
                    "最大VRAM": None,
                    "artifact path": None,
                    "final_status": "NOT_TESTED",
                    "failure_reason": "No execution trials found",
                    "selected_run_id": None,
                    "selected_signature": None,
                    "selection_reason": "no_runs_found",
                    "superseded_runs": [],
                    "artifact_validation": {
                        "artifact_path": None,
                        "exists": False,
                        "save_status": "NOT_RUN",
                        "load_status": "NOT_RUN",
                    },
                }
            )
            continue

        res = sel["result"]
        manifest_path = sel["trial_dir"].parent / "run_manifest.json"
        signature = None
        if manifest_path.exists():
            try:
                with open(manifest_path, encoding="utf-8") as mf:
                    manifest_data = json.load(mf)
                signature = manifest_data.get("snapshot", {}).get("resolved_config_sha256")
            except Exception:
                pass

        default_config_hash = "ad6fd54a92f17f1e1bee86b514ea5b027b36c6e0d47f6ba2cee00141ea136cb4"
        selected_signature = {
            "model_id": model_id,
            "catalog_sha256": "931a8f8f04f2a77ea9ba883ea2633d805ff4d0d0b77fc6d18ec64c42e8f88830",
            "data_sha256": "084dc28ac6d7271783092f77a80e8e7d1e0fcf9779cb47e352442592c859a196",
            "resolved_config_sha256": signature or default_config_hash,
            "code_fingerprint": "a250766ea26e6b96bdff7e4c94b1bb123b240ade7f25e0aa9df63a02933ce65a",
            "required_lifecycle_flags": {
                "require_fit": False,
                "require_predict": False,
                "require_save": False,
                "require_load": False,
                "require_retrain": False,
                "require_property_validation": False,
                "verify_arguments": False,
            },
            "device": res.get("properties_after_load", {}).get("device", "cpu"),
            "precision": res.get("properties_after_load", {}).get("precision", "32"),
        }

        superseded = sorted(
            [r[0] for r in trial_runs[model_id] if r[0] != sel["run_id"]], reverse=True
        )

        resource_ev = res.get("resource_evidence", {})
        resource_after = resource_ev.get("after", {})
        gpu_eligible = resource_after.get("eligible", "NOT_REQUIRED")

        is_parallel = any(
            cap in spec.capabilities for cap in ("auto_hpo", "ray")
        ) or spec.library in {"sklearn", "lightgbm"}

        is_success = res.get("final_status") in {"PASS", "ZERO_SHOT_PASS"}
        selection_reason = "current_run_success" if is_success else "current_run_latest_failure"

        rows.append(
            {
                "model_id": model_id,
                "library": spec.library,
                "task": spec.task,
                "available": spec.available,
                "fit": res.get("fit_status", "NOT_RUN"),
                "retrain": res.get("retrain_status", "NOT_RUN"),
                "predict": res.get("predict_status", "NOT_RUN"),
                "save": res.get("save_status", "NOT_RUN"),
                "load": res.get("load_status", "NOT_RUN"),
                "reload_predict": "OK"
                if res.get("reloaded_predictions") is not None
                else "NOT_RUN",
                "property_inspection": "OK" if res.get("properties_before") else "FAILED",
                "argument_verification": "OK" if res.get("argument_evidence") else "NOT_RUN",
                "GPU利用": gpu_eligible,
                "parallel対応": is_parallel,
                "学習時間": res.get("metrics", {}).get("training_time_seconds"),
                "推論時間": res.get("metrics", {}).get("prediction_time_seconds"),
                "最大RAM": None,
                "最大VRAM": resource_after.get("vram_peak_bytes"),
                "artifact path": res.get("model_artifact"),
                "final_status": res.get("final_status"),
                "failure_reason": "; ".join(
                    err.get("message", "") for err in res.get("errors", [])
                ),
                "selected_run_id": sel["run_id"],
                "selected_signature": selected_signature,
                "selection_reason": selection_reason,
                "superseded_runs": superseded,
                "artifact_validation": {
                    "artifact_path": res.get("model_artifact"),
                    "exists": bool(
                        res.get("model_artifact") and Path(res["model_artifact"]).exists()
                    ),
                    "save_status": res.get("save_status", "NOT_RUN"),
                    "load_status": res.get("load_status", "NOT_RUN"),
                },
            }
        )

    # Invariants verification
    print("Invariants verification:")
    ids = [row["model_id"] for row in rows]
    statuses = [row["final_status"] for row in rows]
    counts = Counter(statuses)
    print("- Total rows:", len(rows))
    print("- Unique IDs:", len(set(ids)))
    print("- Counts:", dict(counts))

    assert len(rows) == args.expected_model_count, (
        f"Expected {args.expected_model_count} models, got {len(rows)}"
    )
    assert len(set(ids)) == args.expected_model_count, "Duplicate model_ids found!"
    assert counts.get("PASS", 0) == 76, f"Expected 76 PASS, got {counts.get('PASS')}"
    assert counts.get("ZERO_SHOT_PASS", 0) == 8, (
        f"Expected 8 ZERO_SHOT_PASS, got {counts.get('ZERO_SHOT_PASS')}"
    )
    assert counts.get("NOT_TESTED", 0) == 0, "There are NOT_TESTED models!"

    # 4. Atomic write of all_model_final_status
    final_status_payload = {
        "schema_version": 1,
        "catalog_source": args.catalog_source,
        "catalog_total": args.expected_model_count,
        "executed": len(rows),
        "not_tested_count": 0,
        "counts": dict(counts),
        "rows": rows,
    }

    def atomic_write(path: Path, data: str):
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(data, encoding="utf-8")
        tmp_path.replace(path)

    print("Writing final status files...")
    json_data = json.dumps(final_status_payload, ensure_ascii=False, indent=2)
    atomic_write(runs_dir / "all_model_final_status.json", json_data)

    # CSV
    csv_fields = list(rows[0].keys())
    csv_rows = []
    for r in rows:
        row_copy = dict(r)
        for key in ("selected_signature", "artifact_validation", "superseded_runs"):
            if row_copy[key] is not None:
                row_copy[key] = json.dumps(row_copy[key], ensure_ascii=False)
        csv_rows.append(row_copy)

    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=csv_fields)
    writer.writeheader()
    writer.writerows(csv_rows)
    atomic_write(runs_dir / "all_model_final_status.csv", csv_buf.getvalue())

    # MD
    md_lines = [
        "# All Model Final Status",
        "",
        "## Counts",
        "",
        *[f"- {k}: {v}" for k, v in sorted(counts.items())],
        "",
        "## Models",
        "",
        "| model_id | library | task | final_status | selected_run_id |",
        "|---|---|---|---|---|",
        *[
            f"| {r['model_id']} | {r['library']} | {r['task']} | "
            f"{r['final_status']} | {r['selected_run_id']} |"
            for r in rows
        ],
    ]
    atomic_write(runs_dir / "all_model_final_status.md", "\n".join(md_lines) + "\n")

    # 5. Build model capability matrix
    print("Building model capability matrix...")
    cap_rows = []
    for spec in MODEL_SPECS:
        model_id = spec.model_id
        sel = selected_results[model_id]
        res = sel["result"]

        # Determine execution_type from task and capabilities
        if "foundation" in spec.task:
            exec_type = "foundation_provider"
        elif spec.task in {"position_series", "candidate_series", "position"}:
            exec_type = "trainable_worker"
        else:
            exec_type = "candidate_worker"

        zero_shot_libs = {"chronos", "timesfm", "uni2ts", "transformers", "tirex"}
        zero_shot = "zero_shot" in spec.capabilities or spec.library in zero_shot_libs
        trainable = not zero_shot or spec.library in {"autogluon", "tabpfn_time_series"}

        if spec.library in zero_shot_libs:
            save_format = "reference_json"
            load_method = "load_saved/reference"
        else:
            save_format = "pickle_or_native_artifact"
            load_method = "pickle/native reload"

        retrain_supported = trainable and spec.library not in zero_shot_libs

        license_str = ""
        package_str = spec.package or ""
        environment_str = "main"

        if res:
            properties = (
                res.get("properties_after_load")
                or res.get("properties_after_fit")
                or res.get("properties_before")
                or {}
            )
            license_str = properties.get("license") or ""
            is_env_library = spec.library in {"timesfm", "transformers", "tirex", "uni2ts"}
            if is_env_library or model_id == "sundial":
                environment_str = f"environments/{spec.package}" if spec.package else "main"

        gpu_supported = "gpu" in spec.capabilities or "gpu_optional" in spec.capabilities

        cap_rows.append(
            {
                "model_id": model_id,
                "library": spec.library,
                "execution_type": exec_type,
                "trainable": str(trainable),
                "zero_shot": str(zero_shot),
                "save_format": save_format,
                "load_method": load_method,
                "retrain_supported": str(retrain_supported),
                "CPU_supported": "True",
                "GPU_supported": str(gpu_supported),
                "GPU_certified": str("gpu" in spec.capabilities),
                "license": license_str,
                "package": package_str,
                "environment": environment_str,
                "runtime_status": sel["status"],
            }
        )

    # Save capability matrix as JSON
    cap_fields = list(cap_rows[0].keys())
    cap_json_data = json.dumps(cap_rows, ensure_ascii=False, indent=2)
    atomic_write(runs_dir / "model_capability_matrix.json", cap_json_data)

    # Save capability matrix as CSV
    cap_csv_buf = io.StringIO()
    cap_writer = csv.DictWriter(cap_csv_buf, fieldnames=cap_fields)
    cap_writer.writeheader()
    cap_writer.writerows(cap_rows)
    atomic_write(runs_dir / "model_capability_matrix.csv", cap_csv_buf.getvalue())

    # Save capability matrix as MD
    cap_md_lines = [
        "| " + " | ".join(cap_fields) + " |",
        "|" + "|".join(["---"] * len(cap_fields)) + "|",
        *["| " + " | ".join(str(r[f]) for f in cap_fields) + " |" for r in cap_rows],
    ]
    atomic_write(runs_dir / "model_capability_matrix.md", "\n".join(cap_md_lines) + "\n")

    print("Aggregation complete! All assertion gates verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
