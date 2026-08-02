from __future__ import annotations

import pandas as pd

from loto_ops.config import load_settings
from loto_ops.quality.profiling import profile_important_tables
from loto_ops.quality.validators import QualityValidator


def quality_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    settings = load_settings()
    profiles = profile_important_tables(settings)
    issues = QualityValidator().validate_profiles(profiles)
    return pd.DataFrame([p.__dict__ for p in profiles]), pd.DataFrame([i.__dict__ for i in issues])
