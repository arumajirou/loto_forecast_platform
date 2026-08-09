from __future__ import annotations

from pathlib import Path


def main() -> None:
    path = Path("src/loto/models/autogluon_shared.py")
    text = path.read_text(encoding="utf-8")

    old_values = '''    if isinstance(raw, str):
        values = (raw,)
    else:
        values = tuple(str(value) for value in raw)
'''
    new_values = '''    values: tuple[str, ...]
    if isinstance(raw, str):
        values = (raw,)
    else:
        values = tuple(str(value) for value in raw)
'''
    if text.count(old_values) != 1:
        raise SystemExit("unexpected _model_ids values block")
    text = text.replace(old_values, new_values, 1)

    start_marker = "    request = ProviderRequestV2(\n"
    end_marker = '    return request.model_dump(mode="json")\n'
    start = text.find(start_marker)
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise SystemExit("request constructor markers not found")
    end += len(end_marker)

    replacement = '''    request = ProviderRequestV2.model_validate(
        {
            "run_id": _worker_run_id(identity_payload),
            "operation": operation,
            "execution_mode": mode,
            "model_ids": model_ids,
            "artifact_dir": str(Path(artifact_dir).resolve()),
            "history": tuple(records),
            "geometry": {
                "game_id": profile.game_id,
                "position_columns": columns,
                "candidate_min": profile.candidate_min,
                "candidate_max": profile.candidate_max,
                "selection_count": profile.position_count,
                "horizon": horizon,
                "allow_duplicates": profile.allow_duplicates,
                "sort_policy": profile.sort_policy,
            },
            "predictor": {
                "target": "target",
                "prediction_length": horizon,
                "freq": "D",
                "eval_metric": str(params.get("eval_metric", "MAE")),
                "quantile_levels": quantile_levels,
                "cache_predictions": bool(params.get("cache_predictions", True)),
            },
            "fit": {
                "time_limit_seconds": int(
                    params.get("time_limit_seconds", params.get("time_limit", 120))
                ),
                "presets": params.get("presets", "fast_training"),
                "hyperparameters": params.get("hyperparameters"),
                "hyperparameter_tune_kwargs": params.get("hyperparameter_tune_kwargs"),
                "num_val_windows": params.get("num_val_windows", 1),
                "refit_every_n_windows": params.get("refit_every_n_windows", 1),
                "refit_full": bool(params.get("refit_full", False)),
                "enable_ensemble": bool(params.get("enable_ensemble", True)),
                "skip_model_selection": bool(params.get("skip_model_selection", False)),
            },
            "seed": seed,
            "requested_device": device,
        }
    )
    return request.model_dump(mode="json")
'''
    text = text[:start] + replacement + text[end:]
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
