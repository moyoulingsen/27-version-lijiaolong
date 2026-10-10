#!/usr/bin/env bash
set -euo pipefail
source /opt/ros/jazzy/setup.bash

printf '
[WSL-BUILD] 更新 rosdep 索引
'
rosdep update

workspace="/mnt/c/Users/ASUS/Desktop/27-version-lijiaolong/decision/27_ws"
cd "$workspace"

printf '
[WSL-BUILD] 构建 decision_process 与 rm_decision_sim
'
bash map/build_simulation.sh

source "$HOME/.ros/decision_27_ws_nav2/install/setup.bash"

printf '
[WSL-VERIFY] ROS_DISTRO=%s
' "$ROS_DISTRO"
ros2 pkg prefix decision_process
ros2 pkg prefix rm_decision_sim
for package in nav2_controller nav2_navfn_planner ros_gz_sim behaviortree_cpp; do
  ros2 pkg prefix "$package" >/dev/null
  printf '%s=AVAILABLE
' "$package"
done

printf '
[WSL-VERIFY] Python ROS 消息导入
'
python3 -c "from decision_process.msg import ReceiveData, DesicionSendData, AutoaimToDecision, DecisionToAutoaim; print('decision_process messages=AVAILABLE')"

