"""Bayesian regression, ordinal, spline, GAM, BART and GP models.

The authoritative primary backend and graph assignment is stored in
``configs/probabilistic/native_primary.yaml``. Native execution is selected with
``backend_policy: primary_native``. The reference helpers remain exported only for
backward compatibility and are never used as a silent replacement in native mode.
"""

from loto.probabilistic.models.reference import ReferencePosterior, fit_reference, posterior_draws

__all__ = ["ReferencePosterior", "fit_reference", "posterior_draws"]
