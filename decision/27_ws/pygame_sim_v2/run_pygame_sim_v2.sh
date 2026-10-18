#!/usr/bin/env bash
# Launch the v2 Pygame rule validator without touching the original pygame_sim.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

has_pygame() {
  "$1" -c 'import pygame' >/dev/null 2>&1
}

python_bin=""

# 1. Prefer the v2 local virtual environment.
if [ -x ".venv/bin/python" ] && has_pygame ".venv/bin/python"; then
  python_bin="$script_dir/.venv/bin/python"
# 2. Reuse the original pygame_sim virtual environment when available.
elif [ -x "../pygame_sim/.venv/bin/python" ] && has_pygame "../pygame_sim/.venv/bin/python"; then
  python_bin="../pygame_sim/.venv/bin/python"
# 3. Fall back to a system Python that already has pygame.
elif command -v python3 >/dev/null 2>&1 && has_pygame "$(command -v python3)"; then
  python_bin="$(command -v python3)"
fi

if [ -z "$python_bin" ]; then
  echo "[pygame_sim_v2] pygame not found; creating .venv ..." >&2
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[pygame_sim_v2] python3 is required but was not found" >&2
    exit 1
  fi
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt
  python_bin="$script_dir/.venv/bin/python"
fi

echo "[pygame_sim_v2] python: $python_bin"
echo "[pygame_sim_v2] workdir: $script_dir"
exec "$python_bin" main.py "$@"
