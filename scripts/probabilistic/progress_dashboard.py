from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

from loto.probabilistic.progress import render_dashboard


FINAL_STATUSES = {"PASS", "PARTIAL", "FAILED", "STOPPED_BY_USER", "DRY_RUN"}


def discover(output_root: Path) -> Path | None:
    candidates = list(output_root.glob("*/report/progress.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def process_alive(pid: int | None) -> bool:
    if not pid:
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir")
    parser.add_argument("--output-root")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--runner-pid", type=int)
    args = parser.parse_args()

    if not args.run_dir and not args.output_root:
        parser.error("--run-dir or --output-root is required")

    explicit = Path(args.run_dir).resolve() if args.run_dir else None
    output_root = Path(args.output_root).resolve() if args.output_root else None

    def stop_runner(signum: int, _frame: object) -> None:
        if args.runner_pid:
            try:
                os.killpg(os.getpgid(args.runner_pid), signal.SIGINT)
            except OSError:
                try:
                    os.kill(args.runner_pid, signal.SIGINT)
                except OSError:
                    pass
        print(f"\n停止シグナル({signum})を受信しました。途中結果を保存して終了します。", flush=True)
        raise SystemExit(130)

    if args.runner_pid:
        signal.signal(signal.SIGINT, stop_runner)
        signal.signal(signal.SIGTERM, stop_runner)
        if hasattr(signal, "SIGTSTP"):
            signal.signal(signal.SIGTSTP, stop_runner)

    last_text = ""
    missing_since = time.monotonic()

    while True:
        progress_path = (
            explicit / "report" / "progress.json" if explicit is not None else discover(output_root)  # type: ignore[arg-type]
        )
        if progress_path is None or not progress_path.is_file():
            if not process_alive(args.runner_pid) and time.monotonic() - missing_since > 3:
                print("Runner ended before progress.json was created.", file=sys.stderr)
                return 2
            text = "progress.jsonを待っています..."
        else:
            try:
                payload = json.loads(progress_path.read_text(encoding="utf-8"))
                text = render_dashboard(payload)
            except Exception as exc:
                text = f"progress.json読込中: {type(exc).__name__}: {exc}"
                payload = {}

        if text != last_text or args.once:
            if sys.stdout.isatty() and not args.once:
                print("\033[2J\033[H", end="")
            print(text, flush=True)
            last_text = text

        if args.once:
            return 0
        if progress_path is not None and progress_path.is_file():
            status = str(payload.get("status", ""))
            if status in FINAL_STATUSES:
                return 0
        if not process_alive(args.runner_pid):
            time.sleep(1)
            if progress_path is None or not progress_path.is_file():
                return 2
            try:
                payload = json.loads(progress_path.read_text(encoding="utf-8"))
            except Exception:
                return 2
            if str(payload.get("status", "")) not in FINAL_STATUSES:
                return 1
        time.sleep(max(args.interval, 0.2))


if __name__ == "__main__":
    raise SystemExit(main())
