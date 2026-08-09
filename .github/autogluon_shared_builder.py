from __future__ import annotations

from pathlib import Path


def patch_workers() -> None:
    path = Path("src/loto/models/workers.py")
    text = path.read_text(encoding="utf-8")
    import_anchor = "from loto.models.providers import FoundationProviderError, get_foundation_provider\n"
    import_block = """from loto.models.autogluon_shared import (\n    AutoGluonSharedContractError,\n    adapt_autogluon_provider_response,\n    build_autogluon_provider_request,\n)\nfrom loto.models.providers import FoundationProviderError, get_foundation_provider\n"""
    if "from loto.models.autogluon_shared import" not in text:
        if text.count(import_anchor) != 1:
            raise RuntimeError("unexpected workers import anchor count")
        text = text.replace(import_anchor, import_block, 1)

    start_marker = "    def _invoke_autogluon_subprocess(self, request: dict[str, Any]) -> dict[str, Any]:\n"
    end_marker = "    def _darts(self, history: pd.DataFrame) -> WorkerOutput:\n"
    start = text.find(start_marker)
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise RuntimeError("AutoGluon worker replacement markers not found")

    replacement = '''    def _invoke_autogluon_subprocess(self, request: dict[str, Any]) -> dict[str, Any]:
        if not AUTOGLUON_ENV.exists():
            raise WorkerSubprocessError(
                "DEPENDENCY_MISSING",
                f"missing AutoGluon-TimeSeries environment: {AUTOGLUON_ENV}",
            )
        if not (AUTOGLUON_ENV / "uv.lock").exists():
            raise WorkerSubprocessError(
                "DEPENDENCY_MISSING",
                f"missing AutoGluon-TimeSeries lockfile: {AUTOGLUON_ENV / 'uv.lock'}",
            )
        if not AUTOGLUON_RUNNER.exists():
            raise WorkerSubprocessError(
                "PROVIDER_NOT_IMPLEMENTED",
                f"missing AutoGluon-TimeSeries runner: {AUTOGLUON_RUNNER}",
            )
        with tempfile.TemporaryDirectory(prefix="loto-autogluon-ts-") as tmp:
            request_path = Path(tmp) / "provider_request.json"
            response_path = Path(tmp) / "provider_response.json"
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(AUTOGLUON_ENV),
                    "--locked",
                    "python",
                    str(AUTOGLUON_RUNNER),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=int(self.params.get("provider_timeout", 900)),
                check=False,
            )
            if proc.returncode != 0:
                raise WorkerSubprocessError(
                    "ERROR",
                    "AutoGluon-TimeSeries subprocess failed "
                    f"rc={proc.returncode}: {proc.stderr[-2000:] or proc.stdout[-2000:]}",
                )
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise WorkerSubprocessError(
                    "ERROR",
                    f"AutoGluon-TimeSeries provider returned invalid JSON: {exc}",
                ) from exc
        if response.get("status") != "OK":
            if int(request.get("schema_version", 1)) == 2:
                error = response.get("error") or {}
                code = str(error.get("code") or response.get("status") or "ERROR")
                message = str(
                    error.get("message")
                    or response.get("message")
                    or "AutoGluon-TimeSeries provider failed"
                )
            else:
                code = str(response.get("status", "ERROR"))
                message = str(
                    response.get("message", "AutoGluon-TimeSeries provider failed")
                )
            raise WorkerSubprocessError(code, message)

        if int(request.get("schema_version", 1)) == 1:
            predictions = np.asarray(response.get("predictions"), dtype=float)
            expected = len(request.get("position_columns", []))
            if expected <= 0:
                raise WorkerSubprocessError(
                    "INVALID_REQUEST",
                    "provider request has no position columns",
                )
            if predictions.shape != (expected,) or not np.isfinite(predictions).all():
                raise WorkerSubprocessError(
                    "PREDICTION_MISMATCH",
                    "AutoGluon-TimeSeries provider returned invalid "
                    f"predictions shape={predictions.shape}",
                )
        return response

    def _autogluon_v1_compat(self, history: pd.DataFrame) -> WorkerOutput:
        columns = [*self._columns(history), "draw_date"]
        payload = history[columns].copy()
        payload["draw_date"] = payload["draw_date"].astype(str)
        artifact_dir = tempfile.mkdtemp(prefix="loto-autogluon-artifact-")
        request = {
            "schema_version": 1,
            "model_id": self.spec.model_id,
            "mode": "fit_predict_save",
            "artifact_dir": artifact_dir,
            "history": payload.to_dict(orient="records"),
            "position_columns": self._columns(history),
            "presets": self.params.get("presets", "fast_training"),
            "time_limit": self.params.get("time_limit", 120),
            "prediction_length": 1,
            "eval_metric": "MAE",
            "seed": self.seed,
            "device": self.device if self.device != "auto" else "cpu",
        }
        response = self._invoke_autogluon_subprocess(request)
        values = np.asarray(response["predictions"], dtype=float)
        properties = response.get("properties", {})
        return WorkerOutput(
            values,
            {
                "library": "autogluon",
                "protocol_version": 1,
                "compatibility_path": True,
                "model_best": properties.get("model_best"),
                "presets": properties.get("presets"),
            },
            model_artifact_payload={
                "library": "autogluon",
                "artifact_dir": artifact_dir,
                "request": request,
                "response": response,
            },
        )

    def _autogluon(self, history: pd.DataFrame) -> WorkerOutput:
        protocol_version = int(self.params.get("protocol_version", 2))
        if protocol_version == 1:
            return self._autogluon_v1_compat(history)
        if protocol_version != 2:
            raise WorkerSubprocessError(
                "PROTOCOL_VERSION_UNSUPPORTED",
                f"unsupported AutoGluon protocol_version={protocol_version}",
            )

        operation = str(self.params.get("operation", "fit_predict_save"))
        configured_artifact_dir = self.params.get("artifact_dir")
        if operation == "load_predict" and not configured_artifact_dir:
            raise WorkerSubprocessError(
                "ARTIFACT_MISSING",
                "AutoGluon load_predict requires params['artifact_dir']",
            )
        if configured_artifact_dir:
            artifact_dir = str(Path(str(configured_artifact_dir)).resolve())
        else:
            artifact_dir = tempfile.mkdtemp(prefix="loto-autogluon-artifact-")

        requested_device = (
            self.device
            if self.device != "auto"
            else str(self.params.get("requested_device", "cpu"))
        )
        try:
            request = build_autogluon_provider_request(
                history,
                position_columns=self._columns(history),
                params=self.params,
                requested_device=requested_device,
                artifact_dir=artifact_dir,
            )
            response = self._invoke_autogluon_subprocess(request)
            result = adapt_autogluon_provider_response(
                request,
                response,
                params=self.params,
            )
        except AutoGluonSharedContractError as exc:
            raise WorkerSubprocessError(exc.code, str(exc)) from exc

        return WorkerOutput(
            np.asarray(result.position_values, dtype=float),
            result.metadata,
            model_artifact_payload={
                "library": "autogluon",
                "artifact_dir": artifact_dir,
                "request": request,
                "response": response,
            },
        )

'''
    text = text[:start] + replacement + text[end:]
    path.write_text(text, encoding="utf-8")


