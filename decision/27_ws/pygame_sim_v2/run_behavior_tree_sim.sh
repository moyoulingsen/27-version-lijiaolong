#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace="$(cd "$script_dir/.." && pwd)"

set +u
source /opt/ros/jazzy/setup.bash
set -u
cd "$workspace"
ros_build_root="$HOME/.ros/decision_27_ws_runtime"
mkdir -p "$ros_build_root"
colcon --log-base "$ros_build_root/log" build \
  --packages-select decision_process \
  --packages-ignore behaviortree_cpp \
  --build-base "$ros_build_root/build" \
  --install-base "$ros_build_root/install" \
  --cmake-args \
    -DPython3_EXECUTABLE=/usr/bin/python3 \
    -DPYTHON_EXECUTABLE=/usr/bin/python3
set +u
source "$ros_build_root/install/setup.bash"
set -u

ros2 launch decision_process integrated_sim.launch.py &
launch_pid=$!
cleanup() {
  kill -INT "$launch_pid" 2>/dev/null || true
  wait "$launch_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 1
cd "$script_dir"
if [ -x .venv/bin/python ]; then
  python_bin=".venv/bin/python"
elif [ -x ../pygame_sim/.venv/bin/python ]; then
  python_bin="../pygame_sim/.venv/bin/python"
else
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
  python_bin=".venv/bin/python"
fi
"$python_bin" main.py
