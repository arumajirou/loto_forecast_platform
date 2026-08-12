"""Statistical analysis primitives for leakage-safe lottery research.

These functions are exploratory/development analysis tools. They do not open Holdout or
Prospective data and association results never imply causality.
"""

from loto.analysis.dependence import (
    lag_autocorrelation,
    ljung_box_test,
    pearson_association,
    spearman_association,
)
from loto.analysis.multiple_testing import (
    adjust_hypotheses,
    benjamini_hochberg_adjust,
    holm_adjust,
)
from loto.analysis.trends import linear_trend, mean_shift_scan

__all__ = [
    "adjust_hypotheses",
    "benjamini_hochberg_adjust",
    "holm_adjust",
    "lag_autocorrelation",
    "linear_trend",
    "ljung_box_test",
    "mean_shift_scan",
    "pearson_association",
    "spearman_association",
]
