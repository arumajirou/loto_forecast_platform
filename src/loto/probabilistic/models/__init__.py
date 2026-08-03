"""Probabilistic model implementations and legacy reference helpers."""

from loto.probabilistic.models.dglm_native import MultinomialDGLMState, fit_multinomial_dglm
from loto.probabilistic.models.reference import ReferencePosterior, fit_reference, posterior_draws
from loto.probabilistic.models.subset_native import (
    ConditionalBernoulliPosterior,
    fit_conditional_bernoulli_map,
)

__all__ = [
    "ConditionalBernoulliPosterior",
    "MultinomialDGLMState",
    "ReferencePosterior",
    "fit_conditional_bernoulli_map",
    "fit_multinomial_dglm",
    "fit_reference",
    "posterior_draws",
]
