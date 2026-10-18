#!/usr/bin/env bash
# Launch the read-only RMUC 2026 SQLite replay player.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

has_pygame() {
  "$1" -c 'import pygame' >/dev/null 2>&1
}

python_bin=""
if [ -x ".venv/bin/python" ] && has_pygame ".venv/bin/python"; then
  python_bin="$script_dir/.venv/bin/python"
elif [ -x "../pygame_sim/.venv/bin/python" ] && has_pygame "../pygame_sim/.venv/bin/python"; then
  python_bin="../pygame_sim/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1 && has_pygame "$(command -v python3)"; then
  python_bin="$(command -v python3)"
fi

if [ -z "$python_bin" ]; then
  echo "[pygame_sim_v2 replay] pygame not found; creating .venv ..." >&2
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt
  python_bin="$script_dir/.venv/bin/python"
fi

exec "$python_bin" main.py --replay "$@"
