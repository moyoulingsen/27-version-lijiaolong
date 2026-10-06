#!/usr/bin/env bash

# 使用独立 ROS 域，避免接收同一网络中其他仿真系统的节点和 /rosout 日志。
# 如需使用其他域，可在调用脚本前显式设置 ROS_DOMAIN_ID 覆盖默认值。
export ROS_DOMAIN_ID="${RETURN_HOME_ROS_DOMAIN_ID:-27}"
export ROS_AUTOMATIC_DISCOVERY_RANGE="${RETURN_HOME_DISCOVERY_RANGE:-LOCALHOST}"

echo "[测试隔离] ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "[测试隔离] ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE}"

set -eo pipefail

SOURCE_WORKSPACE="/home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws"
VERIFY_WORKSPACE="/home/lijiaolong/decision_process_verify_ws"

echo "[1/5] 清除旧工作区环境变量"
unset COLCON_PREFIX_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH
source /opt/ros/jazzy/setup.bash

echo "[2/5] 准备纯英文验证工作区：${VERIFY_WORKSPACE}"
mkdir -p "${VERIFY_WORKSPACE}"
if [[ -e "${VERIFY_WORKSPACE}/src" && ! -L "${VERIFY_WORKSPACE}/src" ]]; then
  echo "错误：${VERIFY_WORKSPACE}/src 已存在且不是软链接，请先人工确认该目录。"
  exit 1
fi
ln -sfnT "${SOURCE_WORKSPACE}/src" "${VERIFY_WORKSPACE}/src"

echo "[3/5] 进入纯英文工作区"
cd "${VERIFY_WORKSPACE}"

echo "[4/5] 构建 decision_process"
colcon build \
  --packages-select decision_process \
  --packages-ignore behaviortree_cpp

echo "[5/5] 启动第一个返航回归消息流"
source "${VERIFY_WORKSPACE}/install/setup.bash"
exec ros2 launch decision_process test_return_home_message_flow.launch.py
