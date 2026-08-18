from __future__ import annotations

import argparse
import collections
import json
import pathlib
import subprocess
import sys


def _relative_filename(value: str) -> str:
    path = pathlib.Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(pathlib.Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _signature(item: dict[str, object]) -> tuple[str, str, int, int, str]:
    location = item.get("location")
    if not isinstance(location, dict):
        raise RuntimeError(f"Ruff diagnostic missing location: {item!r}")
    code = item.get("code")
    message = item.get("message")
    filename = item.get("filename")
    if not isinstance(code, str) or not isinstance(message, str) or not isinstance(filename, str):
        raise RuntimeError(f"Ruff diagnostic has invalid fields: {item!r}")
    row = location.get("row")
    column = location.get("column")
    if not isinstance(row, int) or not isinstance(column, int):
        raise RuntimeError(f"Ruff diagnostic has invalid location: {item!r}")
    return (_relative_filename(filename), code, row, column, message)


def _read_baseline(path: pathlib.Path) -> collections.Counter[tuple[str, str, int, int, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, list):
        raise RuntimeError("lint baseline diagnostics must be a list")
    rows: list[tuple[str, str, int, int, str]] = []
    for item in diagnostics:
        if not isinstance(item, dict):
            raise RuntimeError(f"invalid lint baseline row: {item!r}")
        filename = item.get("filename")
        code = item.get("code")
        row = item.get("row")
        column = item.get("column")
        message = item.get("message")
        if not isinstance(filename, str) or not isinstance(code, str) or not isinstance(message, str):
            raise RuntimeError(f"invalid lint baseline fields: {item!r}")
        if not isinstance(row, int) or not isinstance(column, int):
            raise RuntimeError(f"invalid lint baseline location: {item!r}")
        rows.append((filename, code, row, column, message))
    return collections.Counter(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    parser.add_argument("targets", nargs="+")
    args = parser.parse_args()

    baseline = _read_baseline(args.baseline)
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format", "json", *args.targets],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in {0, 1}:
        print(proc.stdout, end="")
        print(proc.stderr, end="", file=sys.stderr)
        return proc.returncode

    raw = json.loads(proc.stdout or "[]")
    if not isinstance(raw, list):
        raise RuntimeError("Ruff JSON output is not a list")
    current = collections.Counter(_signature(item) for item in raw if isinstance(item, dict))

    introduced = current - baseline
    resolved = baseline - current
    inherited = current & baseline

    print(f"RUFF_LINT_BASELINE={sum(baseline.values())}")
    print(f"RUFF_LINT_CURRENT={sum(current.values())}")
    print(f"RUFF_LINT_INHERITED={sum(inherited.values())}")
    print(f"RUFF_LINT_RESOLVED={sum(resolved.values())}")
    print(f"RUFF_LINT_INTRODUCED={sum(introduced.values())}")

    for signature, count in sorted(introduced.items()):
        filename, code, row, column, message = signature
        print(
            f"NEW_LINT_DEBT={filename}:{row}:{column}:{code}:{message} x{count}",
            file=sys.stderr,
        )

    if introduced:
        print("RUFF_LINT_BASELINE_GATE=FAIL", file=sys.stderr)
        return 1

    print("RUFF_LINT_BASELINE_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
