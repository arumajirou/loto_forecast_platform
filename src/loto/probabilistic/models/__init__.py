"""Probabilistic model implementations and legacy reference helpers."""

from loto.probabilistic.models.bocpd_native import (
    BOCPDDirichletCategoricalState,
    fit_bocpd_dirichlet_categorical,
)
from loto.probabilistic.models.copula_native import (
    GaussianCopulaCategoricalState,
    fit_gaussian_copula_categorical,
)
from loto.probabilistic.models.dglm_native import MultinomialDGLMState, fit_multinomial_dglm
from loto.probabilistic.models.reference import ReferencePosterior, fit_reference, posterior_draws
from loto.probabilistic.models.subset_native import (
    ConditionalBernoulliPosterior,
    fit_conditional_bernoulli_map,
)

__all__ = [
    "BOCPDDirichletCategoricalState",
    "ConditionalBernoulliPosterior",
    "GaussianCopulaCategoricalState",
    "MultinomialDGLMState",
    "ReferencePosterior",
    "fit_bocpd_dirichlet_categorical",
    "fit_conditional_bernoulli_map",
    "fit_gaussian_copula_categorical",
    "fit_multinomial_dglm",
    "fit_reference",
    "posterior_draws",
]
