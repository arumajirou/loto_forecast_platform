"""One-sided anytime-valid e-process adoption gate.

A low e-value is not evidence for the reverse hypothesis, so this implementation
never emits a reverse REJECT decision. A separate reverse/equivalence process is
required for such a claim.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np


@dataclass
class PaceConfig:
    alpha: float = 0.05
    lam_cap: float = 1.5
    min_draws: int = 20
    protocol_hash: str = ""


class PaceGate:
    def __init__(self, config: PaceConfig):
        self.config=config; self.log_e=0.0; self.n=0; self._sum=0.0; self._sum_sq=0.0

    def _lambda(self) -> float:
        if self.n < 2: return 0.5
        mu=self._sum/self.n; var=max(self._sum_sq/self.n-mu*mu,1e-6)
        return float(np.clip((mu-0.5)/var,0.0,self.config.lam_cap))

    def update(self, hits_candidate: np.ndarray, hits_champion: np.ndarray) -> dict:
        a=np.asarray(hits_candidate,bool); b=np.asarray(hits_champion,bool)
        if a.shape != b.shape: raise ValueError("paired hit vectors must align")
        diff=float(a.mean()-b.mean()); u=(diff+1)/2; lam=self._lambda(); factor=1+lam*(u-0.5)
        if factor <= 0: raise AssertionError("betting factor must be positive")
        self.log_e += float(np.log(factor)); self.n += 1; self._sum += u; self._sum_sq += u*u
        return self.state() | {"diff":diff,"lambda":lam}

    def decision(self) -> str:
        if self.n < self.config.min_draws: return "COLLECTING"
        if self.log_e >= np.log(1/self.config.alpha): return "ACCEPT"
        return "INCONCLUSIVE"

    def state(self) -> dict:
        e=float(np.exp(self.log_e))
        return {"n":self.n,"e_value":e,"anytime_p":float(min(1,1/e)),"decision":self.decision()}
