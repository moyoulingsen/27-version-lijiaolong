#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

exec > >(tee -a /var/log/decision_27_ws_setup.log) 2>&1

step() {
  printf '
[WSL-SETUP] %s
' "$1"
}

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must run as root." >&2
  exit 1
fi

. /etc/os-release
if [ "$ID" != "ubuntu" ] || [ "$VERSION_ID" != "24.04" ]; then
  echo "Ubuntu 24.04 is required. Found: $PRETTY_NAME" >&2
  exit 1
fi

available_kb=$(df --output=avail / | tail -1 | tr -d ' ')
required_kb=$((12 * 1024 * 1024))
if [ "$available_kb" -lt "$required_kb" ]; then
  echo "At least 12 GiB free space is required. Available KiB: $available_kb" >&2
  exit 2
fi

step "更新 Ubuntu 软件索引"
apt-get -o Acquire::ForceIPv4=true update

step "安装证书、软件源与区域设置工具"
apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends   ca-certificates curl gnupg lsb-release locales software-properties-common

locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
add-apt-repository universe -y

step "配置 ROS 2 Jazzy 官方软件源"
install -m 0755 -d /etc/apt/keyrings
curl -4 -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key   -o /etc/apt/keyrings/ros-archive-keyring.gpg
chmod 0644 /etc/apt/keyrings/ros-archive-keyring.gpg
architecture=$(dpkg --print-architecture)
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main
' "$architecture"   > /etc/apt/sources.list.d/ros2.list
apt-get -o Acquire::ForceIPv4=true update

step "选择 BehaviorTree.CPP 软件包"
bt_package=ros-jazzy-behaviortree-cpp
if ! apt-cache show "$bt_package" >/dev/null 2>&1; then
  bt_package=ros-jazzy-behaviortree-cpp-v3
fi
if ! apt-cache show "$bt_package" >/dev/null 2>&1; then
  echo "No ROS Jazzy BehaviorTree.CPP package was found." >&2
  exit 3
fi

echo "BehaviorTree package: $bt_package"

step "安装 ROS 2、Nav2、Gazebo、BehaviorTree.CPP 与开发工具"
apt-get -o Acquire::ForceIPv4=true install -y   ros-jazzy-desktop   ros-dev-tools   "$bt_package"   ros-jazzy-navigation2   ros-jazzy-nav2-bringup   ros-jazzy-ros-gz   python3-pygame

step "初始化 rosdep"
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  rosdep init
fi

step "配置所有 WSL shell 自动加载 ROS 2"
printf '%s
'   'if [ -f /opt/ros/jazzy/setup.bash ]; then'   '  source /opt/ros/jazzy/setup.bash'   'fi'   > /etc/profile.d/ros-jazzy.sh
chmod 0644 /etc/profile.d/ros-jazzy.sh

apt-get clean
step "系统级 ROS 环境安装完成"

