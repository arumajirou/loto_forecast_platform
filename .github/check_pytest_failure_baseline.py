from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys


SUMMARY_PATTERN = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.MULTILINE)


def read_baseline(path: pathlib.Path) -> set[str]:
    rows: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value in rows:
            raise RuntimeError(f"duplicate pytest baseline nodeid: {value}")
        rows.add(value)
    return rows


def parse_failures(output: str) -> set[str]:
    return {match.group(1) for match in SUMMARY_PATTERN.finditer(output)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    args = parser.parse_args()

    baseline = read_baseline(args.baseline)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        check=False,
        capture_output=True,
        text=True,
    )

    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    if proc.returncode == 0:
        current: set[str] = set()
    elif proc.returncode == 1:
        current = parse_failures(proc.stdout + "\n" + proc.stderr)
        if not current:
            print("PYTEST_BASELINE_TOOL_ERROR=unable_to_parse_failures", file=sys.stderr)
            return 2
    else:
        print(f"PYTEST_BASELINE_TOOL_ERROR=pytest_exit_{proc.returncode}", file=sys.stderr)
        return proc.returncode

    introduced = current - baseline
    resolved = baseline - current
    inherited = current & baseline

    print(f"PYTEST_BASELINE={len(baseline)}")
    print(f"PYTEST_CURRENT_FAILURES={len(current)}")
    print(f"PYTEST_INHERITED_FAILURES={len(inherited)}")
    print(f"PYTEST_RESOLVED_FAILURES={len(resolved)}")
    print(f"PYTEST_INTRODUCED_FAILURES={len(introduced)}")

    for nodeid in sorted(resolved):
        print(f"RESOLVED_PYTEST_FAILURE={nodeid}")
    for nodeid in sorted(introduced):
        print(f"NEW_PYTEST_FAILURE={nodeid}", file=sys.stderr)

    if introduced:
        print("PYTEST_BASELINE_GATE=FAIL", file=sys.stderr)
        return 1

    print("PYTEST_BASELINE_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
