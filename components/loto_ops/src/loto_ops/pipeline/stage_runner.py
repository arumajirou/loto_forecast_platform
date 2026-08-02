from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class StageResult:
    success: bool
    artifacts: list[Path]
    error_message: str | None = None


class StageRunner:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def run_stage(
        self, stage_name: str, with_exog: bool = False, dry_run: bool = False
    ) -> StageResult:
        logging.info(f"[StageRunner] Running stage: {stage_name}")

        # For dry_run, return success with empty artifacts
        if dry_run:
            return StageResult(success=True, artifacts=[])

        # For actual execution, we would call the appropriate stage function
        # For now, return a mock success result
        return StageResult(success=True, artifacts=[])
