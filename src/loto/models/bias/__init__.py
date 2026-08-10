"""Explicit non-IID challenger models.

These models are research candidates for detecting or representing pre-specified deviations from
the exact IID-null distribution. Their existence is not evidence that such a bias exists.
"""

from loto.models.bias.dynamic_categorical import (
    DirichletCategoricalBiasModel,
    fit_dirichlet_categorical_bias,
)
from loto.models.bias.shrinkage import mix_positional_distributions
from loto.models.bias.weighted_subset import WeightedSubsetBiasModel, fit_weighted_subset_bias

__all__ = [
    "DirichletCategoricalBiasModel",
    "WeightedSubsetBiasModel",
    "fit_dirichlet_categorical_bias",
    "fit_weighted_subset_bias",
    "mix_positional_distributions",
]
