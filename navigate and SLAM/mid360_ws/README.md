# mid360_ws

这是独立于 `定位导航参考资料/26_task_ws` 的 ROS 2 工作空间，专门用于
车体 + 相机 + Livox MID360 仿真：

```text
mid360_ws/src/
├── bot_description/
└── ros2_livox_simulation/
```

`ros2_livox_simulation` 是由项目提供的 `livox_laser_simulation_ros2-main`
复制而来。为了让它在当前 ROS 2 Humble 容器中直接构建，工作空间副本移除了
插件源码中未使用的 `livox_ros_driver2/msg/CustomMsg` 编译依赖；插件仍发布
`sensor_msgs/msg/PointCloud2`，MID360 点云功能不变。

## 构建

在已经配置好 ROS 2 Humble、Gazebo Classic 和 `gazebo_ros` 的环境中执行：

```bash
cd "/home/lijiaolong/桌面/27-version-lijiaolong/路径规划与SLAM/mid360_ws"
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

如果当前目录之前构建过旧内容，可以先删除本工作空间自己的构建产物：

```bash
rm -rf build install log
```

## 启动

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch bot_description gazebo.launch.py
```

同时启动 Gazebo 和已配置好两个点云显示的 RViz：

```bash
ros2 launch bot_description sim_with_rviz.launch.py
```

无图形界面检查：

```bash
ros2 launch bot_description gazebo.launch.py gui:=false
```

## 验证

启动后另开终端执行：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 topic list
ros2 topic echo /mid360_points --once
ros2 topic echo /laser_points --once
ros2 topic echo /camera/camera_info --once
ros2 run tf2_tools view_frames
```

应能看到至少以下坐标系：

```text
base_footprint
base_link
front_camera_link
front_camera_optical_link
mid360
laser_link
```

应能看到：

```text
/mid360_points
/laser_points
/camera/image_raw
/camera/camera_info
/cmd_vel
/odom
```

默认 `mid360_demo.world` 含有带 collision 的动态方块和圆柱。它们会受重力下落，
在 Gazebo 中拖动到车体附近可直接检查不穿模；也可以通过 `world:=...` 替换场景。

无图形界面环境中 Gazebo 可能提示 `Unable to create CameraSensor`，这是渲染
显示不可用造成的；MID360 插件仍可加载。要观察相机图像，请在有可用 DISPLAY
的环境中启动 Gazebo GUI。

## 容器说明

原来的 `ros-humble-task` 容器把旧工作空间挂载为 `/ws`，所以它不会自动看到
宿主机上的新 `mid360_ws`。推荐先把已经配置好 Gazebo 依赖的现有容器提交为
一个本地镜像，再创建一个挂载新工作空间的容器：

```bash
docker commit ros-humble-task ros-humble-task-mid360:local
```

然后：

```bash
docker run --name ros-humble-mid360 --network host \
  -e DISPLAY="$DISPLAY" \
  -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v "/home/lijiaolong/桌面/27-version-lijiaolong/路径规划与SLAM/mid360_ws:/ws" \
  -it ros-humble-task-mid360:local bash
```

如果不使用现有容器提交的镜像，而是直接使用 `osrf/ros:humble-desktop`，且该
镜像中尚未安装 Gazebo ROS 依赖，先安装项目原来使用的依赖，再执行上面的构建命令：

```bash
apt-get update
apt-get install -y \
  ros-humble-gazebo-ros-pkgs \
  ros-humble-gazebo-plugins \
  ros-humble-xacro \
  python3-colcon-common-extensions
```
