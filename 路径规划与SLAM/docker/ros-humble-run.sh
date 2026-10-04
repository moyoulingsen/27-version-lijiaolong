#!/usr/bin/env bash
set -Eeuo pipefail

# Generic ROS 2 Humble development container.
# Usage:
#   ./docker/ros-humble-run.sh /path/to/ros2_ws
#   ./docker/ros-humble-run.sh /path/to/ros2_ws -- colcon build --symlink-install
#
# The workspace is mounted at /ws. Build products therefore remain on the host
# even though the container itself is disposable.

IMAGE="${ROS_HUMBLE_IMAGE:-osrf/ros:humble-desktop}"

usage() {
  cat <<'EOF'
Usage:
  ros-humble-run.sh [workspace] [-- command ...]

Examples:
  ros-humble-run.sh .
  ros-humble-run.sh ~/src/my_humble_ws -- colcon build --symlink-install
  ROS_HUMBLE_CONTAINER=my-project ros-humble-run.sh ~/src/my_humble_ws

Environment variables:
  ROS_HUMBLE_IMAGE      Image to use (default: osrf/ros:humble-desktop)
  ROS_HUMBLE_CONTAINER Container name (default: ros-humble-<workspace-name>)
  ROS_HUMBLE_KEEP       Set to 1 to keep the container after exit (default: 1)
  ROS_HUMBLE_GPU        Set to 1 to pass all NVIDIA GPUs (default: 0)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

workspace="${1:-$PWD}"
shift || true

if [[ "${1:-}" == "--" ]]; then
  shift
  command=("$@")
else
  command=()
fi

workspace="$(realpath "$workspace")"
if [[ ! -d "$workspace" ]]; then
  printf 'Workspace does not exist: %s\n' "$workspace" >&2
  exit 2
fi

workspace_name="$(basename "$workspace")"
workspace_name="$(printf '%s' "$workspace_name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_.-]/-/g')"
container_name="${ROS_HUMBLE_CONTAINER:-ros-humble-${workspace_name}}"

# Use a locally cached image when available. This is important on hosts whose
# Docker daemon has a temporarily unavailable registry proxy configured.
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  printf 'Image %s is not cached; pulling it from Docker Hub...\n' "$IMAGE" >&2
  docker pull "$IMAGE"
fi

run_args=(run)
if [[ "${ROS_HUMBLE_KEEP:-1}" != "1" ]]; then
  run_args+=(--rm)
fi

# Allocate a terminal for a human shell, but remain usable from IDE tasks and
# CI jobs where stdin is not a TTY.
if [[ -t 0 && -t 1 ]]; then
  run_args+=(-it)
fi

run_args+=(
  --name "$container_name"
  --network host
  --ipc host
  --env ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
  --env ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
  --volume "$workspace:/ws"
  --workdir /ws
)

if [[ "${ROS_HUMBLE_GPU:-0}" == "1" ]]; then
  run_args+=(--gpus all)
fi

# Forward the host display when available (Gazebo/RViz). Headless builds work
# without these options.
if [[ -n "${DISPLAY:-}" && -d /tmp/.X11-unix ]]; then
  run_args+=(
    --env "DISPLAY=$DISPLAY"
    --env QT_X11_NO_MITSHM=1
    --volume /tmp/.X11-unix:/tmp/.X11-unix:rw
  )

  # GDM commonly stores the cookie outside $HOME (for example
  # /run/user/1000/gdm/Xauthority). Mount the active cookie read-only so
  # Gazebo's Qt client can authenticate to DISPLAY instead of failing with
  # "Authorization required".
  xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
  if [[ -f "$xauthority" ]]; then
    run_args+=(
      --env XAUTHORITY=/tmp/.docker.xauth
      --volume "$xauthority:/tmp/.docker.xauth:ro"
    )
  fi
fi

if ((${#command[@]} == 0)); then
  command=(bash)
fi

docker "${run_args[@]}" "$IMAGE" bash -lc '
  source /opt/ros/humble/setup.bash
  if [[ -f /ws/install/setup.bash ]]; then
    source /ws/install/setup.bash
  fi
  exec "$@"
' -- "${command[@]}"
