#!/usr/bin/env bash
# ROS 2 的 setup.bash 会读取部分尚未定义的环境变量，不能在加载前启用 nounset。
set -eo pipefail

# ROS Jazzy 使用系统 Python 3.12。若从 Conda base 启动，env python3 可能被
# 替换为 Conda Python 3.13，导致 rclpy 的二进制扩展无法加载。
if [[ -n "${CONDA_PREFIX:-}" ]]; then
  ACTIVE_CONDA_PREFIX="${CONDA_PREFIX}"
  CLEAN_PATH=""
  OLD_IFS="${IFS}"
  IFS=':' read -r -a PATH_PARTS <<< "${PATH:-}"
  IFS="${OLD_IFS}"
  for path_part in "${PATH_PARTS[@]}"; do
    if [[ -z "${path_part}" || "${path_part}" == "${ACTIVE_CONDA_PREFIX}"* ]]; then
      continue
    fi
    CLEAN_PATH="${CLEAN_PATH:+${CLEAN_PATH}:}${path_part}"
  done
  export PATH="/usr/bin:/bin:${CLEAN_PATH}"
  unset CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER CONDA_SHLVL
  unset PYTHONHOME PYTHONPATH _CE_CONDA _CE_M
  unset QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH
  hash -r
  echo "[环境隔离] 已忽略 Conda Python，ROS 工具使用系统 Python。"
fi

# 必须与 run_return_home_message_flow.sh 使用相同的 ROS 域。
export ROS_DOMAIN_ID="${RETURN_HOME_ROS_DOMAIN_ID:-27}"
export ROS_AUTOMATIC_DISCOVERY_RANGE="${RETURN_HOME_DISCOVERY_RANGE:-LOCALHOST}"

source /opt/ros/jazzy/setup.bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
if [[ -f "${WORKSPACE_ROOT}/install/setup.bash" ]]; then
  source "${WORKSPACE_ROOT}/install/setup.bash"
fi
if [[ -f "/home/lijiaolong/decision_process_verify_ws/install/setup.bash" ]]; then
  source "/home/lijiaolong/decision_process_verify_ws/install/setup.bash"
fi

echo "[测试隔离] ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "[测试隔离] ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE}"
echo "[观察工具] 只接收本机当前测试域中的 ROS 数据。"

BAG_ROOT="${WORKSPACE_ROOT}/log/return_home_bags"
BAG_OUTPUT="${BAG_ROOT}/return_home_run_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${BAG_ROOT}"

PIDS=()
cleanup() {
  trap - EXIT INT TERM
  echo
  echo "[观察工具] 正在关闭窗口并结束 rosbag 录制……"
  for pid in "${PIDS[@]}"; do
    kill -INT "${pid}" 2>/dev/null || true
  done
  for _ in {1..20}; do
    alive=false
    for pid in "${PIDS[@]}"; do
      if kill -0 "${pid}" 2>/dev/null; then
        alive=true
      fi
    done
    [[ "${alive}" == false ]] && break
    sleep 0.1
  done
  for pid in "${PIDS[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill -TERM "${pid}" 2>/dev/null || true
    fi
  done
  sleep 0.5
  for pid in "${PIDS[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill -KILL "${pid}" 2>/dev/null || true
    fi
  done
  wait "${PIDS[@]}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[1/4] 启动 rosbag，保存到：${BAG_OUTPUT}"
ros2 bag record -o "${BAG_OUTPUT}" --topics \
  /serial_receive_data \
  /state_estimation \
  /autoaim_to_decision \
  /serial_send_data \
  /decision_to_autoaim \
  /goal_pose &
PIDS+=("$!")

echo "[2/4] 启动 rqt_console"
ros2 run rqt_console rqt_console &
PIDS+=("$!")

echo "[3/4] 启动 rqt_graph"
ros2 run rqt_graph rqt_graph &
PIDS+=("$!")

echo "[4/4] 启动 PlotJuggler"
if ros2 pkg executables plotjuggler 2>/dev/null | grep -q '[[:space:]]plotjuggler$'; then
  ros2 run plotjuggler plotjuggler &
  PIDS+=("$!")
elif ros2 pkg executables plotjuggler_ros 2>/dev/null | grep -q '[[:space:]]plotjuggler$'; then
  ros2 run plotjuggler_ros plotjuggler &
  PIDS+=("$!")
else
  echo "[提示] 未安装 PlotJuggler，其余三个工具继续运行。"
  echo "       安装命令：sudo apt install ros-jazzy-plotjuggler-ros"
fi

echo
echo "[观察工具] 全部就绪。请在另一个终端运行返航消息流脚本。"
echo "[观察工具] 检查结束后在本终端按 Ctrl+C，rosbag 会正常收尾。"
wait
