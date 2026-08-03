from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from importlib.util import find_spec
import subprocess
import sys
from typing import Any


@dataclass(frozen=True)
class BackendProbe:
    backend: str
    available: bool
    implemented: bool
    modules: tuple[str, ...]
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "available": self.available,
            "implemented": self.implemented,
            "modules": list(self.modules),
            "detail": self.detail,
        }


class ProbabilisticBackend(ABC):
    backend_id: str
    modules: tuple[str, ...] = ()
    implemented: bool = False

    def probe(self) -> BackendProbe:
        discoverable = all(find_spec(module) is not None for module in self.modules)
        error = ""
        available = discoverable
        if discoverable and self.modules:
            script = ";".join(f"import {module}" for module in self.modules)
            try:
                proc = subprocess.run(
                    [sys.executable, "-c", script],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                available = proc.returncode == 0
                if not available:
                    error = (proc.stderr or proc.stdout)[-800:].strip()
            except Exception as exc:
                available = False
                error = f"{type(exc).__name__}: {exc}"
        detail = "ready" if available and self.implemented else (
            f"package import failed: {error}" if discoverable and not available else (
                "package unavailable" if not available else
                "adapter contract present; native family implementation is opt-in"
            )
        )
        return BackendProbe(
            backend=self.backend_id,
            available=available,
            implemented=self.implemented,
            modules=self.modules,
            detail=detail,
        )

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any: ...
