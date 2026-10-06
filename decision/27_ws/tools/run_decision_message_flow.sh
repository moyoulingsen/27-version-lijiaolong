#!/usr/bin/env bash

# 通用消息端测试入口。负责环境隔离、英文路径构建和场景启动。
# 用法：bash run_decision_message_flow.sh <1..5|场景名称>
set -eo pipefail

SCENARIO="${1:-}"
case "${SCENARIO}" in
  1|return_home) SCENARIO_NAME="return_home"; TASK_LABEL="任务1 归位" ;;
  2|posture) SCENARIO_NAME="posture"; TASK_LABEL="任务2 姿态" ;;
  3|attack_outpost) SCENARIO_NAME="attack_outpost"; TASK_LABEL="任务3 打前哨" ;;
  4|no_ammo) SCENARIO_NAME="no_ammo"; TASK_LABEL="任务4 无弹补给" ;;
  5|dodge) SCENARIO_NAME="dodge"; TASK_LABEL="任务5 躲避" ;;
  *)
    echo "用法：bash $0 <1|2|3|4|5|return_home|posture|attack_outpost|no_ammo|dodge>" >&2
    exit 2
    ;;
esac

# ROS Jazzy 应使用系统 Python，避免 Conda Python 覆盖 rclpy 运行环境。
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
  hash -r
  echo "[环境隔离] 已忽略 Conda Python。"
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_WORKSPACE="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VERIFY_WORKSPACE="${DECISION_VERIFY_WORKSPACE:-${HOME}/decision_process_verify_ws}"
ROS_SETUP="/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"

if [[ ! -f "${ROS_SETUP}" ]]; then
  echo "错误：未找到 ROS 2 环境 ${ROS_SETUP}" >&2
  exit 1
fi

export ROS_DOMAIN_ID="${DECISION_MESSAGE_FLOW_ROS_DOMAIN_ID:-${RETURN_HOME_ROS_DOMAIN_ID:-27}}"
export ROS_AUTOMATIC_DISCOVERY_RANGE="${DECISION_MESSAGE_FLOW_DISCOVERY_RANGE:-${RETURN_HOME_DISCOVERY_RANGE:-LOCALHOST}}"

echo "[测试场景] ${TASK_LABEL} (${SCENARIO_NAME})"
echo "[测试隔离] ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "[测试隔离] ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE}"

unset COLCON_PREFIX_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH
source "${ROS_SETUP}"

mkdir -p "${VERIFY_WORKSPACE}"
if [[ -e "${VERIFY_WORKSPACE}/src" && ! -L "${VERIFY_WORKSPACE}/src" ]]; then
  echo "错误：${VERIFY_WORKSPACE}/src 已存在且不是软链接，请先人工确认。" >&2
  exit 1
fi
ln -sfnT "${SOURCE_WORKSPACE}/src" "${VERIFY_WORKSPACE}/src"
cd "${VERIFY_WORKSPACE}"

if [[ "${DECISION_MESSAGE_FLOW_SKIP_BUILD:-0}" != "1" ]]; then
  echo "[1/2] 构建 decision_process"
  colcon build \
    --packages-select decision_process \
    --packages-ignore behaviortree_cpp
else
  echo "[1/2] 复用已有构建结果"
fi

if [[ ! -f "${VERIFY_WORKSPACE}/install/setup.bash" ]]; then
  echo "错误：未找到构建结果，请取消 DECISION_MESSAGE_FLOW_SKIP_BUILD 后重试。" >&2
  exit 1
fi

source "${VERIFY_WORKSPACE}/install/setup.bash"
echo "[2/2] 启动 ${TASK_LABEL}"
ros2 launch decision_process test_decision_message_flow.launch.py \
  scenario:="${SCENARIO_NAME}"
