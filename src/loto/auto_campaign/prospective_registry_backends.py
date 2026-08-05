"""Backend facade for Prospective scoring registration."""

from .prospective_registry_mlflow import record_mlflow, redact_uri
from .prospective_registry_postgres import (
    POSTGRES_TABLES,
    finalize_postgres,
    mark_postgres_blocked,
    prepare_postgres,
)

__all__ = [
    "POSTGRES_TABLES",
    "finalize_postgres",
    "mark_postgres_blocked",
    "prepare_postgres",
    "record_mlflow",
    "redact_uri",
]
