#! /bin/bash

sudo apt install ros-humble-joint-state-publisher
sudo apt install ros-humble-xacro
sudo apt install ros-humble-test-*
sudo apt install ros-humble-octomap*

sudo apt install libusb-dev ros-humble-gazebo-msgs \
ros-humble-gazebo-plugins ros-humble-gazebo-ros ros-humble-gazebo-ros2-control \
ros-humble-gazebo-ros-pkgs python3-colcon-common-extensions

sudo apt-get install ros-humble-rqt-tf-tree
echo "export IGN_IP=127.0.0.1" >> ~/.bashrc

file="$HOME/.bashrc"
pattern="sentry_kill"
sed -i "/$pattern/d" "$file"
dir=$(pwd);
echo "alias sentry_kill='. ${dir}/all_kill.sh'" >> ~/.bashrc

