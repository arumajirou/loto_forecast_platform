from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sqlalchemy import create_engine
import pytest


def load_data() -> pd.DataFrame:
    required = (
        "DB_USER",
        "DB_PASSWORD",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
    )

    missing = [
        name
        for name in required
        if not os.environ.get(name)
    ]

    if missing:
        pytest.skip(
            "Database integration environment is not configured: "
            + ", ".join(missing)
        )

    url = (
        f"postgresql+psycopg://{os.environ['DB_USER']}:"
        f"{os.environ['DB_PASSWORD']}@"
        f"{os.environ['DB_HOST']}:"
        f"{os.environ['DB_PORT']}/"
        f"{os.environ['DB_NAME']}"
    )

    engine = create_engine(url)

    return pd.read_sql(
        """
        SELECT
            unique_id,
            ds,
            y,
            hist_lag_1,
            hist_lag_7,
            hist_diff_1,
            hist_diff_7
        FROM dataset.loto_y_ts_unified
        WHERE loto = 'loto7'
          AND ts_type = 'raw'
        ORDER BY unique_id, ds
        """,
        engine,
    )


def test_diff_features_do_not_reconstruct_target():
    df = load_data()

    for column in (
        "y",
        "hist_lag_1",
        "hist_lag_7",
        "hist_diff_1",
        "hist_diff_7",
    ):
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    reconstructions = {
        "hist_diff_1": (
            df["hist_lag_1"]
            + df["hist_diff_1"]
        ),
        "hist_diff_7": (
            df["hist_lag_7"]
            + df["hist_diff_7"]
        ),
    }

    for name, reconstruction in reconstructions.items():
        valid = pd.DataFrame(
            {
                "y": df["y"],
                "reconstruction": reconstruction,
            }
        ).dropna()

        exact_rate = np.mean(
            np.isclose(
                valid["y"],
                valid["reconstruction"],
                atol=1e-10,
                rtol=0,
            )
        )

        assert exact_rate < 0.99, (
            f"Target leakage detected: "
            f"{name} reconstructs y with "
            f"exact_rate={exact_rate}"
        )
