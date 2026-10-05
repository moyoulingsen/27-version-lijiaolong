#!/usr/bin/env bash

set -eo pipefail

MAP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${MAP_DIR}/.." && pwd)"
ROS_DISTRO_NAME="${ROS_DISTRO:-jazzy}"
ROS_SETUP="/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
ASCII_ROOT="${HOME}/.ros/decision_27_ws_nav2"

if [[ ! -f "${ROS_SETUP}" ]]; then
  echo "ROS 2 environment not found: ${ROS_SETUP}" >&2
  exit 1
fi

mkdir -p "${ASCII_ROOT}"
ln -sfn "${WORKSPACE_DIR}/src" "${ASCII_ROOT}/src"
ln -sfn "${MAP_DIR}" "${ASCII_ROOT}/map"

set +u
source "${ROS_SETUP}"
set -u

# Use the system colcon explicitly. ROS 2 Jazzy rclpy uses Python 3.12; a
# Conda colcon would generate decision_process message bindings for Python 3.13.
/usr/bin/colcon --log-base "${ASCII_ROOT}/log" build \
  --base-paths "${ASCII_ROOT}/src" "${ASCII_ROOT}/map" \
  --build-base "${ASCII_ROOT}/build" \
  --install-base "${ASCII_ROOT}/install" \
  --symlink-install \
  --packages-up-to decision_process rm_decision_sim \
  --cmake-args \
    -DPython3_EXECUTABLE=/usr/bin/python3 \
    -DPython3_FIND_VIRTUALENV=STANDARD \
  "$@"

echo
echo "Build finished. Source the workspace with:"
echo "source ${ASCII_ROOT}/install/setup.bash"