def patch_catalog() -> None:
    path = Path("src/loto/models/catalog_full.py")
    text = path.read_text(encoding="utf-8")
    typing_anchor = "from dataclasses import dataclass, field\nfrom typing import Any, Literal\n"
    typing_replacement = """from collections.abc import Iterable\nfrom dataclasses import dataclass, field\nfrom typing import Any, Literal\n\nfrom loto.adapters.autogluon.inventory import (\n    AutoGluonRuntimeInventory,\n    SOURCE_MODEL_SPECS as AUTOGLUON_SOURCE_MODEL_SPECS,\n)\n"""
    if "AutoGluonRuntimeInventory" not in text:
        if text.count(typing_anchor) != 1:
            raise RuntimeError("unexpected catalog import anchor count")
        text = text.replace(typing_anchor, typing_replacement, 1)

    all_anchor = '    "PRIMARY_SOURCES",\n]'
    if '    "autogluon_runtime_catalog",' not in text:
        if text.count(all_anchor) != 1:
            raise RuntimeError("unexpected catalog __all__ anchor count")
        text = text.replace(
            all_anchor,
            '    "PRIMARY_SOURCES",\n    "autogluon_runtime_catalog",\n]',
            1,
        )

    source_anchor = '    "tsfm": "huggingface.co/models?pipeline_tag=time-series-forecasting (2026-07-30)",\n}'
    primary_block = text.split("PRIMARY_SOURCES", 1)[1].split("}", 1)[0]
    if '    "autogluon":' not in primary_block:
        if text.count(source_anchor) != 1:
            raise RuntimeError("unexpected PRIMARY_SOURCES anchor count")
        text = text.replace(
            source_anchor,
            '    "tsfm": "huggingface.co/models?pipeline_tag=time-series-forecasting (2026-07-30)",\n'
            '    "autogluon": "autogluon.timeseries 1.5.0 runtime model registry",\n}',
            1,
        )

    function_anchor = "\ndef catalog_counts() -> dict[str, int]:\n"
    runtime_function = '''
def autogluon_runtime_catalog(
    inventory: AutoGluonRuntimeInventory | None = None,
    *,
    certified_aliases: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Project source/runtime AutoGluon availability without inventing runtime success."""
    by_alias = {entry.alias: entry for entry in inventory.models} if inventory is not None else {}
    source_aliases = {spec.alias for spec in AUTOGLUON_SOURCE_MODEL_SPECS}
    certified = {str(alias) for alias in certified_aliases}
    unknown_certified = sorted(certified - source_aliases)
    if unknown_certified:
        raise ValueError(f"unknown certified AutoGluon aliases: {unknown_certified}")

    rows: list[dict[str, Any]] = []
    for spec in AUTOGLUON_SOURCE_MODEL_SPECS:
        state = by_alias.get(spec.alias)
        runtime_discovered = bool(state and state.runtime_discovered)
        runtime_importable = bool(state and state.runtime_importable)
        runtime_certified = bool(state and state.runtime_certified) or spec.alias in certified
        if runtime_certified and not (runtime_discovered and runtime_importable):
            raise ValueError(
                f"cannot certify AutoGluon alias {spec.alias!r} without "
                "discovered/importable runtime evidence"
            )
        failure = state.failure if state is not None else None
        rows.append(
            {
                "model_id": f"autogluon-{spec.alias.lower()}",
                "alias": spec.alias,
                "class_name": spec.class_name,
                "category": spec.category,
                "source_declared": True,
                "runtime_discovered": runtime_discovered,
                "runtime_importable": runtime_importable,
                "runtime_certified": runtime_certified,
                "runtime_class_name": state.runtime_class_name if state is not None else None,
                "failure": (
                    None
                    if failure is None
                    else {
                        "category": failure.category.value,
                        "subject": failure.subject,
                        "message": failure.message,
                        "dependency": failure.dependency,
                        "error_type": failure.error_type,
                    }
                ),
                "inventory_sha256": inventory.inventory_sha256 if inventory is not None else None,
            }
        )
    return rows

'''
    if "def autogluon_runtime_catalog(" not in text:
        if text.count(function_anchor) != 1:
            raise RuntimeError("unexpected catalog function anchor count")
        text = text.replace(function_anchor, runtime_function + function_anchor, 1)

    provider_caps = (
        '            capabilities=("position", "probability", "automl"),\n'
        "            supports_probabilistic=True,\n"
    )
    provider_caps_new = (
        '            capabilities=("position", "probability", "automl", "protocol_v2"),\n'
        "            supports_probabilistic=True,\n"
        '            notes="stable provider; runtime states use autogluon_runtime_catalog",\n'
    )
    if provider_caps in text:
        text = text.replace(provider_caps, provider_caps_new, 1)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_workers()
    patch_catalog()


if __name__ == "__main__":
    main()
