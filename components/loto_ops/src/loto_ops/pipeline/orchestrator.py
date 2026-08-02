"""Orchestrator for running Loto Ops pipeline stages in order.

Implements the run_all method that executes pipeline stages sequentially,
handling errors, writing incidents, and managing retry logic with exponential backoff.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loto_ops.pipeline.retry_manager import RetryManager

from loto_ops.pipeline.manifest import PipelineManifest

logger = logging.getLogger("loto_ops.pipeline.orchestrator")


def _suggest_error(error_message: str) -> str:
    """Generate a suggestion based on error content."""
    msg_lower = error_message.lower()
    if "connection" in msg_lower or "refused" in msg_lower:
        return "ネットワーク接続の問題です。Gateway が実行中か確認してください。"
    if "permission" in msg_lower or "access" in msg_lower:
        return "ファイルの権限が不足しています。実行ユーザーのアクセス権を確認してください。"
    if "not found" in msg_lower:
        return "指定されたファイルまたはディレクトリが存在しません。パスを確認してください。"
    if "module" in msg_lower or "import" in msg_lower:
        return "必要な Python モジュールがインストールされていません。pip install で依存関係を確認してください。"
    return "エラー内容を確認し、根本原因を特定してください。"


def _classify_error(error: Exception) -> str:
    """Classify an exception into error categories.

    Returns:
        Single character error class: M, H, T, R, V, E, U
    """
    if isinstance(error, (ConnectionError, OSError, FileNotFoundError, PermissionError)):
        return "E"  # Environment
    elif isinstance(error, (ModuleNotFoundError, ImportError, AttributeError)):
        return "T"  # Tooling/Parser
    elif isinstance(error, AssertionError):
        return "V"  # Validator/Test
    elif isinstance(error, (ValueError, TypeError)):
        return "M"  # Model
    else:
        return "U"  # Unknown


def _write_incident(
    run_id: str, stage: str, error_message: str, error_class: str = "U"
) -> Path | None:
    """Write an incident JSON file for the failed run.

    Creates a JSON file with run_id, stage, error_message, and error_class.
    Returns the path to the created incident file, or None on failure.
    """
    try:
        incidents_dir = Path("/mnt/e/env/ts/shared-ai-memory/incidents")
        incidents_dir.mkdir(parents=True, exist_ok=True)

        incident_path = incidents_dir / f"incident_{run_id}.json"

        import json

        incident_data = {
            "run_id": run_id,
            "stage": stage,
            "error_message": error_message,
            "error_class": error_class,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        with open(incident_path, "w") as f:
            json.dump(incident_data, f, indent=2)

        logger.info(f"Incident written to: {incident_path}")
        return incident_path
    except Exception as e:
        logger.error(f"Failed to write incident file: {e}")
        return None


def _find_latest_run_id(runs_dir: Path) -> str | None:
    """Find the latest run_id from run_manifest.json files.

    Scans runs/ directory for the most recently modified run_manifest.json
    and returns the run_id portion of the directory name.

    Args:
        runs_dir: Path to the runs directory

    Returns:
        The run_id string if found, None if no manifests exist
    """
    if not runs_dir.exists():
        return None

    latest_run_id = None
    latest_mtime = -1

    for manifest_path in runs_dir.glob("*/run_manifest.json"):
        try:
            import json

            with open(manifest_path) as f:
                json.load(f)

            mtime = manifest_path.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_run_id = manifest_path.parent.name
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read manifest at {manifest_path}: {e}")

    return latest_run_id


def run_all(
    stages: list[tuple[str, Callable[..., Any]]],
    *,
    retry_manager: RetryManager | None = None,
) -> dict[str, Any]:
    """Execute all pipeline stages in order, with error handling and retry logic.

    Args:
        stages: List of (stage_name, stage_function) tuples
        retry_manager: Optional RetryManager instance for retry control

    Returns:
        Dictionary with pipeline results
    """
    from loto_ops.pipeline.manifest import PipelineManifest

    run_manifest = PipelineManifest(run_id="unknown")

    for stage_name, stage_func in stages:
        logger.info(f"Starting stage: {stage_name}")
        attempt = 0

        while True:
            try:
                stage_func()
                run_manifest.last_successful_stage = stage_name
                logger.info(f"Stage {stage_name} completed successfully")

                # Write manifest after successful stage
                try:
                    import json

                    from loto_ops.config import load_settings

                    runs_dir = load_settings().paths.runs_dir
                    runs_dir.mkdir(exist_ok=True)

                    # Generate run_id if not set
                    if run_manifest.run_id == "unknown":
                        import datetime

                        now = datetime.datetime.now()
                        run_id = f"loto_ops_{now.strftime('%Y%m%d_%H%M%S')}"
                        run_manifest.run_id = run_id

                    manifest_path = runs_dir / f"{run_id}" / "run_manifest.json"
                    manifest_path.parent.mkdir(parents=True, exist_ok=True)

                    with open(manifest_path, "w") as f:
                        json.dump(run_manifest.to_dict(), f, indent=2, default=str)

                    logger.info(f"Manifest written to: {manifest_path}")
                except Exception as manifest_err:
                    logger.warning(f"Failed to write manifest: {manifest_err}")

                return {
                    "status": "success",
                    "completed_stages": [s[0] for s in stages],
                    "last_successful_stage": stage_name,
                }

            except Exception as e:
                logger.error(f"Stage {stage_name} failed: {e}")

                # Auto-classify error
                error_class = _classify_error(e)
                logger.warning(f"Error class: {error_class}")

                # Write incident with auto-classification
                _write_incident(run_manifest.run_id, stage_name, str(e), error_class)

                # Check if retry is possible
                if retry_manager and retry_manager.should_retry(stage_name, e):
                    logger.info(f"Retrying stage {stage_name} with exponential backoff...")
                    time.sleep(2**attempt)
                    attempt += 1
                    continue
                else:
                    logger.error(f"Stage {stage_name} cannot be retried, stopping pipeline.")
                    run_manifest.set_status("failed")
                    run_manifest.add_error(stage_name, str(e))
                    return {
                        "status": "failed",
                        "failed_stage": stage_name,
                        "error": str(e),
                        "error_class": error_class,
                        "completed_stages": [s[0] for s in stages if s[0] != stage_name],
                    }

    return {"status": "completed", "completed_stages": [s[0] for s in stages]}


class PipelineOrchestrator:
    """Main orchestrator class for managing Loto Ops pipeline execution."""

    def __init__(self, settings: Any = None):
        """Initialize the orchestrator.

        Args:
            settings: Pipeline settings (optional)
        """
        self.settings = settings
        self.manifest = PipelineManifest(run_id="")

        # Validate selected workflow
        workflow_config = {}
        if settings and hasattr(settings, "workflow"):
            workflow_config = settings.workflow or {}

        self.selected_workflow = workflow_config.get("selected_workflow", "A")
        if self.selected_workflow not in ["A", "F"]:
            raise NotImplementedError(
                f"Workflow '{self.selected_workflow}' is not implemented. "
                f"Supported workflows are: A, F."
            )

    def _compute_run_dir(self, game: str, prefix: str) -> Path:
        """Compute the run directory path for a game.

        Args:
            game: Game name
            prefix: Run prefix

        Returns:
            Path to the run directory
        """
        if self.settings is None:
            raise RuntimeError("Pipeline settings are required")

        if hasattr(self.settings, "paths") and hasattr(self.settings.paths, "runs_dir"):
            base = Path(self.settings.paths.runs_dir)
        else:
            raw = getattr(self.settings, "raw", {}) or {}
            runs_dir = raw.get("runs_dir")
            if not runs_dir:
                raise KeyError("runs_dir")
            base = Path(runs_dir)

        run_dir = base / f"{prefix}_{game}"
        return run_dir

    def preflight(self, auto_fix: bool = False) -> dict[str, Any]:
        """Inspect required paths and safely create local output directories.

        External source projects are never fabricated.  ``auto_fix`` only
        creates directories owned by this project or its configured ZIP output.
        """
        if self.settings is None or not hasattr(self.settings, "paths"):
            return {
                "status": "FAIL",
                "ready": False,
                "errors": ["settings.paths is unavailable"],
                "warnings": [],
                "fixes": [],
                "checks": {},
            }

        paths = self.settings.paths
        checks: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        warnings: list[str] = []
        fixes: list[str] = []

        def record(name: str, path: Path, *, required: bool, kind: str = "any") -> bool:
            exists = path.exists()
            valid = exists and (
                kind == "any"
                or (kind == "dir" and path.is_dir())
                or (kind == "file" and path.is_file())
            )
            checks[name] = {
                "path": str(path),
                "exists": exists,
                "valid": valid,
                "required": required,
                "kind": kind,
            }
            if not valid:
                message = f"{name} is missing or invalid: {path}"
                (errors if required else warnings).append(message)
            return valid

        record("ops_project", Path(paths.ops_project), required=True, kind="dir")

        local_dirs = {
            "runs_dir": Path(paths.runs_dir),
            "artifacts_dir": Path(paths.artifacts_dir),
            "reports_dir": Path(paths.reports_dir),
            "zips_dir": Path(paths.zips_dir),
            "runtime_logs_dir": Path(paths.ops_project) / "runtime" / "logs",
            "zip_output_dir": Path(paths.zip_output_dir),
        }
        for name, directory in local_dirs.items():
            if auto_fix and not directory.exists():
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                    fixes.append(f"created {name}: {directory}")
                except OSError as exc:
                    errors.append(f"failed to create {name} {directory}: {exc}")
            record(name, directory, required=name in {"runs_dir", "artifacts_dir"}, kind="dir")

        life_ok = record(
            "loto_life_project",
            Path(paths.loto_life_project),
            required=False,
            kind="dir",
        )
        forecast_ok = record(
            "loto_forecast_project",
            Path(paths.loto_forecast_project),
            required=False,
            kind="dir",
        )
        interim_dir = Path(paths.loto_life_project) / "data" / "interim"
        interim_ok = record("normalized_interim_dir", interim_dir, required=False, kind="dir")
        sqlite_ok = record("sqlite_path", Path(paths.sqlite_path), required=False, kind="file")
        postgres_load_ok = record(
            "postgres_load_dir",
            Path(paths.postgres_load_dir),
            required=False,
            kind="dir",
        )

        password = getattr(getattr(self.settings, "db", None), "password", "")
        database_configured = bool(password and password != "CHANGE_ME")
        if not database_configured:
            warnings.append("database password is unset or still CHANGE_ME")

        ready = not errors
        ready_for_fast_pipeline = ready and life_ok and interim_ok and database_configured
        status = "PASS" if ready and not warnings else ("PARTIAL" if ready else "FAIL")
        return {
            "status": status,
            "ready": ready,
            "ready_for_fast_pipeline": ready_for_fast_pipeline,
            "errors": errors,
            "warnings": warnings,
            "fixes": fixes,
            "checks": checks,
            "capabilities": {
                "legacy_run": ready,
                "run_all_fast": ready_for_fast_pipeline,
                "forecast_project_available": forecast_ok,
                "sqlite_available": sqlite_ok,
                "postgres_load_available": postgres_load_ok,
                "database_configured": database_configured,
            },
        }

    def _should_continue(self, game: str) -> bool:
        """Check if pipeline should continue for a game.

        Args:
            game: Game name

        Returns:
            True if pipeline should continue, False if it should stop
        """
        run_dir = self._compute_run_dir(game, "loto_ops")
        manifest_path = run_dir / "run_manifest.json"

        if not manifest_path.exists():
            return True

        try:
            import json

            with open(manifest_path) as f:
                manifest_data = json.load(f)

            # Check if pipeline is already completed
            if manifest_data.get("status") == "completed":
                logger.info(f"Pipeline already completed for game: {game}")
                return False

            # Check if pipeline is failed and should be retried
            if manifest_data.get("status") == "failed":
                logger.info(f"Pipeline failed for game: {game}, should retry")
                return True

        except Exception as e:
            logger.warning(f"Failed to read manifest for game {game}: {e}")

        return True

    def run_pipeline(self, games: list[str]) -> dict[str, Any]:
        """Run the full pipeline for multiple games.

        Args:
            games: List of game names to process

        Returns:
            Dictionary with pipeline results
        """
        import datetime
        import json
        from pathlib import Path

        def log_trace_event(event_data: dict[str, Any]) -> None:
            try:
                trace_dir = Path(self.settings.paths.ops_project) / ".ai" / "runtime" / "phase15"
                trace_dir.mkdir(parents=True, exist_ok=True)
                trace_file = trace_dir / "workflow_traces.jsonl"
                with open(trace_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"Failed to log trace event {event_data}: {e}")

        results = {}

        for game in games:
            logger.info(f"Running pipeline for game: {game} (Workflow: {self.selected_workflow})")

            # 1. log workflow selection
            log_trace_event(
                {
                    "event": "workflow_selected",
                    "workflow": self.selected_workflow,
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )

            try:
                # Compute run directory
                run_dir = self._compute_run_dir(game, "loto_ops")
                run_dir.mkdir(parents=True, exist_ok=True)

                # Check if we should continue
                if not self._should_continue(game):
                    results[game] = {"status": "skipped", "reason": "already completed"}
                    continue

                # 2. Planner Stage
                if self.selected_workflow == "F":
                    log_trace_event(
                        {
                            "event": "planner_started",
                            "timestamp": datetime.datetime.now().isoformat(),
                        }
                    )
                    # Create plan file run_plan.json
                    plan_path = run_dir / "run_plan.json"
                    plan_data = {
                        "workflow": "F",
                        "game": game,
                        "planned_stages": [
                            "data_collection",
                            "data_validation",
                            "model_training",
                            "model_evaluation",
                            "deployment",
                        ],
                        "timestamp": datetime.datetime.now().isoformat(),
                    }
                    with open(plan_path, "w", encoding="utf-8") as f:
                        json.dump(plan_data, f, indent=2, ensure_ascii=False)
                    logger.info(f"Planner output created at: {plan_path}")

                # 3. Executor Stage
                log_trace_event(
                    {"event": "executor_started", "timestamp": datetime.datetime.now().isoformat()}
                )

                # 4. Validator Stage (Fresh Context or not)
                val_session_id = "standard"
                if self.selected_workflow == "F":
                    val_session_id = (
                        f"val_session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
                    )
                    log_trace_event(
                        {
                            "event": "validator_started",
                            "fresh_context": True,
                            "session_id": val_session_id,
                            "timestamp": datetime.datetime.now().isoformat(),
                        }
                    )
                else:
                    log_trace_event(
                        {
                            "event": "validator_started",
                            "fresh_context": False,
                            "session_id": val_session_id,
                            "timestamp": datetime.datetime.now().isoformat(),
                        }
                    )

                # 5. Memory Retrieve Stage
                memory_count = 0
                if self.selected_workflow == "F":
                    log_trace_event(
                        {
                            "event": "memory_retrieved",
                            "timestamp": datetime.datetime.now().isoformat(),
                        }
                    )
                    # Scan shared-ai-memory for JSON/YAML files
                    memory_dir = Path("/mnt/e/env/ts/shared-ai-memory")
                    if memory_dir.exists():
                        for p in memory_dir.glob("**/*"):
                            if p.is_file() and p.suffix in [".json", ".yaml", ".yml"]:
                                memory_count += 1
                    logger.info(f"Memory retrieved: {memory_count} files found")

                # Run stages
                stages = [
                    ("data_collection", self._collect_data),
                    ("data_validation", self._validate_data),
                    ("model_training", self._train_model),
                    ("model_evaluation", self._evaluate_model),
                    ("deployment", self._deploy_model),
                ]

                # Execute stages with retry manager
                from loto_ops.pipeline.retry_manager import RetryManager

                retry_manager = RetryManager()

                # Handle stages with custom loop to support logging retry_decision
                result = None
                completed_stages = []
                for stage_name, stage_func in stages:
                    logger.info(f"Starting stage: {stage_name}")
                    attempt = 0
                    while True:
                        try:
                            stage_func()
                            completed_stages.append(stage_name)
                            break
                        except Exception as stage_err:
                            logger.error(f"Stage {stage_name} failed: {stage_err}")
                            if self.selected_workflow == "F":
                                log_trace_event(
                                    {
                                        "event": "retry_decision",
                                        "stage": stage_name,
                                        "error_class": retry_manager.get_error_class(stage_err),
                                        "error_message": str(stage_err),
                                        "timestamp": datetime.datetime.now().isoformat(),
                                    }
                                )
                            else:
                                log_trace_event(
                                    {
                                        "event": "retry_decision",
                                        "stage": stage_name,
                                        "error_message": str(stage_err),
                                        "timestamp": datetime.datetime.now().isoformat(),
                                    }
                                )

                            if retry_manager.should_retry(stage_name, stage_err):
                                attempt += 1
                                continue
                            else:
                                result = {
                                    "status": "failed",
                                    "failed_stage": stage_name,
                                    "error": str(stage_err),
                                    "error_class": retry_manager.get_error_class(stage_err),
                                    "completed_stages": completed_stages,
                                }
                                break
                    if result and result["status"] == "failed":
                        break

                if result is None:
                    result = {
                        "status": "success",
                        "completed_stages": completed_stages,
                        "last_successful_stage": completed_stages[-1] if completed_stages else None,
                    }

                results[game] = result

                # Update manifest
                if result.get("status") == "success":
                    self.manifest.set_status("success")
                    logger.info(f"Pipeline completed successfully for game: {game}")
                else:
                    self.manifest.set_status("failed")
                    self.manifest.add_error(game, str(result.get("error", "Unknown error")))
                    self.manifest.last_successful_stage = None
                    # Write incident file for this failure
                    error_msg = result.get("error", "Unknown error")
                    error_class = result.get("error_class", "U")
                    _write_incident(game, "pipeline", error_msg, error_class)

                # 6. Handover Stage
                if self.selected_workflow == "F":
                    # Export handover data
                    handover_dir = Path("/mnt/e/env/ts/shared-ai-memory/handovers")
                    handover_dir.mkdir(parents=True, exist_ok=True)
                    handover_path = handover_dir / "latest_handover.json"
                    handover_data = {
                        "handover_id": f"ho_{datetime.datetime.now(datetime.UTC).isoformat()}",
                        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                        "run_id": self.manifest.run_id
                        or f"loto_ops_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        "status": self.manifest.status,
                        "last_successful_stage": self.manifest.last_successful_stage,
                        "memory_retrieved_count": memory_count,
                        "val_session_id": val_session_id,
                    }
                    with open(handover_path, "w", encoding="utf-8") as f:
                        json.dump(handover_data, f, indent=2, ensure_ascii=False)

                    # Also write to local run_dir
                    local_handover_path = run_dir / "latest_handover.json"
                    with open(local_handover_path, "w", encoding="utf-8") as f:
                        json.dump(handover_data, f, indent=2, ensure_ascii=False)

                    log_trace_event(
                        {
                            "event": "handover_written",
                            "handover_path": str(handover_path),
                            "timestamp": datetime.datetime.now().isoformat(),
                        }
                    )

            except Exception as e:
                logger.error(f"Pipeline failed for game: {game}: {e}")
                self.manifest.set_status("failed")
                self.manifest.add_error(game, str(e))
                self.manifest.last_successful_stage = None
                error_class = _classify_error(e)
                _write_incident(game, "pipeline", str(e), error_class)
                results[game] = {
                    "status": "failed",
                    "failed_stage": "pipeline",
                    "error": str(e),
                    "error_class": error_class,
                    "completed_stages": [],
                }

        return results

    def _collect_data(self) -> dict[str, Any]:
        """Collect data stage."""
        logger.info("Collecting data...")
        return {"data_collected": True}

    def _validate_data(self) -> dict[str, Any]:
        """Validate data stage."""
        logger.info("Validating data...")
        return {"data_valid": True}

    def _train_model(self) -> dict[str, Any]:
        """Train model stage."""
        logger.info("Training model...")
        return {"model_trained": True}

    def _evaluate_model(self) -> dict[str, Any]:
        """Evaluate model stage."""
        logger.info("Evaluating model...")
        return {"model_evaluated": True}

    def _deploy_model(self) -> dict[str, Any]:
        """Deploy model stage."""
        logger.info("Deploying model...")
        return {"model_deployed": True}
