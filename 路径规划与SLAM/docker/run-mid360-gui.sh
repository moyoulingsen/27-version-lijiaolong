#!/usr/bin/env bash
set -Eeuo pipefail

# One-command launcher for the independent MID360 workspace.
# Run this script from the repository on the Jazzy host. All ROS commands run
# inside the Humble container.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="$ROOT_DIR/路径规划与SLAM/mid360_ws"
IMAGE="${ROS_HUMBLE_IMAGE:-ros-humble-task-mid360:local}"
CONTAINER="${ROS_HUMBLE_CONTAINER:-ros-humble-mid360}"

if [[ ! -d "$WORKSPACE/src" ]]; then
  printf 'Workspace not found: %s\n' "$WORKSPACE" >&2
  exit 2
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  printf 'Docker image not found: %s\n' "$IMAGE" >&2
  printf 'Create it first with: docker commit ros-humble-task %s\n' "$IMAGE" >&2
  exit 2
fi

# The old task container and the new container use host networking, so only
# one Gazebo master may run at a time. Stop old containers/processes first.
docker exec ros-humble-task pkill -x gzserver 2>/dev/null || true
docker exec ros-humble-task pkill -x gzclient 2>/dev/null || true
docker stop "$CONTAINER" >/dev/null 2>&1 || true
docker rm "$CONTAINER" >/dev/null 2>&1 || true

run_args=(
  run --name "$CONTAINER"
  --gpus all
  --network host
  --ipc host
  --env ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
  --env ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
  --volume "$WORKSPACE:/ws"
  --workdir /ws
)

if [[ -t 0 && -t 1 ]]; then
  run_args+=(-it)
else
  # Keep stdin available for non-interactive CI/IDE invocations while still
  # allowing the GUI launch process to stream its logs.
  run_args+=(-i)
fi

if [[ -n "${DISPLAY:-}" && -d /tmp/.X11-unix ]]; then
  # The container runs as root. Permit only the local root user while this
  # launcher is active; the EXIT trap restores the previous X11 access rule.
  if command -v xhost >/dev/null 2>&1; then
    xhost +SI:localuser:root >/dev/null 2>&1 || true
    trap 'xhost -SI:localuser:root >/dev/null 2>&1 || true' EXIT
  fi
  run_args+=(
    --env "DISPLAY=$DISPLAY"
    --env QT_X11_NO_MITSHM=1
    --volume /tmp/.X11-unix:/tmp/.X11-unix:rw
  )
  xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
  if [[ -f "$xauthority" ]]; then
    run_args+=(
      --env XAUTHORITY=/tmp/.docker.xauth
      --volume "$xauthority:/tmp/.docker.xauth:ro"
    )
  fi
fi

docker "${run_args[@]}" "$IMAGE" bash -lc '
  set -e
  source /opt/ros/humble/setup.bash
  rm -rf build install log
  colcon build --symlink-install
  source /ws/install/setup.bash
  echo
  echo "Starting Gazebo GUI with the MID360 robot..."
  echo "Press Ctrl-C to stop Gazebo; a Humble shell will remain open."
  ros2 launch bot_description gazebo.launch.py
  exec bash
'
