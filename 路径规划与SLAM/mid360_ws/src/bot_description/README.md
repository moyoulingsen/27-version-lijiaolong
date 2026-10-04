# bot_description

这是一个用于 Gazebo Classic / ROS 2 Humble 的简易车体描述包，包含：

- `base_link` 和 `base_footprint` 车体坐标系；
- `front_camera` RGB 相机及 `front_camera_optical_link`；
- Livox MID360 的固定安装模型和仿真传感器；
- `robot_state_publisher`、Gazebo 生成和简单平面运动控制启动文件。

## 构建

`mid360_mount.xacro` 使用 `libros2_livox.so`。该库来自本工作空间中的
`ros2_livox_simulation`（由项目提供的 `livox_laser_simulation_ros2-main`
复制而来）。本工作空间版本保留 `sensor_msgs/PointCloud2` 输出，并移除了
当前插件源码中未使用的 `livox_ros_driver2/msg/CustomMsg` 编译依赖，因此可在
ROS 2 Humble 容器中直接构建：

```bash
cd /ws
colcon build --symlink-install
source install/setup.bash
```

如果暂时只检查车体和 Xacro 结构，也可以单独构建：

```bash
colcon build --packages-select bot_description --symlink-install
```

## 启动

```bash
source /ws/install/setup.bash
ros2 launch bot_description gazebo.launch.py
```

无图形界面运行：

```bash
ros2 launch bot_description gazebo.launch.py gui:=false
```

可通过参数覆盖话题和初始位置：

```bash
ros2 launch bot_description gazebo.launch.py \
  camera_topic:=/camera/image_raw \
  camera_info_topic:=/camera/camera_info \
  mid360_topic:=/mid360_points \
  x:=0.0 y:=0.0 z:=0.2
```

启动后可检查：

```bash
ros2 topic list
ros2 topic echo /mid360_points --once
ros2 topic echo /camera/camera_info --once
```

如果 Gazebo 报 `Failed to load plugin libros2_livox.so`，说明 Livox 仿真
插件尚未编译或其工作空间尚未 `source`；车体仍可能被生成，但不会有 MID360
点云。请先在本工作空间重新构建并 source `install/setup.bash`。
