#!/usr/bin/env bash
# Setup and activate loto_ops_pipeline in the current shell.
# Usage:
#   cd /mnt/e/env/ts/loto_ops
#   source scripts/setup_and_activate.sh
#
# This file must be sourced to keep the virtual environment active.

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_project_dir="$(cd "$_script_dir/.." && pwd)"
cd "$_project_dir" || return 1

if [[ ! -d .venv ]]; then
  uv sync
fi

# shellcheck disable=SC1091
source "$_project_dir/activate_env.sh"
unset _script_dir _project_dir
