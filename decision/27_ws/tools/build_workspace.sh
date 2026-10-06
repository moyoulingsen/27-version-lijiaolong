#!/usr/bin/env bash

set -eo pipefail

WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROS_DISTRO_NAME="${ROS_DISTRO:-jazzy}"
ROS_SETUP="/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
ASCII_ROOT="${HOME}/.ros/decision_27_ws"

if [[ ! -f "${ROS_SETUP}" ]]; then
  echo "ROS 2 environment not found: ${ROS_SETUP}" >&2
  exit 1
fi

mkdir -p "${ASCII_ROOT}"

# rosidl in ROS 2 Jazzy cannot reliably generate interfaces from this workspace's
# Chinese absolute path. Keep source code in 27_ws, but access it through an ASCII link.
ln -sfn "${WORKSPACE_DIR}/src" "${ASCII_ROOT}/src"

set +u
source "${ROS_SETUP}"
set -u

colcon --log-base "${ASCII_ROOT}/log" build \
  --base-paths "${ASCII_ROOT}/src" \
  --build-base "${ASCII_ROOT}/build" \
  --install-base "${ASCII_ROOT}/install" \
  --symlink-install \
  "$@"

echo
echo "Build finished. Run the following command before using the nodes:"
echo "source ${ASCII_ROOT}/install/setup.bash"
