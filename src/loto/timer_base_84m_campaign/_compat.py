from __future__ import annotations

try:
    from enum import StrEnum as StrEnum
except ImportError:  # pragma: no cover - exercised by the isolated Python 3.10 Timer lane
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]  # noqa: UP042
        """Python 3.10 compatibility shim matching Python 3.11 StrEnum string semantics."""

        def __str__(self) -> str:
            return str(self.value)
