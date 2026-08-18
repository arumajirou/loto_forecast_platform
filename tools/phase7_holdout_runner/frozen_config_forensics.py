from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEEDS = (1, 42, 1729, 20260730)
EXPECTED_FREEZE_SHA256 = "deae004023fd1367d4bd30a6edad8b4ac687b939413c4b4ce641187664fa316c"
NUMERIC_KEY_RE = re.compile(r"-?(?:0|[1-9][0-9]*)$")


class PairDict(dict):
    """JSON object retaining duplicate-key evidence."""

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        super().__init__()
        self.duplicate_keys: list[str] = []
        seen: set[str] = set()
        for key, value in pairs:
            if key in seen:
                self.duplicate_keys.append(key)
            seen.add(key)
            self[key] = value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_phase6c_root() -> Path:
    return (
        Path.home()
        / "Downloads"
        / "automlforecast-phase6c-ensemble-freeze-20260818-101021"
    )


def default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Downloads" / f"phase7-canonical-key-forensics-v3-{stamp}"


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def preview(value: Any, limit: int = 1200) -> str:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        text = repr(value)
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def json_path(parent: str, key: str) -> str:
    return parent + "[" + json.dumps(key, ensure_ascii=False) + "]"


def load_json_pairs(path: Path) -> PairDict:
    result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=PairDict)
    if not isinstance(result, PairDict):
        raise RuntimeError(f"expected JSON object: {path}")
    return result


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def scan_phase6c(
    *,
    phase6c_root: Path,
    output_dir: Path,
    expected_freeze_sha256: str = EXPECTED_FREEZE_SHA256,
) -> dict[str, Any]:
    frozen_dir = phase6c_root / "artifacts" / "frozen_component_evidence"
    freeze_path = phase6c_root / "artifacts" / "CANDIDATE_FREEZE.json"

    if not freeze_path.is_file():
        raise RuntimeError(f"candidate freeze missing: {freeze_path}")
    if not frozen_dir.is_dir():
        raise RuntimeError(f"frozen evidence directory missing: {frozen_dir}")

    freeze_sha = sha256_file(freeze_path)
    if freeze_sha != expected_freeze_sha256:
        raise RuntimeError(
            "Candidate Freeze SHA mismatch: "
            f"expected={expected_freeze_sha256} actual={freeze_sha}"
        )

    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("selected_candidate") != "catboost_seed_mean":
        raise RuntimeError("unexpected frozen candidate")

    components: dict[int, dict[str, Any]] = {}
    for component in freeze.get("components", []):
        if isinstance(component, dict) and component.get("seed") is not None:
            components[int(component["seed"])] = component

    if sorted(components) != sorted(SEEDS):
        raise RuntimeError(f"frozen seed set mismatch: {sorted(components)}")

    source_files: list[Path] = [freeze_path]
    config_paths: dict[int, Path] = {}
    trial_paths: dict[int, Path] = {}
    for seed in SEEDS:
        config = frozen_dir / f"AutoCatboost__seed{seed}__BEST_EFFECTIVE_CONFIG.json"
        trials = frozen_dir / f"AutoCatboost__seed{seed}__optuna_trials.csv"
        if not config.is_file():
            raise RuntimeError(f"frozen config missing seed={seed}: {config}")
        if not trials.is_file():
            raise RuntimeError(f"frozen trials missing seed={seed}: {trials}")
        config_paths[seed] = config
        trial_paths[seed] = trials
        source_files.extend((config, trials))

    before = {str(path): sha256_file(path) for path in source_files}

    numeric_rows: list[dict[str, Any]] = []
    duplicate_rows: list[dict[str, Any]] = []
    field_rows: list[dict[str, Any]] = []
    trial_rows: list[dict[str, Any]] = []
    component_reports: list[dict[str, Any]] = []

    for seed in SEEDS:
        config_path = config_paths[seed]
        trials_path = trial_paths[seed]
        payload = load_json_pairs(config_path)

        if isinstance(payload.get("config"), dict):
            effective = payload["config"]
            root_path = '$["config"]'
        else:
            effective = payload
            root_path = "$"

        numeric_start = len(numeric_rows)
        duplicate_start = len(duplicate_rows)

        def walk(value: Any, path: str) -> None:
            if isinstance(value, PairDict):
                for duplicate in value.duplicate_keys:
                    duplicate_rows.append(
                        {
                            "seed": seed,
                            "mapping_path": path,
                            "duplicate_key": duplicate,
                        }
                    )
                for key, item in value.items():
                    if NUMERIC_KEY_RE.fullmatch(key):
                        numeric_rows.append(
                            {
                                "seed": seed,
                                "mapping_path": path,
                                "key": key,
                                "value_type": value_type(item),
                                "value_preview": preview(item),
                            }
                        )
                    walk(item, json_path(path, key))
                return

            if isinstance(value, dict):
                for key, item in value.items():
                    key_text = str(key)
                    if NUMERIC_KEY_RE.fullmatch(key_text):
                        numeric_rows.append(
                            {
                                "seed": seed,
                                "mapping_path": path,
                                "key": key_text,
                                "value_type": value_type(item),
                                "value_preview": preview(item),
                            }
                        )
                    walk(item, json_path(path, key_text))
                return

            if isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, f"{path}[{index}]")

        walk(effective, root_path)

        mlf_init = (
            effective.get("mlf_init_params", {}) if isinstance(effective, dict) else {}
        )
        for field in (
            "lags",
            "lag_transforms",
            "date_features",
            "target_transforms",
            "num_threads",
        ):
            value = mlf_init.get(field) if isinstance(mlf_init, dict) else None
            field_rows.append(
                {
                    "seed": seed,
                    "field": field,
                    "value_type": value_type(value),
                    "value": preview(value, 4000),
                }
            )

        component = components[seed]
        best_trial = component.get("best_trial", component.get("best_trial_number"))

        with trials_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            headers = list(reader.fieldnames or [])

        trial_id_column = next(
            (name for name in ("trial", "number", "trial_number") if name in headers),
            None,
        )
        matched: dict[str, str] | None = None
        if best_trial is not None and trial_id_column is not None:
            for row in rows:
                try:
                    current = int(float(row[trial_id_column]))
                except Exception:
                    continue
                if current == int(best_trial):
                    matched = row
                    break

        index_fields = {
            header: (None if matched is None else matched.get(header))
            for header in headers
            if (
                "target_transforms_idx" in header
                or "lags_idx" in header
                or "lag_transforms_idx" in header
            )
        }

        trial_rows.append(
            {
                "seed": seed,
                "best_trial": best_trial,
                "trial_row_found": matched is not None,
                "index_fields": json.dumps(
                    index_fields,
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            }
        )
        component_reports.append(
            {
                "seed": seed,
                "config_file": config_path.name,
                "config_sha256": sha256_file(config_path),
                "trials_file": trials_path.name,
                "trials_sha256": sha256_file(trials_path),
                "best_trial": best_trial,
                "numeric_key_count": len(numeric_rows) - numeric_start,
                "duplicate_key_count": len(duplicate_rows) - duplicate_start,
                "trial_index_fields": index_fields,
            }
        )

    after = {str(path): sha256_file(path) for path in source_files}
    if before != after:
        raise RuntimeError("source evidence changed during forensic scan")

    output_dir.mkdir(parents=True, exist_ok=False)

    write_csv(
        output_dir / "NUMERIC_KEY_PATHS.csv",
        numeric_rows,
        ["seed", "mapping_path", "key", "value_type", "value_preview"],
    )
    write_csv(
        output_dir / "DUPLICATE_JSON_KEYS.csv",
        duplicate_rows,
        ["seed", "mapping_path", "duplicate_key"],
    )
    write_csv(
        output_dir / "CONFIG_FIELD_SUMMARY.csv",
        field_rows,
        ["seed", "field", "value_type", "value"],
    )
    write_csv(
        output_dir / "TRIAL_INDEX_EVIDENCE.csv",
        trial_rows,
        ["seed", "best_trial", "trial_row_found", "index_fields"],
    )
    write_csv(
        output_dir / "INPUT_SHA256_BEFORE.csv",
        [{"path": path, "sha256": digest} for path, digest in sorted(before.items())],
        ["path", "sha256"],
    )
    write_csv(
        output_dir / "INPUT_SHA256_AFTER.csv",
        [{"path": path, "sha256": digest} for path, digest in sorted(after.items())],
        ["path", "sha256"],
    )

    seed1 = next(item for item in component_reports if item["seed"] == 1)
    report = {
        "schema_version": "phase7-canonical-key-forensics/v3",
        "status": "PASS",
        "read_only": True,
        "source": "phase6c_frozen_component_evidence",
        "candidate_freeze_sha256": freeze_sha,
        "replay_executed": False,
        "holdout_executed": False,
        "actuals_accessed": 0,
        "numeric_key_count_total": len(numeric_rows),
        "seed1_numeric_key_count": seed1["numeric_key_count"],
        "duplicate_json_key_count_total": len(duplicate_rows),
        "source_immutability": "PASS",
        "components": component_reports,
    }

    report_path = output_dir / "FROZEN_CONFIG_FORENSICS.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    checksum_path = output_dir / "SHA256SUMS"
    output_files = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path != checksum_path
    )
    checksum_path.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in output_files),
        encoding="ascii",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Phase 6C frozen-config forensic scan. "
            "Does not run replay, access Holdout actuals, or read canonical data."
        )
    )
    parser.add_argument("--phase6c-root", type=Path, default=default_phase6c_root())
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--expected-freeze-sha256",
        default=EXPECTED_FREEZE_SHA256,
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = args.output_dir or default_output_dir()
    report = scan_phase6c(
        phase6c_root=args.phase6c_root,
        output_dir=output_dir,
        expected_freeze_sha256=args.expected_freeze_sha256,
    )

    print(f"FORENSIC_ROOT={output_dir}")
    print(f"NUMERIC_KEY_COUNT_TOTAL={report['numeric_key_count_total']}")
    print(f"SEED1_NUMERIC_KEY_COUNT={report['seed1_numeric_key_count']}")
    print(
        "DUPLICATE_JSON_KEY_COUNT_TOTAL="
        f"{report['duplicate_json_key_count_total']}"
    )
    for component in report["components"]:
        print(
            "SEED="
            f"{component['seed']} "
            "NUMERIC_KEYS="
            f"{component['numeric_key_count']} "
            "BEST_TRIAL="
            f"{component['best_trial']} "
            "INDEX_FIELDS="
            + json.dumps(component["trial_index_fields"], sort_keys=True)
        )
    print("SOURCE_IMMUTABILITY=PASS")
    print("SHA256SUMS_CREATED=YES")
    print("FORENSIC_SCAN=PASS")
    print("REPLAY_EXECUTED=NO")
    print("HOLDOUT_EXECUTED=NO")
    print("ACTUALS_ACCESSED=0")
    print("SAFE_TO_PATCH_SERIALIZER=NO")
    print("SAFE_TO_RUN_REPLAY_ONLY=NO")
    print("SAFE_TO_EXECUTE_HOLDOUT=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
