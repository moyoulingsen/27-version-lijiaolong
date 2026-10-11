#!/usr/bin/env bash
set -euo pipefail
set +u
source /opt/ros/jazzy/setup.bash
set -u

workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_root="$HOME/.ros/decision_27_ws_runtime"
cd "$workspace"

printf '
[WSL-BUILD] 构建 decision_process
'
mkdir -p "$runtime_root"
colcon --log-base "$runtime_root/log" build \
  --packages-select decision_process \
  --packages-ignore behaviortree_cpp \
  --build-base "$runtime_root/build" \
  --install-base "$runtime_root/install" \
  --cmake-args \
    -DPython3_EXECUTABLE=/usr/bin/python3 \
    -DPYTHON_EXECUTABLE=/usr/bin/python3

set +u
source "$runtime_root/install/setup.bash"
set -u

printf '
[WSL-VERIFY] ROS_DISTRO=%s
' "$ROS_DISTRO"
ros2 pkg prefix decision_process
for package in behaviortree_cpp; do
  ros2 pkg prefix "$package" >/dev/null
  printf '%s=AVAILABLE
' "$package"
done

printf '
[WSL-VERIFY] Python ROS 消息导入
'
python3 -c "from decision_process.msg import ReceiveData, DesicionSendData, AutoaimToDecision, DecisionToAutoaim; print('decision_process messages=AVAILABLE')"
