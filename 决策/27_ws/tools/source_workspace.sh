#!/usr/bin/env bash

ASCII_SETUP="${HOME}/.ros/decision_27_ws/install/setup.bash"

if [[ ! -f "${ASCII_SETUP}" ]]; then
  echo "Workspace is not built. Run: bash tools/build_workspace.sh" >&2
  return 1 2>/dev/null || exit 1
fi

set +u
source "${ASCII_SETUP}"
echo "decision_process workspace sourced"
