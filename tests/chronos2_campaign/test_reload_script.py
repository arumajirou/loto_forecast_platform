from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_chronos2_provider.py"
    spec = importlib.util.spec_from_file_location("run_chronos2_provider", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_response_writer_emits_real_json(tmp_path: Path) -> None:
    module = load_script()
    output = tmp_path / "response.json"
    module._write_response(output, {"status": "OK"})
    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "OK"}


def test_script_adds_repository_src_to_import_path() -> None:
    module = load_script()
    assert str(module.SRC) in module.sys.path
