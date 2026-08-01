from pathlib import Path

FORBIDDEN = {
    "hist_diff_1",
    "hist_diff_7",
}

FILES = [
    Path(
        "scripts/experiments/"
        "run_ml_exog_ablation.py"
    ),
    Path(
        "scripts/experiments/"
        "run_neuralforecast_exog_ablation.py"
    ),
    Path(
        "scripts/experiments/"
        "run_tft_selected_exog_comparison.py"
    ),
]


def test_experiment_scripts_exclude_leaking_features():
    for path in FILES:
        text = path.read_text(encoding="utf-8")

        found = sorted(
            feature
            for feature in FORBIDDEN
            if feature in text
        )

        assert not found, (
            f"{path} contains leaking features: "
            f"{found}"
        )
