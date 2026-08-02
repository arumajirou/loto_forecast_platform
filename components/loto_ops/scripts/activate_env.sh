#!/usr/bin/env bash
# Activate loto_ops_pipeline virtual environment in the current shell.
# Usage:
#   cd /mnt/e/env/ts/loto_ops
#   source ./activate_env.sh

_loto_ops_activate() {
  local script_path project_dir venv_dir cmd_path
  if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    script_path="${BASH_SOURCE[0]}"
  else
    script_path="$0"
  fi
  project_dir="$(cd "$(dirname "$script_path")" && pwd)"
  venv_dir="${project_dir}/.venv"

  if [[ ! -d "$venv_dir" ]]; then
    echo "[loto-ops] .venv が見つかりません: $venv_dir" >&2
    echo "[loto-ops] 先に実行してください: ./scripts/setup_uv.sh" >&2
    return 1 2>/dev/null || exit 1
  fi

  # shellcheck disable=SC1091
  source "$venv_dir/bin/activate"

  export LOTO_OPS_HOME="$project_dir"

  if [[ -f "$project_dir/.loto_ops_env" ]]; then
    # shellcheck disable=SC1091
    source "$project_dir/.loto_ops_env"
  else
    export LOTO_OPS_PROJECT="$project_dir"
    export LOTO_OPS_CONFIG="${LOTO_OPS_CONFIG:-$project_dir/configs/loto_ops.yaml}"
    export LOTO_OPS_RUNS_DIR="${LOTO_OPS_RUNS_DIR:-$project_dir/runs}"
    export LOTO_HANDOVER_DIR="${LOTO_HANDOVER_DIR:-$project_dir/shared-ai-memory/handovers}"
    export LOTO_SKILLS_DIR="${LOTO_SKILLS_DIR:-$project_dir/shared-ai-memory/skills}"
  fi

  # Hermes venvをPYTHONPATHへ追加しない
  # プロジェクトのsrcだけを設定
  export PYTHONPATH="$project_dir/src"

  # PROJECT_VENV/bin を PATH 先頭に
  export PATH="$venv_dir/bin:$PATH"

  unset PYTHONHOME
  export PYTHONNOUSERSITE=1

  # Hermes venvを PATH 先頭に追加しない
  # Hermes CLIが必要なら絶対パスで呼ぶ

  # プロジェクトの bin スクリプト
  if [[ ! -x "$venv_dir/bin/loto-ops" ]]; then
    cat > "$venv_dir/bin/loto-ops" <<EOS
#!/usr/bin/env bash
export PYTHONPATH="$project_dir/src:\${PYTHONPATH:-}"
exec "$venv_dir/bin/python" -m loto_ops.cli "\$@"
EOS
    chmod +x "$venv_dir/bin/loto-ops"
  fi

  hash -r 2>/dev/null || true
  cmd_path="$(command -v loto-ops || true)"

  echo "[loto-ops] activated: $venv_dir"
  echo "[loto-ops] python: $(command -v python)"
  if [[ -n "$cmd_path" ]]; then
    echo "[loto-ops] command: $cmd_path"
  else
    echo "[loto-ops] command: MISSING"
    echo "[loto-ops] 復旧: ./scripts/setup_uv.sh を再実行してください" >&2
  fi
}

_loto_ops_activate "$@"
unset -f _loto_ops_activate
