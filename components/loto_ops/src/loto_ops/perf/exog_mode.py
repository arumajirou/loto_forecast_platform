from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from loto_ops.config import AppSettings
from loto_ops.db.connection import make_engine

HEAVY_EXOG_TABLES = ("chronos", "merlion", "pypots", "timesfm", "uni2ts")


@dataclass(frozen=True)
class ExogModeResult:
    action: str
    moved: list[str]
    status: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "moved": self.moved, "status": self.status}


class ExogModeManager:
    """Move research-heavy exog tables away from daily light-mode discovery."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def status(self) -> dict[str, list[str]]:
        engine = make_engine(self.settings.db)
        try:
            with engine.begin() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT table_schema, table_name
                        FROM information_schema.tables
                        WHERE table_schema IN ('exog', 'exog_full', 'exog_disabled')
                        ORDER BY table_schema, table_name
                        """
                    )
                ).all()
        finally:
            engine.dispose()
        out: dict[str, list[str]] = {"exog": [], "exog_full": [], "exog_disabled": []}
        for schema, table in rows:
            out.setdefault(schema, []).append(table)
        return out

    def set_light(self) -> ExogModeResult:
        moved: list[str] = []
        engine = make_engine(self.settings.db)
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS exog_full"))
                for table_name in HEAVY_EXOG_TABLES:
                    exists = conn.execute(
                        text(
                            """
                            SELECT EXISTS (
                              SELECT 1 FROM information_schema.tables
                              WHERE table_schema='exog' AND table_name=:table_name
                            )
                            """
                        ),
                        {"table_name": table_name},
                    ).scalar()
                    if exists:
                        conn.execute(text(f'ALTER TABLE exog."{table_name}" SET SCHEMA exog_full'))
                        moved.append(f"exog.{table_name} -> exog_full.{table_name}")
        finally:
            engine.dispose()
        return ExogModeResult("set-light", moved, self.status())

    def set_full(self) -> ExogModeResult:
        moved: list[str] = []
        engine = make_engine(self.settings.db)
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS exog"))
                for table_name in HEAVY_EXOG_TABLES:
                    exists = conn.execute(
                        text(
                            """
                            SELECT EXISTS (
                              SELECT 1 FROM information_schema.tables
                              WHERE table_schema='exog_full' AND table_name=:table_name
                            )
                            """
                        ),
                        {"table_name": table_name},
                    ).scalar()
                    if exists:
                        conn.execute(text(f'ALTER TABLE exog_full."{table_name}" SET SCHEMA exog'))
                        moved.append(f"exog_full.{table_name} -> exog.{table_name}")
        finally:
            engine.dispose()
        return ExogModeResult("set-full", moved, self.status())
