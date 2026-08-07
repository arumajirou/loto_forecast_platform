from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_provider_entrypoint_bootstraps_src_without_pythonpath(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    request = {
        "schema_version": "1.0",
        "operation": "identity",
        "output_dir": str(tmp_path / "identity"),
        "environment_lane": "basicts-py311",
        "expected_basicts_version": "1.1.0",
        "expected_upstream_revision": "c2bb6e31e591167e84459775a21a62e70a5893ce",
    }
    request_path = tmp_path / "identity.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["BASICTS_UPSTREAM_REVISION"] = request["expected_upstream_revision"]

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_basicts_provider.py"),
            "--request",
            str(request_path),
        ],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode in {0, 2}
    assert "No module named 'loto'" not in completed.stderr
    assert (tmp_path / "identity" / "response.json").is_file()
